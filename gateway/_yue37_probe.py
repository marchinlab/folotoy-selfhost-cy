# -*- coding: utf-8 -*-
"""v1.37 声学探针：验证「亚->亞(aa3)、华->華(waa4)」及其他候选字嘅简体G2P劫持。

复用 _yue32_probe2 校准过嘅方法：edge-tts(zh-HK-HiuMaanNeural) + ffmpeg PCM
+ Goertzel F1/F2(元音) + F0自相关(声调) + 逐音节时长。三段：
  A) 单字简/繁/正音锚/反锚：F0med(调高)/F0slope(升降)/F1F2(元音)/sz/md5
  B) 真机词内前后半：东亚/東亞、华夷/華夷、中华/中華、亚洲/亞洲
  C) 批量候选字扫描：27 对简体/繁体单字，sort by 简繁声学距离，揪出疑似劫持字
判据：简体若贴【普通话音反锚】而繁体贴【粤语正音锚】-> 确认劫持 -> 收入 tts_pron.FIXES。
用法(网关容器)：python3 _yue37_probe.py
"""
import subprocess, os, struct, math, re, hashlib

V = "zh-HK-HiuMaanNeural"
R = "+20%"          # 与生产 7 键答话一致（NEWS_RATE+0% 只影响播报）
D = "/audio/pron_yue37"
FS = 16000
os.makedirs(D, exist_ok=True)

# A) 单字：简体目标 / 繁体正音侧 / 正音锚(铁定该粤音) / 反锚(错音方向)
# 「亚」正音 aa3(阴去)，普通话 yà 会压成 jaa3/ngaa6 方向 -> 反锚用「讶/娅」
# 「华」正音 waa4(阳平)，普通话 huá 会压成 faa4/waa(带h) 方向 -> 反锚用「化/花」
SINGLE = [
    ("a_j", "亚", "目标简体 亚 aa3?"),
    ("a_f", "亞", "繁体 亞 aa3(正音侧)"),
    ("a_anchor", "阿", "正音锚 阿 aa3(阴去,同韵)"),
    ("a_anchor2", "啊", "正音锚2 啊 aa3"),
    ("a_bad", "讶", "反锚 讶 ngaa5/普通话ya(错音侧)"),
    ("a_bad2", "娅", "反锚2 娅 jaa3(普通话yà方向)"),
    ("h_j", "华", "目标简体 华 waa4?"),
    ("h_f", "華", "繁体 華 waa4(正音侧)"),
    ("h_anchor", "华", "正音锚 用「華」对比下方「化」"),
    ("h_anchor2", "娃", "正音锚2 娃 waa1(阳平升,同韵waa)"),
    ("h_bad", "化", "反锚 化 faa3(普通话huà压韵方向)"),
    ("h_bad2", "花", "反锚2 花 faa1(同 f 系)"),
    ("h_bad3", "話", "参照 話 waa6(阳去,同waa韵)"),
]
# B) 真机词
WORDS = [("w_dy_j", "东亚"), ("w_dy_f", "東亞"),
         ("w_hy_j", "华夷"), ("w_hy_f", "華夷"),
         ("w_zg_j", "中华"), ("w_zg_f", "中華"),
         ("w_yz_j", "亚洲"), ("w_yz_f", "亞洲")]
# C) 同机制候选：简体被普通话卷舌/舌面/零声母 G2P 劫持嘅高风险字
#    (tag, 简体, 繁体, 粤语正音, 普通话音, 备注)
SCAN = [
    ("东", "東", "dung1", "dōng", "卷舌声母差异"),
    ("车", "車", "ceoi1", "chē", "卷舌ceoi vs che"),
    ("长", "長", "coeng4", "cháng", "卷舌"),
    ("声", "聲", "seng1", "shēng", "卷舌sh vs s"),
    ("说", "說", "syut3", "shuō", "卷舌sh+韵"),
    ("书", "書", "syu1", "shū", "卷舌sh+韵"),
    ("识", "識", "sik1", "shí", "卷舌sh"),
    ("实", "實", "sat6", "shí", "卷舌sh"),
    ("种", "種", "zung2", "zhǒng", "卷舌zh"),
    ("众", "眾", "zung3", "zhòng", "卷舌zh"),
    ("终", "終", "zung1", "zhōng", "卷舌zh"),
    ("转", "轉", "zyun2", "zhuǎn", "卷舌zh"),
    ("政", "政", "zing3", "zhèng", "卷舌zh(同形,对照)"),
    ("机", "機", "gei1", "jī", "舌面j vs g"),
    ("计", "計", "gai3", "jì", "舌面j vs g"),
    ("讲", "講", "gong2", "jiǎng", "舌面j vs g"),
    ("进", "進", "zeon3", "jìn", "舌面j vs z"),
    ("经", "經", "ging1", "jīng", "舌面j vs g"),
    ("举", "舉", "geoi2", "jǔ", "舌面j vs g"),
    ("界", "界", "gaai3", "jiè", "舌面j vs g(同形,对照)"),
    ("无", "無", "mou4", "wú", "零声母w vs m"),
    ("万", "萬", "maan6", "wàn", "零声母w vs m"),
    ("外", "外", "ngoi6", "wài", "零声母w vs ng(同形,对照)"),
    ("为", "為", "wai4", "wéi", "零声母"),
    ("人", "人", "jan4", "rén", "卷舌r vs j(同形,对照)"),
    ("日", "日", "jat6", "rì", "卷舌r vs j(同形,对照)"),
    ("亚", "亞", "aa3", "yà", "零声母(本次目标)"),
    ("华", "華", "waa4", "huá", "h声母(本次目标)"),
]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    if r.returncode or not os.path.exists(mp3):
        print("  GEN_ERR %-10s %s" % (tag, r.stderr.decode("utf-8", "ignore")[:90]))
        return None, None
    return mp3, srt


