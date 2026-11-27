# -*- coding: utf-8 -*-
"""v1.32 声学探针：时间(si4-gaan1) / 儿子(ji4-zi2) 到底哪个音节、什么调被念错。
两套独立判据（复用 v1.28 字节碰撞 + v1.30 逐音节 F0/F1F2）：
  A) 整词 mp3 字节/md5/dur —— 同音素序列字节完全相同，可判「目标==哪个锚」。
  B) word-boundary 字幕逐音节 F0(声调)/F1F2(元音) —— 定位错在哪个字。
候选写法：简体 / 繁体 / 正音同音锚 / 反锚。
用法(在网关容器)：python3 _yue32_probe.py
"""
import subprocess, os, struct, math, re, hashlib

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue32"
FS = 16000
os.makedirs(D, exist_ok=True)

# (tag, 文本, 说明)
CASES = [
    # 时间 si4 gaan1：正音「時」si4(阳平)/「間」gaan1(阴平)
    ("sj_j", "时间", "简体 时间"),
    ("sj_f", "時間", "繁体 時間"),
    ("sj_a", "時艱", "正音锚 時(si4)艱(gaan1)"),   # 艱=gaan1 阴平锚
    ("sj_a2", "時姦", "正音锚2 時(si4)姦(gaan1)"),
    ("sj_b1", "事艱", "反锚 事(si6) 测「时」调"),
    ("sj_b2", "時澗", "反锚 澗(gaan3) 测「间」调"),
    ("sj_b3", "是艱", "反锚 是(si6)"),
    # 儿子 ji4 zi2：正音「兒」ji4(阳平)/「子」zi2(阴上)
    ("ez_j", "儿子", "简体 儿子"),
    ("ez_f", "兒子", "繁体 兒子"),
    ("ez_a", "而子", "正音锚 而(ji4)子(zi2)"),      # 而=ji4 阳平锚
    ("ez_a2", "宜子", "正音锚2 宜(ji4)"),
    ("ez_b1", "二子", "反锚 二(ji6) 测「儿」调"),
    ("ez_b2", "而自", "反锚 自(zi6) 测「子」调"),
    ("ez_b3", "兒紫", "锚 紫(zi2) 测繁「兒」+子"),
]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    if r.returncode or not os.path.exists(mp3):
        print("  GEN_ERR %-7s %s" % (tag, r.stderr.decode("utf-8", "ignore")[:100]))
        return None, None
    return mp3, srt


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", p], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def parse_srt(path):
    if not path or not os.path.exists(path):
        return []
    txt = open(path, encoding="utf-8-sig").read().replace("\r", "")
    blocks = re.split(r"\n\s*\n", txt.strip())
    out = []
    for b in blocks:
        lines = [l for l in b.split("\n") if l.strip() != ""]
        if len(lines) < 2:
            continue
        tm = next((l for l in lines if "-->" in l), None)
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


def analyze_syl(s, ss, ee):
    a = max(0, int(ss * FS) + int(0.015 * FS))
    b = min(len(s), int(ee * FS) - int(0.015 * FS))
    if b - a < int(0.05 * FS):
        a, b = int(ss * FS), min(len(s), int(ee * FS))
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
    return (f1, f2, med, slope)


def main():
    print("=" * 92)
    print("A) 整词字节碰撞（sz/md5/dur）—— 同音素必同字节")
    print("%-7s %-8s %8s %12s %8s  %s" % ("tag", "文本", "sz", "md5", "dur", "说明"))
    print("-" * 92)
    info = {}
    for tag, text, note in CASES:
        mp3, srt = gen(tag, text)
        if not mp3:
            continue
        sz = os.path.getsize(mp3)
        md = hashlib.md5(open(mp3, "rb").read()).hexdigest()[:10]
        dt = dur(mp3)
        info[tag] = (text, sz, note, srt, mp3)
        print("%-7s %-8s %8d %12s %8.3f  %s" % (tag, text, sz, md, dt, note))

    print()
    print("=" * 92)
    print("B) 逐音节 F0(声调) / F1F2(元音)")
    print("%-9s %-4s %6s %6s %8s %9s" % ("tag#idx", "字", "F1", "F2", "F0med", "F0slope"))
    print("-" * 92)
    syls_by_tag = {}
    for tag, (text, sz, note, srt, mp3) in info.items():
        s = pcm(mp3)
        sl = parse_srt(srt)
        syls_by_tag[tag] = sl
        for j, (ch, ss, ee) in enumerate(sl):
            r = analyze_syl(s, ss, ee)
            if not r:
                print("%-9s %-4s SKIP" % (tag + "#" + str(j), ch))
                continue
            print("%-9s %-4s %6d %6d %8s %9s" %
                  (tag + "#" + str(j), ch, r[0], r[1],
                   ("%d" % r[2]) if r[2] else "n/a",
                   ("%+.0f" % r[3]) if r[3] is not None else "n/a"))

    print()
    print("=" * 92)
    print("C) 判读辅助：目标 vs 各锚 的字节差")
    def sz(tag):
        return info[tag][1] if tag in info else None
    for tgt, anchors in [("sj_j", ["sj_f", "sj_a", "sj_a2", "sj_b1", "sj_b2", "sj_b3"]),
                         ("sj_f", ["sj_a", "sj_a2", "sj_b1", "sj_b2"]),
                         ("ez_j", ["ez_f", "ez_a", "ez_a2", "ez_b1", "ez_b2", "ez_b3"]),
                         ("ez_f", ["ez_a", "ez_a2", "ez_b1", "ez_b2", "ez_b3"])]:
        t = sz(tgt)
        if t is None:
            continue
        parts = []
        for a in anchors:
            v = sz(a)
            if v is not None:
                parts.append("%s=%d(%+d)" % (a, v, v - t))
        print("  %-5s sz=%-6d | %s" % (tgt, t, " ".join(parts)))
    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
