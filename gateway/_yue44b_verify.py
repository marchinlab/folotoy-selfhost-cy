# -*- coding: utf-8 -*-
"""v1.44b 精确判调（纯离线、用 SRT 字幕整词时间取首字窗，修正物理 onset 切歪）：
钉死「称帝/称王」换 cing1 同音锚(清/青/卿)后词内首字系咪稳念第一声(高平约300Hz)。

判据：ching1(阴平) 高平 ~300Hz、slope 小；cing3(阴上) 中低 ~240-270。
已知单字锚：称302 / 清302 / 秤246。
容器内：python3 _yue44b_verify.py
"""
import subprocess, os, struct, math, re

FS = 16000
D = "/audio/pron_yue44b"


def pcm(path):
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-ac", "1", "-ar", str(FS),
                          "-f", "s16le", "-"], capture_output=True).stdout
    n = len(raw) // 2
    return list(struct.unpack("<%dh" % n, raw[: n * 2]))


def srt_span(tag):
    p = "%s/%s.srt" % (D, tag)
    if not os.path.exists(p):
        return None
    txt = open(p, encoding="utf-8-sig").read().replace("\r", "")
    m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", txt)
    if not m:
        return None
    g = [int(x) for x in m.groups()]
    s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
    e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
    return s, e


def f0_curve(seg, hop=64, win=384):
    out = []
    for st in range(0, len(seg) - win, hop):
        fr = seg[st:st + win]
        mean = sum(fr) / win
        x = [v - mean for v in fr]
        e0 = sum(v * v for v in x)
        if e0 < 2e5:
            out.append(None)
            continue
        lo, hi = int(FS / 320), int(FS / 70)
        best, bestlag = 0.0, 0
        for lag in range(lo, hi + 1):
            sc = sum(x[i] * x[i + lag] for i in range(win - lag)) / (e0 + 1e-9)
            if sc > best:
                best, bestlag = sc, lag
        if best >= 0.32:
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


# (tag, 文本, 是否双字词)
CASES = [
    ("cd_j", "称帝", 2), ("cd_f", "稱帝", 2),
    ("cd_qing", "清帝", 2), ("cd_qing2", "青帝", 2),
    ("cd_qing3", "卿帝", 2), ("cd_cheng", "秤帝", 2),
    ("cw_j", "称王", 2), ("cw_f", "稱王", 2),
    ("cw_qing", "清王", 2), ("cw_qing2", "青王", 2),
    ("cw_qing3", "卿王", 2), ("cw_cheng", "秤王", 2),
]


def first_syl(tag, text, is_word):
    mp3 = "%s/%s.mp3" % (D, tag)
    if not os.path.exists(mp3):
        return None
    s = pcm(mp3)
    sp = srt_span(tag)
    if sp:
        st, en = sp
        a = int(st * FS) + int(0.012 * FS)
        # 双字词首字取前 42% 时长；单字取全字（留 12ms 头尾）
        b = int((st + (en - st) * 0.42) * FS) if is_word == 2 else int(en * FS) - int(0.012 * FS)
    else:
        a, b = int(0.02 * FS), int(0.24 * FS)
    seg = s[a:max(a + 200, b)]
    return summ(f0_curve(seg))


def main():
    print("=" * 84)
    print("称帝/称王 首字精确判调（SRT 整词前 42% 窗）：ching1 高平≈300 / cing3 中低≈240-270")
    print("  单字已知锚：称302 清302 秤246")
    print("-" * 84)
    print("%-10s %-8s %8s %8s %7s  %s" % ("tag", "text", "F0med", "slope", "frames", "判定"))
    for tag, text, w in CASES:
        r = first_syl(tag, text, w)
        if not r:
            print("%-10s %-8s MISSING" % (tag, text))
            continue
        med, slope, n = r
        if med is None:
            print("%-10s %-8s  n/a" % (tag, text))
            continue
        if med >= 288:
            verdict = "高平 → cing1 第一声"
        elif med >= 255:
            verdict = "中平/升 → 疑似 cing3"
        else:
            verdict = "低 → 非第一声"
        print("%-10s %-8s %8d %+8d %7d  %s" % (tag, text, med, slope, n, verdict))
    print("\n=== DONE_VERIFY_44b ===")


if __name__ == "__main__":
    main()
