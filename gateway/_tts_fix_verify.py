# -*- coding: utf-8 -*-
"""生产链路顺序验证：yue_polish.polish() 之后 tts_pron.fix()，再合成 A/B 整句。"""
import subprocess, sys
sys.path.insert(0, "/app")
import tts_pron, yue_polish

V = "zh-HK-HiuMaanNeural"
D = "/audio/pron3/"
demo = "听日我同你去街市，呢个机会真系好合适。听朝落雨就唔去啦，越秀区见。"

p = yue_polish.polish(demo)
f = tts_pron.fix(p)
print("RAW   :", demo)
print("POLISH:", p)
print("FIXED :", f)

# 断言：三处正音全部落地、且繁体没被 polish 打回
checks = {
    "听日->汀日": "汀日" in f and "听日" not in f and "聽日" not in f,
    "听朝->汀朝": "汀朝" in f and "听朝" not in f,
    "会->會": "机會" in f and "机会" not in f and "會" in f,
    "适->適": "合適" in f and "合适" not in f,
    "区->區(保)": "越秀區" in f,
    "无残留": not any(x in f for x in ("听日", "聽日", "听朝", "听晚")),
}
for k, v in checks.items():
    print("  %-14s %s" % (k, "OK" if v else "FAIL"))
assert all(checks.values()), "正音断言未全过"

def syn(text, name):
    subprocess.run(["/usr/local/bin/edge-tts.real", "--voice", V, "--rate=-12%",
                    "--text", text, "--write-media", D + name], capture_output=True)

syn(demo, "z_raw_sentence.mp3")     # 修正前
syn(f, "z_fixed_sentence.mp3")      # 修正后
print("SYNTH: OK (z_raw_sentence / z_fixed_sentence)")
