# -*- coding: utf-8 -*-
"""v1.42 声学探针：主人实测「称帝」的「称」要第一声(cing1)、「走过来」的「过」发音唔啱。
两套独立判据（复用 v1.32 _yue32_probe.py 已验证框架）：
  A) 整词 mp3 字节/md5/dur —— 同音素序列必同字节，可判「目标==哪个锚」。
  B) word-boundary 字幕逐音节 F0(声调)/F1F2(元音) —— 定位错在哪个字、什么调。

粤语背景（探针要回答的问题）：
  · 称 cing1(阴平,第一声)：称帝/称王/称呼/声称；另读 cing3(阴去)：对称/相称/称职。
    ? 「称帝」简体现今念成第几声？繁「稱」能否正音 cing1？定系要换 cing1 同音锚字(如「清/青/卿」cing1)？
  · 过 gwo3(阴去)：走过来/过去/过马路。v1.30 证「过程/过/過」简繁本就啱(单字简繁同)。
    ? 「走过来」到底边个字错、错成乜？简「过」vs 繁「過」？定系「来」被卷舌(loi4->lai)？
    故设词级整词对照 + 拆字到词内单音节。
用法(在网关容器)：python3 _yue42_probe.py
"""
import subprocess, os, struct, math, re, hashlib

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue42"
FS = 16000
os.makedirs(D, exist_ok=True)

# (tag, 文本, 说明)
CASES = [
    # ===== 称帝 cing1 dai3：目标 vs 繁体 vs cing1 同音锚 vs cing3 反锚 =====
    ("cd_j",  "称帝",   "简体 称帝(主人报,称要第一声)"),
    ("cd_f",  "稱帝",   "繁体 稱帝(候选)"),
    ("cd_a1", "清帝",   "正音锚 清(cing1)帝"),
    ("cd_a2", "卿帝",   "正音锚2 卿(cing1)帝"),
    ("cd_a3", "青帝",   "正音锚3 青(cing1)帝"),
    ("cd_b1", "趁帝",   "反锚 趁(cing3) 测称若念第三声"),
    ("cd_b2", "秤帝",   "反锚 秤(cing3)"),
    ("cd_b3", "沉帝",   "反锚 沉(cam4) 测是否卷舌/他调"),
    # 词内单字：称 单独(观察声库对简体称的默认音)
    ("ch_j",  "称",     "简体 称 单字"),
    ("ch_f",  "稱",     "繁体 稱 单字"),
    # 控件：已知 cing1/cing3 正确词，确认声库调类
    ("ctl_c1","称呼",   "控件 称呼(cing1) 应准"),
    ("ctl_c3","对称",   "控件 对称(cing3) 应准"),
    # ===== 走过来 zau2 gwo3 lai4 =====
    ("zg_j",  "走过来", "简体 走过来(主人报,过唔啱)"),
    ("zg_f",  "走過來", "繁体 走過來(候选)"),
    ("zg_f2", "走過来", "混合 走过→過 来简( isolating 过)"),
    ("zg_m1", "行過嚟", "地道粤语锚 行過嚟(haang4 gwo3 lai4)"),
    ("zg_a1", "走果来", "正音锚 果(gwo2) 测过调(应差一调)"),
    ("zg_a2", "走過来", "只转过→過,来保持简( isolates 过繁简)"),
    ("zg_b1", "走锅来", "反锚 锅(gwo1) 测过若念第一声"),
    ("zg_b2", "走国来", "反锚 国(gwok3 入声) 测韵尾"),
    # 过 单字 + 词组，隔离 G2P
    ("guo_j", "过",     "简体 过 单字"),
    ("guo_f", "過",     "繁体 過 单字"),
    ("guo_l", "过来",   "简体 过来(两字)"),
    ("guo_f2","過来",   "过→過 来简(两字,isolate过)"),
    ("guo_q", "过去",   "简体 过去(控件,v1.30称本就啱?)"),
    ("guo_gc","过程",   "简体 过程(v1.30 已证本就啱, 回归控件)"),
    # 来 卷舌排查
    ("lai_j", "来",     "简体 来 单字(卷舌 lai?)"),
    ("lai_f", "來",     "繁体 來 单字"),
]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    if r.returncode or not os.path.exists(mp3):
        print("  GEN_ERR %-7s %s" % (tag, r.stderr.decode("utf-8", "ignore")[:120]))
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
    print("=" * 96)
    print("A) 整词字节碰撞（sz/md5/dur）—— 同音素必同字节")
    print("%-7s %-9s %8s %12s %8s  %s" % ("tag", "文本", "sz", "md5", "dur", "说明"))
    print("-" * 96)
    info = {}
    for tag, text, note in CASES:
        mp3, srt = gen(tag, text)
        if not mp3:
            continue
        sz = os.path.getsize(mp3)
        md = hashlib.md5(open(mp3, "rb").read()).hexdigest()[:10]
        dt = dur(mp3)
        info[tag] = (text, sz, note, srt, mp3)
        print("%-7s %-9s %8d %12s %8.3f  %s" % (tag, text, sz, md, dt, note))

    print()
    print("=" * 96)
    print("B) 逐音节 F0(声调) / F1F2(元音)")
    print("%-10s %-4s %6s %6s %8s %9s" % ("tag#idx", "字", "F1", "F2", "F0med", "F0slope"))
    print("-" * 96)
    for tag, (text, sz, note, srt, mp3) in info.items():
        s = pcm(mp3)
        sl = parse_srt(srt)
        for j, (ch, ss, ee) in enumerate(sl):
            r = analyze_syl(s, ss, ee)
            if not r:
                print("%-10s %-4s SKIP" % (tag + "#" + str(j), ch))
                continue
            print("%-10s %-4s %6d %6d %8s %9s" %
                  (tag + "#" + str(j), ch, r[0], r[1],
                   ("%d" % r[2]) if r[2] else "n/a",
                   ("%+.0f" % r[3]) if r[3] is not None else "n/a"))

    print()
    print("=" * 96)
    print("C) 判读辅助：目标 vs 锚 的字节差")
    def sz(t):
        return info[t][1] if t in info else None
    groups = [
        ("称帝 目标 cd_j", "cd_j", ["cd_f", "cd_a1", "cd_a2", "cd_a3", "cd_b1", "cd_b2", "cd_b3"]),
        ("称 单字 ch_j", "ch_j", ["ch_f", "cd_a1", "cd_b1"]),
        ("走过来 目标 zg_j", "zg_j", ["zg_f", "zg_f2", "zg_m1", "zg_a1", "zg_a2", "zg_b1", "zg_b2"]),
        ("过来 guo_l", "guo_l", ["guo_f2", "guo_q"]),
        ("过 单字 guo_j", "guo_j", ["guo_f", "zg_a1"]),
    ]
    for label, tgt, anchors in groups:
        t = sz(tgt)
        if t is None:
            continue
        parts = []
        for a in anchors:
            v = sz(a)
            if v is not None:
                parts.append("%s=%d(%+d)" % (a, v, v - t))
        print("  %-20s sz=%-6d | %s" % (label, t, " ".join(parts)))
    print("\n=== DONE_42 ===")


if __name__ == "__main__":
    main()
