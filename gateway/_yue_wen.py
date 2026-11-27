# -*- coding: utf-8 -*-
"""v1.30 深挖「文」+「文风」+ 验证 polish 打回问题 + 全部候选的真实管线落地。
A) 「文」单字锚对照：文 vs 聞/聞/文(繁同) vs 雲(wan4) vs 門(mun4) —— 定位「文」念成啥
B) 「文风/文風/聞風/文風(换字)」整词对照
C) polish 繁转简表对全部候选字的影响：哪些繁体会被打回、fix 必须防
D) 最终候选 FIXES 逐一在 polish+fix 后能否保住
"""
import subprocess, os, struct, math, sys

sys.path.insert(0, "/app")
import yue_polish, tts_pron

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue30_wen"
FS = 16000
os.makedirs(D, exist_ok=True)


def gen(tag, text):
    p = "%s/%s.mp3" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", p], capture_output=True)
    return p if (not r.returncode and os.path.exists(p)) else None


def feat(p):
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", p, "-ac", "1", "-ar", str(FS),
                          "-f", "s16le", "-"], capture_output=True).stdout
    n = len(raw) // 2
    s = list(struct.unpack("<%dh" % n, raw[: n * 2]))
    a, b = int(0.06 * FS), min(int(0.34 * FS), int(len(s) * 0.62))
    seg = s[a:b]
    N = len(seg)
    if N < FS * 0.05:
        return None
    win = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (N - 1)) for i in range(N)]
    sig = [seg[i] * win[i] for i in range(N)]

    def gz(freq):
        k = 2.0 * math.cos(2.0 * math.pi * freq / FS)
        s1 = s2 = 0.0
        for x in sig:
            s0 = x + k * s1 - s2
            s2, s1 = s1, s0
        return s1 * s1 + s2 * s2 - k * s1 * s2
    fr = list(range(250, 2901, 40))
    E = {f: gz(f) for f in fr}
    f1 = max([f for f in fr if 250 <= f <= 1100], key=lambda f: E[f])
    f2 = max([f for f in fr if 1050 <= f <= 2900], key=lambda f: E[f])
    # F0
    f0s = []
    for st in range(0, max(1, N - 384), 128):
        x = [seg[st + i] - sum(seg[st:st + 384]) / 384 for i in range(384)] if st + 384 <= N else []
        if len(x) < 384:
            break
        e0 = sum(v * v for v in x)
        if e0 < 4e5:
            continue
        best, bl = 0.0, 0
        for lag in range(int(FS / 320), int(FS / 70) + 1):
            sc = sum(x[i] * x[i + lag] for i in range(384 - lag)) / (e0 + 1e-9)
            if sc > best:
                best, bl = sc, lag
        if best >= 0.36:
            v = FS / float(bl)
            if 70 <= v <= 320:
                f0s.append(v)
    med = slope = None
    if f0s:
        sv = sorted(f0s)
        med = sv[len(sv) // 2]
        k = max(1, len(f0s) // 3)
        slope = sum(f0s[-k:]) / k - sum(f0s[:k]) / k
    return f1, f2, med, slope


def row(tag, text):
    p = gen(tag, text)
    if not p:
        print("  %-10s ERR" % tag)
        return
    f = feat(p)
    if not f:
        print("  %-10s SKIP" % tag)
        return
    print("  %-10s %-4s F1=%-5d F2=%-5d F0=%-4s slope=%s" %
          (tag, text, f[0], f[1], f[2] or "n/a", ("%+.0f" % f[3]) if f[3] is not None else "n/a"))


print("\n=== A) 「文」单字锚（定位文念成啥；文/聞=man4，雲=wan4，門=mun4）===")
for t, x in [("wen_j", "文"), ("wen_a", "聞"), ("wen_wan", "雲"), ("wen_mun", "門"), ("wen_man", "慢")]:
    row(t, x)
print("\n=== B) 「文风」整词（简/繁/闻风/换「雯」）===")
for t, x in [("wf_j", "文风"), ("wf_f", "文風"), ("wf_a", "聞風"), ("wf_h", "雯風")]:
    row(t, x)

print("\n=== C) polish 繁转简表对候选繁体的影响（原样 polish，不 fix）===")
for w in ["淨力", "陳橋", "發達", "質量", "一齊", "組隊", "火藥", "過程",
          "文風", "聞風", "雯風", "單詞", "機會", "適合", "地區"]:
    print("    %-6s --polish--> %s" % (w, yue_polish.polish(w)))

print("\n=== D) 候选 FIXES 经 polish+fix 后能否保住（模拟 fix 已加）===")
# 临时构造 fix 逻辑（不落盘，仅模拟）
SIM = [("质量", "質量"), ("一齐", "一齊"), ("净", "淨"), ("陈", "陳"),
       ("药", "藥"), ("风", "風"), ("组", "組"), ("队", "隊"),
       ("发达", "發達"), ("文风", "聞風")]
def simfix(t):
    for a, b in SIM:
        t = t.replace(a, b)
    return t
for w in ["净力", "陈桥", "发达", "质量", "一齐", "组队", "火药", "过程", "文风",
          "头发", "发现", "文风鼎盛", "质量成反比"]:
    after_polish = yue_polish.polish(w)
    print("    %-10s polish=%-10s simfix=%s" % (w, after_polish, simfix(after_polish)))
print("\n=== DONE ===")
