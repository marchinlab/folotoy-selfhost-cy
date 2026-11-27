# -*- coding: utf-8 -*-
"""v1.30 验证：候选替换在【真实播报管线 polish+fix】后是否落地 + 声调换字方案 + 一对多安全。
1) 落盘真实原句 -> polish(繁转简会打回) -> 看候选繁体是否被 fix 保住。
2) 「量」声调修正：比较 质量/質量/質亮/質諒/質量(换词) 的 F0 slope，选最接近 亮(loeng6) 的写法。
3) 一对多安全：头发(髮) 不能被 发→發 误伤；组词「发现/发生」不受影响。
"""
import subprocess, os, struct, math, sys, json, glob

sys.path.insert(0, "/app")
import yue_polish, tts_pron

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue30_fix"
FS = 16000
os.makedirs(D, exist_ok=True)


def gen(tag, text, sub=False):
    p = "%s/%s.mp3" % (D, tag)
    args = ["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
            "--text", text, "--write-media", p]
    if sub:
        args += ["--write-subtitles", "%s/%s.srt" % (D, tag)]
    r = subprocess.run(args, capture_output=True)
    if r.returncode or not os.path.exists(p):
        print("  GEN_ERR %s %s %s" % (tag, text, r.stderr.decode("utf-8", "ignore")[:100]))
        return None
    return p


def dur_of(p):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", p], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return -1


def f0_slope(path):
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-ac", "1", "-ar", str(FS),
                          "-f", "s16le", "-"], capture_output=True).stdout
    n = len(raw) // 2
    s = list(struct.unpack("<%dh" % n, raw[: n * 2]))
    a, b = int(0.06 * FS), min(int(0.30 * FS), int(len(s) * 0.62))
    seg = s[a:b]
    f0s = []
    for st in range(0, max(1, len(seg) - 512), 160):
        fr = seg[st:st + 512]
        if len(fr) < 512:
            break
        mean = sum(fr) / 512
        x = [fr[i] - mean for i in range(512)]
        e0 = sum(v * v for v in x)
        if e0 < 1e6:
            continue
        lo, hi = int(FS / 320.0), int(FS / 70.0)
        best, bestlag = 0.0, 0
        for lag in range(lo, hi + 1):
            sc = sum(x[i] * x[i + lag] for i in range(512 - lag)) / (e0 + 1e-9)
            if sc > best:
                best, bestlag = sc, lag
        if best >= 0.35:
            v = FS / float(bestlag)
            if 70 <= v <= 320:
                f0s.append(v)
    if len(f0s) < 3:
        return None
    m = len(f0s)
    pre = sum(f0s[:max(1, m // 3)]) / max(1, m // 3)
    post = sum(f0s[-(max(1, m // 3)):]) / max(1, m // 3)
    return post - pre


# ===== 1) 真实播报管线：候选繁体能否被 fix 保住 =====
print("\n===== 1) 真实落盘原句 -> polish -> fix 播报字形 =====")
CANDS = ["净", "淨", "陈桥", "陳橋", "发", "發", "髮", "药", "藥",
         "组队", "組隊", "发达", "發達", "火药", "火藥", "过程", "過程",
         "文风", "文風", "质量", "質量", "一齐", "一齊"]
# 直接测：模型输出这些写法 -> 管线后剩什么
for w in CANDS:
    bc = tts_pron.fix(yue_polish.polish(w))
    print("    %-6s -> %s" % (w, bc))

# ===== 2) 「量」声调换字方案 =====
print("\n===== 2) 「质量」声调修正候选（F0 slope 越接近 亮锚 -17 越好）=====")
for tag, txt in [("m_j", "质量"), ("m_f", "質量"),
                 ("m_liang", "質亮"), ("m_liang2", "質諒"),
                 ("m_anchor", "質" + "亮")]:
    p = gen(tag, txt)
    if p:
        print("    %-10s %-6s dur=%.3f  F0slope=%s" %
              (tag, txt, dur_of(p), ("%+.1f" % f0_slope(p)) if f0_slope(p) is not None else "n/a"))

# ===== 3) 一对多安全：「发」在 头发/发现/发生/发达 =====
print("\n===== 3) 一对多安全（发→發 只放行词级「发达」，唔伤「头发」）=====")
for word in ["头发", "发现", "发生", "发言", "发达"]:
    print("    %-6s -> %s" % (word, tts_pron.fix(yue_polish.polish(word))))
print("\n=== DONE ===")
