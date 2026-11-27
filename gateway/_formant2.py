# -*- coding: utf-8 -*-
"""验证集共振峰：汀字全局替代(F1应低~250=/i/ting1) vs 听原字(F1高~370=/e/teng1)"""
import subprocess, struct, math, os
from _formant import analyze

D = "/audio/pron3"
order = [
    ("v_tingri", "汀日"), ("v_hao", "好汀"), ("v_ge", "汀歌"),
    ("v_jian", "汀见"), ("v_hua", "汀话"), ("v_chao", "汀朝"),
    ("v_tingyuan", "听日(原字对照)"), ("v_haoting", "好听(原字对照)"),
    ("t_teng", "厅日(teng反面锚)"), ("t_ting", "汀日(首轮锚)"),
]
print("%-13s %-18s %6s %6s %8s %s" % ("file", "label", "F1", "F2", "hi/mid", "主元音判读"))
print("-" * 76)
for name, label in order:
    p = os.path.join(D, name + ".mp3")
    if not os.path.exists(p):
        print("%-13s MISSING" % name); continue
    r = analyze(p)
    if not r:
        print("%-13s SKIP" % name); continue
    f1, f2, ratio, hi, mid = r
    vowel = "/i/(ting1正音)" if f1 < 320 else "/e/(teng1厅音)"
    print("%-13s %-18s %6d %6d %8.2f %s" % (name, label, f1, f2, ratio, vowel))
