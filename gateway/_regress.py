# -*- coding: utf-8 -*-
"""yue_polish 小数点/时间点误伤回归 + 整篇稿零残留复校。"""
import sys
sys.path.insert(0, "/app")
import yue_polish as y

cases = [
    ("广州录得二十一度四", "广州录得二十一度四"),   # 本次稿写法，保持不变
    ("广州录得二十一点四度", "广州录得二十一点四度"),  # 小数点不被改
    ("二十五点三公里", "二十五点三公里"),
    ("十一点钟", "十一点钟"),       # 时间点
    ("一点钟", "一点钟"),
    ("一点半", "一点半"),
    ("一点多", "一点多"),
    ("第一点要讲清楚", "第一点要讲清楚"),   # 序数
    ("有一点累", "有一啲累"),       # 真·程度副词，应转（「有一啲」是固定地道搭配）
    ("快一点", "快一啲"),
    ("慢一点都得", "慢一啲都得"),
]
fail = 0
for src, want in cases:
    got = y.polish(src)
    ok = (got == want)
    if not ok:
        fail += 1
    print(("OK  " if ok else "FAIL"), repr(src), "->", repr(got), "| want", repr(want))

# 整篇稿必须仍零残留
t = open("/app/_aqing_script.txt", encoding="utf-8").read().strip()
c, h = y.polish(t, report=True)
print("SCRIPT_CHANGED", c != t, "HITS", h)
print("REGRESS_FAIL", fail)
