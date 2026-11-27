# -*- coding: utf-8 -*-
"""意图诊断：验证「介绍庐山」类问句会不会误命中广州/新闻/搜索注入。"""
import llm_gateway as g

qs = [
    "介绍庐山",
    "介绍一下庐山",
    "同我介绍下庐山",
    "详细讲下庐山",
    "讲下庐山嘅历史",
    "庐山有咩玩",
    "介绍下庐山瀑布",
    "读一下望庐山瀑布",
    "介绍广州",
    "广州本地新闻",
    "今日天气",
    "介绍下黄山",
    "介绍下西湖",
]
for q in qs:
    w = g.is_weather_intent(q)
    gz = g.is_gz_news_intent(q)
    nw = g.is_news_intent(q)
    se = g.is_search_intent(q)
    lo = g.is_long_intent(q)
    po = g.is_poem_intent(q)
    inj = []
    if po:
        pass  # 豁免全部
    else:
        if w:
            inj.append("WEATHER")
        if gz:
            inj.append("GZ_NEWS")
        elif nw or (se and not w):
            inj.append("NEWS/SEARCH")
    print("=" * 70)
    print("Q      :", q)
    print("  intent: weather=%s gz=%s news=%s search=%s long=%s poem=%s" % (w, gz, nw, se, lo, po))
    print("  inject:", inj or "(无联网注入，纯透传)")
    print("  qy    :", repr(g.extract_query(q)))
    print("  city  :", g.extract_city(q)[0])
