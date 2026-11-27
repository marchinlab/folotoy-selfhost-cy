# -*- coding: utf-8 -*-
"""精确诊断：打印清理后每个残留 IPA 字符的前后上下文，同原文字段对照，定位跨行块模式。"""
import json, re, glob
import yue_polish as y

IPA = re.compile("[\u0250-\u02af\u1d00-\u1dff\u02b0-\u02ffˈˌːˑʼɑɒæʌɔɜəɪʊøœɐɯɤɵʃʒŋθðçʝɲɳɽɾʔ]")
for fn in sorted(glob.glob("/data/conversations/*.jsonl")):
    for line in open(fn, encoding="utf-8"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        a = d.get("a", "") or ""
        if "/" not in a:
            continue
        cleaned = y.clean_tts_symbols(a)
        if not IPA.search(cleaned):
            continue
        print("=== role=%s ===" % d.get("role", ""))
        print("【原文含 / 的行】:")
        for i, l in enumerate(a.split("\n")):
            if "/" in l:
                print("   L%d: %r" % (i, l))
        print("【清后残留 IPA 上下文】:")
        for m in IPA.finditer(cleaned):
            s = max(0, m.start() - 25); e = min(len(cleaned), m.end() + 25)
            print("   %r ...%r... " % (m.group(), cleaned[s:e]))
        print()
