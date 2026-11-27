# -*- coding: utf-8 -*-
"""v1.42 逐音节判调：edge-tts 中文 WordBoundary 只给整词，故自己按【理论等分+能量谷】
切出每个音节，逐音节算 F0 轨迹(前/中/后三段中位) + F1/F2，判「称/过」词内到底念第几声。

复用 _yue32_probe.py 的 goertzel/pcm；新增：
  split_syl(pcm, s, e, n) -> [(a,b),...]  在 s..e 内按 n 等分，每个理论边界 ±12% 找能量谷微调。
  f0_track(seg) -> (first_med, mid_med, last_med, overall_med, nframes)  逐帧自相关。

分析对象：直接读 _yue42_probe.py 已生成的 /audio/pron_yue42/*.mp3 + *.srt，不重新合成。
粤语六声 F0 轨迹（HK HiuMaan 女声，基频约 150~320Hz）：
  1 阴平 高平(~290-315, 平) | 2 阴上 中升 | 3 阴去 中降/中平(~210-240) |
  4 阳平 低平/低升(~185-205) | 5 阳上 低升 | 6 阳去 低平(~180-195)
判「称」：cing1 应高平(~300)；若掉到 ~230 降 = 被念成 cing3(第三声)=错。
判「过」：gwo3 应中降/中平(~215-235)；若 ~300 高平=gwo1(锅,第一声)错；~250 升=gwo2(果)错。
用法(在网关容器)：python3 _yue42_syl.py
"""
import subprocess, os, struct, math, re

FS = 16000
D = "/audio/pron_yue42"

# (tag, 文本, 音节数, 关注第几个音节(0起), 说明)
CASES = [
    # 称帝：关注首音节「称」
    ("cd_j",  "称帝", 2, 0, "称帝·简体(主人报) 首字称"),
    ("cd_f",  "稱帝", 2, 0, "稱帝·繁体候选 首字稱"),
    ("cd_a1", "清帝", 2, 0, "清帝·cing1正音锚 首字清"),
    ("cd_a3", "青帝", 2, 0, "青帝·cing1正音锚2 首字青"),
    ("cd_b2", "秤帝", 2, 0, "秤帝·cing3反锚 首字秤"),
    ("cd_b1", "趁帝", 2, 0, "趁帝·can3反锚 首字趁"),
    ("ctl_c1","称呼", 2, 0, "称呼·控件 cing1应准 首字称"),
    ("ctl_c3","对称", 2, 1, "对称·控件 cing3 次字称"),
    ("ch_j",  "称",   1, 0, "称·单字"),
    ("ch_f",  "稱",   1, 0, "稱·单字"),
    # 走过来：关注中间音节「过」
    ("zg_j",  "走过来", 3, 1, "走过来·简体(主人报) 中字过"),
    ("zg_f",  "走過來", 3, 1, "走過來·繁体 中字過"),
    ("zg_m1", "行過嚟", 3, 1, "行過嚟·地道粤语锚 中字過"),
    ("zg_a1", "走果来", 3, 1, "走果来·果gwo2锚 中字果"),
    ("zg_b1", "走锅来", 3, 1, "走锅来·锅gwo1反锚 中字锅"),
    ("zg_b2", "走国来", 3, 1, "走国来·国gwok3入声反锚 中字国"),
    ("guo_l", "过来", 2, 0, "过来·简体两字 首字过"),
    ("guo_f2","過来", 2, 0, "過来·过转繁 首字過"),
    ("guo_q", "过去", 2, 0, "过去·控件 首字过"),
    ("guo_gc","过程", 2, 0, "过程·v1.30称本就啱控件 首字过"),
    ("guo_j", "过",   1, 0, "过·单字"),
    ("guo_f", "過",   1, 0, "過·单字"),
    ("lai_j", "来",   1, 0, "来·单字(卷舌排查)"),
]


def pcm_of(path):
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-ac", "1", "-ar", str(FS),
                          "-f", "s16le", "-"], capture_output=True).stdout
    n = len(raw) // 2
    return list(struct.unpack("<%dh" % n, raw[: n * 2]))


def srt_span(path):
    if not path or not os.path.exists(path):
        return None
    txt = open(path, encoding="utf-8-sig").read().replace("\r", "")
    m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", txt)
    if not m:
        return None
    g = [int(x) for x in m.groups()]
    s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
    e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
    return s, e


def energy_env(sig, hop=160):
    out = []
    for i in range(0, len(sig) - hop, hop):
        fr = sig[i:i + hop]
        out.append(sum(v * v for v in fr) / hop)
    return out


