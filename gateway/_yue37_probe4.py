# -*- coding: utf-8 -*-
"""v1.37 探针 v4（定案·单字载体）：把目标字放【三字中间】，取 srt 中段边界切音，
避开词首协同发音。构造「呢亚呢 / 呢亞呢」「呢华呢 / 呢華呢」+ 锚/反锚同位置。
若简体亚贴 aa3 锚(啊)、繁体亞贴别的 -> 转繁无益甚至有害 -> 唔改(同 v1.30 过程)。
若简体亚贴 ya 反锚、繁体亞贴 aa3 锚 -> 确认劫持 -> 改。
用法(网关容器)：python3 _yue37_probe4.py
"""
import subprocess, os, struct, math, re

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue37d"
FS = 16000
os.makedirs(D, exist_ok=True)

# 载体字「嘅」(ge3, 粤语高频、与目标元音分离)，三字中间=目标
CARRIER = "嘅"
CASES = [
    ("亚", "亚", "简体亚"), ("亞", "亞", "繁体亞"),
    ("啊", "啊", "aa3锚(啊)"), ("阿", "阿", "aa3锚(阿)"),
    ("婭", "婭", "jaa3反锚(普通话ya)"), ("訝", "訝", "ngaa5反锚"), ("鸭", "鸭", "aap3参照"),
    ("华", "华", "简体华"), ("華", "華", "繁体華"),
    ("嘩", "嘩", "waa1锚"), ("蛙", "蛙", "waa1锚2"), ("話", "話", "waa6锚"),
    ("化", "化", "faa3反锚(普通话hua)"), ("花", "花", "faa1反锚"),
]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    if r.returncode or not os.path.exists(mp3):
        print("  GEN_ERR %-8s %s" % (tag, r.stderr.decode("utf-8", "ignore")[:80]))
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
    if len(seg) < int(0.03 * FS):
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
    return (f1, f2, f0med, int(len(seg) / float(FS) * 1000))


def dist(a, b):
    if not a or not b:
        return 999.0
    d = abs(a[0] - b[0]) / 260.0 + abs(a[1] - b[1]) / 480.0
    if a[2] and b[2]:
        d += abs(a[2] - b[2]) / 38.0
    return d


def main():
    print("=" * 84)
    print("三字载体「%sX%s」中段 srt 边界切音 (F1 F2 F0med dur)" % (CARRIER, CARRIER))
    print("%-4s %-6s %-20s %s" % ("字", "角色", "F1 F2 F0 dur", "srt"))
    print("-" * 84)
    store = {}
    for tag, ch, role in CASES:
        text = CARRIER + ch + CARRIER
        mp3, srt = gen(tag, text)
        if not mp3:
            continue
        sl = parse_srt(srt)
        s = pcm(mp3)
        # 中段 = 第2条 srt(若3条) 或 均分中段
        if len(sl) >= 3:
            ss, ee = sl[1][1], sl[1][2]
        elif len(sl) == 2:
            ss, ee = sl[0][2], sl[1][2]
        else:
            tot = len(s) / float(FS)
            ss, ee = tot / 3.0, 2 * tot / 3.0
        a = max(0, int(ss * FS) + int(0.006 * FS))
        b = min(len(s), int(ee * FS) - int(0.006 * FS))
        r = seg_feat(s[a:b])
        store[tag] = r
        srttxt = "/".join(w for w, _, _ in sl)
        print("%-4s %-6s %-20s %s" % (ch, role,
              ("%4d %4d %3d %3dms" % (r[0], r[1], r[2], r[3])) if r else "  --  --  --  --", srttxt))

    print()
    print("判读：简体到【粤语正音锚】vs【普通话反锚】距离（小=贴近）")
    for name, jt, anchors, bads in [
        ("亚", "亚", ["啊", "阿"], ["婭", "訝", "鸭"]),
        ("华", "华", ["嘩", "蛙", "話"], ["化", "花"]),
    ]:
        tagmap = {c[0]: c[0] for c in CASES}
        T = store.get(tagmap.get(jt))
        if not T:
            continue
        line = ["[%s 简]" % name]
        for a in anchors:
            R = store.get(tagmap.get(a))
            if R:
                line.append("d(%s粤锚)=%.2f" % (a, dist(T, R)))
        for b in bads:
            R = store.get(tagmap.get(b))
            if R:
                line.append("d(%s反)=%.2f" % (b, dist(T, R)))
        F = store.get(tagmap.get("亞" if name == "亚" else "華"))
        if F:
            line.append(" | 繁体到粤锚: " + " ".join(
                "d(%s)=%.2f" % (a, dist(F, store[tagmap[a]]))
                for a in anchors if a in store))
        print("  " + "  ".join(line))
    print("=== DONE ===")


if __name__ == "__main__":
    main()
