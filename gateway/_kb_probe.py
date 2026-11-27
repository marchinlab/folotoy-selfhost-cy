#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测：①Bing RSS 抓知识题的真实质量 ②yue_polish 能否清掉 30B 普通话残留。"""
import sys, urllib.request, urllib.parse, ssl, json
sys.path.insert(0, "/app")
import yue_polish
CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BING = "https://www.bing.com/search?q={q}&format=rss"

def rss(q):
    try:
        req = urllib.request.Request(BING.format(q=urllib.parse.quote(q)), headers=UA)
        return urllib.request.urlopen(req, timeout=8, context=CTX).read()
    except Exception as e:
        return ("FAIL %s %s" % (type(e).__name__, e)).encode()

def parse(xml):
    import xml.etree.ElementTree as ET, html, re
    def strip(s): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()
    out = []
    try:
        root = ET.fromstring(xml)
        for it in root.iter():
            if it.tag.split("}")[-1].lower() != "item": continue
            t = d = ""
            for ch in it:
                tag = ch.tag.split("}")[-1].lower()
                if tag == "title" and not t: t = strip(ch.text)
                elif tag == "description" and not d: d = strip(ch.text)
            if t: out.append((t, d))
    except Exception as e:
        out.append(("PARSE_FAIL " + str(e), ""))
    return out

print("=" * 64)
print("① Bing RSS 知识题质量（前4条 title / desc）")
for q in ("庐山 简介 海拔 位置", "黄山 在那个省", "李白 简介 朝代",
          "珠穆朗玛峰 海拔 多少米", "量子力学 是什么"):
    items = parse(rss(q))
    print("\n### %s  -> %d 条" % (q, len(items)))
    for t, d in items[:4]:
        print("  T:", t[:70])
        print("  D:", d[:90])

print("\n" + "=" * 64)
print("② yue_polish 清理 30B 普通话残留")
samples = [
    "庐山啊，因为凉快，所以夏天人哋都去度夏。",
    "我有个朋友去咗，讲真系一生一次嘅体验，可以话好值得。",
    "这是一个好有味道嘅地方，我们广州人通常都系揾个假期去。",
    "时候唔早啦，一个钟头之后要返去喇。",
    "含鄱口系睇日出嘅好位置，早晨天未光，云海慢慢翻滚。",
]
for s in samples:
    try:
        out, rep = yue_polish.polish(s, report=True)
    except TypeError:
        out, rep = yue_polish.polish(s), {}
    print("\n  原:", s)
    print("  改:", out)
    print("  命中:", rep)
print("\nKB_PROBE_DONE")
