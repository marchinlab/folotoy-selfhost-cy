# -*- coding: utf-8 -*-
"""诊断：对落盘【清理前】完整稿跑 clean_tts_symbols，找清理后仍残留的 IPA 字符上下文。
在网关容器内跑，读 /data/conversations/<today>.jsonl（落盘=清理前双轨稿）。"""
import json, re, sys, glob
import yue_polish as y

IPA = re.compile("[\u0250-\u02af\u1d00-\u1dff\u02b0-\u02ffˈˌːˑʼɑɒæʌɔɜəɪʊøœɐɯɤɵʃʒŋθðçʝɲɳɽɾʔ]")
files = sorted(glob.glob("/data/conversations/*.jsonl"))
n = 0
for fn in files:
    for line in open(fn, encoding="utf-8"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        a = d.get("a", "") or ""
        if "/" not in a:
            continue
        cleaned = y.clean_tts_symbols(a)
        hits = IPA.findall(cleaned)
        if hits:
            n += 1
            print("--- #%d role=%s 残留=%s" % (n, d.get("role", ""), "".join(sorted(set(hits)))))
            print("  原文:", repr(a[:200]))
            print("  清后:", repr(cleaned[:200]))
print("### 清理后仍含 IPA 的记录数:", n)
