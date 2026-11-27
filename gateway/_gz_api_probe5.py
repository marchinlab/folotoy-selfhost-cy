#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深挖5：广视网首页到底用哪个 templateId 拿今日要闻 + 花城+App(com.hcj.gznews)网页源搜索。"""
import urllib.request as u, re, json
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
     "Referer": "https://www.gztv.com/", "Accept": "*/*"}

def get(url, timeout=12):
    r = u.urlopen(u.Request(url, headers=H), timeout=timeout)
    return r.read()

base = "https://gzbn.gztv.com:7443"

# 1. app.js 里首页组件调用的模板 ID（queryTemplateContentList 参数是 templateId）
print("=" * 70, "\n1. app.js 模板相关 templateId 数字")
try:
    js = get("https://www.gztv.com/js/app.755a143f.js", timeout=15).decode("utf-8", "replace")
    # 找 templateId 附近数字
    for m in re.finditer(r"templateId:\s*(\d+)", js):
        print("  templateId:", m.group(1), "| ctx:", js[max(0, m.start()-80):m.start()+80].replace("\n"," "))
    # home 组件 chunk 引用
    print("  chunk files referenced:", sorted(set(re.findall(r'js/chunk[^\"\']*?\.js', js)))[:5])
    # 找 topicTag / queryTopicByTopicTag 参数
    for kw in ("queryTopicByTopicTag", "topicTag", "queryTopicInfoByTemplate", "queryTemplateContentList"):
        for m in list(re.finditer(re.escape(kw), js))[:2]:
            print("  [%s] %s" % (kw, js[max(0, m.start()-120):m.start()+140].replace("\n"," ")))
except Exception as e:
    print("  FAIL", repr(e)[:100])

# 2. 遍历 templateId 1..40 看哪些返回今日(含2026-11)标题
print("\n" + "=" * 70, "\n2. 扫 templateId 1..40 找今日新闻流")
path = "/media-cloud-manage-app/webPage/queryTemplateContentList"
found = []
for tid in range(1, 41):
    try:
        d = json.loads(get(base + path + "?templateId=%d&pageNum=1&pageSize=6" % tid, timeout=6).decode("utf-8", "replace"))
        recs = (d.get("data") or {}).get("records", [])
        titles = [str(r.get("operateTitle") or r.get("title") or "")[:26] for r in recs]
        times = [str(r.get("operateTime") or r.get("createTime") or "")[:10] for r in recs]
        recent = any(t.startswith("2026-11") for t in times)
        if recs:
            print("  tid=%-3d n=%-2d recent=%s | %s | %s" % (tid, len(recs), "YES" if recent else "no", titles[0], times[0]))
        if recent:
            found.append(tid)
    except Exception as e:
        pass
print("  含2026-11的 templateId:", found)

# 3. 花城+ App 内容是否有网页镜像（gz-cmc 是广报新花城；广州台花城+ 另找）
print("\n" + "=" * 70, "\n3. 广州台花城+ 网页源候选")
for url in [
    "https://www.gz-cmc.com/contentapi/api/content/getChannelAllContents?siteId=5e88c884e2ed4e7a9a8d5225c299f707&channelId=1&pageNum=1&pageSize=5",
    "https://huacheng.gz-cmc.com/json/channel/gztv/list.json",
    "https://huacheng.gz-cmc.com/json/channel/yaowen/list.json",
]:
    try:
        raw = get(url, timeout=8)
        print("  OK %-80s len=%d head=%s" % (url[-55:], len(raw), raw[:70].decode("utf-8","replace").replace("\n"," ")))
    except Exception as e:
        print("  FAIL %-80s %s" % (url[-55:], type(e).__name__))
