# -*- coding: utf-8 -*-
"""v1.37 声学探针 v2：把 v1 单字误报/存疑嘅字，放落【真实词首字】+【字节碰撞】钉死方向。

项目最硬判据（v1.28「单词==善词」）：同音素序列 -> mp3 字节数+md5 完全相同。
再加词内首字 F1/F2/F0（整词稳定段主要盖首字，v1.32 校准）。
  A) 字节碰撞：目标繁词 vs【粤语正音同音锚词】vs【普通话劫持反锚词】
     - 亞洲 vs 啊洲(aa3锚) / 婭洲(jaa3普通话yà反锚)
     - 華夷 vs 嘩夷(waa1锚) / 化夷(faa3普通话huà反锚)
     - 車站 vs 趨站(ceoi1锚) / 扯站(ce2反锚)
     - 識別 vs 識色(sik1同音锚) / 識十(sat6反锚)
     - 說話 vs 雪話(syut3同音锚) / 縮話(suk1反锚)
     - 計算 vs 計較? (gai3锚) / 計較唔用，改 計量(loeng6反)... 简化只比简繁
  B) 真实词简/繁首字特征对比（目标字放首字，F0段最稳）
用法(网关容器)：python3 _yue37_probe2.py
"""
import subprocess, os, struct, math, re, hashlib

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue37b"
FS = 16000
os.makedirs(D, exist_ok=True)

# A) 字节碰撞组：(组名, [(tag, 文本, 角色)])
COLLIDE = [
    ("亚 aa3 vs 普通话ya", [("jg", "亚洲", "简体目标"), ("jf", "亞洲", "繁体目标"),
                       ("anchor1", "啊洲", "aa3正音锚"), ("anchor2", "阿洲", "aa3正音锚2"),
                       ("bad1", "婭洲", "jaa3反锚(普通话yà)"), ("bad2", "訝洲", "ngaa5反锚")]),
    ("华 waa4 vs 普通话hua", [("jg", "华夷", "简体目标"), ("jf", "華夷", "繁体目标"),
                        ("anchor1", "嘩夷", "waa1锚(同waa韵)"), ("anchor2", "畫夷", "waa6锚(同waa韵)"),
                        ("bad1", "化夷", "faa3反锚(普通话huà)"), ("bad2", "花夷", "faa1反锚")]),
    ("车 ceoi1 vs 普通话che", [("jg", "车站", "简体目标"), ("jf", "車站", "繁体目标"),
                        ("anchor1", "趨站", "ceoi1正音锚"), ("anchor2", "車站", "繁体自锚"),
                        ("bad1", "扯站", "ce2反锚"), ("bad2", "扯站", "ce2反锚2")]),
    ("识 sik1 vs 普通话shi", [("jg", "识别", "简体目标"), ("jf", "識別", "繁体目标"),
                        ("anchor1", "識色", "sik1同音锚"), ("anchor2", "色别", "sik1锚2"),
                        ("bad1", "十别", "sap6反锚"), ("bad2", "實别", "sat6反锚")]),
    ("说 syut3 vs 普通话shuo", [("jg", "说话", "简体目标"), ("jf", "說話", "繁体目标"),
                        ("anchor1", "雪話", "syut3同音锚"), ("anchor2", "刷話", "saaat3锚"),
                        ("bad1", "縮話", "suk1反锚"), ("bad2", "索話", "sok3反锚")]),
    ("计 gai3 vs 普通话ji", [("jg", "计算", "简体目标"), ("jf", "計算", "繁体目标"),
                        ("anchor1", "計較", "gai3锚(计较)"), ("anchor2", "際算", "zai3锚"),
                        ("bad1", "寄算", "gei3反锚"), ("bad2", "記算", "gei3反锚2")]),
]
# B) 真实词简/繁首字对比（含 dist≈0 对照，确认「无病」）
WORDS = [("亚洲", "亞洲"), ("华夷", "華夷"), ("中华", "中華"), ("东亚", "東亞"),
         ("车站", "車站"), ("汽车", "汽車"), ("识别", "識別"), ("认识", "認識"),
         ("说话", "說話"), ("说明", "說明"), ("计算", "計算"), ("计划", "計劃"),
         ("机会", "機會"), ("声音", "聲音"), ("东方", "東方"), ("语言", "語言")]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3], capture_output=True)
    if r.returncode or not os.path.exists(mp3):
        print("  GEN_ERR %-14s %s" % (tag, r.stderr.decode("utf-8", "ignore")[:80]))
        return None
    return mp3


