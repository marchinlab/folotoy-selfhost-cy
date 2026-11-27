# -*- coding: utf-8 -*-
"""验 fix 单字方案嘅真实产物：说→說 得「說话」(繁說+简话)、渐→漸 得「漸进」。
对比正音锚「說話/漸進」字节——同音素必同字节；唔同就说明次字简繁喺词内被另待，
需要升级做词级。容器内：python3 _yue44b_mix.py
"""
import subprocess, os

D = "/audio/pron_yue44b"
V = "zh-HK-HiuMaanNeural"
R = "+20%"
CASES = [
    ("sw_fix", "說话"),   # 单字 fix 真实产物：说→說、话保留简
    ("sw_f", "說話"),     # 全繁正音锚
    ("sw_j", "说话"),     # 现状(主人报)
    ("sw_a1", "雪話"),    # syut3 waa6 正音锚
    ("jj_fix", "漸进"),   # 单字 fix 产物
    ("jj_f", "漸進"),     # 全繁
    ("jj_j", "渐渐"),     # 现状
]


def main():
    for tag, text in CASES:
        p = "%s/%s.mp3" % (D, tag)
        subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", p], capture_output=True)
        if os.path.exists(p):
            print("%-8s %-6s %d bytes" % (tag, text, os.path.getsize(p)))
        else:
            print("%-8s %-6s ERR" % (tag, text))
    print("=== DONE_MIX ===")


if __name__ == "__main__":
    main()
