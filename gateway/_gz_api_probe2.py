#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深挖2：① 新花城 API list 字段 + 频道 siteId/channelId；② 广视网 gzbn.gztv.com:7443 接口路径。"""
import urllib.request as u, re, json, html
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
     "Referer": "https://huacheng.gz-cmc.com/", "Accept": "*/*"}

def get(url, timeout=12):
    r = u.urlopen(u.Request(url, headers=H), timeout=timeout)
    return r.read(), r.headers.get("Content-Type", "")

# 1. 新花城 API list 结构
print("=" * 70, "\n1. 新花城 getChannelAllContents list 字段结构")
base = "https://www.gz-cmc.com/contentapi/api/content/getChannelAllContents"
try:
    raw, _ = get(base + "?siteId=1&channelId=1&pageNum=1&pageSize=5")
    d = json.loads(raw.decode("utf-8", "replace"))
    print("  keys:", list(d.keys()), "total=%s pages=%s listlen=%d" % (d.get("total"), d.get("pages"), len(d.get("list", []))))
    if d.get("list"):
        it = d["list"][0]
        print("  item keys:", list(it.keys()))
        for k, v in it.items():
            sv = str(v)
            print("     %-18s %s" % (k, sv[:100]))
    print("  --- 前5条标题 ---")
    for it in d.get("list", [])[:5]:
        print("     ", str(it.get("title", ""))[:50], "|", it.get("publishTime") or it.get("createTime") or it.get("pubTime"))
except Exception as e:
    print("  FAIL", repr(e)[:120])

# 2. 首页里每个频道的 siteId/pdId（siteId 是频道关键）
print("\n" + "=" * 70, "\n2. 新花城首页频道 siteId/pdId 映射")
raw, _ = get("https://huacheng.gz-cmc.com/")
t = raw.decode("utf-8", "replace")
# 抓 nav-child-li 带 siteid/pdId 的
for m in re.finditer(r'<[^>]*nav-child-li[^>]*>', t):
    tag = m.group(0)
    sid = re.search(r'siteid=["\']?([^"\'\s>]+)', tag, re.I)
    pd = re.search(r'pdId=["\']?([^"\'\s>]+)', tag, re.I)
    nm = re.search(r'>([^<>]{2,10})<', t[m.end():m.end() + 60])
    if sid or pd:
        print("     siteid=%-34s pdId=%-8s name=%s" % (sid.group(1) if sid else "?", pd.group(1) if pd else "?", nm.group(1) if nm else "?"))
# 直接看默认 siteId 上下文
m = re.search(r"var siteId\s*=\s*'([^']+)'", t)
print("  默认 siteId =", m.group(1) if m else "?")
m2 = re.search(r"channelId\s*=\s*'?([^;\n']+)", t)
print("  默认 channelId =", m2.group(1) if m2 else "?")

# 3. 静态 JSON 频道列表（更简单可信）
print("\n" + "=" * 70, "\n3. 静态 JSON 频道（huacheng /json/channel/*/list.json）")
for slug in ("xuexijinxingshi", "yaowen", "re wen", "chengshi", "news", "toutiao", "shouye"):
    url = "https://huacheng.gz-cmc.com/json/channel/%s/list.json" % slug.replace(" ", "")
    try:
        raw, ct = get(url, timeout=8)
        d = raw.decode("utf-8", "replace")
        print("  %-18s OK len=%d head=%s" % (slug, len(raw), d[:90].replace("\n", " ")))
    except Exception as e:
        print("  %-18s FAIL %s" % (slug, type(e).__name__))

# 4. 广视网接口：从 chunk-vendors + app.js 找 gzbn.gztv.com:7443 下的路径
print("\n" + "=" * 70, "\n4. 广视网 API 路径（app.js 中 baseURL 附近的 axios 调用）")
try:
    jsb, _ = get("https://www.gztv.com/js/app.755a143f.js", timeout=15)
    js = jsb.decode("utf-8", "replace")
    # 找所有 n.Z.post/get 或 axios 调用的 url 字符串
    paths = set(re.findall(r'["\'](/[a-zA-Z0-9_./\-]{4,80})["\']', js))
    api_paths = sorted(p for p in paths if any(k in p.lower() for k in ("api", "news", "list", "column", "content", "article", "channel", "home", "index", "query", "search")))
    print("  API-ish paths (%d):" % len(api_paths))
    for p in api_paths[:50]:
        print("     ", p)
    # 找 .post/.get 上下文
    for pat in (r"\.post\(.{0,160}", r"\.get\(.{0,160}"):
        mm = re.findall(pat, js)
        print("  %s -> %d; sample=%s" % (pat[:7], len(mm), mm[0][:170].replace("\n", " ") if mm else ""))
except Exception as e:
    print("  FAIL", repr(e)[:120])