def sig_of(p):
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", p, "-ac", "1", "-ar", str(FS),
                          "-f", "s16le", "-"], capture_output=True).stdout
    n = len(raw) // 2
    return list(struct.unpack("<%dh" % n, raw[: n * 2]))


def md5sz(p):
    b = open(p, "rb").read()
    return len(b), hashlib.md5(b).hexdigest()[:8]


def feat(seg):
    if len(seg) < int(0.04 * FS):
        return None
    N = len(seg)
    win = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (N - 1)) for i in range(N)]
    x = [seg[i] * win[i] for i in range(N)]
    freqs = list(range(250, 2901, 40))
    k = 2.0 * math.cos(2.0 * math.pi * 1.0 / FS)  # placeholder, unused
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
    return (f1, f2)


def head_feat(s):
    """整词前 0.05~0.30s 稳定段，主要覆盖首字（v1.32 校准）。"""
    a, b = int(0.05 * FS), min(int(0.30 * FS), int(len(s) * 0.6))
    return feat(s[a:b]) if b - a >= int(0.06 * FS) else None


def f0med(s):
    best = None
    f0s = []
    for st in range(0, max(1, len(s) - 384), 128):
        fr = s[st:st + 384]
        if len(fr) < 384:
            break
        mean = sum(fr) / 384
        x = [fr[i] - mean for i in range(384)]
        e0 = sum(v * v for v in x)
        if e0 < 3.5e5:
            continue
        lo, hi = int(FS / 320.0), int(FS / 70.0)
        bs, bl = 0.0, 0
        for lag in range(lo, hi + 1):
            sc = sum(x[i] * x[i + lag] for i in range(384 - lag)) / (e0 + 1e-9)
            if sc > bs:
                bs, bl = sc, lag
        if bs >= 0.34:
            v = FS / float(bl)
            if 70 <= v <= 320:
                f0s.append(v)
    return int(sorted(f0s)[len(f0s) // 2]) if f0s else None


def fmt(jf, f0):
    if not jf:
        return "  --   --  --"
    return "%4d %4d %3s" % (jf[0], jf[1], f0 if f0 else "--")


def main():
    print("=" * 78)
    print("A) 字节碰撞：同音素 -> sz+md8 完全相同（判定简体/繁体到底念成边个锚）")
    for gname, cases in COLLIDE:
        print("\n--- %s ---" % gname)
        base = {}
        for tag, text, role in cases:
            p = gen(gname[:2] + "_" + tag, text)
            if not p:
                continue
            sz, m5 = md5sz(p)
            base[tag] = (sz, m5, text)
            print("  %-9s %-4s %-22s sz=%-6d md8=%s" % (tag, text, role, sz, m5))
        if "jg" in base and "jf" in base:
            if base["jg"][:2] == base["jf"][:2]:
                print("  >> 简繁【完全同音素】—— 呢个字转繁对发音无帮助")
            else:
                print("  >> 简繁【不同音素】—— 转繁会改变发音，继续对照锚")
            for tgt in ("jg", "jf"):
                for a in ("anchor1", "anchor2", "bad1", "bad2"):
                    if tgt in base and a in base and base[tgt][:2] == base[a][:2]:
                        print("  >> 碰撞: %s(%s) == %s(%s)  [同音素铁证]" %
                              (base[tgt][1], tgt, base[a][1], a))

    print()
    print("=" * 78)
    print("B) 真实词首字：简/繁 F1 F2 F0med（首字不同->md5必异，看元音/声调方向）")
    print("%-5s %-5s | %-12s | %-12s | %s" % ("简词", "繁词", "简 F1 F2 F0", "繁 F1 F2 F0", "判读"))
    print("-" * 78)
    for jw, fw in WORDS:
        pj = gen("w_j_" + jw[0], jw)
        pf = gen("w_f_" + fw[0], fw)
        if not pj or not pf:
            continue
        sj, sf = sig_of(pj), sig_of(pf)
        jf, ff = head_feat(sj), head_feat(sf)
        j0, f0 = f0med(sj), f0med(sf)
        d1 = (jf[0] - ff[0]) if (jf and ff) else None
        d2 = (jf[1] - ff[1]) if (jf and ff) else None
        note = "同形/无差" if (d1 is not None and abs(d1) < 60 and abs(d2) < 120) else \
               ("简F2低%d(疑j介音/卷舌)" % (-d2) if (d2 is not None and d2 < -300) else
                ("简F1低%d(疑闭/非a)" % (-d1) if (d1 is not None and d1 < -300) else "有差,需碰撞"))
        print("%-5s %-5s | %-12s | %-12s | %s" % (jw, fw, fmt(jf, j0), fmt(ff, f0), note))
    print("=== DONE ===")


if __name__ == "__main__":
    main()
