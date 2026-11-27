# -*- coding: utf-8 -*-
"""v1.30 单字声学判据：F1/F2 共振峰(判元音) + F0 基频轮廓(判声调)，纯标准库。
无 ASR 环境下判「edge-tts 到底把某个字念成了什么音」：
  · 元音：Goertzel 扫 F1(250-1000)/F2(1000-2900) 峰值，二维距离比大小。
  · 声调：自相关逐帧估 F0，取稳定段中位数 + 线性斜率（阳去低平 vs 阳平低升）。
  · 判据：目标写法与【正音锚】的 (元音+声调) 距离 < 与【反锚】的距离 -> 念对。
用法：python3 _yue_sound.py calib | all
  calib = 只跑「净」字组（已知 净错/淨对），校准分析器是否可信。
  all   = 跑 9 词全部嫌疑字。
"""
import subprocess, os, struct, math, sys, hashlib

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue30_sound"
FS = 16000
os.makedirs(D, exist_ok=True)

# 字组：(label, 文本, 拼音标注, 角色)  role: target简 / target繁 / anchor正音锚 / bad反锚
GROUPS = {
    "净": [("jing_j", "净", "zing6? 简体待判", "target_j"),
           ("jing_f", "淨", "zing6 繁体候选", "target_f"),
           ("jing_a", "靜", "zing6 正音锚", "anchor"),
           ("jing_b", "爭", "zang1 反锚(/a/)", "bad")],
    "量": [("liang_j", "量", "loeng6? 待判", "target_j"),
           ("liang_a", "亮", "loeng6 正音锚(阳去低平)", "anchor"),
           ("liang_b", "涼", "loeng4 反锚(阳平低升)", "bad")],
    "齐": [("cai_j", "齐", "cai4? 待判", "target_j"),
           ("cai_f", "齊", "cai4 繁体候选", "target_f"),
           ("cai_a", "臍", "cai4 正音锚", "anchor"),
           ("cai_b", "齋", "zaai1 反锚", "bad")],
    "陈": [("can_j", "陈", "can4? 待判", "target_j"),
           ("can_f", "陳", "can4 繁体候选", "target_f"),
           ("can_a", "塵", "can4 正音锚", "anchor")],
    "桥": [("kiu_j", "桥", "kiu4? 待判", "target_j"),
           ("kiu_f", "橋", "kiu4 繁体候选", "target_f"),
           ("kiu_a", "喬", "kiu4 正音锚", "anchor")],
    "组": [("zou_j", "组", "zou2? 待判", "target_j"),
           ("zou_f", "組", "zou2 繁体候选", "target_f"),
           ("zou_a", "祖", "zou2 正音锚", "anchor")],
    "队": [("deoi_j", "队", "deoi6? 待判", "target_j"),
           ("deoi_f", "隊", "deoi6 繁体候选", "target_f"),
           ("deoi_a", "兌", "deoi6 正音锚", "anchor")],
    "发": [("faat_j", "发", "faat3? 待判", "target_j"),
           ("faat_f", "發", "faat3 繁体候选", "target_f"),
           ("faat_a", "法", "faat3 正音锚", "anchor")],
    "达": [("daat_j", "达", "daat6? 待判", "target_j"),
           ("daat_f", "達", "daat6 繁体候选", "target_f"),
           ("daat_a", "踏", "daap6 近音反锚", "bad")],
    "药": [("joek_j", "药", "joek6? 待判", "target_j"),
           ("joek_f", "藥", "joek6 繁体候选", "target_f"),
           ("joek_a", "若", "joek6 正音锚", "anchor")],
    "过": [("gwo_j", "过", "gwo3? 待判", "target_j"),
           ("gwo_f", "過", "gwo3 繁体候选", "target_f"),
           ("gwo_a", "果", "gwo2 近音反锚", "bad")],
    "程": [("cing_j", "程", "cing4? 待判(无简繁)", "target_j"),
           ("cing_a", "情", "cing4 正音锚", "anchor"),
           ("cing_b", "清", "cing1 反锚(阴平高平)", "bad")],
    "文": [("man_j", "文", "man4? 待判(无简繁)", "target_j"),
           ("man_a", "聞", "man4 正音锚", "anchor")],
    "风": [("fung_j", "风", "fung1? 待判", "target_j"),
           ("fung_f", "風", "fung1 繁体候选", "target_f"),
           ("fung_a", "封", "fung1 正音锚", "anchor")],
}

ALL = ["净", "量", "齐", "陈", "桥", "组", "队", "发", "达", "药", "过", "程", "文", "风"]


def gen(tag, text):
    p = "%s/%s.mp3" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", p], capture_output=True)
    if r.returncode or not os.path.exists(p):
        print("  GEN_ERR %s %s %s" % (tag, text, r.stderr.decode("utf-8", "ignore")[:100]))
        return None
    return p


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


