#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深挖 www.baike.com（快懂百科）：多词条可靠性 + 正文段落提取（喂 1000 字长文）。"""
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
    s = re.sub(r"<style[^>]*>.*?</style>", " ", s, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()

NAMES = ["李白", "杜甫", "鲁迅", "牛顿", "苏轼", "爱因斯坦", "孔子",
         "庐山", "黄山", "西湖", "长城", "故宫", "珠穆朗玛峰", "珠江",
         "量子力学", "相对论", "光合作用", "唐朝", "明清", "微信", "抖音"]

print("=== ① 多词条：meta description 命中率 + 长度 ===")
ok = 0
for name in NAMES:
    h = get("https://www.baike.com/wiki/" + urllib.parse.quote(name)).decode("utf-8", "replace")
    if h.startswith("FAIL"):
        print("  [%s] FAIL %s" % (name, h[:50])); continue
    m = re.search(r'<meta\s+name="description"\s+content="([^"]{20,})"', h, re.I) or \
        re.search(r'<meta\s+content="([^"]{20,})"\s+name="description"', h, re.I)
    d = strip(m.group(1)) if m else ""
    hit = "OK" if d else "--"
    if d: ok += 1
    print("  [%s] %s len=%d  %r" % (name, hit, len(d), d[:110]))
print("  >>> meta 命中 %d/%d" % (ok, len(NAMES)))

print("\n=== ② 正文段落提取（李白 / 庐山）：睇能唔能够喂 800~1000 字长文 ===")
for name in ("李白", "庐山"):
    h = get("https://www.baike.com/wiki/" + urllib.parse.quote(name)).decode("utf-8", "replace")
    if h.startswith("FAIL"):
        print("  [%s] %s" % (name, h[:50])); continue
    # 尝试 JSON-LD / abstract / 段落
    paras = re.findall(r"<p[^>]*>(.*?)</p>", h, re.S | re.I)
    cn_paras = []
    for p in paras:
        t = strip(p)
        cn = len(re.findall(r"[\u4e00-\u9fff]", t))
        if cn >= 25 and not any(x in t for x in ("广告", "版权", "免责", "登录", "下载APP")):
            cn_paras.append(t)
    body = "\n".join(cn_paras)
    print("  [%s] 段落数=%d 正文汉字=%d" % (name, len(cn_paras), len(re.findall(r"[\u4e00-\u9fff]", body))))
    for p in cn_paras[:3]:
        print("     ·", p[:130])
print("\nBAIKE_PROBE_DONE")
