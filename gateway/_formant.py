# -*- coding: utf-8 -*-
"""声学判定「听」念 ting1(/tiŋ/) 定是 teng1(/teŋ/)：量第一音节主元音共振峰。
/i/ 的 F2 高(~2300Hz)，/e/ 的 F2 低(~1900Hz)；用 2100-2700 与 1400-2000 能量比作鲁棒判据。
纯标准库 Goertzel，无 numpy 依赖；容器内 ffmpeg 解码。"""
import subprocess, struct, math, os, glob

D = "/audio/pron3"
FS = 16000


def pcm(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", path, "-ac", "1", "-ar", str(FS), "-f", "s16le", "-"],
        capture_output=True).stdout
    n = len(raw) // 2
    return list(struct.unpack("<%dh" % n, raw[: n * 2]))


def goertzel(sig, freq):
    """单频点能量（Goertzel），sig 已加窗。"""
    k = 2.0 * math.cos(2.0 * math.pi * freq / FS)
    s1 = s2 = 0.0
    for x in sig:
        s0 = x + k * s1 - s2
        s2, s1 = s1, s0
    return s1 * s1 + s2 * s2 - k * s1 * s2


def analyze(path):
    s = pcm(path)
    if len(s) < FS * 0.3:
        return None
    # 第一音节稳定段：0.05~0.20s（避开起音爆发与第二个字「日」）
    a, b = int(0.05 * FS), int(0.20 * FS)
    seg = s[a:b]
    N = len(seg)
    win = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (N - 1)) for i in range(N)]  # Hann
    sig = [seg[i] * win[i] for i in range(N)]
    # 扫频找 F1(250~1000) 和 F2(1000~2900) 峰值
    freqs = list(range(250, 2901, 40))
    E = {f: goertzel(sig, f) for f in freqs}
    f1 = max([f for f in freqs if 250 <= f <= 1000], key=lambda f: E[f])
    f2 = max([f for f in freqs if 1000 <= f <= 2900], key=lambda f: E[f])
    e_hi = sum(E[f] for f in freqs if 2100 <= f <= 2700)   # /i/ 的 F2 区
    e_mid = sum(E[f] for f in freqs if 1400 <= f <= 2000)  # /e/ 的 F2 区
    ratio = e_hi / (e_mid + 1e-9)
    return f1, f2, ratio, e_hi, e_mid


if __name__ == "__main__":
    order = [
        ("t_jian", "听日(简体·待判)"), ("t_fan", "聽日(繁体·候选)"),
        ("t_ting", "汀日(ting1锚/i/)"), ("t_ting2", "町日(ting1锚)"),
        ("t_teng", "厅日(teng1反面/e/)"), ("t_tin", "天日(tin1前鼻)"),
        ("t_zhao", "听朝(听+朝)"), ("t_zhaofan", "聽朝(繁体)"),
        ("t_ming", "明日(词替)"), ("t_mingzhao", "明朝(词替)"),
    ]
    print("%-12s %-22s %6s %6s %8s %s" % ("file", "label", "F1", "F2", "hi/mid", "判定"))
    print("-" * 78)
    for name, label in order:
        p = os.path.join(D, name + ".mp3")
        if not os.path.exists(p):
            continue
        r = analyze(p)
        if not r:
            print("%-12s SKIP" % name)
            continue
        f1, f2, ratio, hi, mid = r
        # ratio>1.0 倾向 /i/(ting1)，<1.0 倾向 /e/(teng1)
        verdict = " ting1(/i/)" if ratio > 1.0 else " teng1(/e/)"
        print("%-12s %-22s %6d %6d %8.2f %s" % (name, label, f1, f2, ratio, verdict))
