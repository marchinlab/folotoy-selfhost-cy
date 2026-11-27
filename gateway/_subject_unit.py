#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.22 学科老师改造单元回归：角色识别 / 学科意图 / 查询词 / 英语豁免 / 字数上限。"""
import sys, json
sys.path.insert(0, "/app" if "/app" in sys.path else ".")
sys.path.insert(0, ".")
import llm_gateway as g

fails = 0
def ck(name, cond, extra=""):
    global fails
    flag = "OK  " if cond else "FAIL"
    if not cond: fails += 1
    print("[%s] %s %s" % (flag, name, extra))

# 1) 7 种角色识别
roles = json.load(open("../config/roles.json", encoding="utf-8"))
for rid, key in [("1","aqing_chat"),("2","chinese_teacher"),("3","math_teacher"),
                 ("4","english_teacher"),("5","physics_teacher"),("6","chemistry_teacher"),
                 ("7","history_teacher")]:
    msgs = [{"role":"system","content":roles[rid]["prompt"]}, {"role":"user","content":"你好"}]
    ck("detect_role %s->%s" % (rid, key), g.detect_role(msgs) == key, "got=%r" % g.detect_role(msgs))
ck("detect_role 空(普通阿晴)", g.detect_role([{"role":"user","content":"hi"}]) == "")

# 2) 学科意图命中（各老师各一条典型题）
cases = [
    ("chinese_teacher", "「床前明月光」嘅作者系边个？"),
    ("math_teacher", "解一元二次方程 x²-5x+6=0"),
    ("physics_teacher", "欧姆定律嘅公式同单位系乜？"),
    ("chemistry_teacher", "写吓水电解嘅化学方程式"),
    ("history_teacher", "唐朝建立于公元几多年？"),
]
for key, q in cases:
    ck("学科意图 %s" % key, g.is_subject_question(q, key) is True, "q=%r" % q)
# 英语老师唔走学科抓料（佢自己既项目），闲聊/寒暄唔搜
ck("英语老师唔走学科抓料", g.is_subject_question("How do I use 'affect'?", "english_teacher") is False)
ck("闲聊老师唔搜", g.is_subject_question("你今日心情点呀", "aqing_chat") is False)
ck("学科老师寒暄唔搜", g.is_subject_question("老师你好", "math_teacher") is False)

# 3) 学科查询词：核心概念前置、唔带引新闻嘅噪音词
for key in ("math_teacher","physics_teacher","chemistry_teacher","history_teacher","chinese_teacher"):
    sq = g.subject_search_query("点解咁样", key)
    ck("查询词干净 %s" % key, len(sq) > 1 and "新闻" not in sq, "sq=%r" % sq)
# 短主词条：史实题唔好切出「唐朝建立于公元」呢类长串
ck("短主词条 唐朝", g._subject_baike_term("唐朝建立于公元几多年", "history_teacher") == "唐朝",
   "got=%r" % g._subject_baike_term("唐朝建立于公元几多年", "history_teacher"))
# 短锚点要拆出「唐朝」
ck("短锚点含唐朝", "唐朝" in g._subject_anchors("唐朝建立于公元几多年", "history_teacher"))

# 4) 英语豁免：polish_response(skip=True) 原样透传（含英文/普通话都唔改）
body = json.dumps({"choices":[{"message":{"content":"She is reading. 她正在读书，present continuous 表进行。"}}]}, ensure_ascii=False).encode()
out, hits = g.polish_response(body, stream=False, skip=True)
ck("英语豁免原样透传(英文保留)", json.loads(out)["choices"][0]["message"]["content"] == "She is reading. 她正在读书，present continuous 表进行。", "hits=%s" % hits)
# 对照：唔 skip 时英文会被清（验证豁免真系有必要）
out2, _ = g.polish_response(body, stream=False, skip=False)
ck("对照:非豁免会清英文", "She" not in json.loads(out2)["choices"][0]["message"]["content"])

# 5) 字数硬上限配置
ck("HARD_MAX_CHARS=1000", g.HARD_MAX_CHARS == 1000)
ck("HARD_MAX_TOKENS=1800", g.HARD_MAX_TOKENS == 1800)

# 6) health 仍 OK（model 覆盖）
ck("ROLE_MARKERS 7个", len(g.ROLE_MARKERS) == 7)
ck("TEACHER_MARKERS 6个", len(g.TEACHER_MARKERS) == 6)

print("\n" + ("SUBJECT_UNIT_ALL_PASS" if fails == 0 else "SUBJECT_UNIT_FAIL=%d" % fails))
sys.exit(0 if fails == 0 else 1)
