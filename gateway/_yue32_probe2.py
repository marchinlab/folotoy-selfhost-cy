# -*- coding: utf-8 -*-
"""v1.32 声学探针 v2：定位「时间/儿子」错在哪个字、什么调。
教训：整词字节碰撞会被字形韵律污染（時艱 8928 vs 時姦 8784 同为 si4-gaan1），
整词 F0 稳定段只盖首字。故改用两套更硬的判据：
  A) 单字简/繁/正音锚/反锚 的 F0(声调)/F1F2(元音)/sz —— v1.30 校准过的方法。
  B) 词内按 srt 边界(有则真实、无则均分)切前后半，逐半 F0/F1F2 —— 治「单字 G2P≠词内 G2P」。
用法(网关容器)：python3 _yue32_probe2.py
"""
import subprocess, os, struct, math, re

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue32b"
FS = 16000
os.makedirs(D, exist_ok=True)

# 单字：(tag, 字, 说明)。锚=铁定念该粤语正音的字；反锚=错调/错音方向。
SINGLE = [
    ("sh_j", "时", "目标简体 时 si4?"),
    ("sh_f", "時", "繁体 時 si4(正音侧)"),
    ("sh_b", "事", "反锚 事 si6(阳去)"),
    ("gn_j", "间", "目标简体 间 gaan1?"),
    ("gn_f", "間", "繁体 間 gaan1(正音侧)"),
    ("gn_a", "艱", "正音锚 艱 gaan1(阴平)"),
    ("gn_b", "澗", "反锚 澗 gaan3(阴去)"),
    ("er_j", "儿", "目标简体 儿 ji4?"),
    ("er_f", "兒", "繁体 兒 ji4(正音侧)"),
    ("er_a", "而", "正音锚 而 ji4(阳平)"),
    ("er_b", "二", "反锚 二 ji6(阳去)"),
    ("er_c", "耳", "参照 耳 ji5(阳上)"),
    ("zi_j", "子", "目标 子 zi2?"),
    ("zi_b", "自", "反锚 自 zi6(阳去)"),
]
# 双字词：(tag, 文本)。切前后半定位词内哪字错。
WORDS = [("w_sj_j", "时间"), ("w_sj_f", "時間"),
         ("w_ez_j", "儿子"), ("w_ez_f", "兒子")]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    if r.returncode or not os.path.exists(mp3):
        print("  GEN_ERR %-8s %s" % (tag, r.stderr.decode("utf-8", "ignore")[:90]))
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
        if e0 < 3.5e5:
            continue
        lo, hi = int(FS / 320.0), int(FS / 70.0)
        best, bestlag = 0.0, 0
        for lag in range(lo, hi + 1):
            sc = sum(x[i] * x[i + lag] for i in range(384 - lag)) / (e0 + 1e-9)
            if sc > best:
                best, bestlag = sc, lag
        if best >= 0.34:
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


def feat(seg):
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


def feat_whole(s):
    a, b = int(0.05 * FS), min(int(0.32 * FS), int(len(s) * 0.75))
    if b - a < int(0.08 * FS):
        a, b = int(0.03 * FS), int(len(s) * 0.7)
    return feat(s[a:b])


def dist(a, b):
    if not a or not b:
        return 999.0
    d = abs(a[0] - b[0]) / 260.0 + abs(a[1] - b[1]) / 480.0
    if a[2] and b[2]:
        d += abs(a[2] - b[2]) / 38.0
    if a[3] is not None and b[3] is not None:
        d += abs(a[3] - b[3]) / 16.0
    return d


def show(tag, text, sz, r):
    if not r:
        print("%-8s %-4s %6d  SKIP" % (tag, text, sz))
        return
    print("%-8s %-4s %6d %6d %6d %8s %9s" %
          (tag, text, sz, r[0], r[1], ("%d" % r[2]) if r[2] else "n/a",
           ("%+.0f" % r[3]) if r[3] is not None else "n/a"))


def main():
    store = {}
    print("=" * 88)
    print("A) 单字：F0med(声调高度) / F0slope(升+/降-) / F1F2(元音) / sz")
    print("%-8s %-4s %6s %6s %6s %8s %9s" % ("tag", "字", "sz", "F1", "F2", "F0med", "F0slope"))
    print("-" * 88)
    for tag, ch, note in SINGLE:
        mp3, _ = gen(tag, ch)
        if not mp3:
            continue
        sz = os.path.getsize(mp3)
        r = feat_whole(pcm(mp3))
        store[tag] = (r, sz, ch, note)
        show(tag, ch, sz, r)

    print()
    print("=" * 88)
    print("A2) 单字判读：目标简/繁 到【正音锚】vs【反锚】的距离（小=贴近）")
    groups = [
        ("时", "sh_j", ["sh_f"], ["sh_b"]),
        ("间", "gn_j", ["gn_f", "gn_a"], ["gn_b"]),
        ("儿", "er_j", ["er_f", "er_a"], ["er_b"]),
        ("子", "zi_j", [], ["zi_b"]),
    ]
    for name, tgt, anchors, bads in groups:
        if tgt not in store:
            continue
        T = store[tgt][0]
        line = ["[%s] 简(%s)" % (name, store[tgt][2])]
        for a in anchors:
            if a in store:
                line.append("d(%s)=%.2f" % (store[a][2], dist(T, store[a][0])))
        for b in bads:
            if b in store:
                line.append("d(%s反)=%.2f" % (store[b][2], dist(T, store[b][0])))
        print("  " + "  ".join(line))

    print()
    print("=" * 88)
    print("B) 词内前后半（srt 有真实边界则用，否则均分）：定位词内哪字错")
    print("%-10s %-6s %6s %6s %8s %9s" % ("tag#half", "近似字", "F1", "F2", "F0med", "F0slope"))
    print("-" * 88)
    for tag, text in WORDS:
        mp3, srt = gen(tag, text)
        if not mp3:
            continue
        s = pcm(mp3)
        total = len(s) / float(FS)
        sl = parse_srt(srt)
        halves = []
        if len(sl) >= 2:
            halves = [(sl[0][1], sl[0][2]), (sl[1][1], sl[1][2])]
        elif len(sl) == 1:
            mid = (sl[0][1] + sl[0][2]) / 2.0
            halves = [(sl[0][1], mid), (mid, sl[0][2])]
        else:
            halves = [(0.03, total / 2), (total / 2, total - 0.03)]
        for i, (ss, ee) in enumerate(halves):
            a = max(0, int(ss * FS) + int(0.012 * FS))
            b = min(len(s), int(ee * FS) - int(0.012 * FS))
            r = feat(s[a:b])
            ch = text[i] if i < len(text) else "?"
            if not r:
                print("%-10s %-6s SKIP" % (tag + "#" + str(i), ch))
                continue
            print("%-10s %-6s %6d %6d %8s %9s" %
                  (tag + "#" + str(i), ch, r[0], r[1],
                   ("%d" % r[2]) if r[2] else "n/a",
                   ("%+.0f" % r[3]) if r[3] is not None else "n/a"))
        print()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
