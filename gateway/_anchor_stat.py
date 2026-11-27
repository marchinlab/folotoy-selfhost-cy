# -*- coding: utf-8 -*-
"""统计三策在【高温度 0.95（最恶劣，模拟玩具端）】下介绍庐山的广州污染率。
每组跑 6 次，统计答案里出现广州系地名/旧话题的次数。
  A 带广州景点历史、无锚定        （复现 bug 基线）
  B 带历史 + v2 强锚定            （纯 prompt 抑制）
  C 清空历史（人设+本轮问题，纯净）（物理移除惯性）
"""
import json, urllib.request, re

BASE = "http://127.0.0.1:8010/v1/chat/completions"
roles = json.load(open("../config/roles.json", encoding="utf-8"))
SYS = roles["3"]["prompt"]
MODEL = roles["3"]["model"]
TEMP = 0.95   # 最恶劣

SPOT_HIST = [
    {"role": "user", "content": "介绍下广州塔"},
    {"role": "assistant", "content": "广州塔喺海珠区，人称小蛮腰，高六百几米，夜晚灯光亮起就好靓，顶层有观景台可以俯瞰成个珠江新城。"},
    {"role": "user", "content": "介绍下陈家祠"},
    {"role": "assistant", "content": "陈家祠喺荔湾区，系清代陈氏书院，木雕砖雕灰塑都好出名，系广州西关建筑嘅代表，而家做咗民间工艺博物馆。"},
    {"role": "user", "content": "介绍下沙面"},
    {"role": "assistant", "content": "沙面系珠江边一个人工岛，清末民初有好多洋楼，而家变成步行街，啲人钟意去嗰边散步影相，气氛好悠闲。"},
]

GZ = ("广州", "珠江", "羊城", "穗", "西关", "小蛮腰", "越秀", "海珠", "荔湾",
      "沙面", "陈家祠", "广州塔", "天河", "东山口", "上下九", "泮塘", "越秀",
      "广东", "白云山", "北京路")

V2 = (
    "【本轮唯一主题·最高优先级】用户而家呢一句问嘅对象系【庐山】。你今次嘅答案要讲【庐山】本身："
    "佢嘅地理位置、有咩睇、有咩历史特色、值唔值得去。唔确定就老实讲唔知，千祈唔好乱作。"
    "【隔离历史】头先几轮倾过嘅城市同景点全部系旧话题，同【庐山】冇关系，唔好带出嚟、唔好做对比，"
    "直接净系讲【庐山】。照旧简体中文地道粤语口语。"
)


def call(messages):
    body = json.dumps({"model": MODEL, "messages": messages,
                       "max_tokens": 500, "temperature": TEMP, "stream": False},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=120).read())
    return d["choices"][0]["message"]["content"]


def run(name, maker, n=6):
    hit = 0
    hits = []
    for i in range(n):
        txt = call(maker())
        found = [g for g in GZ if g in txt]
        if found:
            hit += 1
            hits.append((i + 1, found, txt.strip().replace("\n", " ")[:90]))
        else:
            hits.append((i + 1, [], txt.strip().replace("\n", " ")[:40]))
    print("=" * 72)
    print("%s  污染 %d/%d" % (name, hit, n))
    for i, f, s in hits:
        print("  #%d %s %s" % (i, ("[污染:" + "/".join(f) + "]") if f else "[ok]", s))
    print()
    return hit


q = {"role": "user", "content": "介绍庐山"}
run("A 带广州景点历史 · 无锚定", lambda: [{"role": "system", "content": SYS}] + SPOT_HIST + [q])
run("B 带历史 + v2 强锚定", lambda: [{"role": "system", "content": SYS}] + SPOT_HIST
    + [{"role": "user", "content": V2}, q])
run("C 清空历史（人设+本轮问题）", lambda: [{"role": "system", "content": SYS}, q])
print("=== STAT_DONE temperature=%.2f ===" % TEMP)
