# -*- coding: utf-8 -*-
"""扫描生产落盘 jsonl 里 '/' 的真实上下文，判断斜杠用途分布。"""
import json, re, sys

p = sys.argv[1] if len(sys.argv) > 1 else "/opt/folotoy/conversations/2026-11-11.jsonl.bak-pre-1.28-clean"
n = 0
for i, line in enumerate(open(p, encoding="utf-8")):
    try:
        d = json.loads(line)
    except Exception:
        continue
    a = d.get("a", "") or ""
    q = d.get("q", "") or ""
    if "/" not in a and "/" not in q:
        continue
    n += 1
    print("--- #%d role=%s auto_en=%s" % (i, d.get("role", ""), d.get("auto_en")))
    print("Q:", q[:80].replace("\n", " "))
    for m in re.finditer(r".{0,20}/.{0,20}", a):
        print("  A...", m.group().replace("\n", " "))
print("### 含斜杠记录数:", n)
