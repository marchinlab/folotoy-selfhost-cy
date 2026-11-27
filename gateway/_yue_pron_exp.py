# -*- coding: utf-8 -*-
"""v1.30 正音实验：9 个词「净力/质量/一齐/陈桥/组队/发达/火药/过程/文风」错在哪、怎么念才对。
沿用 v1.28「同音字字节数碰撞 + 时长」声学方法（无 ASR 环境下的硬判据）：
  · 同 voice/rate 下，若两串文本发音【音素序列完全相同】，edge-tts 输出 mp3 字节数完全相同。
  · 故：目标词 == 正音锚 字节数 -> 目标词念的是正音；目标词 != 锚而 繁体 == 锚 -> 简错繁对。
  · 时长(ffprobe) 辅助：字节数正比时长，差异>~2% 视为异音。
阶段0：读落盘真实 a 字段 -> polish+fix -> 打印 9 词实际【播报字形】（确认繁被打回简）。
阶段1：9 词 简体 vs 繁体 对照。
阶段2：繁简同形/易歧字 补正音锚（净/量/齐/陈/组/发/药/程/风）。
"""
import subprocess, os, hashlib, sys, json, glob

sys.path.insert(0, "/app")
import yue_polish, tts_pron

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue30"
os.makedirs(D, exist_ok=True)
WORDS = ["净力", "淨力", "质量", "一齐", "陈桥", "组队", "发达", "火药", "过程", "文风"]


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", p], capture_output=True, text=True)
    try:
        return "%.3f" % float(r.stdout.strip())
    except Exception:
        return "ERR"


def synth(tag, text):
    p = "%s/%s.mp3" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", p], capture_output=True)
    if r.returncode or not os.path.exists(p):
        print("  %-14s ERR  %s" % (tag, r.stderr.decode("utf-8", "ignore")[:140]))
        return None
    sz = os.path.getsize(p)
    md = hashlib.md5(open(p, "rb").read()).hexdigest()[:10]
    print("  %-14s sz=%-7d md5=%-10s dur=%-6s | %s" % (tag, sz, md, dur(p), text))
    return (sz, md, dur(p))


def to_broadcast(raw):
    r = yue_polish.polish(raw)
    if isinstance(r, tuple):
        r = r[0]
    return tts_pron.fix(r)


# ===== 阶段0：真实播报字形 =====
print("\n===== 阶段0  落盘真实 a 字段 -> polish+fix 后的播报字形 =====")
n = 0
_logs = sorted(set(glob.glob("/data/conversations/*.jsonl*") +
                   glob.glob("/opt/folotoy/conversations/*.jsonl*")))
for fn in _logs:
    for line in open(fn, encoding="utf-8"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        a = d.get("a", "") or ""
        if not any(w in a or (w[0] in a) for w in ["净", "淨", "质量", "一齐", "陈桥", "组队", "发达", "火药", "过程", "文风"]):
            continue
        bc = to_broadcast(a)
        print("\n [%s] role=%s" % (fn.split("/")[-1], d.get("role", "")))
        print("   原文片段:", " / ".join(w for w in WORDS if w in a) or "(仅繁体形态)")
        print("   播报命中:", " / ".join(w for w in WORDS if w in bc))
        n += 1
        if n >= 6:
            break
    if n >= 6:
        break

# ===== 阶段1：9 词 简体 vs 繁体 =====
print("\n===== 阶段1  9 词 简体 vs 繁体（sz/md5/dur）=====")
pairs = [("净力", "淨力"), ("质量", "質量"), ("一齐", "一齊"), ("陈桥", "陳橋"),
         ("组队", "組隊"), ("发达", "發達"), ("火药", "火藥"), ("过程", "過程"), ("文风", "文風")]
res1 = {}
for i, (j, f) in enumerate(pairs):
    print(" [%d] %s  /  %s" % (i, j, f))
    res1[j] = (synth("p%d_jian" % i, j), synth("p%d_fan" % i, f))

# ===== 阶段2：繁简同形/易歧字 补正音锚 =====
# 每个锚 = 用【铁定念粤语正音】的同音字替换嫌疑字，作为「正音」参照。
print("\n===== 阶段2  正音锚（嫌疑字换成铁定粤语正音字）=====")
anchors = [
    ("净力", "靜力", "zing6 lik6，靜=净/淨正音锚"),
    ("质量", "質亮", "zat1 loeng6，亮=量(loeng6)正音锚，排「量」多音"),
    ("一齐", "一齊", "jat1 cai4，繁体齊=cai4"),
    ("陈桥", "塵橋", "can4 kiu4，塵=陈(can4)锚"),
    ("组队", "祖隊", "zou2 deoi6，祖=组(zou2)锚、隊=队繁"),
    ("发达", "法達", "faat3 daat6，法=发(faat3)锚、達=达繁"),
    ("火药", "火若", "fo2 joek6，若=药(joek6)锚"),
    ("过程", "過情", "gwo3 cing4，情=程(cing4)锚、過=过繁"),
    ("文风", "聞風", "man4 fung1，聞=文(man4)锚、風=风繁"),
]
res2 = {}
for i, (orig, anchor, note) in enumerate(anchors):
    print(" [%d] %s  ->锚  %s   (%s)" % (i, orig, anchor, note))
    res2[orig] = synth("a%d_anchor" % i, anchor)

# ===== 汇总对照 =====
print("\n===== 汇总：目标(sz) vs 繁(sz) vs 锚(sz) =====")
for i, (j, f) in enumerate(pairs):
    jr, fr = res1[j]
    ar = res2[j]
    js = jr[0] if jr else "ERR"
    fs = fr[0] if fr else "ERR"
    assz = ar[0] if ar else "ERR"
    verdict = []
    if jr and ar:
        verdict.append("简=锚" if abs(jr[0] - ar[0]) <= 2 else "简≠锚")
    if fr and ar:
        verdict.append("繁=锚" if abs(fr[0] - ar[0]) <= 2 else "繁≠锚")
    if jr and fr:
        verdict.append("简=繁" if abs(jr[0] - fr[0]) <= 2 else "简≠繁")
    print("  %-4s 简=%-6s 繁=%-6s 锚=%-6s  %s" % (j, js, fs, assz, " ".join(verdict)))
print("\n===== DONE =====")
