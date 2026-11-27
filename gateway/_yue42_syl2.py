# -*- coding: utf-8 -*-
"""v1.42 逐字判调（第2版）：中文连读 WordBoundary 只给整词，改【字间插分隔符】强制逐字 boundary。
先自动探测哪种分隔符能让 SRT 逐字切（普通空格 > 零宽空格 > 全角逗号），再全量合成候选写法，
逐字取【中段 30~70% 浊音】算稳健 F0 中位 + 段内斜率，判「称/过」词内字调落在粤语第几声。

分隔符只用于【声学判调】，代表每个字的独立字调（消除连读协同），不代表生产文本。
生产修法仍按项目惯例做字形/同音字替换（无停顿副作用）。

粤语字调参考(HK HiuMaan 女声, 150~320Hz)：
  阴平1 高平~305-320 | 阴上2 升 | 阴去3 降~235-265 | 阳平4 低平/低升~185-205 | 阳去6 低平~180-195
用法(在网关容器)：python3 _yue42_syl2.py
"""
import subprocess, os, struct, math, re

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue42b"
FS = 16000
os.makedirs(D, exist_ok=True)


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    if r.returncode or not os.path.exists(mp3):
        return None, None
    return mp3, srt


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
        w = "".join(l for l in lines if "-->" not in l and not l.strip().isdigit())
        out.append((w, s, e))
    return out


def pcm_of(path):
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


