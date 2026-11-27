# -*- coding: utf-8 -*-
"""v1.44 纯离线判读（不联网、只读现成 mp3）—— 攻三个决策点：
  A)【说】游说/遊說 尾字到底 syut3(入声-t短促) 定 seoi3(去声开尾长) → 全局 说→說 会否带偏
  B)【称】称帝/称王 词内首字系咪降调(错)、清帝/清王 锚系咪高平 cing1(啱) → 定词级换字锚
  C)【渐/亲】转繁 首字 F0 + F1F2 有冇干净方向

方法(避 v1.42 切字坑)：
  · 词【首字】= 取音频物理开头 0.05~0.22s 稳态窗(第一个字一定喺开头，唔使估边界)。
  · 词【尾字】= 去尾静音后取最后 0.22s(尾字后系静音，边界最干净)。
  · 单字 = 同首字窗，作锚。
  · F0 自相关判调(平/降/升)，F1/F2 goertzel 判元音。
  · 整词字节 sz 作辅助(只同音素先相等，8k 区会碰撞，唔单独定案)。
容器内：python3 _yue44_offline.py
"""
import subprocess, os, struct, math

FS = 16000
DIRS = ["/audio/pron_yue44", "/audio/pron_yue43", "/audio/pron_yue42"]


def find(tag):
    for d in DIRS:
        p = "%s/%s.mp3" % (d, tag)
        if os.path.exists(p):
            return p
    return None


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


def f0_curve(seg, hop=80, win=384):
    out = []
    for st in range(0, len(seg) - win, hop):
        fr = seg[st:st + win]
        mean = sum(fr) / win
        x = [v - mean for v in fr]
        e0 = sum(v * v for v in x)
        if e0 < 3e5:
            out.append(None)
            continue
        lo, hi = int(FS / 320), int(FS / 70)
        best, bestlag = 0.0, 0
        for lag in range(lo, hi + 1):
            sc = sum(x[i] * x[i + lag] for i in range(win - lag)) / (e0 + 1e-9)
            if sc > best:
                best, bestlag = sc, lag
        if best >= 0.34:
            v = FS / float(bestlag)
            out.append(v if 70 <= v <= 320 else None)
        else:
            out.append(None)
    return out


