# -*- coding: utf-8 -*-
"""话题锚定单元自测：判定函数 + payload 改写，覆盖误伤场景。"""
import llm_gateway as g

# (问句, 历史文本, 期望是否需要隔离)
CASES = [
    # 核心 bug：介绍非本地地点 + 历史讲过广州景点 -> 隔离
    ("介绍庐山", "介绍下广州塔 广州塔喺海珠区 陈家祠 沙面", True),
    ("同我介绍下黄山", "讲讲广州塔同沙面", True),
    ("讲下西湖嘅历史", "头先介绍咗陈家祠 荔湾", True),
    ("介绍一下泰山", "广州塔 小蛮腰 珠江新城", True),
    # 唔该隔离：问广州本地 -> 交返 gz 新闻，唔郁
    ("介绍广州塔", "讲下庐山", False),
    ("介绍下陈家祠", "黄山", False),
    # 唔该隔离：问句本身带明确地名（多城市/天气类会走别的intent，呢度只测判定）
    ("介绍下北京嘅故宫", "广州塔", True),   # 北京非本地，历史有广州 -> 隔离（合理）
    # 唔该隔离：历史冇广州景点 -> 唔使隔离
    ("介绍庐山", "你好呀 今日想倾乜 讲个笑话", False),
    ("介绍庐山", "", False),
    # 唔该隔离：唔似地名/介绍对象 -> 唔隔离
    ("讲下个笑话", "广州塔 沙面", False),
    ("讲下你自己", "广州塔", False),
    ("介绍下呢个游戏", "广州塔", False),
    # 唔该隔离：纯闲聊/承接
    ("佢有咩好玩", "广州塔 沙面", False),
    ("再讲多啲", "广州塔", False),
]

print("=== 判定函数 extract_intro_place / is_place_anchor_needed ===")
fail = 0
for q, hist, want in CASES:
    place = g.extract_intro_place(q)
    msgs = [{"role": "system", "content": "阿晴人设"},
            {"role": "user", "content": hist or "（无历史）"},
            {"role": "user", "content": q}]
    got = g.is_place_anchor_needed(q, msgs)
    ok = (got == want)
    if not ok:
        fail += 1
    print("  %s q=%-18r place=%-8r need=%s (expect %s)" %
          ("OK " if ok else "FAIL", q, place, got, want))

print()
print("=== payload 改写：隔离后只剩 system + 当前 user，且带正向尾注 ===")
payload = {"messages": [
    {"role": "system", "content": "阿晴人设prompt"},
    {"role": "user", "content": "介绍下广州塔"},
    {"role": "assistant", "content": "广州塔喺海珠区，小蛮腰。"},
    {"role": "user", "content": "介绍下陈家祠"},
    {"role": "assistant", "content": "陈家祠喺荔湾，西关建筑。"},
    {"role": "user", "content": "介绍庐山"},
]}
q = "介绍庐山"
assert g.is_place_anchor_needed(q, payload["messages"]), "应判定需隔离"
g.apply_place_anchor(payload, q, False)
ms = payload["messages"]
print("  改后消息数:", len(ms), "(期望 2)")
print("  角色序列:", [m["role"] for m in ms])
print("  system 保留:", ms[0]["content"])
print("  user 尾注:", ms[-1]["content"][-120:])
assert len(ms) == 2 and ms[0]["role"] == "system" and ms[1]["role"] == "user"
assert "庐山" in ms[1]["content"] and "专注" in ms[1]["content"]

print()
print("=== 隔离时温度压制：0.95 -> 0.6；低温不动 ===")
for t0, want in ((0.95, 0.6), (0.85, 0.6), (0.6, 0.6), (0.4, 0.4)):
    p3 = {"temperature": t0, "messages": [
        {"role": "system", "content": "人设"},
        {"role": "user", "content": "介绍庐山"},
        {"role": "assistant", "content": "广州塔喺海珠区"},
        {"role": "user", "content": "介绍黄山"},
    ]}
    g.apply_place_anchor(p3, "介绍黄山", False)
    print("  %.2f -> %.2f (期望 %.2f) %s" % (t0, p3["temperature"], want,
          "OK" if p3["temperature"] == want else "FAIL"))
    assert p3["temperature"] == want

print()
print("=== 无 system 兜底：唔隔离，保住人设 ===")
p2 = {"messages": [{"role": "user", "content": "介绍庐山"}]}
changed = g.apply_place_anchor(p2, "介绍庐山", False)
print("  changed=", changed, "（期望 False，无 system 唔郁）")
assert changed is False

print()
print("=== FAIL 数:", fail, "===")
assert fail == 0
print("ALL_UNIT_PASS")
