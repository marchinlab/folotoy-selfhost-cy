# -*- coding: utf-8 -*-
"""验证「本轮主题锚定」能否压住历史广州景点 few-shot 带来的话题惯性。
走本地 8010 网关（透传：q 仍是最后一条真 user，锚定作为独立 user 消息插在它前面，
不会污染网关的意图识别）。对照 / v1 / v2 × 庐山 / 黄山。
"""
import json, urllib.request

BASE = "http://127.0.0.1:8010/v1/chat/completions"
roles = json.load(open("../config/roles.json", encoding="utf-8"))
r = roles["3"]
SYS = r["prompt"]

SPOT_HIST = [
    {"role": "user", "content": "介绍下广州塔"},
    {"role": "assistant", "content": "广州塔喺海珠区，人称小蛮腰，高六百几米，夜晚灯光亮起就好靓，顶层有观景台可以俯瞰成个珠江新城。"},
    {"role": "user", "content": "介绍下陈家祠"},
    {"role": "assistant", "content": "陈家祠喺荔湾区，系清代陈氏书院，木雕砖雕灰塑都好出名，系广州西关建筑嘅代表，而家做咗民间工艺博物馆。"},
    {"role": "user", "content": "介绍下沙面"},
    {"role": "assistant", "content": "沙面系珠江边一个人工岛，清末民初有好多洋楼，而家变成步行街，啲人钟意去嗰边散步影相，气氛好悠闲。"},
]


def anchor_v1(t):
    return (
        "【本轮提问·最高优先级】我呢一句问嘅系关于【%s】。请净系围绕【%s】本身答："
        "佢喺边、有咩特色、有咩值得讲、点解值得去；讲唔知就坦率讲唔知，唔好凭印象乱作。"
        "我哋头先倾过嘅所有嘢，无论系边个城市、边啲景点定系新闻，同【%s】呢一题一律无关，"
        "唔好引用、唔好联想、唔好拎嚟比较、亦唔好先讲「唔系边度」再纠正，直接由【%s】讲起。"
        "照旧全程简体中文地道粤语口语、温柔沉静、短句。" % (t, t, t, t)
    )


def anchor_v2(t):
    return (
        "【本轮唯一主题·最高优先级】用户而家呢一句问嘅对象系【%s】。"
        "你今次嘅答案第一句就要讲【%s】本身，全部内容净系可以讲【%s】："
        "佢嘅地理位置、有咩睇、有咩历史特色、值唔值得去。唔确定就老实讲唔知，千祈唔好乱作。\n"
        "【严厉隔离历史】头先几轮倾过嘅城市同景点（无论讲过边度）全部系旧话题，"
        "同【%s】冇任何关系：绝对唔好带出嚟、唔好做对比、唔好用佢哋开场、"
        "更加唔好先讲一句「唔系嗰个城市」再纠正——呢种搬旧话题嘅讲法一律唔准。"
        "就好似头先乜都冇讲过噉，直接、净系讲【%s】。"
        "【语言】照旧简体中文地道粤语口语，温柔沉静、短句。" % (t, t, t, t, t)
    )


def call(messages, tag):
    body = json.dumps({
        "model": r["model"], "messages": messages,
        "max_tokens": 600, "temperature": r["temperature"], "stream": False,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=120).read())
    txt = d["choices"][0]["message"]["content"]
    print("=" * 72)
    print(tag)
    print("-" * 72)
    print(txt)
    print()
    return txt


for topic in ("庐山", "黄山"):
    q = "介绍" + topic
    prefix = [{"role": "system", "content": SYS}] + SPOT_HIST
    call(prefix + [{"role": "user", "content": q}],
         "对照(无锚定) · " + q)
    call(prefix + [{"role": "user", "content": anchor_v1(topic)}, {"role": "user", "content": q}],
         "v1 锚定 · " + q)
    call(prefix + [{"role": "user", "content": anchor_v2(topic)}, {"role": "user", "content": q}],
         "v2 强锚定 · " + q)
