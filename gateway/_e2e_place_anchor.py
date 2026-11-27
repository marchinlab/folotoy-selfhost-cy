# -*- coding: utf-8 -*-
"""端到端验证（部署 1.18 后跑）：直接打 8010，让网关自己的话题锚定逻辑生效。
每组高温度 0.95 跑 5 次，统计广州系污染率。
  A 带广州景点历史 + 问庐山（期望网关隔离 -> 0 污染）
  B 带广州景点历史 + 问黄山（同上）
  C 回归：问广州本地新闻（期望不误隔离，仍走 gz 注入）
  D 回归：问天气（期望不误隔离，仍走 weather 数值注入）
  E 回归：读诗（期望 poem 豁免不受影响）
"""
import json, urllib.request, re, sys

BASE = "http://127.0.0.1:8010/v1/chat/completions"
roles = json.load(open("../config/roles.json", encoding="utf-8"))
SYS = roles["3"]["prompt"]
MODEL = roles["3"]["model"]

SPOT_HIST = [
    {"role": "system", "content": SYS},
    {"role": "user", "content": "介绍下广州塔"},
    {"role": "assistant", "content": "广州塔喺海珠区，人称小蛮腰，高六百几米，顶层有观景台可以俯瞰成个珠江新城。"},
    {"role": "user", "content": "介绍下陈家祠"},
    {"role": "assistant", "content": "陈家祠喺荔湾区，系清代陈氏书院，木雕砖雕灰塑都好出名，系广州西关建筑嘅代表。"},
    {"role": "user", "content": "介绍下沙面"},
    {"role": "assistant", "content": "沙面系珠江边一个人工岛，清末民初有好多洋楼，而家变成步行街，气氛好悠闲。"},
]
GZ = ("广州", "珠江", "羊城", "西关", "小蛮腰", "越秀", "海珠", "荔湾", "沙面",
      "陈家祠", "广州塔", "天河", "上下九", "广东", "白云山", "北京路")


def call(messages, temp=0.95, max_tokens=500):
    body = json.dumps({"model": MODEL, "messages": messages,
                       "max_tokens": max_tokens, "temperature": temp, "stream": False},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=120).read())
    return d["choices"][0]["message"]["content"]


def stat(name, base_msgs, q, n=5):
    hit = 0
    lines = []
    for i in range(n):
        msgs = list(base_msgs) + [{"role": "user", "content": q}]
        txt = call(msgs)
        found = [g for g in GZ if g in txt]
        if found:
            hit += 1
        lines.append("  #%d %s %s" % (i + 1, ("[污染:" + "/".join(found) + "]") if found else "[ok]",
                                      txt.strip().replace("\n", " ")[:70]))
    print("=" * 72)
    print("%s  污染 %d/%d" % (name, hit, n))
    print("\n".join(lines))
    print()
    return hit


a = stat("A 带广州景点历史 · 介绍庐山（应隔离）", SPOT_HIST, "介绍庐山")
b = stat("B 带广州景点历史 · 介绍黄山（应隔离）", SPOT_HIST, "同我介绍下黄山")

print("=" * 72)
print("C 回归 · 广州本地新闻（唔好误隔离，仍应答广州本地事）")
c = call([{"role": "system", "content": SYS}] + SPOT_HIST[1:] +
         [{"role": "user", "content": "广州本地有咩新闻"}], temp=0.6, max_tokens=600)
print(c.strip()[:300])
print()

print("=" * 72)
print("D 回归 · 问天气（唔好误隔离，仍应答实况数值）")
d = call([{"role": "system", "content": SYS}] + SPOT_HIST[1:] +
         [{"role": "user", "content": "广州今日天气点样"}], temp=0.6, max_tokens=400)
print(d.strip()[:300])
print()

print("=" * 72)
print("E 回归 · 读诗豁免（poem 模式不受隔离影响）")
e = call([{"role": "system", "content": SYS}] + SPOT_HIST[1:] +
         [{"role": "user", "content": "读下「同是天涯沦落人」俾我听"}], temp=0.6, max_tokens=400)
print(e.strip()[:300])
print()

print("=== E2E_DONE A_pollute=%d B_pollute=%d ===" % (a, b))
sys.exit(0 if (a == 0 and b == 0) else 2)
