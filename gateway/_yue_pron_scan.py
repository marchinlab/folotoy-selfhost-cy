# -*- coding: utf-8 -*-
"""扫描落盘备份里 9 个目标词的真实上下文，确认走哪条路径、完整句子长什么样。"""
import json, glob, re

WORDS = ["净力", "淨力", "质量", "質量", "一齐", "一齊", "陈桥", "陳橋",
         "组队", "組隊", "发达", "發達", "火药", "火藥", "过程", "過程",
         "文风", "文風"]

files = sorted(glob.glob("/opt/folotoy/conversations/*.jsonl*"))
total = 0
for fn in files:
    for i, line in enumerate(open(fn, encoding="utf-8")):
        try:
            d = json.loads(line)
        except Exception:
            continue
        a = d.get("a", "") or ""
        q = d.get("q", "") or ""
        hit = [w for w in WORDS if (w in a) or (w in q)]
        if not hit:
            continue
        total += 1
        base = fn.split("/")[-1]
        print("--- %s #%d role=%s auto_en=%s hit=%s" %
              (base, i, d.get("role", ""), d.get("auto_en", ""), ",".join(hit)))
        print("  Q:", q[:100].replace("\n", " "))
        for w in hit:
            for m in re.finditer(re.escape(w), a):
                s = max(0, m.start() - 24)
                e = min(len(a), m.end() + 24)
                print("  A...[%s] %s" % (w, a[s:e].replace("\n", " ")))
                break
print("### 命中记录数:", total)
