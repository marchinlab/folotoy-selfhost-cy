#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""容器内联网自测：直接调 gather_weather / gather_news 验证真实数据。"""
import sys
sys.path.insert(0, "/app")
import llm_gateway as g

print("=== 天气：广州 ===")
r = g.gather_weather("广州天气", "而家广州天气点啊")
print(r if r else "WEATHER_NONE")

print("\n=== 天气：深圳 ===")
r2 = g.gather_weather("深圳天气", "深圳听日落雨吗")
print(r2 if r2 else "WEATHER_NONE")

print("\n=== 新闻：今日 ===")
n = g.gather_news("新闻")
print(n if n else "NEWS_NONE")
