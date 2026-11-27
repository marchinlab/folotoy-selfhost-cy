#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深挖3：① 新花城 list[].data 真实字段；② 广视网 queryTemplateContentList POST 参数；③ 首页模板参数。"""
import urllib.request as u, re, json
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
     "Referer": "https://huacheng.gz-cmc.com/", "Accept": "*/*"}

def get(url, timeout=12, data=None, ctype=None):
    hdr = dict(H)
    if ctype:
        hdr["Content-Type"] = ctype
    r = u.urlopen(u.Request(url, headers=hdr, data=data, method="POST" if data else "GET"), timeout=timeout)
    return r.read(), r.headers.get("Content-Type", "")

# 1. 新花城 shouye/yaowen list[].data 字段 + 今日标题
print("=" * 70, "\n1. 新花城静态 JSON list[].data 字段与今日标题")
for slug in ("shouye", "yaowen"):
    url = "https://huacheng.gz-cmc.com/json/channel/%s/list.json" % slug
    try:
        raw, _ = get(url)
        d = json.loads(raw.decode("utf-8", "replace"))
        lst = d.get("list", [])
        print("  [%s] listlen=%d" % (slug, len(lst)))
        if lst:
            data = lst[0].get("data", {})
            print("     data keys:", list(data.keys()))
            # 找标题/时间字段名
            for k in data:
                if any(x in k.lower() for x in ("title", "time", "date", "publish", "create", "summary", "desc", "url", "source")):
                    print("       %-20s %s" % (k, str(data[k])[:80]))
            print("     --- 前8条 ---")
            for it in lst[:8]:
                dd = it.get("data", {})
                title = dd.get("title") or dd.get("contentTitle") or dd.get("name") or "?"
                tm = dd.get("publishTime") or dd.get("publishDate") or dd.get("createTime") or dd.get("pubTime") or dd.get("time") or "?"
                print("       %-46s | %s" % (str(title)[:44], tm))
    except Exception as e:
        print("  [%s] FAIL %s" % (slug, repr(e)[:100]))

# 2. 广视网 queryTemplateContentList POST 参数
print("\n" + "=" * 70, "\n2. 广视网 gzbn.gztv.com:7443 queryTemplateContentList")
base = "https://gzbn.gztv.com:7443"
path = "/media-cloud-manage-app/webPage/queryTemplateContentList"
# 先试 GET 与空 POST 看报错提示
for label, data, ct in [
    ("GET空", None, None),
    ("POST空json", b"{}", "application/json"),
    ("POST templateId=1", json.dumps({"templateId": "1", "pageNum": 1, "pageSize": 10}).encode(), "application/json"),
]:
    try:
        raw, _ = get(base + path, timeout=12, data=data, ctype=ct)
        print("  %-20s OK len=%d head=%s" % (label, len(raw), raw.decode("utf-8", "replace")[:180].replace("\n", " ")))
    except Exception as e:
        print("  %-20s FAIL %s" % (label, repr(e)[:90]))

# 从 app.js 找调用 queryTemplateContentList 时传的参数 e
print("\n  --- app.js 调用上下文 ---")
try:
    jsb, _ = get("https://www.gztv.com/js/app.755a143f.js", timeout=15)
    js = jsb.decode("utf-8", "replace")
    i = js.find("queryTemplateContentList")
    if i > 0:
        print("  ", js[max(0, i - 400):i + 200].replace("\n", " "))
    # 找 focusNews / channel 调用
    for kw in ("focusNews", '"/channel"', "searchList"):
        j = js.find(kw)
        if j > 0:
            print("  [%s] %s" % (kw, js[max(0, j - 260):j + 120].replace("\n", " ")))
except Exception as e:
    print("  js FAIL", repr(e)[:100])
