# -*- coding: utf-8 -*-
"""v1.43 声学探针：主人实测「说话」的「说」发音唔啱。

复用 v1.42 / v1.32 已验证框架，但【避开 v1.42 踩过嘅坑】——edge-tts 中文
WordBoundary 系【整词一个 boundary、唔逐字】，靠能量谷/等分切词内字会飘、F0
自相矛盾。故本轮判据分两级：
  A) 整词/单字 mp3 字节碰撞（sz/md5/dur）——同音素序列必同字节，最硬。
  B) 【单字】F0(声调)/F1F2(元音卷舌)/时长(入声-t尾)——单字一个 boundary、
     分析窗口=成个字，最干净可信。词内逐音节只打印参考、唔攞嚟定案。
  D) 单字声学指纹汇总——一眼睇「说」似正音锚「雪」定似边个反锚。

粤语背景（探针要答嘅问题）：
  · 说 正音 syut3（阴入：s 非卷舌 + 圆唇前元音 /y/ + 短促 -t 塞尾）：
    说话/说明/演说/小说/传说/说服。普通话 shuō = 卷舌 sh + 开尾 uo，差好远。
    v1.32「时/儿」已坐实：HK 声库对【简体】按普通话卷舌 G2P 劫持，转繁返粤。
    ? 简体「说」单字而家念成乜？似「雪」syut3、定似卷舌/他韵反锚？转繁「說」能否正音？
  · ⚠️「说」系【多音字】：syut3(说话/说明) vs seoi3(游说 jau5 seoi3)。
    故【全局 说→說 前必须验「游说/遊說」唔会被带偏】；若有风险只落词级。
  · 地道粤语口语「说话」多讲「讲嘢」gong2 je5，但「说话」作名词(说话技巧/
    佢嘅说话)仍用 syut3 waa6，唔可一律换词。A/B 试听交主人耳定。
  · 同音锚 syut3 常用得净系「雪」「說」两字；反锚覆盖所有可能误读：
    sok3(索 -k)、suk1(叔 -k 圆唇)、cuk1(速 -k)、seoi3(税 -i 去声)、
    so1(梳 开尾)、so2(所 开尾)、seot1(恤 -t 但韵 /eot/)。
用法(网关容器)：python3 _yue43_probe.py
"""
import subprocess, os, struct, math, re, hashlib

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue43"
FS = 16000
os.makedirs(D, exist_ok=True)

