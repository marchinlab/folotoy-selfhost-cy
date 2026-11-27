#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探广州本地三源的结构：广视网 gztv / 花城+ huacheng / 搜狗微信 / wechat2rss。"""
import urllib.request as u, re, html, sys
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
     "Accept": "text/html,application/json,*/*"}

def get(url, timeout=10):
    r = u.urlopen(u.Request(url, headers=H), timeout=timeout)
    return r.read(), r.geturl(), r.headers.get("Content-Type", "")

def probe(name, url):
    print("\n" + "=" * 70)
    print(name, url)
    print("=" * 70)
    try:
        raw, final, ct = get(url)
        try:
            t = raw.decode("utf-8")
        except UnicodeDecodeError:
            t = raw.decode("gbk", "replace")
        print("final=%s ct=%s bytes=%d" % (final, ct, len(raw)))
        # 内联数据线索
        for kw in ("__NUXT__", "__INITIAL_STATE__", "__NEXT_DATA__", "window.__", "api/", "/api", "baseURL", "axios", "XMLHttpRequest", "fetch("):
            if kw in t:
                i = t.find(kw)
                print("  KW %-18s @%d ...%s" % (kw, i, t[max(0, i - 30):i + 90].replace("\n", " ")))
        # JS 文件
        js = re.findall(r'<script[^>]+src=["\']([^"\']+)', t)
        print("  JS files:", js[:10])
        # 纯文本片段（去 script/style）
        txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
        txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
        txt = re.sub(r"\s+", " ", txt).strip()
        print("  TEXT[:900]:", txt[:900])
        # 中文标题样（<a> 或 h）
        links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>\s*([^<]{4,80})', t)
        cn = [(h, re.sub(r"\s+", " ", x).strip()) for h, x in links if re.search(r"[\u4e00-\u9fa5]{4,}", x)]
        print("  CN LINKS[:12]:")
        for h, x in cn[:12]:
            print("     ", x[:46], "|", h[:70])
    except Exception as e:
        print("  FAIL", type(e).__name__, str(e)[:120])

for name, url in [
    ("广视网首页", "https://www.gztv.com/"),
    ("花城+网页版", "https://huacheng.gz-cmc.com/"),
    ("搜狗微信-广州广播电视台", "https://weixin.sogou.com/weixin?type=2&query=%E5%B9%BF%E5%B7%9E%E5%B9%BF%E6%92%AD%E7%94%B5%E8%A7%86%E5%8F%B0"),
    ("wechat2rss说明", "https://wechat2rss.xlab.app/"),
]:
    probe(name, url)
