# -*- coding: utf-8 -*-
"""复现「介绍庐山变广州」：对比 干净上下文 / 带广州历史对话 两种情形。
打本地网关 127.0.0.1:8010（网关自己会注入 upstream key 并做粤语化后处理）。
"""
import json, urllib.request

BASE = "http://127.0.0.1:8010/v1/chat/completions"
roles = json.load(open("../config/roles.json", encoding="utf-8"))
r = roles["3"]           # 阿晴·答疑
sys_prompt = r["prompt"]


def call(msgs, tag):
    body = json.dumps({
        "model": r["model"],
        "messages": msgs,
        "max_tokens": 600,
        "temperature": r["temperature"],
        "stream": False,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    raw = urllib.request.urlopen(req, timeout=120).read()
    d = json.loads(raw)
    txt = d["choices"][0]["message"]["content"]
    print("=" * 72)
    print(tag)
    print("-" * 72)
    print(txt)
    print()
    return txt


hist_gz = [
    {"role": "user", "content": "讲下今日广州本地新闻"},
    {"role": "assistant", "content": "好呀，今日广州有几条街坊值得知嘅新闻，南沙有新嘅交通规划，越秀区旧楼加装电梯又推进咗，荔湾泮塘嘅花市都准备紧。"},
    {"role": "user", "content": "今日广州天气点样？"},
    {"role": "assistant", "content": "而家广州气温二十几度，体感微热，今日同听日都大致天晴，出门记得带把遮，热就饮多啲水。"},
    {"role": "user", "content": "读首静夜思俾我听"},
    {"role": "assistant", "content": "床前明月光，疑是地上霜。举头望明月，低头思故乡。"},
]

SPOT_HIST = [
    {"role": "user", "content": "介绍下广州塔"},
    {"role": "assistant", "content": "广州塔喺海珠区，人称小蛮腰，高六百几米，夜晚灯光亮起就好靓，顶层有观景台可以俯瞰成个珠江新城。"},
    {"role": "user", "content": "介绍下陈家祠"},
    {"role": "assistant", "content": "陈家祠喺荔湾区，系清代陈氏书院，木雕砖雕灰塑都好出名，系广州西关建筑嘅代表，而家做咗民间工艺博物馆。"},
    {"role": "user", "content": "介绍下沙面"},
    {"role": "assistant", "content": "沙面系珠江边一个人工岛，清末民初有好多洋楼，而家变成步行街，啲人钟意去嗰边散步影相，气氛好悠闲。"},
]

NEWS_HIST = [
    {"role": "user", "content": "讲下今日广州本地新闻"},
    {"role": "assistant", "content": "今日广州要闻有：南沙新区交通规划推进，越秀旧楼加装电梯，荔湾花市筹备，广州台报道咗几单民生事，街坊都几关注。"},
    {"role": "user", "content": "广州本地新闻"},
    {"role": "assistant", "content": "广州日报新花城同广视网今日报道，广州各区有唔同民生工程，海珠、天河、白云都有新进展，市政府促消费活动都开场喇。"},
    {"role": "user", "content": "广州天气点样"},
    {"role": "assistant", "content": "而家广州二十几度，体感微热，今日同听日大致天晴，落雨机会低，出门带把遮稳妥啲。"},
]

call([{"role": "system", "content": sys_prompt}] + SPOT_HIST +
     [{"role": "user", "content": "介绍庐山"}],
     "D · 三轮「介绍广州景点」few-shot 后：介绍庐山")

call([{"role": "system", "content": sys_prompt}] + NEWS_HIST +
     [{"role": "user", "content": "介绍庐山"}],
     "E · 大段广州新闻/天气历史后：介绍庐山")

call([{"role": "system", "content": sys_prompt}] +
     [{"role": "user", "content": "介绍广州"},
      {"role": "assistant", "content": "广州系广东省会，两千几年历史，别名羊城花城，西关荔湾、越秀北京路、天河珠江新城各有风味，粤菜早茶同骑楼街巷最出名。"}] +
     [{"role": "user", "content": "介绍庐山"}],
     "F · 一轮「介绍广州」后：介绍庐山")

call([{"role": "system", "content": sys_prompt}] + SPOT_HIST +
     [{"role": "user", "content": "介绍黄山"}],
     "G · 三轮广州景点 few-shot 后：介绍黄山")
