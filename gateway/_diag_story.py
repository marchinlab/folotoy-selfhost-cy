# -*- coding: utf-8 -*-
"""诊断/回归：史实讲述题（「讲唐朝开国嘅故事」）会因「故事」被 KNOWLEDGE_BLOCK
一刀切排除联网 -> 30B 凭记忆乱作（把「天下为公」塞畀李渊）。
本脚本打印 do_POST 核心分流嘅每个布尔，改代码前后各跑一次做对比。"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm_gateway as g

def judge(q, role_key="aqing_chat"):
    w = g.is_weather_intent(q)
    gz = g.is_gz_news_intent(q)
    nw = g.is_news_intent(q)
    se = g.is_search_intent(q)
    po = g.is_poem_intent(q)
    fact = g.is_fact_check_needed(q)
    know = g.is_knowledge_intent(q)
    kb = (not w and not gz and not nw) and (know or fact)
    subj = (role_key in g.SUBJECT_HINTS and role_key != "english_teacher"
            and g.is_subject_question(q, role_key))
    if subj:
        kb = False
    lo = g.is_long_intent(q) or g.is_intro_place(q)
    net = any((w, gz, nw, se, kb, subj, po))
    return dict(weather=w, gz=gz, news=nw, search=se, poem=po,
                fact=fact, know=know, want_kb=kb, want_subject=subj,
                long=lo, NET=net,
                fact_subject=g._fact_subject(q), kb_subject=g._kb_subject(q))

CASES = [
    ("讲唐朝开拓嘅故事。",              "aqing_chat",      True,  "问题原句·必须联网"),
    ("帮我讲下唐朝开国嘅故事。",        "aqing_chat",      True,  "问题原句·必须联网"),
    ("同我讲下唐朝开国嘅历史。😔",       "aqing_chat",      True,  "对照组·已联网"),
    ("讲下李白嘅故事",                  "aqing_chat",      True,  "历史人物+故事·应联网"),
    ("讲下秦始皇嘅故事",                "aqing_chat",      True,  "历史人物+故事·应联网"),
    ("讲抗日战争嘅故事",                "aqing_chat",      True,  "历史事件+故事·应联网"),
    ("讲霍去病嘅故事",                  "aqing_chat",      True,  "表外人物泛化·应联网"),
    ("讲下天下为公嘅出处",              "aqing_chat",      True,  "思想名句归属·应联网"),
    ("讲个童话故事",                    "aqing_chat",      False, "纯虚构·保持唔搜"),
    ("讲个鬼故事",                      "aqing_chat",      False, "纯虚构·保持唔搜"),
    ("讲个笑话",                        "aqing_chat",      False, "纯笑话·保持唔搜"),
    ("讲我嘅故事",                      "aqing_chat",      False, "第一人称·保持唔搜"),
    ("唐朝开国",                        "history_teacher", True,  "历史老师·应联网"),
    ("介绍庐山",                        "aqing_chat",      True,  "既有能力·勿破坏"),
    ("今日天气",                        "aqing_chat",      True,  "既有能力·勿破坏"),
    ("读一首静夜思",                    "aqing_chat",      True,  "诗词意图命中·豁免口语化(勿破坏)"),
]

print("=" * 92)
print("%-30s %-16s %-6s %-6s %-5s %-5s %-5s %-5s %-6s" %
      ("问句", "角色", "fact", "know", "kb", "subj", "poem", "long", "NET"))
print("-" * 92)
bad = 0
for q, role, expect_net, note in CASES:
    r = judge(q, role)
    flag = "OK " if r["NET"] == expect_net else "!!!"
    if r["NET"] != expect_net:
        bad += 1
    print("%s %-28s %-16s %-6s %-6s %-5s %-5s %-5s %-5s %-6s  %s" %
          (flag, q[:26], role, r["fact"], r["know"], r["want_kb"],
           r["want_subject"], r["poem"], r["long"], r["NET"], note))
    print("      fact_subject=%r kb_subject=%r" % (r["fact_subject"], r["kb_subject"]))
print("-" * 92)
print("NET 判定与期望不符：%d / %d" % (bad, len(CASES)))
print("=" * 92)
