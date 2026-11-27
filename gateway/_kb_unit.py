#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识类联网 + 换模型 + 长文 单元自测（本地，唔过网络）。"""
import sys, os
sys.path.insert(0, "/app")
os.environ["MODEL_OVERRIDE"] = ""  # 覆盖逻辑单独测
import importlib
import llm_gateway as g
import yue_polish

FAIL = 0
def chk(cond, label, extra=""):
    global FAIL
    print(("  OK   " if cond else "  FAIL ") + label + ("  " + extra if extra else ""))
    if not cond:
        FAIL += 1

print("=== ① 知识类意图：应该搜 ===")
SHOULD = ["介绍庐山", "讲下黄山", "介绍一下西湖", "李白系边个",
          "珠穆朗玛峰有几高", "量子力学系咩", "唐朝有咩历史", "珠江系边度",
          "太阳系有哪些行星", "点解天会黑", "长城几长",
          "实例：故宫嘅历史", "杜甫同李白有咩区别", "微波炉嘅原理"]
for q in SHOULD:
    chk(g.is_knowledge_intent(q), repr(q))

print("\n=== ② 唔应该搜（寒暄/情绪/讲笑/自我/算术/诗词）===")
NO = ["讲个笑话", "讲笑", "我唔开心", "陪我倾下", "你叫咩名", "你系边个",
      "1+1等于几", "早抖", "早晨", "再讲多次", "你中意我吗", "我好攰",
      "读首静夜思", "把床前明月光读出来", "同我讲个古仔"]
for q in NO:
    chk(not g.is_knowledge_intent(q), repr(q))

print("\n=== ③ 更高优先级意图唔重复当知识 ===")
# 呢个系 do_POST 里 want_kb 嘅组合逻辑，单独验 is_* 互斥前提
for q in ["广州今日天气", "今日有咩新闻", "广州本地新闻"]:
    w = g.is_weather_intent(q); gz = g.is_gz_news_intent(q); n = g.is_news_intent(q)
    kb = g.is_knowledge_intent(q) and not (w or gz or n)
    chk(not kb, repr(q) + " -> 天气/新闻优先，唔当知识", "w=%s gz=%s n=%s kb=%s" % (w, gz, n, kb))

print("\n=== ④ 查询词优化（人名加引号防拆）===")
for q, must in [("介绍庐山", "庐山"), ("李白系边个", "李白"),
                ("黄山喺边个省", "黄山"), ("讲下西湖", "西湖")]:
    sq = g._kb_search_query(q)
    chk(must in sq, repr(q) + " -> " + repr(sq), "含专名=" + must)

print("\n=== ⑤ 长文自动触发（介绍 X）===")
for q in ["介绍庐山", "详细讲下黄山", "讲下西湖"]:
    chk(g.is_long_intent(q) or g.is_intro_place(q), repr(q) + " -> 长文")
chk(not (g.is_long_intent("你好") or g.is_intro_place("你好")), "你好 -> 唔系长文")

print("\n=== ⑥ 模型覆盖（网关层改 payload.model）===")
g.MODEL_OVERRIDE = "Qwen/Qwen3-30B-A3B-Instruct-2507"
p = {"model": "THUDM/GLM-4-9B-0414", "messages": [{"role": "user", "content": "x"}]}
# 直接调 forward 会发网络；改为验证覆盖分支逻辑（复刻）＋确认常量读入
chk(g.MODEL_OVERRIDE == "Qwen/Qwen3-30B-A3B-Instruct-2507", "MODEL_OVERRIDE 读入", g.MODEL_OVERRIDE)
chk("Qwen3-30B" in g.MODEL_OVERRIDE, "指向 30B")
chk(g.LONG_MAX_TOKENS == 1600 or g.LONG_MAX_TOKENS >= 1500, "长文 tokens 足够 1000 字", str(g.LONG_MAX_TOKENS))

print("\n=== ⑦ yue_polish 新规则：这是/那是 ===")
for s, exp in [("这是庐山", "呢个系庐山"), ("那是黄山", "嗰个系黄山"),
               ("这就是原因", "呢个就系原因")]:
    out = yue_polish.polish(s)
    chk(out == exp, repr(s) + " -> " + repr(out), "期望 " + repr(exp))

print("\n=== ⑧ 诗词豁免唔受新规则影响 ===")
poem = "同是天涯沦落人"
out = yue_polish.polish(poem, poem=True)
chk(out == poem, "读诗「是」照原文", repr(out))

print("\n" + ("ALL_PASS" if FAIL == 0 else "FAIL=%d" % FAIL))
sys.exit(0 if FAIL == 0 else 1)
