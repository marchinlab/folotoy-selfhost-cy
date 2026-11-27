# -*- coding: utf-8 -*-
"""v1.37 探针 v5（词组协同定案）：三字词让 srt 逐字成条，取目标字位切音，
验证「亚->阿/啊」换字喺【真实词组协同】下系咪都稳定开口 aa3（唔止载体里对）。
用法(网关容器)：python3 _yue37_probe5.py
"""
import subprocess, os, struct, math, re

V, R, D, FS = "zh-HK-HiuMaanNeural", "+20%", "/audio/pron_yue37e", 16000
os.makedirs(D, exist_ok=True)
# (词, 目标字在词内 index, 标注)
CASES = [
    ("亚洲好", 0, "亚 简"), ("亞洲好", 0, "亞 繁"),
    ("阿洲好", 0, "阿 aa3锚"), ("啊洲好", 0, "啊 aa3锚"), ("婭洲好", 0, "婭 jaa3反"),
    ("东亚好", 1, "亚@2位 简"), ("東亞好", 1, "亞@2位 繁"),
    ("东阿好", 1, "阿@2位 换字"), ("东啊好", 1, "啊@2位 换字"), ("東阿好", 1, "東阿@2位"),
    ("东南亚", 2, "亚@3位 简"), ("東南亞", 2, "亞@3位 繁"), ("東南阿", 2, "阿@3位 换字"),
    ("华夷好", 0, "华 简"), ("華夷好", 0, "華 繁"),
    ("嘩夷好", 0, "嘩 waa1锚"), ("化夷好", 0, "化 faa3反"), ("話夷好", 0, "話 waa6锚"),
    ("中华好", 1, "华@2位 简"), ("中華好", 1, "華@2位 繁"),
    ("中蛙好", 1, "蛙@2位 锚"), ("中話好", 1, "話@2位 锚"), ("中化好", 1, "化@2位 反"),
]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    return (mp3, srt) if (not r.returncode and os.path.exists(mp3)) else (None, None)


def parse_srt(path):
    txt = open(path, encoding="utf-8-sig").read().replace("\r", "") if os.path.exists(path) else ""
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
    if len(seg) < int(0.028 * FS):
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
    return (f1, f2, int(len(seg) / float(FS) * 1000))


def main():
    print("=" * 76)
    print("三字词逐字 srt 边界, 取目标字位切音 (F1 F2 dur)")
    print("%-7s %-14s %-16s %s" % ("词", "标注", "F1 F2 dur", "srt条目"))
    print("-" * 76)
    for i, (w, idx, note) in enumerate(CASES):
        mp3, srt = gen("c%d" % i, w)
        if not mp3:
            print("%-7s GEN_ERR" % w)
            continue
        sl = parse_srt(srt)
        s = pcm(mp3)
        if len(sl) > idx:
            ss, ee = sl[idx][1], sl[idx][2]
        else:  # fallback 均分
            tot = len(s) / float(FS)
            ss, ee = tot * idx / len(w), tot * (idx + 1) / len(w)
        a = max(0, int(ss * FS) + int(0.006 * FS))
        b = min(len(s), int(ee * FS) - int(0.006 * FS))
        r = seg_feat(s[a:b])
        srttxt = " ".join(x[0] for x in sl)
        print("%-7s %-14s %-16s %s" %
              (w, note, ("%4d %4d %3dms" % (r[0], r[1], r[2])) if r else " --  --  --", srttxt))
    print("=== DONE ===")


if __name__ == "__main__":
    main()