def summ(vals):
    v = sorted([x for x in vals if x])
    if not v:
        return None, None, 0
    med = v[len(v) // 2]
    k = max(1, len(v) // 3)
    slope = sum(v[-k:]) / k - sum(v[:k]) / k
    return round(med), round(slope), len(v)


def head(path):
    """首字/单字：自动找开头能量上升沿后取 0.19s 稳态窗；返 (F0med,F0slope,n,F1,F2)。"""
    s = pcm(path)
    hop = 160
    onset = 0
    for st in range(0, min(len(s), int(0.8 * FS)), hop):
        seg0 = s[st:st + hop]
        e = sum(v * v for v in seg0) / max(1, len(seg0))
        if e > 1.5e6:
            onset = st
            break
    a = onset + int(0.01 * FS)
    b = a + int(0.19 * FS)
    seg = s[a:b]
    med, slope, n = summ(f0_curve(seg))
    # F1/F2 用同一窗口加 hann
    N = len(seg)
    if N > 8:
        w = [0.5 - 0.5 * math.cos(2 * math.pi * i / (N - 1)) for i in range(N)]
        sig = [seg[i] * w[i] for i in range(N)]
        fr = list(range(250, 2901, 40))
        E = {f: goertzel(sig, f) for f in fr}
        f1 = max([f for f in fr if 250 <= f <= 1100], key=lambda f: E[f])
        f2 = max([f for f in fr if 1050 <= f <= 2900], key=lambda f: E[f])
    else:
        f1 = f2 = 0
    return med, slope, n, f1, f2


def tail(path):
    """尾字：去尾静音后最后 0.24s；返 (F0med,F0slope,n,voiced_dur_s)。"""
    s = pcm(path)
    hop = 160
    last = len(s)
    # 由后往前找最后一段有能量嘅位置
    for st in range(len(s) - hop, max(0, len(s) - int(1.2 * FS)), -hop):
        seg = s[st:st + hop]
        e = sum(v * v for v in seg) / max(1, len(seg))
        if e > 1.5e6:
            last = min(len(s), st + hop * 5)
            break
    a = max(0, last - int(0.24 * FS))
    med, slope, n = summ(f0_curve(s[a:last]))
    return med, slope, n, round((last - a) / FS, 3)


def row(tag, text, note, mode="head"):
    p = find(tag)
    if not p:
        print("  %-8s %-6s MISSING" % (tag, text))
        return
    sz = os.path.getsize(p)
    if mode == "tail":
        med, slope, n, vd = tail(p)
        print("  %-8s %-6s sz=%-5d 尾字 F0med=%-5s slope=%-5s frames=%-3d voiced=%.3fs  %s"
              % (tag, text, sz, med or "n/a", ("%+d" % slope) if slope is not None else "n/a",
                 n, vd, note))
    else:
        med, slope, n, f1, f2 = head(p)
        print("  %-8s %-6s sz=%-5d 首字 F0med=%-5s slope=%-5s F1/F2=%d/%d n=%-3d  %s"
              % (tag, text, sz, med or "n/a", ("%+d" % slope) if slope is not None else "n/a",
                 f1, f2, n, note))


def main():
    print("=" * 100)
    print("A)【说】游说/遊說 尾字判调：syut3(入声-t 短促,似雪) vs seoi3(去声开尾长,似税)")
    print("   —— 若 遊說 尾字仍似「税」(seoi3) → 全局 说→說 安全；若被带成「雪」(syut3) → 只词级")
    for t, x, note in [
        ("sh_a1", "雪", "syut3 正音锚(入声-t,短促)"),
        ("sh_b4", "税", "seoi3 反锚(去声-i,开尾长)"),
        ("sh_f", "說", "繁 說 单字(syut3)"),
        ("sh_j", "说", "简 说 单字(主人报错)"),
        ("ysh_j", "游说", "⚠️简体 游说 现状"),
        ("ysh_f", "遊說", "⚠️转繁 遊說 会否仍 seoi3"),
        ("sw_f", "說話", "對照 說話(syut3+話)"),
    ]:
        row(t, x, note, mode="tail")

    print()
    print("=" * 100)
    print("B)【称】词内首字判调：称帝/称王 应高平 cing1；清帝/清王 锚；秤帝(cing3)反锚")
    for t, x, note in [
        ("c_j", "称", "单字 称(已知 cing1 高平,锚)"),
        ("c_a1", "清", "单字 清(cing1 同音锚)"),
        ("c_a2", "秤", "单字 秤(cing3 反锚)"),
        ("cd_j", "称帝", "⚠️称帝 词内首字"),
        ("cd_a", "清帝", "锚 清帝(cing1)"),
        ("cd_b", "秤帝", "反锚 秤帝(cing3)"),
        ("cd_f", "稱帝", "繁 稱帝(v1.42 证更乱)"),
        ("cw_j", "称王", "⚠️称王 词内首字"),
        ("cw_a", "清王", "锚 清王(cing1)"),
        ("dc_j", "对称", "控件 对称(应 cing3)"),
    ]:
        row(t, x, note)

    print()
    print("=" * 100)
    print("C)【渐/亲】转繁 首字 F0/F1F2")
    for t, x, note in [
        ("j_j", "渐", "简 渐 单字"),
        ("j_f", "漸", "繁 漸 单字(候选正音 jim6 去声降)"),
        ("j_b3", "尖", "反锚 尖(zim1 高平)"),
        ("jj_j", "渐渐", "⚠️渐渐 词内首字"),
        ("jj_f", "漸漸", "繁 漸漸"),
        ("zj_j", "逐渐", "逐渐 词内次字位(参考)"),
        ("q_j", "亲", "简 亲 单字"),
        ("q_f", "親", "繁 親 单字"),
        ("q_b4", "餐", "锚 餐(caan1 长a)"),
        ("q_b1", "千", "反锚 千(cin1)"),
        ("qz_j", "亲自", "⚠️亲自 词内首字"),
        ("qz_f", "親自", "繁 親自"),
    ]:
        row(t, x, note)

    print("\n=== DONE_OFFLINE_44 ===")


if __name__ == "__main__":
    main()
