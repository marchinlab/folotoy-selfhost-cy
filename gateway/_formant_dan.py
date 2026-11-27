# -*- coding: utf-8 -*-
"""v1.28 声学确认：「单」第一音节主元音系 /aː/(daan1 正音) 定 /iː/(sin6 =「善」错音)。
/iː/ F2 高(2100~2700, hi 区)、F1 低(<400)；/aː/ F2 低、F1 高(>500)。
用 _formant.py 现成纯标准库 Goertzel 量第一音节 0.05~0.20s 稳态段。"""
import os
from _formant import analyze

D = "/audio/pron_dan"
order = [
    ("a_ci",    "单词·简体单(主人报错)"),
    ("b_sin",   "善词·sin6错音锚"),
    ("c_fan",   "單詞·繁体候选"),
    ("d_dan",   "丹詞·daan1正音锚"),
    ("e_dan6",  "但詞·daan6对照"),
    ("f_jian",  "单位·简体"),
    ("g_sin",   "善位·sin锚"),
    ("h_fan",   "單位·繁体候选"),
    ("i_dan",   "丹位·正音锚"),
    ("j_jian",  "简单·简体"),
    ("k_sin",   "简善·错音锚"),
    ("l_fan",   "簡單·繁体候选"),
    ("m_dan",   "简丹·正音锚"),
    ("n_jian",  "名单·简体"),
    ("o_sin",   "名善·错音锚"),
    ("p_fan",   "名單·繁体候选"),
    ("q_dan",   "名丹·正音锚"),
    ("r_hui_j", "机会·会(wui6控件)"),
    ("s_hui_f", "機會·会正音控件"),
]
print("%-10s %-22s %6s %6s %8s %s" % ("file", "label", "F1", "F2", "hi/mid", "第一音节主元音"))
print("-" * 82)
for name, label in order:
    p = os.path.join(D, name + ".mp3")
    if not os.path.exists(p):
        print("%-10s MISSING" % name); continue
    r = analyze(p)
    if not r:
        print("%-10s SKIP" % name); continue
    f1, f2, ratio, hi, mid = r
    v = "/iː/ sin6(善·错)" if ratio > 1.0 else "/aː/ daan1(正)"
    print("%-10s %-22s %6d %6d %8.2f %s" % (name, label, f1, f2, ratio, v))
