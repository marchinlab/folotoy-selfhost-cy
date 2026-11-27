#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深挖：① 花城+新花城频道页 API 调用；② 广视网 JS 里的 API 地址。"""
import urllib.request as u, re, json, html
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
     "Referer": "https://huacheng.gz-cmc.com/", "Accept": "*/*"}

def get(url, timeout=12):
    r = u.urlopen(u.Request(url, headers=H), timeout=timeout)
    return r.read(), r.geturl(), r.headers.get("Content-Type", "")

# ---------- 1. 花城+/新花城：抓频道页看 API 参数 ----------
print("=" * 70, "\n1. 新花城首页里 getChannelAllContents 的调用上下文")
raw, _, _ = get("https://huacheng.gz-cmc.com/")
t = raw.decode("utf-8", "replace")
for m in re.finditer(r"getChannelAllContents", t):
    i = m.start()
    print("  @%d ...%s" % (i, t[max(0, i - 260):i + 260].replace("\n", " ")))
    break
# 抽 siteId / channelId 之类
for kw in ("siteId", "siteid", "channelId", "channelid", "siteid=", "getChannelAllContents"):
    hits = re.findall(r".{0,50}%s.{0,60}" % re.escape(kw), t)
    print("  %s -> %d hits; sample=%s" % (kw, len(hits), hits[0].replace("\n", " ")[:110] if hits else ""))

# index.js 里找 ajax 调用格式
print("\n" + "=" * 70, "\n2. 新花城 index.js 找 API 调用格式")
try:
    jsb, _, _ = get("https://huacheng.gz-cmc.com/js/site/index.js")
    js = jsb.decode("utf-8", "replace")
    for m in re.finditer(r"getChannelAllContents", js):
        i = m.start()
        print("  CALL ...%s" % js[max(0, i - 300):i + 300].replace("\n", " "))
        break
    # 找参数拼装
    for kw in ("siteId", "channelId", "pageNum", "pageSize", "$.ajax", "$.post", "url:"):
        mm = re.search(r".{0,40}%s.{0,120}" % re.escape(kw), js)
        if mm:
            print("  %-12s %s" % (kw, mm.group(0).replace("\n", " ")[:150]))
except Exception as e:
    print("  index.js FAIL", repr(e)[:100])

# 直接试常见 REST 参数
print("\n" + "=" * 70, "\n3. 试 getChannelAllContents 各种参数")
base = "https://www.gz-cmc.com/contentapi/api/content/getChannelAllContents"
tries = [
    base,
    base + "?siteId=1&channelId=1&pageNum=1&pageSize=10",
    base + "?siteid=1&channelid=1&page=1&size=10",
]
for url in tries:
    try:
        raw, _, ct = get(url, timeout=10)
        d = raw.decode("utf-8", "replace")
        print("  OK %-70s ct=%s len=%d head=%s" % (url.replace(base, "..."), ct, len(raw), d[:130].replace("\n", " ")))
    except Exception as e:
        print("  FAIL %-70s %s" % (url.replace(base, "..."), repr(e)[:70]))

# ---------- 4. 广视网 JS 找 API ----------
print("\n" + "=" * 70, "\n4. 广视网 app.js 里的 API 地址")
try:
    jsb, _, _ = get("https://www.gztv.com/js/app.755a143f.js", timeout=15)
    js = jsb.decode("utf-8", "replace")
    print("  app.js bytes=%d" % len(js))
    # 抓 http(s) 域名和 /api 路径
    urls = set(re.findall(r"https?://[a-zA-Z0-9.\-]+(?:/[a-zA-Z0-9_./\-]*)?", js))
    apis = sorted(u for u in urls if "api" in u.lower() or "gztv" in u.lower() or "cmc" in u.lower())
    print("  API-ish urls (%d):" % len(apis))
    for u in apis[:40]:
        print("     ", u[:110])
    # baseURL 上下文
    for kw in ("baseURL", "axios.create", "/api/", "VUE_APP"):
        mm = re.findall(r".{0,60}%s.{0,120}" % re.escape(kw), js)
        print("  %-12s %d hits; %s" % (kw, len(mm), mm[0][:180].replace("\n", " ") if mm else ""))
except Exception as e:
    print("  app.js FAIL", repr(e)[:120])
