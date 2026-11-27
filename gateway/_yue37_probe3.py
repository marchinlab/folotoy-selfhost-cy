# -*- coding: utf-8 -*-
"""v1.37 探针 v3（定案）：用 edge-tts srt【真实词边界】切出首字音节，避开均分窗口抖动。
对「亚洲/亞洲/啊洲/婭洲」「华夷/華夷/嘩夷/化夷」等，取第 1 条 srt 的 start~end
切 PCM 算首字 F1/F2/F0/F0slope/sz；同一词重复 2 次验可复现性。
若首字简 F2 明显低于繁(普通话 j/w 介音压 F2)且贴近反锚 -> 确认劫持。
用法(网关容器)：python3 _yue37_probe3.py
"""
import subprocess, os, struct, math, re, hashlib

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue37c"
FS = 16000
os.makedirs(D, exist_ok=True)

# (组名, 词列表)  —— 首字为目标，第2字固定「洲/夷」做载体
GROUPS = [
    ("亚-aa3-yà", ["亚洲", "亞洲", "啊洲", "阿洲", "婭洲", "訝洲", "鸭洲"]),
    ("华-waa4-huá", ["华夷", "華夷", "嘩夷", "畫夷", "化夷", "花夷", "蛙夷"]),
]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    if r.returncode or not os.path.exists(mp3):
        print("  GEN_ERR %-12s %s" % (tag, r.stderr.decode("utf-8", "ignore")[:80]))
        return None, None
    return mp3, srt


def parse_srt(path):
    if not path or not os.path.exists(path):
        return []
    txt = open(path, encoding="utf-8-sig").read().replace("\r", "")
    out = []
    for b in re.split(r"\n\s*\n", txt.strip()):
        lines = [l for l in b.split("\n") if l.strip() != ""]
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
        out.append((word, s, e))
    return out


def pcm(path):
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-ac", "1", "-ar", str(FS),
                          "-f", "s16le", "-"], capture_output=True).stdout
    n = len(raw) // 2
    return list(struct.unpack("<%dh" % n, raw[: n * 2]))


def seg_feat(seg):
    """F1/F2 元音 + F0 中位数/slope + 时长(ms)。"""
    if len(seg) < int(0.035 * FS):
        return None
    N = len(seg)
    win = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (N - 1)) for i in range(N)]
    x = [seg[i] * win[i] for i in range(N)]
    freqs = list(range(250, 2901, 40))
    def gz(freq):
        kk = 2.0 * math.cos(2.0 * math.pi * freq / FS)
        s1 = s2 = 0.0
        for v in x:
            s0 = v + kk * s1 - s2
            s2, s1 = s1, s0
        return s1 * s1 + s2 * s2 - kk * s1 * s2
    E = {f: gz(f) for f in freqs}
    f1 = max([f for f in freqs if 250 <= f <= 1100], key=lambda f: E[f])
    f2 = max([f for f in freqs if 1050 <= f <= 2900], key=lambda f: E[f])
    f0s = []
    for st in range(0, max(1, len(seg) - 320), 96):
        fr = seg[st:st + 320]
        if len(fr) < 320:
            break
        mean = sum(fr) / 320
        y = [fr[i] - mean for i in range(320)]
        e0 = sum(v * v for v in y)
        if e0 < 2.0e5:
            continue
        lo, hi = int(FS / 320.0), int(FS / 75.0)
        bs, bl = 0.0, 0
        for lag in range(lo, hi + 1):
            sc = sum(y[i] * y[i + lag] for i in range(320 - lag)) / (e0 + 1e-9)
            if sc > bs:
                bs, bl = sc, lag
        if bs >= 0.32:
            v = FS / float(bl)
            if 75 <= v <= 320:
                f0s.append(v)
    f0med = int(sorted(f0s)[len(f0s) // 2]) if f0s else None
    k = max(1, len(f0s) // 3) if f0s else 1
    slope = (sum(f0s[-k:]) / k - sum(f0s[:k]) / k) if len(f0s) >= 2 else None
    return (f1, f2, f0med, slope, int(len(seg) / float(FS) * 1000))


def fmt(r):
    if not r:
        return "  --   --  --    --   --"
    return "%4d %4d %3s %6s %3dms" % (r[0], r[1], r[2] if r[2] else "--",
                                        ("%+.0f" % r[3]) if r[3] is not None else "--", r[4])


def main():
    for gname, words in GROUPS:
        print("=" * 82)
        print("[%s] 首字(srt真实边界) F1 F2 F0med F0slope dur —— 每词跑2次验稳定" % gname)
        print("%-5s %-24s %-24s %s" % ("词", "run1 F1 F2 F0 slp dur", "run2 F1 F2 F0 slp dur", "srt条目"))
        print("-" * 82)
        first_cache = {}
        for wi, w in enumerate(words):
            runs = []
            srt_show = ""
            for rn in (1, 2):
                mp3, srt = gen("%s_%d_%d" % (gname[:2], wi, rn), w)
                if not mp3:
                    runs.append(None)
                    continue
                sl = parse_srt(srt)
                srt_show = ";".join("%s[%.2f-%.2f]" % (a, b, c) for a, b, c in sl[:3])
                s = pcm(mp3)
                if sl:
                    ss, ee = sl[0][1], sl[0][2]
                else:
                    ss, ee = 0.0, len(s) / float(FS) / 2
                a = max(0, int(ss * FS) + int(0.008 * FS))
                b = min(len(s), int(ee * FS) - int(0.008 * FS))
                r = seg_feat(s[a:b])
                runs.append(r)
            first_cache[w] = runs
            print("%-5s %-24s %-24s %s" % (w, fmt(runs[0]), fmt(runs[1]), srt_show[:40]))
        print()
        print("  判读（目标简体 vs 繁体 vs 锚）：")
        base = words[0]  # 简体
        for w in words:
            r1, r2 = first_cache.get(w, (None, None))
            if r1 and r2:
                stable = "稳" if (abs(r1[0]-r2[0])<90 and abs(r1[1]-r2[1])<160 and
                                  (r1[2] is None)==(r2[2] is None)) else "★不稳"
            else:
                stable = "缺"
            print("    %-4s F1/F2 run1=%4d/%4d F0=%s  %s" %
                  (w, r1[0], r1[1], r1[2] if r1 else "--", stable))
        print()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