def f0_autocorr(seg):
    """单帧自相关估 F0；返回 Hz 或 None。"""
    N = len(seg)
    mean = sum(seg) / N
    x = [seg[i] - mean for i in range(N)]
    e0 = sum(v * v for v in x)
    if e0 < 1e6:
        return None
    lo = int(FS / 320.0)   # 320Hz
    hi = int(FS / 70.0)    # 70Hz
    best, bestlag = 0.0, 0
    for lag in range(lo, hi + 1):
        s = sum(x[i] * x[i + lag] for i in range(N - lag))
        norm = s / (e0 + 1e-9)
        if norm > best:
            best, bestlag = norm, lag
    if best < 0.35:
        return None
    return FS / float(bestlag)


def analyze(path):
    s = pcm(path)
    if len(s) < FS * 0.25:
        return None
    # 稳定段：0.06~0.30s（避起音爆发/收尾），且不超过 60% 总长
    a = int(0.06 * FS)
    b = min(int(0.30 * FS), int(len(s) * 0.62))
    if b - a < int(0.10 * FS):
        a, b = int(0.04 * FS), int(len(s) * 0.55)
    seg = s[a:b]
    N = len(seg)
    win = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (N - 1)) for i in range(N)]
    sig = [seg[i] * win[i] for i in range(N)]
    # 共振峰
    freqs = list(range(250, 2901, 40))
    E = {f: goertzel(sig, f) for f in freqs}
    f1 = max([f for f in freqs if 250 <= f <= 1050], key=lambda f: E[f])
    f2 = max([f for f in freqs if 1050 <= f <= 2900], key=lambda f: E[f])
    # F0 轮廓：帧长 512 hop 160，稳定段内
    f0s = []
    for st in range(0, max(1, N - 512), 160):
        fr = seg[st:st + 512]
        if len(fr) < 512:
            break
        v = f0_autocorr(fr)
        if v and 70 <= v <= 320:
            f0s.append((st, v))
    f0med = slope = None
    if len(f0s) >= 3:
        vals = [v for _, v in f0s]
        vals_sorted = sorted(vals)
        f0med = vals_sorted[len(vals_sorted) // 2]
        # 首尾各取 1/3 求均，斜率=后-前（升调>0）
        m = len(f0s)
        pre = sum(vals[:max(1, m // 3)]) / max(1, m // 3)
        post = sum(vals[-(max(1, m // 3)):]) / max(1, m // 3)
        slope = post - pre
    return f1, f2, f0med, slope, len(s) / float(FS)


def dist(a, b):
    """(f1,f2,f0,slope) 归一化距离；None 维度跳过。"""
    if a[0] is None or b[0] is None:
        return 999.0
    d = abs(a[0] - b[0]) / 260.0 + abs(a[1] - b[1]) / 480.0  # 元音
    if a[2] is not None and b[2] is not None:
        d += abs(a[2] - b[2]) / 38.0                        # 平均基频
    if a[3] is not None and b[3] is not None:
        d += abs(a[3] - b[3]) / 16.0                        # 声调斜率
    return d


def run(mode):
    keys = ["净"] if mode == "calib" else ALL
    store = {}
    print("\n%-10s %-4s %-24s %5s %5s %7s %7s %6s" %
          ("tag", "字", "标注", "F1", "F2", "F0 med", "F0 slope", "dur"))
    print("-" * 88)
    for key in keys:
        for tag, text, note, role in GROUPS[key]:
            p = gen(tag, text)
            if not p:
                continue
            r = analyze(p)
            if not r:
                print("  %-10s ANALYZE_SKIP" % tag)
                continue
            store[tag] = (r, note, role, text)
            print("%-10s %-4s %-24s %5d %5d %7s %7s %6.3f" %
                  (tag, text, note[:24], r[0], r[1],
                   ("%d" % r[2]) if r[2] else "n/a",
                   ("%+.1f" % r[3]) if r[3] is not None else "n/a", r[4]))
        # 判定
        anchor = [t for t, _, _, role in GROUPS[key] if role == "anchor"]
        bad = [t for t, _, _, role in GROUPS[key] if role == "bad"]
        targ = [t for t, _, _, role in GROUPS[key] if role.startswith("target")]
        if anchor and anchor[0] in store:
            A = store[anchor[0]][0]
            B = store[bad[0]][0] if bad and bad[0] in store else None
            print("  >>> 判据 [%s] 锚=%s" % (key, store[anchor[0]][1]))
            for t in targ:
                if t not in store:
                    continue
                T = store[t][0]
                da = dist(T, A)
                db = dist(T, B) if B else None
                verdict = ("≈正音" if (db is None or da < db) else "≠正音(偏反锚)")
                print("      %-10s d(锚)=%.2f  d(反锚)=%s  %s" %
                      (t, da, ("%.2f" % db) if db else "-", verdict))
        print()
    print("=== DONE (%s) ===" % mode)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "calib")
