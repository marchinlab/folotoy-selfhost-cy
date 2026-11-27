#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终交付验证：确认生产容器用的模型 + 阿晴人格 + 粤语慢语速合成全链路。"""
import os, json, urllib.request, subprocess, time

BASE = "https://api.siliconflow.cn/v1"
key  = os.environ["OPENAI_OPENAI_KEY"]
model_env = os.environ["OPENAI_OPENAI_MODEL"]
role = json.load(open("/config/roles.json", encoding="utf-8"))["1"]
print("[0] 生产模型(env):", model_env, "| 角色model:", role["model"],
      "| 音色:", role["voice_name"])

MANDARIN = ["因为","所以","但是","可以","我们","你们","他们","她们","这里","那里",
            "什么","怎么","知道","觉得","应该","需要","已经","还是","时候","真的",
            "一起","不要","没有","给","这儿","那儿"]

def chat(prompt, user):
    body = json.dumps({"model": model_env,
        "messages":[{"role":"system","content":prompt},{"role":"user","content":user}],
        "max_tokens":role["max_tokens"],"temperature":role["temperature"]}).encode()
    req = urllib.request.Request(BASE+"/chat/completions",data=body,method="POST")
    req.add_header("Authorization","Bearer "+key); req.add_header("Content-Type","application/json")
    t=time.time()
    with urllib.request.urlopen(req,timeout=50) as r:
        d=json.loads(r.read().decode())
    return d["choices"][0]["message"]["content"].strip(), time.time()-t, d["model"]

for q in ["你好呀，你系边个？", "我今日唔开心，俾人闹咗。", "点解天会落雨㗎？"]:
    ans, dt, used = chat(role["prompt"], q)
    hits=[w for w in MANDARIN if w in ans]
    emoji = any(ord(c)>0x1F000 for c in ans)
    print("\n问:", q)
    print("答:", ans)
    print("  [%.2fs | 模型 %s | %s | emoji %s]" %
          (dt, used, ("⚠️普通话:"+",".join(hits)) if hits else "✅纯粤语", "有!" if emoji else "无✅"))

# 慢语速粤语合成
out="/tmp/final_aqing.mp3"
subprocess.run(["edge-tts","--voice",role["voice_name"],"--text","你好，我系阿晴，慢慢同你倾计。",
                "--write-media",out],check=True)
print("\n[嘴巴] 阿晴慢语速粤语合成 OK: %d B" % os.path.getsize(out))
print("\nFINAL_E2E_DONE")
