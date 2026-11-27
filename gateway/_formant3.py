# -*- coding: utf-8 -*-
"""末次声学确认：听朝/听晚 vs 厅(错)/汀(正) 的第一音节主元音 F1。"""
import os
from _formant import analyze

D = "/audio/pron3"
order = [
    ("x_tingchao", "听朝"), ("x_tingchao_hall", "厅朝(错参照)"), ("x_tingchao_tin", "汀朝(正音)"),
    ("x_tingwan", "听晚"), ("x_tingwan_hall", "厅晚(错参照)"), ("x_tingwan_tin", "汀晚(正音)"),
    ("t_jian", "听日(主人报)"), ("t_ting", "汀日(正音)"), ("t_teng", "厅日(错参照)"),
]
print("%-16s %-16s %6s %6s %s" % ("file", "label", "F1", "F2", "主元音"))
print("-" * 66)
for name, label in order:
    p = os.path.join(D, name + ".mp3")
    if not os.path.exists(p):
        print("%-16s MISSING" % name); continue
    r = analyze(p)
    if not r:
        print("%-16s SKIP" % name); continue
    f1, f2, ratio, hi, mid = r
    v = "/i/ ting1(正)" if f1 < 320 else "/e/ teng1(厅音)"
    print("%-16s %-16s %6d %6d %s" % (name, label, f1, f2, v))