# (tag, 文本, 说明)
CASES = [
    # ===== 单字区（判据主力：一个 boundary、声学最干净）=====
    ("sh_j",  "说",   "简体 说 单字(主人报,音唔啱)"),
    ("sh_f",  "說",   "繁体 說 单字(候选正音)"),
    ("sh_a1", "雪",   "正音锚 雪(syut3 入声-t, 圆唇前元音/y/)"),
    ("sh_b1", "索",   "反锚 索(sok3 入声-k)"),
    ("sh_b2", "叔",   "反锚 叔(suk1 入声-k, 圆唇/u/)"),
    ("sh_b3", "速",   "反锚 速(cuk1 入声-k)"),
    ("sh_b4", "税",   "反锚 税(seoi3 去声 -i尾, 即游说嗰读)"),
    ("sh_b5", "梳",   "反锚 梳(so1 平声 开尾/o/)"),
    ("sh_b6", "所",   "反锚 所(so2 上声 开尾/o/)"),
    ("sh_b7", "恤",   "反锚 恤(seot1 入声-t 但韵/eot/)"),
    # ===== 话 单字（确认「话」本身简繁系咪一致）=====
    ("w_j",   "话",   "简体 话 单字"),
    ("w_f",   "話",   "繁体 話 单字"),
    # ===== 词「说话」syut3 waa6（整词字节 + 时长，唔判词内字）=====
    ("sw_j",  "说话", "简体 说话(主人报)"),
    ("sw_f",  "說話", "繁体 說話(候选)"),
    ("sw_a1", "雪話", "正音锚 雪話(syut3 waa6)"),
    ("sw_b1", "税話", "反锚 税話(seoi3 waa6)"),
    ("sw_m1", "讲嘢", "地道粤语锚 讲嘢(gong2 je5)"),
    ("sw_m2", "講嘢", "地道粤语锚繁 講嘢"),
    # ===== 护字词简体（评估全局 说→說 误伤面）=====
    ("sm_j",  "说明", "说明 syut3 ming4"),
    ("ys_j",  "演说", "演说 jim5 syut3"),
    ("xs_j",  "小说", "小说 siu2 syut3"),
    ("cs_j",  "传说", "传说 cyun4 syut3"),
    ("sf_j",  "说服", "说服 syut3 fuk6"),
    ("ysh_j", "游说", "⚠️多音 游说 jau5 seoi3(全局风险关键)"),
    ("sfa_j", "说法", "说法 syut3 faat3"),
    # ===== 护字词繁体（对比转繁后是否仍准、游说有冇被带偏）=====
    ("sm_f",  "說明", "說明"),
    ("ys_f",  "演說", "演說"),
    ("xs_f",  "小說", "小說"),
    ("cs_f",  "傳說", "傳說"),
    ("sf_f",  "說服", "說服"),
    ("ysh_f", "遊說", "⚠️遊說 转繁后系咪仍 seoi3"),
    ("sfa_f", "說法", "說法"),
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
    print("A) 整词/单字字节碰撞（sz/md5/dur）—— 同音素必同字节")
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
        info[tag] = (text, sz, note, srt, mp3, dt)
        print("%-7s %-9s %8d %12s %8.3f  %s" % (tag, text, sz, md, dt, note))

    print()
    print("=" * 96)
    print("B) 逐音节 F0(声调)/F1F2(元音)/时长 —— 【单字行可信】, 词内行仅参考(切字会飘)")
    print("%-10s %-4s %6s %6s %8s %9s" % ("tag#idx", "字", "F1", "F2", "F0med", "F0slope"))
    print("-" * 96)
    for tag, (text, sz, note, srt, mp3, dt) in info.items():
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
    print("C) 判读辅助：目标 vs 锚/反锚 的字节差 + 时长差")
    def sz(t):
        return info[t][1] if t in info else None
    def dt(t):
        return info[t][5] if t in info else None
    groups = [
        ("说 单字 sh_j", "sh_j", ["sh_f", "sh_a1", "sh_b1", "sh_b2", "sh_b3", "sh_b4", "sh_b5", "sh_b6", "sh_b7"]),
        ("说话 sw_j", "sw_j", ["sw_f", "sw_a1", "sw_b1", "sw_m1", "sw_m2"]),
        ("话 单字 w_j", "w_j", ["w_f"]),
        ("说明 sm_j", "sm_j", ["sm_f"]),
        ("演说 ys_j", "ys_j", ["ys_f"]),
        ("小说 xs_j", "xs_j", ["xs_f"]),
        ("传说 cs_j", "cs_j", ["cs_f"]),
        ("说服 sf_j", "sf_j", ["sf_f"]),
        ("游说 ysh_j", "ysh_j", ["ysh_f"]),
        ("说法 sfa_j", "sfa_j", ["sfa_f"]),
    ]
    for label, tgt, anchors in groups:
        t = sz(tgt)
        if t is None:
            continue
        parts = []
        for a in anchors:
            v = sz(a)
            if v is not None:
                d = dt(a)
                parts.append("%s=%d(%+d,%.2fs)" % (a, v, v - t, d if d else 0))
        print("  %-16s sz=%-6d dur=%.2fs | %s" % (label, t, dt(tgt) or 0, " ".join(parts)))

    print()
    print("=" * 96)
    print("D) 单字声学指纹汇总（判据主力）——「说」到底似正音锚「雪」定边个反锚")
    print("%-8s %-6s %6s %6s %8s %9s %8s  %s" %
          ("tag", "字", "F1", "F2", "F0med", "F0slope", "dur", "说明"))
    print("-" * 96)
    for tag in ["sh_j", "sh_f", "sh_a1", "sh_b1", "sh_b2", "sh_b3", "sh_b4", "sh_b5", "sh_b6", "sh_b7", "w_j", "w_f"]:
        if tag not in info:
            continue
        text, sz_, note, srt, mp3, dt_ = info[tag]
        s = pcm(mp3)
        sl = parse_srt(srt)
        r = analyze_syl(s, sl[0][1], sl[0][2]) if sl else analyze_syl(s, 0, dt_)
        if not r:
            print("%-8s %-6s SKIP" % (tag, text))
            continue
        print("%-8s %-6s %6d %6d %8s %9s %8.3f  %s" %
              (tag, text, r[0], r[1],
               ("%d" % r[2]) if r[2] else "n/a",
               ("%+.0f" % r[3]) if r[3] is not None else "n/a",
               dt_, note))
    print("\n=== DONE_43 ===")


if __name__ == "__main__":
    main()
