#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深挖4：① 广视网 records 字段+今日标题；② 广视网参数(templateId等)；③ 花城+App内容网页源。"""
import urllib.request as u, re, json
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
     "Referer": "https://www.gztv.com/", "Accept": "*/*"}

def get(url, timeout=12):
    r = u.urlopen(u.Request(url, headers=H), timeout=timeout)
    return r.read(), r.headers.get("Content-Type", "")

base = "https://gzbn.gztv.com:7443"
path = "/media-cloud-manage-app/webPage/queryTemplateContentList"

# 1. 广视网空 GET 的 records 结构 + 今日标题
print("=" * 70, "\n1. 广视网 queryTemplateContentList 空GET records")
try:
    raw, _ = get(base + path)
    d = json.loads(raw.decode("utf-8", "replace"))
    print("  top keys:", list(d.keys()))
    data = d.get("data", {})
    print("  data keys:", list(data.keys()) if isinstance(data, dict) else type(data))
    recs = data.get("records", []) if isinstance(data, dict) else []
    print("  records=%d total=%s size=%s" % (len(recs), data.get("total"), data.get("size")))
    if recs:
        print("  record keys:", list(recs[0].keys()))
        for k, v in recs[0].items():
            if any(x in k.lower() for x in ("title", "name", "time", "date", "desc", "content", "url", "publish", "create")):
                print("     %-20s %s" % (k, str(v)[:90]))
        print("  --- 前10条 ---")
        for r in recs[:10]:
            title = r.get("title") or r.get("contentTitle") or r.get("name") or r.get("articleTitle") or "?"
            tm = r.get("publishTime") or r.get("createTime") or r.get("pubTime") or "?"
            print("     %-50s | %s" % (str(title)[:48], tm))
except Exception as e:
    print("  FAIL", repr(e)[:140])

# 2. 试参数：templateId / templateCode / page
print("\n" + "=" * 70, "\n2. 广视网参数试探")
params_tries = [
    "?templateId=1&pageNum=1&pageSize=10",
    "?templateCode=home&pageNum=1&pageSize=10",
    "?templateId=1&current=1&size=10",
    "?pageNum=1&pageSize=20",
]
for p in params_tries:
    try:
        raw, _ = get(base + path + p)
        d = json.loads(raw.decode("utf-8", "replace"))
        recs = (d.get("data") or {}).get("records", [])
        print("  %-42s code=%s recs=%d" % (p, d.get("code"), len(recs)))
        if recs:
            print("       sample=", str(recs[0].get("title") or recs[0].get("contentTitle") or "?")[:50])
    except Exception as e:
        print("  %-42s FAIL %s" % (p, repr(e)[:60]))

# 3. 广视网 focusNews / channel / searchList GET
print("\n" + "=" * 70, "\n3. 广视网其它接口 GET")
for p in ("/media-cloud-manage-app/focusNews", "/focusNews", "/media-cloud-manage-app/webPage/channel", "/searchList?keyword=%E5%B9%BF%E5%B7%9E"):
    try:
        raw, _ = get(base + p, timeout=10)
        print("  %-48s OK len=%d head=%s" % (p, len(raw), raw.decode("utf-8", "replace")[:110].replace("\n", " ")))
    except Exception as e:
        print("  %-48s FAIL %s" % (p, type(e).__name__))

# 4. app.js 里 queryTemplateContentList 的调用参数（找 s( 的调用处传了什么）
print("\n" + "=" * 70, "\n4. app.js 里模板列表调用传参")
try:
    jsb, _ = get("https://www.gztv.com/js/app.755a143f.js", timeout=15)
    js = jsb.decode("utf-8", "replace")
    # 找 Ec( 或 .Ec( 调用（s 暴露为 Ec）
    for pat in (r"Ec\(.{0,200}", r"templateId.{0,120}", r"templateCode.{0,120}", r"columnId.{0,120}", r"siteId.{0,120}"):
        mm = re.findall(pat, js)
        print("  %-16s %d hits; %s" % (pat[:12], len(mm), mm[0][:180].replace("\n", " ") if mm else ""))
except Exception as e:
    print("  FAIL", repr(e)[:90])
