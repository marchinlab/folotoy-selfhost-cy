# -*- coding: utf-8 -*-
"""v1.25 英文意图自动路由单元回归：is_english_auto() 正例/反例全覆盖。
只 import 纯函数，唔需要联网、唔需要网关跑起来。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util

# 直接 import llm_gateway 会执行 main()? —— 它系模块化（末尾 if __name__），安全。
import llm_gateway as g

OK = []
def ck(name, cond, extra=""):
    OK.append(bool(cond))
    print("  %s %-46s %s" % ("PASS" if cond else "FAIL", name, extra))

print("== A. 主人两次真实问法（必须命中，否则「例句冇发音」重现）==")
for q, rk in [
    ("i want to a travel to shanghai's tourist sky .", "aqing_chat"),   # 12:06 纯英文
    ("帮我用英文介绍去上海旅行嘅客方案。", "aqing_chat"),                  # 13:03 中文夹「用英文」
    ("用英文教我三个去上海旅行嘅例句", ""),                                # detect_role 认唔到标记
    ("用英文介绍下广州塔", "aqing_chat"),
    ("affect 同 effect 用英文点样分辨？", "aqing_chat"),
    ("teach me english please", ""),
]:
    ck("命中 %r role=%r" % (q[:26], rk or "空"), g.is_english_auto(q, rk) is True)

print("== B. 英文意图词各分支 ==")
for w in ["讲英文", "英文例句", "英文单词", "英文翻译", "译成英文", "英文点讲", "学英文",
          "英文语法", "音标", "in english", "speak english", "grammar", "how do you say"]:
    ck("意图词 %s" % w, g.is_english_auto("我想" + w + "一下", "aqing_chat") is True)

print("== C. 反例：粤语闲聊/天气/新闻/专名，绝唔误路由（唔抢阿晴）==")
for q in [
    "今日广州天气点啊？",
    "你而家系边个啊？",
    "同我讲下今日广州嘅本地新闻",
    "详细介绍下庐山十个景点",
    "帮我读十首唐诗",
    "用粤语讲个笑话",
    "你识唔识英文啊？",           # 裸「英文」+自我认知，唔算要英文输出
    "英文歌有咩好介绍？",         # 「英文」做定语问内容，唔系要英文讲解
    "讲声 OK 就得啦",             # 单专名
    "睇下 NBA 直播",              # 白名单专名
    "用 AI 分析下呢张图",         # 白名单专名
    "呢个 PM2.5 几高？",
    "早晨阿晴",
]:
    ck("唔触发 %r" % q[:24], g.is_english_auto(q, "aqing_chat") is False)

print("== D. 6 个学科键一律唔触发（零回归面，唔抢粤语讲课）==")
for rk in ["chinese_teacher", "math_teacher", "physics_teacher", "chemistry_teacher", "history_teacher"]:
    ck("学科键 %s 唔触发" % rk, g.is_english_auto("用英文解释下 present continuous", rk) is False)

print("== E. 4 号键本身：函数唔拦（由 is_english 嘅 role 判定负责，唔靠 auto）==")
ck("english_teacher 键 auto 函数为 False（正常，主判定兜住）",
   g.is_english_auto("用英文教我", "english_teacher") is False)

print("== F. 主体系英文判定边界 ==")
# 够 3 个实词 + 字母占优 -> 命中
ck("纯英文长句命中", g.is_english_auto("Can you tell me about the plan", "aqing_chat") is True)
# 实词 <3 -> 唔命中（呢类交返阿晴）
ck("英文短问候唔触发", g.is_english_auto("hello how are you", "aqing_chat") is False)
ck("中英夹杂中文占优唔触发",
   g.is_english_auto("阿晴你同我讲下呢个 ok 啦", "aqing_chat") is False)

print("== G. 开关 AUTO_EN=0 一键回滚 ==")
g.AUTO_EN = False
ck("关开关后一律 False", g.is_english_auto("用英文介绍上海", "aqing_chat") is False)
g.AUTO_EN = True

n = len(OK); p = sum(OK)
print("\n===== 结果: %d/%d %s =====" % (p, n, "ALL PASS ✔" if p == n else "有 FAIL ✘"))
sys.exit(0 if p == n else 1)