def split_syl(sig, ss, ee, n):
    a, b = int(ss * FS), min(len(sig), int(ee * FS))
    seg = sig[a:b]
    L = len(seg)
    if L < n * int(0.06 * FS):
        return [(a, b)]
    env = energy_env(seg)
    hop = 160
    # 理论边界（等分），每边界在 ±12% 音节省内找能量最小帧
    bounds = [0]
    for k in range(1, n):
        center = int(L * k / n)
        w = int(L * 0.12 / n)
        lo = max(1, center - w)
        hi = min(len(env) - 1, center + w)
        best_i, best_v = center, 1e18
        for i in range(lo, hi + 1):
            v = sum(env[i - 1:i + 2]) if i > 0 else env[i]
            if v < best_v:
                best_v, best_i = v, i
        bounds.append(min(L - 1, best_i * hop))
    bounds.append(L)
    return [(a + bounds[i], a + bounds[i + 1]) for i in range(n)]


def goertzel(sig, freq):
    k = 2.0 * math.cos(2.0 * math.pi * freq / FS)
    s1 = s2 = 0.0
    for x in sig:
        s0 = x + k * s1 - s2
        s2, s1 = s1, s0
    return s1 * s1 + s2 * s2 - k * s1 * s2


def f0_seq(seg, win=512, hop=128):
    seq = []
    for st in range(0, max(1, len(seg) - win), hop):
        fr = seg[st:st + win]
        if len(fr) < win:
            break
        mean = sum(fr) / win
        x = [fr[i] - mean for i in range(win)]
        e0 = sum(v * v for v in x)
        if e0 < 1.5e5:
            continue
        lo, hi = int(FS / 320.0), int(FS / 70.0)
        best, bestlag = 0.0, 0
        for lag in range(lo, hi + 1):
            sc = sum(x[i] * x[i + lag] for i in range(win - lag)) / (e0 + 1e-9)
            if sc > best:
                best, bestlag = sc, lag
        if best >= 0.30:
            v = FS / float(bestlag)
            if 70 <= v <= 320:
                seq.append(v)
    return seq


def med(v):
    if not v:
        return None
    s = sorted(v)
    return s[len(s) // 2]


def analyze(seg):
    if len(seg) < int(0.04 * FS):
        return None
    N = len(seg)
    winf = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (N - 1)) for i in range(N)]
    sig = [seg[i] * winf[i] for i in range(N)]
    freqs = list(range(250, 2901, 40))
    E = {f: goertzel(sig, f) for f in freqs}
    f1 = max([f for f in freqs if 250 <= f <= 1100], key=lambda f: E[f])
    f2 = max([f for f in freqs if 1050 <= f <= 2900], key=lambda f: E[f])
    seq = f0_seq(seg)
    m = len(seq)
    if m < 3:
        return (f1, f2, None, None, None, None, m)
    k = max(2, m // 3)
    first = med(seq[:k]); mid = med(seq[k:2 * k]); last = med(seq[-k:])
    return (f1, f2, first, mid, last, med(seq), m)


def shape(first, last):
    if first is None or last is None:
        return "?"
    d = last - first
    if d > 25:
        return "升"
    if d < -25:
        return "降"
    return "平"


def main():
    print("%-7s %-3s %-3s %-13s %5s %5s %7s %7s %7s %7s %3s %s" %
          ("tag", "关注", "字", "文本", "F1", "F2", "F0前", "F0中", "F0后", "F0med", "帧", "调形"))
    print("-" * 108)
    for tag, text, n, focus, note in CASES:
        mp3 = "%s/%s.mp3" % (D, tag)
        srt = "%s/%s.srt" % (D, tag)
        if not os.path.exists(mp3):
            print("%-7s MISSING" % tag); continue
        sig = pcm_of(mp3)
        span = srt_span(srt)
        if not span:
            print("%-7s NO_SRT" % tag); continue
        syls = split_syl(sig, span[0], span[1], n)
        a, b = syls[focus]
        r = analyze(sig[a:b])
        ch = text[focus]
        if not r:
            print("%-7s %-3s %-3s %-13s SKIP" % (tag, str(focus), ch, text)); continue
        f1, f2, f0f, f0m, f0l, f0med, nf = r
        fm = lambda v: ("%d" % v) if v is not None else "n/a"
        print("%-7s %-3s %-3s %-13s %5d %5d %7s %7s %7s %7s %3d %s  | %s" %
              (tag, str(focus), ch, text, f1, f2, fm(f0f), fm(f0m), fm(f0l), fm(f0med), nf,
               shape(f0f, f0l), note))
    print("\n=== DONE_42_SYL ===")


if __name__ == "__main__":
    main()
