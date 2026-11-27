#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实测精简版阿晴人设喂给 Qwen2.5-7B：粤语纯度、守规矩、延迟。"""
import os, json, urllib.request, urllib.error, time

BASE = "https://api.siliconflow.cn/v1"
key  = os.environ["OPENAI_OPENAI_KEY"]
roles = json.load(open("/tmp/roles_aqing.json", encoding="utf-8"))

def chat(prompt, user, max_tokens=200):
    body = json.dumps({
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "messages": [{"role": "system", "content": prompt},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens, "temperature": 0.8,
    }).encode()
    req = urllib.request.Request(BASE + "/chat/completions", data=body, method="POST")
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/json")
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode())
        return d["choices"][0]["message"]["content"], time.time()-t, d["usage"]["prompt_tokens"]
    except urllib.error.HTTPError as e:
        return "HTTP %d %s" % (e.code, e.read().decode()[:200]), time.time()-t, 0
    except Exception as e:
        return "ERR " + repr(e)[:200], time.time()-t, 0

tests = [
    ("1", "你好呀，你系边个？"),
    ("5", "我今日唔开心，俾人闹咗。"),
    ("3", "点解天会落雨㗎？"),
    ("7", "讲个笑话我听啦。"),
    ("6", "你平时中意做乜呀？"),
]
for rid, q in tests:
    ans, dt, pt = chat(roles[rid]["prompt"], q, roles[rid]["max_tokens"])
    print("\n=== %s ===" % roles[rid]["name"])
    print("问:", q)
    print("答:", ans.strip())
    print("[%.2fs | prompt %d tok]" % (dt, pt))
print("\nDONE")
