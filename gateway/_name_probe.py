#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""攻「人名/专名搜不到」：对比多种查询词 + 多源，打印全部结果标题，找出可靠攞真事实嘅法。"""
import urllib.request, urllib.parse, ssl, re, html
CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get(url):
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=8, context=CTX).read()
    except Exception as e:
        return ("FAIL:%s:%s" % (type(e).__name__, e)).encode()

def rss_titles(q):
    xml = get("https://www.bing.com/search?q=%s&format=rss" % urllib.parse.quote(q)).decode("utf-8", "replace")
    out = []
    for m in re.finditer(r"<item[^>]*>(.*?)</item>", xml, re.S | re.I):
        t = re.search(r"<title[^>]*>(.*?)</title>", m.group(1), re.S | re.I)
        d = re.search(r"<description[^>]*>(.*?)</description>", m.group(1), re.S | re.I)
        st = html.unescape(re.sub(r"<[^>]+>", "", t.group(1))).strip() if t else ""
        sd = html.unescape(re.sub(r"<[^>]+>", "", d.group(1))).strip() if d else ""
        out.append((st, sd))
    return out

def sogou(q):
    h = get("https://www.sogou.com/web?query=%s" % urllib.parse.quote(q)).decode("utf-8", "replace")
    # 搜狗结果摘要常在 class="str_info" / "text-layout" / "fz-mid"；粗暴攞中文段落
    txt = html.unescape(re.sub(r"<[^>]+>", " ", h))
    txt = re.sub(r"\s+", " ", txt)
    # 抽出含关键词嘅片段
    k = q.split()[0]
    segs = [txt[max(0, m.start()-10):m.start()+110] for m in list(re.finditer(re.escape(k), txt))[:6]]
    return segs

def baike_suggest(q):
    # 百度百科 suggestion 补全（攞精确词条名）
    return get("https://baike.baidu.com/api/openapi/BaikeSuggestion?keyword=%s" % urllib.parse.quote(q)).decode("utf-8", "replace")[:300]

QUERIES = [
    '"李白" 简介 百度百科',
    '李白 唐朝 诗人 生平 简介',
    '李白 是谁 诗仙 代表作',
    '"李白" 诗人 作品 生平',
    '李白 百度百科',
]
print("=" * 66)
print("① Bing RSS 多查询词（重点：有冇真·李白条目）")
for q in QUERIES:
    items = rss_titles(q)
    print("\n### q=%r -> %d 条" % (q, len(items)))
    for i, (t, d) in enumerate(items[:6]):
        mark = "★" if "李白" in (t + d) else " "
        print("  %s[%d] T=%s" % (mark, i, t[:52]))
        print("       D=%s" % d[:88])

print("\n" + "=" * 66)
print("② 搜狗 HTML 中文片段（李白）")
for seg in sogou("李白 简介 唐朝"):
    print("  ·", seg[:120])

print("\n" + "=" * 66)
print("③ 百度百科 suggestion")
print(" ", baike_suggest("李白"))

print("\n" + "=" * 66)
print("④ 控制组：庐山/珠峰 保持质量")
for q in ('"庐山" 简介 百度百科', '"珠穆朗玛峰" 海拔 高度 百度百科'):
    items = rss_titles(q)
    print("\n### %r -> %d 条，前3:" % (q, len(items)))
    for t, d in items[:3]:
        print("  ·", t[:46], "|", d[:70])
print("\nNAME_PROBE_DONE")