def md5of(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()[:8] if p else "--------"


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


def fmt(r):
    return ("%4d %4d %5s %6s" % (r[0], r[1], ("%d" % r[2]) if r[2] else "n/a",
                                   ("%+.0f" % r[3]) if r[3] is not None else "n/a")) if r else "  --   --   --     --"


def main():
    store = {}
    print("=" * 92)
    print("A) 单字 F1 F2 F0med F0slope + sz + md8  (亚正音aa3 / 华正音waa4)")
    print("%-11s %-3s %7s %-9s %18s %-5s %s" % ("tag", "字", "sz", "md8", "F1 F2 F0med F0slp", "note", ""))
    print("-" * 92)
    for tag, ch, note in SINGLE:
        mp3, _ = gen(tag, ch)
        if not mp3:
            continue
        sz = os.path.getsize(mp3)
        r = feat_whole(pcm(mp3))
        store[tag] = (r, sz, ch)
        print("%-11s %-3s %7d %-9s %18s  %s" % (tag, ch, sz, md5of(mp3), fmt(r), note))

    print()
    print("A2) 判读：简体 到【粤语正音锚】vs【普通话反锚】嘅距离（小=贴近）")
    groups = [("亚", "a_j", ["a_f", "a_anchor", "a_anchor2"], ["a_bad", "a_bad2"]),
              ("华", "h_j", ["h_f", "h_anchor2", "h_bad3"], ["h_bad", "h_bad2"])]
    for name, tgt, anchors, bads in groups:
        if tgt not in store or not store[tgt][0]:
            continue
        T = store[tgt][0]
        line = ["[%s 简=%s]" % (name, store[tgt][2])]
        for a in anchors:
            if a in store and store[a][0]:
                line.append("d(%s繁/锚%s)=%.2f" % (store[a][2], "", dist(T, store[a][0])))
        for b in bads:
            if b in store and store[b][0]:
                line.append("d(%s反)=%.2f" % (store[b][2], dist(T, store[b][0])))
        print("  " + "  ".join(line))

    print()
    print("B) 真机词内前后半:F1 F2 F0med F0slope (srt边界,无则均分)")
    print("%-11s %-3s %7s %-9s %18s" % ("tag#half", "字", "sz", "md8", "F1 F2 F0med F0slp"))
    print("-" * 92)
    for tag, text in WORDS:
        mp3, srt = gen(tag, text)
        if not mp3:
            continue
        sz = os.path.getsize(mp3)
        s = pcm(mp3)
        total = len(s) / float(FS)
        sl = parse_srt(srt)
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
            print("%-11s %-3s %7d %-9s %18s" % (tag + "#" + str(i), ch, sz, md5of(mp3), fmt(r)))
        print()

    print("C) 候选字扫描：简/繁单字声学距离（大=简繁G2P不同=疑似劫持，需深挖确认方向）")
    print("%-3s %-3s %-6s %-6s | %-18s | %-18s | %6s %s" %
          ("简", "繁", "粤音", "普通话", "简体 F1 F2 F0med F0slp", "繁体 F1 F2 F0med F0slp", "dist", "备注"))
    print("-" * 92)
    rows = []
    for i, (j, f, yue, putong, note) in enumerate(SCAN):
        jm, _ = gen("s_j_%d" % i, j)
        fm, _ = gen("s_f_%d" % i, f)
        if not jm or not fm:
            continue
        jr = feat_whole(pcm(jm))
        fr = feat_whole(pcm(fm))
        d = dist(jr, fr)
        rows.append((d, j, f, yue, putong, jr, fr, note,
                     os.path.getsize(jm), os.path.getsize(fm), md5of(jm), md5of(fm)))
    for d, j, f, yue, putong, jr, fr, note, jsz, fsz, jm5, fm5 in sorted(rows, reverse=True):
        flag = " ***" if d >= 1.6 else (" *" if d >= 0.9 else "")
        same = " SAME-BYTES" if (jsz == fsz and jm5 == fm5) else ""
        print("%-3s %-3s %-6s %-6s | %-18s | %-18s | %6.2f%s%s %s" %
              (j, f, yue, putong, fmt(jr), fmt(fr), d, flag, same, note))
    print("=== DONE ===")


if __name__ == "__main__":
    main()
