# -*- coding: utf-8 -*-
"""只做粤语化兜底检查，不合成不下发。"""
import sys, difflib
sys.path.insert(0, "/app")
import yue_polish

t = open("/app/_aqing_script.txt", encoding="utf-8").read().strip()
c, h = yue_polish.polish(t, report=True)
print("LEN_RAW", len(t))
print("LEN_CLEAN", len(c))
print("CHANGED", c != t)
print("HITS", repr(h))
if c != t:
    print("=== DIFF (原 -> 后处理) ===")
    for line in difflib.unified_diff(t.split("\n"), c.split("\n"), lineterm=""):
        print(line)