def med(v):
    if not v:
        return None
    s = sorted(v)
    return s[len(s) // 2]


def f0_mid(seg):
    win, hop = 512, 128
    seq = []
    for st in range(0, max(1, len(seg) - win), hop):
        fr = seg[st:st + win]
        if len(fr) < win:
            break
        mean = sum(fr) / win
        x = [fr[i] - mean for i in range(win)]
        e0 = sum(v * v for v in x)
        if e0 < 1.2e5:
            continue
        lo, hi = int(FS / 320.0), int(FS / 70.0)
        best, bl = 0.0, 0
        for lag in range(lo, hi + 1):
            sc = sum(x[i] * x[i + lag] for i in range(win - lag)) / (e0 + 1e-9)
            if sc > best:
                best, bl = sc, lag
        if best >= 0.32:
            f = FS / float(bl)
            if 70 <= f <= 320:
                seq.append((st, f))
    if len(seq) < 4:
        return None
    t0, t1 = seq[0][0], seq[-1][0]
    span = t1 - t0
    def band(a, b):
        return [v for p, v in seq if t0 + span * a <= p <= t0 + span * b]
    mid = band(0.30, 0.70) or [v for _, v in seq]
    pre = band(0.30, 0.44) or mid[:max(1, len(mid)//2)]
    post = band(0.56, 0.70) or mid[max(1, len(mid)//2):]
    return med(mid), (med(post) - med(pre)) if (pre and post) else 0.0, len(seq)


def analyze(seg):
    if len(seg) < int(0.05 * FS):
        return None
    N = len(seg)
    winf = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (N - 1)) for i in range(N)]
    sig = [seg[i] * winf[i] for i in range(N)]
    freqs = list(range(250, 2901, 40))
    E = {f: goertzel(sig, f) for f in freqs}
    f1 = max([f for f in freqs if 250 <= f <= 1100], key=lambda f: E[f])
    f2 = max([f for f in freqs if 1050 <= f <= 2900], key=lambda f: E[f])
    r = f0_mid(seg)
    if not r:
        return (f1, f2, None, None, 0)
    return (f1, f2, r[0], r[1], r[2])


def tone(f0med, slope):
    if f0med is None:
        return "?"
    if f0med >= 295 and abs(slope) < 30:
        return "阴平1(高平)"
    if slope > 28:
        return "升(2/5)"
    if f0med <= 210:
        return "低平(4/6)"
    if slope < -28:
        return "降(3)"
    return "中平(3/6?)"


def detect_sep():
    """探测哪种分隔符能让 2 字词 SRT 逐字切。返回 (sep, 说明)。"""
    seps = [(" ", "空格"), ("\u200b", "零宽空格"), ("，", "全角逗号")]
    for i, (sep, name) in enumerate(seps):
        mp3, srt = gen("sep%d" % i, "称" + sep + "帝")
        b = parse_srt(srt)
        texts = [re.sub(r"\s|\u200b", "", x[0]) for x in b]
        nonblank = [t for t in texts if t]
        if len(nonblank) >= 2:
            return sep, "%s(切出%d字:%s)" % (name, len(nonblank), "".join(nonblank))
    return "，", "全角逗号兜底"


def main():
    sep, sep_note = detect_sep()
    print("自动选用分隔符:", repr(sep), sep_note)
    # (tag, 目标字串, 关注idx, 说明)
    CASES = [
        ("c_j", "称帝", 0, "称帝·简体(主人报) 称"),
        ("c_f", "稱帝", 0, "稱帝·繁体 稱"),
        ("c_q", "清帝", 0, "清帝·清=cing1无歧义锚 清"),
        ("c_q2", "青帝", 0, "青帝·青=cing1无歧义锚 青"),
        ("c_q3", "卿帝", 0, "卿帝·卿=hing1对照 卿"),
        ("c_ch", "秤帝", 0, "秤帝·秤=cing3反锚 秤"),
        ("c_cz", "趁帝", 0, "趁帝·趁=can3反锚 趁"),
        ("c_ctl1", "称呼", 0, "称呼·控件cing1 称"),
        ("c_ctl3", "对称", 1, "对称·控件cing3 称"),
        ("c_one", "称", 0, "称·单字"),
        ("g_j", "走过来", 1, "走过来·简体(主人报) 过"),
        ("g_f", "走過來", 1, "走過來·繁体 過"),
        ("g_m", "行過嚟", 1, "行過嚟·地道粤语锚 過"),
        ("g_guo", "走果来", 1, "走果来·果gwo2锚 果"),
        ("g_g1", "走锅来", 1, "走锅来·锅gwo1反锚 锅"),
        ("g_g3", "走国来", 1, "走国来·国gwok3入声锚 国"),
        ("g_l", "过来", 0, "过来·两字 过"),
        ("g_q", "过去", 0, "过去·控件 过"),
        ("g_gc", "过程", 0, "过程·v1.30称本就啱 过"),
        ("g_one", "过", 0, "过·单字"),
        ("g_zou", "走", 0, "走·单字(zau2控件)"),
        ("g_lai", "来", 0, "来·单字(loi4/卷舌排查)"),
    ]
    print("%-7s %-8s %-3s %-3s %5s %5s %6s %7s %3s %-13s %s" %
          ("tag", "文本", "idx", "字", "F1", "F2", "F0med", "斜率", "帧", "判调", "说明"))
    print("-" * 112)
    for tag, text, focus, note in CASES:
        spaced = sep.join(text)
        mp3, srt = gen(tag, spaced)
        if not mp3:
            print("%-7s GEN_ERR" % tag); continue
        b = parse_srt(srt)
        chars = [re.sub(r"\s|\u200b|，", "", x[0]) for x in b]
        chars = [c for c in chars if c]
        sig = pcm_of(mp3)
        if len(chars) == len(text) and chars[focus] == text[focus]:
            ss, ee = b[focus][1], b[focus][2]
            span_note = "逐字"
        else:
            # fallback：整词等分
            if not b:
                print("%-7s NO_SRT" % tag); continue
            ss, ee = b[0][1], b[0][2]
            dur = (ee - ss) / len(text)
            ss, ee = ss + dur * focus, ss + dur * (focus + 1)
            span_note = "等分"
        a, bb = max(0, int(ss * FS)), min(len(sig), int(ee * FS))
        # 去掉字边界 10ms 防串音
        a += int(0.010 * FS); bb -= int(0.010 * FS)
        seg = sig[a:bb]
        r = analyze(seg)
        ch = text[focus]
        if not r:
            print("%-7s %-8s %-3s %-3s SKIP(%s)" % (tag, text, str(focus), ch, span_note)); continue
        f1, f2, f0m, slope, nf = r
        fm = lambda v: ("%d" % v) if v is not None else "n/a"
        print("%-7s %-8s %-3s %-3s %5d %5d %6s %+7.0f %3d %-13s %s [%s]" %
              (tag, text, str(focus), ch, f1, f2, fm(f0m), slope or 0, nf, tone(f0m, slope or 0), note, span_note))
    print("\n=== DONE_42_SYLEP ===")


if __name__ == "__main__":
    main()
