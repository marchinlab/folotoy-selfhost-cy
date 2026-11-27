# -*- coding: utf-8 -*-
"""v1.30 逐音节声学：用 edge-tts word-boundary 字幕定位每个字，逐字算 F1/F2/F0。
这是唯一能绕开「整词字节数碰撞」+「单字≠词内G2P」的硬办法。
对每个词：合成 mp3+srt -> 解析每字起止 -> ffmpeg 解码 pcm -> 逐字声学参数。
对比 目标简体 / 繁体候选 / 正音锚 的对应音节，定位错字 + 定修法。
"""
import subprocess, os, struct, math, re, sys

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue30_syl"
FS = 16000
os.makedirs(D, exist_ok=True)

# (tag, 文本)  每个词三形态：简 / 繁 / 锚
WORDS = {
    "净力": [("jl_j", "净力"), ("jl_f", "淨力"), ("jl_a", "靜力")],
    "质量": [("zl_j", "质量"), ("zl_f", "質量"), ("zl_a", "質亮"), ("zl_a2", "質諒")],
    "一齐": [("yq_j", "一齐"), ("yq_f", "一齊"), ("yq_a", "一齊")],
    "陈桥": [("cq_j", "陈桥"), ("cq_f", "陳橋"), ("cq_a", "塵喬")],
    "组队": [("zd_j", "组队"), ("zd_f", "組隊"), ("zd_a", "祖隊")],
    "发达": [("fd_j", "发达"), ("fd_f", "發達"), ("fd_a", "法達")],
    "火药": [("hy_j", "火药"), ("hy_f", "火藥"), ("hy_a", "火若")],
    "过程": [("gc_j", "过程"), ("gc_f", "過程"), ("gc_a", "過情")],
    "文风": [("wf_j", "文风"), ("wf_f", "文風"), ("wf_a", "聞風")],
}


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    if r.returncode or not os.path.exists(mp3):
        print("  GEN_ERR %s %s" % (tag, r.stderr.decode("utf-8", "ignore")[:80]))
        return None, None
    return mp3, srt


def parse_srt(path):
    """返回 [(字, start_sec, end_sec), ...]，只取有文本的行。"""
    if not path or not os.path.exists(path):
        return []
    txt = open(path, encoding="utf-8-sig").read().replace("\r", "")
    blocks = re.split(r"\n\s*\n", txt.strip())
    out = []
    for b in blocks:
        lines = [l for l in b.split("\n") if l.strip() != ""]
        if len(lines) < 2:
            continue
        tm = None
        for l in lines:
            if "-->" in l:
                tm = l
                break
        if not tm:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", tm)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
        e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
        word = "".join(l for l in lines if "-->" not in l and not l.strip().isdigit()).strip()
        if word:
            out.append((word, s, e))
    return out


def pcm(path):
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-ac", "1", "-ar", str(FS),
                          "-f", "s16le", "-"], capture_output=True).stdout
    n = len(raw) // 2
    return list(struct.unpack("<%dh" % n, raw[: n * 2]))


def goertzel(sig, freq):
    k = 2.0 * math.cos(2.0 * math.pi * freq / FS)
    s1 = s2 = 0.0
    for x in sig:
        s0 = x + k * s1 - s2
        s2, s1 = s1, s0
    return s1 * s1 + s2 * s2 - k * s1 * s2


def f0_of(seg):
    f0s = []
    for st in range(0, max(1, len(seg) - 384), 128):
        fr = seg[st:st + 384]
        if len(fr) < 384:
            break
        mean = sum(fr) / 384
        x = [fr[i] - mean for i in range(384)]
        e0 = sum(v * v for v in x)
        if e0 < 4e5:
            continue
        lo, hi = int(FS / 320.0), int(FS / 70.0)
        best, bestlag = 0.0, 0
        for lag in range(lo, hi + 1):
            sc = sum(x[i] * x[i + lag] for i in range(384 - lag)) / (e0 + 1e-9)
            if sc > best:
                best, bestlag = sc, lag
        if best >= 0.36:
            v = FS / float(bestlag)
            if 70 <= v <= 320:
                f0s.append(v)
    if not f0s:
        return None, None
    sv = sorted(f0s)
    med = sv[len(sv) // 2]
    m = len(f0s)
    k = max(1, m // 3)
    pre = sum(f0s[:k]) / k
    post = sum(f0s[-k:]) / k
    return med, post - pre


def analyze_syl(s, ss, ee, total_dur):
    a = max(0, int(ss * FS) + int(0.015 * FS))
    b = min(len(s), int(ee * FS) - int(0.015 * FS))
    if b - a < int(0.05 * FS):
        a = int(ss * FS)
        b = min(len(s), int(ee * FS))
    seg = s[a:b]
    if len(seg) < int(0.04 * FS):
        return None
    N = len(seg)
    win = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (N - 1)) for i in range(N)]
    sig = [seg[i] * win[i] for i in range(N)]
    freqs = list(range(250, 2901, 40))
    E = {f: goertzel(sig, f) for f in freqs}
    f1 = max([f for f in freqs if 250 <= f <= 1100], key=lambda f: E[f])
    f2 = max([f for f in freqs if 1050 <= f <= 2900], key=lambda f: E[f])
    med, slope = f0_of(seg)
    return (f1, f2, med, slope, (ee - ss))


def run():
    print("%-8s %-4s %-6s %5s %5s %7s %8s %7s" %
          ("tag", "字", "文本", "F1", "F2", "F0med", "F0slope", "时长"))
    print("-" * 76)
    for word, forms in WORDS.items():
        for tag, text in forms:
            mp3, srt = gen(tag, text)
            if not mp3:
                continue
            syls = parse_srt(srt)
            s = pcm(mp3)
            total = len(s) / float(FS)
            if not syls:
                print("  %-8s NO_SRT  (text=%s)" % (tag, text))
                continue
            for j, (ch, ss, ee) in enumerate(syls):
                r = analyze_syl(s, ss, ee, total)
                if not r:
                    print("  %-8s %-4s SKIP" % (tag, ch))
                    continue
                print("%-8s %-4s %-6s %5d %5d %7s %8s %7.3f" %
                      (tag + "#%d" % j, ch, text, r[0], r[1],
                       ("%d" % r[2]) if r[2] else "n/a",
                       ("%+.0f" % r[3]) if r[3] is not None else "n/a", r[4]))
        print()
    print("=== DONE ===")


if __name__ == "__main__":
    run()
