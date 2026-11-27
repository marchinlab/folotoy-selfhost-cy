#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定稿探测：广视网 tid=3/5 完整字段 + 新花城 yaowen 今日过滤，确认可用标题。"""
import urllib.request as u, json, re
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
     "Referer": "https://www.gztv.com/", "Accept": "*/*"}

def get(url, timeout=12):
    return u.urlopen(u.Request(url, headers=H), timeout=timeout).read()

BASE = "https://gzbn.gztv.com:7443/media-cloud-manage-app/webPage/queryTemplateContentList"
print("=" * 70, "\n1. 广视网 tid=3 要闻 全字段 + 今日")
d = json.loads(get(BASE + "?templateId=3&pageNum=1&pageSize=12").decode("utf-8", "replace"))
recs = d["data"]["records"]
print("  total=%s n=%d" % (d["data"]["total"], len(recs)))
for r in recs[:12]:
    print("  [%s] %s | 栏目=%s | 简介=%s" % (
        str(r.get("operateTime") or "")[:16],
        str(r.get("operateTitle") or "")[:40],
        str(r.get("publishName") or "")[:12],
        str(r.get("title") or "")[:34]))

print("\n" + "=" * 70, "\n2. 广视网 tid=5 联播")
d = json.loads(get(BASE + "?templateId=5&pageNum=1&pageSize=8").decode("utf-8", "replace"))
for r in d["data"]["records"][:8]:
    print("  [%s] %s | %s" % (str(r.get("operateTime") or "")[:16], str(r.get("operateTitle") or "")[:44], str(r.get("publishName") or "")[:12]))

print("\n" + "=" * 70, "\n3. 新花城 yaowen 今日(11-11)条目")
d = json.loads(get("https://huacheng.gz-cmc.com/json/channel/yaowen/list.json").decode("utf-8", "replace"))
lst = d.get("list", [])
today = []
for it in lst:
    dd = it.get("data", {})
    tm = str(dd.get("publishTime") or "")
    title = str(dd.get("title") or "").strip()
    if tm.startswith("2026-11-11") and title:
        today.append((tm, title, str(dd.get("description") or "")[:40], str(dd.get("sourceName") or "")[:10]))
print("  今日条目=%d / 总%d" % (len(today), len(lst)))
for tm, title, desc, src in today[:12]:
    print("  [%s] %s | %s | %s" % (tm[5:16], title[:38], desc, src))
