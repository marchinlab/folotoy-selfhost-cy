#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测网关容器内可用联网搜索源 + 上游配置。一次性探针，不进镜像。"""
import urllib.request, json, ssl
CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get(name, url, show=160, timeout=8):
    try:
        req = urllib.request.Request(url, headers=UA)
        d = urllib.request.urlopen(req, timeout=timeout, context=CTX).read()
        print("[OK] %-22s len=%d head=%r" % (name, len(d), d[:show].decode("utf-8", "replace")))
        return d
    except Exception as e:
        print("[FAIL] %-20s %s: %s" % (name, type(e).__name__, str(e)[:100]))
        return None

# 上游配置
try:
    import llm_gateway as g
    print("UPSTREAM_BASE  =", g.UPSTREAM_BASE)
    print("UPSTREAM_MODEL =", g.UPSTREAM_MODEL)
    print("LONG_MAX_TOKENS=", g.LONG_MAX_TOKENS)
except Exception as e:
    print("import llm_gateway FAIL:", e)

print("--- 百科/知识类 ---")
get("wikipedia", "https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&explaintext=1&format=json&titles=%E5%8D%A2%E5%B1%B1")
get("baidu_baike_suggest", "https://baike.baidu.com/api/openapi/BaikeSuggestion?keyword=%E5%8D%A2%E5%B1%B1")
get("wikidata", "https://www.wikidata.org/w/api.php?action=wbsearchentities&search=%E5%8D%A2%E5%B1%B1&language=zh&format=json")

print("--- 通用搜索 ---")
get("bing_rss", "https://www.bing.com/search?q=%E5%8D%A2%E5%B1%B1+%E7%AE%80%E4%BB%8B&format=rss")
get("bing_news_rss", "https://www.bing.com/news/search?q=%E5%8D%A2%E5%B1%B1&format=rss")
get("duckduckgo_html", "https://html.duckduckgo.com/html/?q=%E5%8D%A2%E5%B1%B1%E7%AE%80%E4%BB%8B")
get("ddg_instant", "https://api.duckduckgo.com/?q=Lushan&format=json&no_html=1")
get("baidu_html", "https://www.baidu.com/s?wd=%E5%8D%A2%E5%B1%B1%E7%AE%80%E4%BB%8B")
get("sogou_html", "https://www.sogou.com/web?query=%E5%8D%A2%E5%B1%B1%E7%AE%80%E4%BB%8B")
get("so360_html", "https://www.so.com/s?q=%E5%8D%A2%E5%B1%B1%E7%AE%80%E4%BB%8B")

print("--- 免费无key聚合/AI搜索 ---")
get("tavily_keyless", "https://api.tavily.com/search", show=60)
get("wikipedia_zh_mobile", "https://zh.m.wikipedia.org/api/rest_v1/page/summary/%E5%8D%A2%E5%B1%B1")
