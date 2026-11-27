# -*- coding: utf-8 -*-
"""A/B 尾注文案：旧(1.19 净专注) vs 新(加讲解员身份，纯正向)，长文高温度。
手动构造隔离后 messages（system 人设 + 长文addon + 带尾注的 user），直接打 8010，
避免依赖已部署版本。各跑 8 次统计广州系污染。"""
import json, urllib.request

BASE = "http://127.0.0.1:8010/v1/chat/completions"
roles = json.load(open("../config/roles.json", encoding="utf-8"))
R = roles["3"]
SYS, MODEL = R["prompt"], R["model"]
LONG_ADDON = "\n\n【用户想听详细版】讲长啲，600至1000字，有条理展开，全程粤语口语短句。"
GZ = ("广州", "珠江", "羊城", "西关", "老广", "广东", "穗", "荔湾", "越秀", "海珠",
      "小蛮腰", "陈家祠", "沙面", "天河", "白云山", "北京路", "珠三角")


def old_note(place, q):
    return (q + "\n\n【本轮提问·请专注】我呢一句问嘅系【%s】，请直接讲【%s】本身："
            "佢喺边、有咩睇、有咩值得讲，讲唔知就坦率讲唔知，唔好凭旧印象乱作。"
            "我哋头先倾过嘅其他话题，无论讲过边个城市、边啲景点，同呢一题都唔相干，"
            "唔好引用、唔好拎嚟比较，直接由【%s】讲起。照旧全程简体中文地道粤语口语、短句。"
            % (place, place, place))


def new_note(place, q):
    return (q + "\n\n【本轮提问·请专注】我呢一句问嘅系【%s】，请直接讲【%s】本身："
            "佢喺边、有咩睇、有咩值得讲，讲唔知就坦率讲唔知，唔好凭旧印象乱作。"
            "我哋头先倾过嘅其他话题，无论讲过边个城市、边啲景点，同呢一题都唔相干，"
            "唔好引用、唔好拎嚟比较，直接由【%s】讲起。\n"
            "【讲解员身份】呢一答你只系一个介绍紧【%s】嘅讲解员，全程内容净系围绕"
            "【%s】嘅地理位置同风景特色展开，唔好扯去任何你熟落嘅本地地方做比较、"
            "亦唔好讲自己嘅出身背景，就净系讲眼前呢个地方。"
            "照旧全程简体中文地道粤语口语、温柔沉静、短句。"
            % (place, place, place, place, place))


def call(msgs):
    body = json.dumps({"model": MODEL, "messages": msgs, "max_tokens": 1100,
                       "temperature": 0.95, "stream": False}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())["choices"][0]["message"]["content"]


def run(name, note_fn, q, place, n=5):
    hit = 0
    detail = []
    for i in range(n):
        msgs = [{"role": "system", "content": SYS + LONG_ADDON},
                {"role": "user", "content": note_fn(place, q)}]
        txt = call(msgs)
        found = [g for g in GZ if g in txt]
        if found:
            hit += 1
            detail.append("#%d[%s]%s" % (i + 1, "/".join(found), txt.strip().replace("\n", " ")[:60]))
    print("=" * 70)
    print("%s :: %s  污染 %d/%d" % (name, q, hit, n))
    for d in detail:
        print("   ", d)
    return hit


for q, place in (("详细介绍下庐山", "庐山"), ("详细讲下黄山", "黄山")):
    o = run("旧尾注(1.19)", old_note, q, place)
    nn = run("新尾注(1.20)", new_note, q, place)
    print("   >> 旧 %d  vs  新 %d" % (o, nn))
print("=== TAILNOTE_AB_DONE ===")
