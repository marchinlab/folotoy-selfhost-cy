#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证：①baike.com 歧义词点样识别(标题/og:title/首个<h1>) ②cn.bing 补充料质量。"""
import urllib.request, urllib.parse, ssl, re, html
CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Accept-Language": "zh-CN,zh;q=0.9"}

def get(url):
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10, context=CTX).read()
    except Exception as e:
        return ("FAIL:%s:%s" % (type(e).__name__, e)).encode()

def strip(s):
    s = re.sub(r"<script[^>]*>.*?</script>", " ", s or "", flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()

print("=== ① baike.com 页面标题/og:title/h1（用嚟验词条系咪对得上）===")
for name in ("李白", "庐山", "西湖", "长城", "故宫", "唐朝", "量子力学"):
    h = get("https://www.baike.com/wiki/" + urllib.parse.quote(name)).decode("utf-8", "replace")
    if h.startswith("FAIL"):
        print("  [%s] %s" % (name, h[:50])); continue
    og = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', h, re.I)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S | re.I)
    title = re.search(r"<title>(.*?)</title>", h, re.S)
    desc = re.search(r'<meta\s+name="description"\s+content="([^"]{20,})"', h, re.I)
    print("  [%s] og=%r h1=%r title=%r" % (name,
          og.group(1)[:30] if og else None,
          strip(h1.group(1))[:30] if h1 else None,
          strip(title.group(1))[:40] if title else None))
    print("       desc头=%r" % (strip(desc.group(1))[:50] if desc else ""))

print("\n=== ② cn.bing.com 补充料（李白/庐山/歧义词 前5条 title+desc）===")
for name in ("李白", "庐山", "西湖", "长城"):
    q = urllib.parse.quote(name)
    x = get("https://cn.bing.com/search?q=%s&format=rss" % q).decode("utf-8", "replace")
    items = []
    for m in re.finditer(r"<item[^>]*>(.*?)</item>", x, re.S | re.I):
        t = re.search(r"<title[^>]*>(.*?)</title>", m.group(1), re.S | re.I)
        d = re.search(r"<description[^>]*>(.*?)</description>", m.group(1), re.S | re.I)
        items.append((strip(t.group(1)) if t else "", strip(d.group(1)) if d else ""))
    print("\n  ### %s -> %d 条" % (name, len(items)))
    for t, d in items[:5]:
        print("     T=%s" % t[:44]); print("        D=%s" % d[:95])
print("\nBAIKE_VERIFY_DONE")
