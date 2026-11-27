#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二轮：按【词条名】精确抓百科页 meta（唔靠搜索引擎分词），救两字人名 + 统一替换 Bing。
容器只能国内直连（wikipedia/duckduckgo 唔通），故只测国内源。"""
import urllib.request, urllib.parse, ssl, re, html
CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Accept-Language": "zh-CN,zh;q=0.9"}

def get(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=8, context=CTX)
        return r.read(), r.geturl()
    except Exception as e:
        return ("FAIL:%s:%s" % (type(e).__name__, e)).encode(), url

def strip(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()

def meta_desc(h):
    for pat in (r'<meta\s+name="description"\s+content="([^"]{20,})"',
                r'<meta\s+content="([^"]{20,})"\s+name="description"',
                r'<meta\s+name="Description"\s+content="([^"]{20,})"'):
        m = re.search(pat, h, re.I)
        if m:
            return strip(m.group(1))
    return ""

NAMES = ["李白", "杜甫", "鲁迅", "牛顿", "庐山", "珠穆朗玛峰", "量子力学", "西湖"]

print("=" * 68)
print("① 百度百科词条页 baike.baidu.com/item/{词条} 的 meta description")
for name in NAMES:
    h, _ = get("https://baike.baidu.com/item/" + urllib.parse.quote(name))
    t = h.decode("utf-8", "replace")
    if t.startswith("FAIL"):
        print("  [%s] %s" % (name, t[:70])); continue
    d = meta_desc(t)
    title = re.search(r"<title>(.*?)</title>", t, re.S)
    print("  [%s] len=%d title=%r" % (name, len(h), strip(title.group(1))[:40] if title else ""))
    print("       desc=%r" % d[:170])

print("\n" + "=" * 68)
print("② 360百科 baike.so.com/doc/  +  搜狗百科 baike.sogou.com")
for name in ("李白", "庐山"):
    for base in ("https://baike.so.com/doc/", "https://baike.sogou.com/v", "https://www.baike.com/wiki/"):
        u = base + urllib.parse.quote(name)
        h, _ = get(u)
        t = h.decode("utf-8", "replace")
        if t.startswith("FAIL"):
            print("  [%s] %-32s %s" % (name, base, t[:55])); continue
        d = meta_desc(t)
        print("  [%s] %-32s len=%d desc=%r" % (name, base, len(h), d[:130]))

print("\n" + "=" * 68)
print("③ Bing cn / 参数变体（对比，确认真救唔到人名）")
def rss_titles(u):
    x = get(u)[0].decode("utf-8", "replace")
    if x.startswith("FAIL"): return x[:60]
    ts = re.findall(r"<title[^>]*>(.*?)</title>", x, re.S | re.I)[:3]
    return " | ".join(strip(t)[:30] for t in ts)
q = urllib.parse.quote("李白")
for u in ("https://cn.bing.com/search?q=%s&format=rss" % q,
          "https://www.bing.com/search?q=%s&format=rss&ensearch=0" % q,
          "https://www.bing.com/search?q=%s&format=rss&mkt=zh-CN&setlang=zh-hans" % q):
    print("  %-62s\n     -> %s" % (u[:62], rss_titles(u)))
print("\nNAME_PROBE2_DONE")
