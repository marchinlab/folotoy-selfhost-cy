# -*- coding: utf-8 -*-
"""只读扫描生产落盘（主文件 + 所有 .bak），定位主人本轮报的 4 个词/短语原文。
不写任何文件、不清落盘。用法: python3 _scan_new_words.py
"""
import os, json, glob, re

D = "/opt/folotoy/conversations"
# 目标：措辞类必看原文；发音类（时间/儿子）也顺带看模型用字语境
PATS = {
    "嗰阵/时期": re.compile(r"嗰阵|呢个嗰阵|时期|时候|呢阵"),
    "想知/定系": re.compile(r"想知|定系|想唔想知|有啲想|想知道|想不想"),
    "时间": re.compile(r"时间|時間"),
    "儿子": re.compile(r"儿子|兒子|仔"),
}
LIMIT = {"嗰阵/时期": 40, "想知/定系": 40, "时间": 20, "儿子": 20}

files = sorted(glob.glob(os.path.join(D, "*.jsonl")) + glob.glob(os.path.join(D, "*.jsonl.bak-*")))
rows = []
for f in files:
    try:
        for ln in open(f, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            d["_src"] = os.path.basename(f)
            rows.append(d)
    except Exception as e:
        print("READ_ERR", f, e)
print("总记录(跨所有文件,含重叠快照):", len(rows))

for name, pat in PATS.items():
    print("\n" + "=" * 70)
    print("###", name)
    n = 0
    for d in sorted(rows, key=lambda x: x.get("epoch", x.get("ts", 0)), reverse=True):
        hay = (d.get("q", "") or "") + " || " + (d.get("a", "") or "")
        if pat.search(hay):
            n += 1
            if n > LIMIT[name]:
                break
            print("\n[%s] role=%s btn=%s net=%s ts=%s" %
                  (d.get("_src"), d.get("role"), d.get("btn"), d.get("net"), d.get("ts")))
            print("  Q:", (d.get("q", "") or "")[:200])
            print("  A:", (d.get("a", "") or "")[:400].replace("\n", " "))
    print("--- 命中(展示上限内):", n)
