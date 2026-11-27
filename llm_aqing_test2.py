#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""加固版阿晴：重点复测陪伴/答疑/闲聊的粤语纯度（检测普通话残留词）。"""
import os, json, urllib.request, urllib.error, time, re

BASE = "https://api.siliconflow.cn/v1"
key  = os.environ["OPENAI_OPENAI_KEY"]
roles = json.load(open("/tmp/roles_aqing.json", encoding="utf-8"))

# 典型普通话残留词，命中即算跑偏
MANDARIN = ["这种", "这样", "那样", "什么", "怎么", "因为", "所以", "但是", "如果",
            "我们", "你们", "他们", "这里", "那里", "哪里", "知道", "觉得", "可以",
            "应该", "需要", "已经", "还是", "时候", "真的", "一起", "深呼吸", "平静",
            "我在这里", "不要", "没有", "一个", "一下", "看看", "告诉"]

def chat(prompt, user, max_tokens):
    body = json.dumps({"model":"Qwen/Qwen2.5-7B-Instruct",
        "messages":[{"role":"system","content":prompt},{"role":"user","content":user}],
        "max_tokens":max_tokens,"temperature":0.8}).encode()
    req = urllib.request.Request(BASE+"/chat/completions",data=body,method="POST")
    req.add_header("Authorization","Bearer "+key); req.add_header("Content-Type","application/json")
    t=time.time()
    try:
        with urllib.request.urlopen(req,timeout=40) as r:
            d=json.loads(r.read().decode())
        return d["choices"][0]["message"]["content"],time.time()-t
    except Exception as e:
        return "ERR "+repr(e)[:150],time.time()-t

tests=[("5","我今日唔开心，俾人闹咗。"),("3","点解天会落雨㗎？"),
       ("1","你好呀，你系边个？"),("2","讲个睡前古仔我听。")]
for rid,q in tests:
    ans,dt=chat(roles[rid]["prompt"],q,roles[rid]["max_tokens"])
    hits=[w for w in MANDARIN if w in ans]
    flag="⚠️ 普通话残留:"+",".join(hits) if hits else "✅ 纯粤语"
    print("\n=== %s | %s ==="%(roles[rid]["name"],flag))
    print("答:",ans.strip())
    print("[%.2fs]"%dt)
print("\nDONE")
