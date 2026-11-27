# -*- coding: utf-8 -*-
"""v1.39 语料挖掘：把落盘稿里含填充口头禅的【句子】切出来，看形态再定清理正则。"""
import json, re, glob

SENT_END = "。！？!?；;\n"
files = sorted(glob.glob("/opt/folotoy/conversations/2026-11-11.jsonl*"))
KEYS = ("你知唔知", "唔好意思", "明唔明", "知唔知", "系咪先", "其实呢", "咁讲啦",
        "我同你讲", "我继续", "唔好急", "慢慢讲", "一句一句", "唔使担心", "熟悉下")

def sents(text):
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch in SENT_END:
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out

hits = {}
for f in files:
    if ".bak" in f:
        continue  # 只看当前活跃主文件，避免重复统计
    try:
        rows = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
    except Exception as e:
        print("skip", f, e); continue
    for r in rows:
        a = r.get("a", "")
        if not isinstance(a, str):
            continue
        for s in sents(a):
            for k in KEYS:
                if k in s:
                    hits.setdefault(k, []).append(s)
                    break

for k in KEYS:
    lst = hits.get(k, [])
    print("=== 「%s」 命中 %d 句 ===" % (k, len(lst)))
    # 去重、打印全部（数量应该唔多）
    seen = set()
    for s in lst:
        if s in seen:
            continue
        seen.add(s)
        print("   |%s|" % s[:120])
    print()
