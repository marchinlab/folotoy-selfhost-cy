#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探微信公众号源可用性：搜狗微信文章条目结构 / 广州本地号 / wechat2rss 免费订阅。"""
import urllib.request as u, re, html
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

def get(url, timeout=10):
    r = u.urlopen(u.Request(url, headers=H), timeout=timeout)
    return r.read()

# 1. 搜狗微信：解析 results 条目结构 + 时间
print("=" * 70, "\n1. 搜狗微信文章列表结构")
for kw in ("%E5%B9%BF%E5%B7%9E%E5%B9%BF%E6%92%AD%E7%94%B5%E8%A7%86%E5%8F%B0", "%E5%B9%BF%E5%B7%9E%E6%9C%AC%E5%9C%B0%E6%96%B0%E9%97%BB", "%E8%8A%B1%E5%9F%8E%E5%8C%BA"):
    url = "https://weixin.sogou.com/weixin?type=2&query=" + kw
    try:
        t = get(url, timeout=10).decode("utf-8", "replace")
        # 条目 <li id="sogou_vr_11002601_box_N">
        boxes = re.findall(r'<li[^>]*id="sogou_vr_[^"]*box_\d+"[^>]*>(.*?)</li>', t, re.S)
        print("  kw=%s boxes=%d" % (kw[:12], len(boxes)))
        for b in boxes[:4]:
            tm = re.search(r'(\d{4}-\d{2}-\d{2}|昨天|\d+小时前|\d+分钟前)', b)
            # 标题
            ttl = re.search(r'<h3[^>]*>(.*?)</h3>', b, re.S)
            acct = re.search(r'account_name[^>]*>(.*?)</a>', b, re.S)
            title = html.unescape(re.sub(r"<[^>]+>", "", ttl.group(1))).strip() if ttl else "?"
            title = re.sub(r"\s+", " ", title)
            acc = html.unescape(re.sub(r"<[^>]+>", "", acct.group(1))).strip() if acct else "?"
            print("     [%s] %s | %s" % (tm.group(1) if tm else "?", title[:40], acc[:16]))
    except Exception as e:
        print("  kw=%s FAIL %s" % (kw[:12], repr(e)[:80]))

# 2. 搜狗微信是否有反爬验证码
print("\n" + "=" * 70, "\n2. 搜狗微信反爬检测")
try:
    t = get("https://weixin.sogou.com/weixin?type=2&query=%E5%B9%BF%E5%B7%9E", timeout=10).decode("utf-8", "replace")
    for kw in ("验证码", "antispider", "请输入验证码", "抱歉", "异常"):
        print("  %-12s %s" % (kw, "命中" if kw in t else "无"))
    print("  boxes:", len(re.findall(r'sogou_vr_[^"]*box_', t)))
except Exception as e:
    print("  FAIL", repr(e)[:80])

# 3. wechat2rss 免费公众号列表（找广州广播电视台/广州本地号有无现成 RSS）
print("\n" + "=" * 70, "\n3. wechat2rss 免费订阅列表")
for url in ("https://wechat2rss.xlab.app/list/", "https://wechat2rss.xlab.app/list.xml", "https://wechat2rss.xlab.app/feed.xml"):
    try:
        raw = get(url, timeout=10)
        t = raw.decode("utf-8", "replace")
        print("  OK %-40s len=%d 广视/广州台命中=%s" % (url[-30:], len(raw), ("广州广播电视台" in t or "广视" in t)))
        if "广州广播电视台" in t or "广视" in t:
            i = t.find("广州广播电视台") if "广州广播电视台" in t else t.find("广视")
            print("     ...%s" % t[max(0,i-80):i+120].replace("\n"," "))
    except Exception as e:
        print("  FAIL %-40s %s" % (url[-30:], type(e).__name__))
