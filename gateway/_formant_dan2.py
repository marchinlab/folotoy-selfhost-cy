# -*- coding: utf-8 -*-
"""v1.28 单字/词首硬验证：/aː/(daan1正, F2低~1970) vs /iː/(sin6=善错, F2高~2050+)。
同一 _formant Goertzel，取第一音节 0.05~0.20s。看相对：单 应贴 善，單 应贴 丹。"""
import os
from _formant import analyze

D = "/audio/pron_dan2"
order = [
    ("z_dan_jian",   "单(简体·待判)"),
    ("z_shan",       "善(sin6错音锚)"),
    ("z_dan_fan",    "單(繁体·候选)"),
    ("z_dan_anchor", "丹(daan1正音锚)"),
    ("z_dan6",       "但(daan6对照)"),
    ("w_danci_j",    "单词(简体)"),
    ("w_shanci",     "善词(错音锚)"),
    ("w_danci_f",    "單詞(繁体候选)"),
    ("w_danci_alt",  "丹词(正音锚)"),
]
print("%-14s %-18s %6s %6s %8s %s" % ("file", "label", "F1", "F2", "hi/mid", "判读(相对锚)"))
print("-" * 78)
rows = {}
for name, label in order:
    p = os.path.join(D, name + ".mp3")
    if not os.path.exists(p):
        print("%-14s MISSING" % name); continue
    r = analyze(p)
    if not r:
        print("%-14s SKIP" % name); continue
    f1, f2, ratio, hi, mid = r
    rows[name] = (f1, f2, ratio)
    print("%-14s %-18s %6d %6d %8.2f" % (name, label, f1, f2, ratio))

def dist(a, b):
    if a not in rows or b not in rows: return None
    return abs(rows[a][0] - rows[b][0]) + abs(rows[a][1] - rows[b][1])

print("-" * 78)
for x, sin, daan in [("z_dan_jian","z_shan","z_dan_anchor"), ("w_danci_j","w_shanci","w_danci_f")]:
    ds, dd = dist(x, sin), dist(x, daan)
    if ds is None or dd is None: continue
    near = "善(sin6·错)" if ds < dd else "丹/單(daan·正)"
    print("%-12s -> 距善=%d  距正音锚=%d  => 更贴 %s" % (x, ds, dd, near))
