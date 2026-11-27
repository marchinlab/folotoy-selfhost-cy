# -*- coding: utf-8 -*-
"""只读：统计 conversations 目录聚合去重后的唯一记录数（部署前后基线对比用）。"""
import os, glob, json
D = os.environ.get("CONV_DIR", "/opt/folotoy/conversations")
seen = set()
n_files = 0
for p in sorted(glob.glob(os.path.join(D, "*.jsonl*"))):
    if not os.path.isfile(p):
        continue
    n_files += 1
    with open(p, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            ep = r.get("epoch")
            if isinstance(ep, (int, float)):
                seen.add(("ep", round(float(ep), 3)))
            else:
                seen.add(("fb", r.get("ts", ""), (r.get("q", ""))[:80], len(r.get("a", "") or "")))
print(len(seen))
