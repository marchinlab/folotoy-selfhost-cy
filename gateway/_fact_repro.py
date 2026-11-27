# -*- coding: utf-8 -*-
"""v1.26 复现探针：证明「英语老师 / 英文 auto 路由 默认不联网 -> 专名凭记忆乱改」。
打生产 8010 真实链路，打印 net 落盘标记 + 返回文本专名 + 正文。测完要清落盘。"""
import json, re, time, urllib.request

BASE = "http://127.0.0.1:8010"
_op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
AQING_SYS = "【角色:aqing_chat】\n你叫阿晴，20岁广州西关女仔。全程只用粤语，唔中英夹杂。"
ENG_SYS = "【角色:english_teacher】\nYou are a patient and professional middle-school English teacher. 你是一位有耐心、专业的初中英语老师。"
CASES = [
    ("4号键-英语老师-上海地标", ENG_SYS,
     "用英文介绍上海嘅标志性景点，特别要讲到东方明珠塔，每句附中文翻译"),
    ("1号键-auto英文-上海地标", AQING_SYS,
     "用英文介绍上海嘅标志性景点，特别要讲到东方明珠塔，每句附中文翻译"),
    ("4号键-英语老师-东方明珠多高", ENG_SYS,
     "用英文同我讲东方明珠塔有几高，边年起好嘅"),
]

def call(system, user):
    p = {"model": "Qwen/Qwen3-30B-A3B-Instruct-2507", "stream": False,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]}
    r = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=json.dumps(p, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    t = time.time()
    with _op.open(r, timeout=180) as f:
        d = json.load(f)
    return d["choices"][0]["message"]["content"], time.time() - t

for name, system, user in CASES:
    try:
        ans, dt = call(system, user)
        names = re.findall(r"东方明珠|明珠塔|上海塔|Oriental Pearl|Pearl Tower|Shanghai Tower|Jin Mao", ans)
        print("\n=== %s (%.1fs) ===" % (name, dt))
        print("专名命中:", names)
        print("正文:", ans[:340].replace("\n", " / "))
    except Exception as e:
        print("\n=== %s === ERR %r" % (name, e))

print("\n=== 落盘 net 标记（呢个系「有冇联网」嘅铁证）===")
try:
    with _op.open(BASE + "/logs?limit=8", timeout=15) as f:
        d = json.load(f)
    for r in d.get("items", []):
        print("  btn=%-2s role=%-16s net=%-5s auto_en=%-5s q=%s" %
              (r.get("btn"), r.get("role"), r.get("net"), r.get("auto_en"), r.get("q", "")[:30]))
except Exception as e:
    print("logs ERR", repr(e))
