# -*- coding: utf-8 -*-
"""只读：把落盘卷里的对话记录全部打印出来，定位双语教学那条。"""
import json, glob, os

d = "/opt/folotoy/conversations"
files = sorted(glob.glob(os.path.join(d, "*.jsonl")))
print("jsonl 文件:", files)
rows = []
for f in files:
    for ln, line in enumerate(open(f, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            r["_src"] = "%s:%d" % (os.path.basename(f), ln)
            rows.append(r)
        except Exception as e:
            print("PARSE_ERR", f, ln, e)
print("总条数:", len(rows))
for r in rows:
    print("=" * 72)
    print("源:", r.get("_src"), "| 时间:", r.get("ts"), "| 键:", r.get("btn"),
          "| 角色:", r.get("role"), "| role_key:", r.get("role_key"))
    print("stream:", r.get("stream"), "| net:", r.get("net"),
          "| model:", r.get("model"), "| dur:", r.get("dur"))
    print("【问】", r.get("q"))
    print("【答】", r.get("a"))
