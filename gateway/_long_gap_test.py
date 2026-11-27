# -*- coding: utf-8 -*-
"""查口子：长文问句「详细介绍下庐山」带广州历史时，因 do_POST 里 not want_long
跳过了话题隔离，是否又被带去广州？高温度跑 6 次。"""
import json, urllib.request

BASE = "http://127.0.0.1:8010/v1/chat/completions"
roles = json.load(open("../config/roles.json", encoding="utf-8"))
SYS, MODEL = roles["3"]["prompt"], roles["3"]["model"]
SPOT = [
    {"role": "system", "content": SYS},
    {"role": "user", "content": "介绍下广州塔"},
    {"role": "assistant", "content": "广州塔喺海珠区，人称小蛮腰，顶层观景台可以俯瞰成个珠江新城，夜晚灯光好靓。"},
    {"role": "user", "content": "介绍下陈家祠"},
    {"role": "assistant", "content": "陈家祠喺荔湾区，系广州西关建筑嘅代表，木雕砖雕好出名。"},
    {"role": "user", "content": "介绍下沙面"},
    {"role": "assistant", "content": "沙面系珠江边人工岛，清末民初洋楼多，而家系步行街。"},
]
GZ = ("广州", "珠江", "羊城", "西关", "小蛮腰", "越秀", "海珠", "荔湾", "沙面",
      "陈家祠", "广州塔", "天河", "广东", "白云山", "北京路")


def call(q):
    body = json.dumps({"model": MODEL, "messages": SPOT + [{"role": "user", "content": q}],
                       "max_tokens": 1100, "temperature": 0.95, "stream": False},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())["choices"][0]["message"]["content"]


for q in ("详细介绍下庐山", "详细讲下黄山"):
    hit = 0
    print("=" * 70)
    print("q =", q)
    for i in range(6):
        txt = call(q)
        found = [g for g in GZ if g in txt]
        if found:
            hit += 1
        print("  #%d %s %s" % (i + 1, ("[污染:" + "/".join(found) + "]") if found else "[ok]",
                               txt.strip().replace("\n", " ")[:85]))
    print("  >> 污染 %d/6" % hit)
print("=== LONG_GAP_DONE ===")
