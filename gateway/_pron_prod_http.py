# -*- coding: utf-8 -*-
"""固化后生产容器端到端：打 HTTP /v1/chat/completions，确认返回文本已正音。
不触发联网意图（问日常话），验证 tts_pron 在对话返回链路真实生效。"""
import json, urllib.request

URL = "http://127.0.0.1:8000/v1/chat/completions"
SYS = ("你系阿晴，20岁广州西关女仔，温柔沉静、含蓄俏皮，用纯正广州粤语同街坊倾偈，"
       "慢语速，唔好讲普通话、唔好英文、唔好emoji、唔好Markdown。")

def ask(q):
    body = json.dumps({
        "model": "THUDM/GLM-4-9B-0414",
        "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": q}],
        "max_tokens": 180, "temperature": 0.7,
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=120).read())
    c = r["choices"][0]["message"]["content"]
    print("Q:", q)
    print("A:", c)
    # 返回文本不应含未正音的易误读写法（模型可能本来就写繁体，那也无妨；关键是若有简体会被转）
    bad = [w for w in ("机会", "合适", "听日", "听朝", "听晚", "越秀区") if w in c]
    print("未正音残留:", bad if bad else "无 ✅")
    print("-" * 60)

ask("你听日有咩计划啊？不如我哋去越秀区行街，揾个机会饮茶。")
ask("你觉得呢个安排合唔合适？")
