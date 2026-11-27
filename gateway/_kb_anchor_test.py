#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关键回归：知识题「介绍庐山」同时 ①注入真实资料 ②历史讲过广州景点。
验证注入 refs 之后，30B 会唔会串广州（话题锚定当前因 not refs 跳过隔离）。
对比：有资料注入 vs 无资料，睇资料能唔能自己压住历史污染。"""
import sys, os, json, time, urllib.request, ssl
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm_gateway as g
import yue_polish, tts_pron
CTX = ssl.create_default_context()
BASE = os.getenv("UPSTREAM_BASE", "https://api.siliconflow.cn/v1").rstrip("/")
KEY = os.getenv("UPSTREAM_KEY", "")
MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"
PERSONA = json.load(open("/config/roles.json", encoding="utf-8"))["3"]["prompt"]

# 历史：三轮介绍广州景点（就系之前污染 9B 嘅 few-shot）
HIST_GZ = [
    {"role": "user", "content": "介绍下广州塔"},
    {"role": "assistant", "content": "广州塔又称小蛮腰，喺海珠区，高六百米，系广州地标㗎。"},
    {"role": "user", "content": "讲下陈家祠"},
    {"role": "assistant", "content": "陈家祠喺荔湾区，系清代陈氏书院，木雕灰塑好出名，去玩好值得。"},
    {"role": "user", "content": "介绍下沙面"},
    {"role": "assistant", "content": "沙面系荔湾区一个岛，有好多欧陆建筑，清末租界留低嘅，而家好多人去行街影相。"},
]

def call(msgs, temp=0.95, mt=1600):
    p = {"model": MODEL, "messages": msgs, "stream": False,
         "temperature": temp, "top_p": 0.95, "max_tokens": mt}
    req = urllib.request.Request(BASE + "/chat/completions",
        data=json.dumps(p, ensure_ascii=False).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=120, context=CTX).read())
        return d["choices"][0]["message"]["content"]
    except Exception as e:
        return "ERR %s %s" % (type(e).__name__, e)

def polish(t):
    t, _ = yue_polish.polish(t, report=True)
    return tts_pron.fix(t)

def build(place, with_ref):
    msgs = [{"role": "system", "content": PERSONA}] + HIST_GZ + [{"role": "user", "content": place}]
    if with_ref:
        ref = g.gather_knowledge(g.extract_query(place), place)
        if ref:
            msgs = list(msgs)
            li = max(i for i, m in enumerate(msgs) if m.get("role") == "user")
            msgs.insert(li, {"role": "user", "content": ref})
            msgs[li + 1] = dict(msgs[li + 1])
            msgs[li + 1]["content"] += "\n（记得根据上面联网查到嘅真实资料答，唔好凭记忆乱作。）"
    return msgs

GZ = ("广州", "小蛮腰", "珠江", "白云山", "越秀", "荔湾", "海珠", "沙面", "陈家祠", "西关", "老广", "省城", "穗", "羊城")
for place in ("介绍庐山", "详细讲下黄山"):
    print("\n" + "=" * 60 + "\n### " + place + "（带三轮广州景点历史，高温0.95）")
    for with_ref in (True, False):
        msgs = build(place, with_ref)
        out = polish(call(msgs))
        hits = [w for w in GZ if w in out]
        print("  [有资料=%s] 广州词:%s  字数:%d" % (with_ref, hits or "无", len(out)))
        print("     ", repr(out[:200]))
print("\nKB_ANCHOR_TEST_DONE")
