#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比候选大脑的粤语纯度+延迟+是否守规矩，挑阿晴最佳模型。
候选都走硅基流动 OpenAI 兼容接口。"""
import os, json, urllib.request, urllib.error, time

BASE = "https://api.siliconflow.cn/v1"
key  = os.environ["OPENAI_OPENAI_KEY"]
role = json.load(open("/config/roles.json", encoding="utf-8"))

CANDIDATES = [
    "Qwen/Qwen2.5-7B-Instruct",       # 当前
    "Qwen/Qwen3-8B",                   # 新一代 8B
    "THUDM/GLM-4-9B-0414",            # 智谱 9B 中文强
    "Qwen/Qwen2.5-14B-Instruct",      # 更大，可能要钱，测了看
]
MANDARIN = ["因为","所以","但是","可以","我们","你们","他们","她们","这里","那里",
            "什么","怎么","知道","觉得","应该","需要","已经","还是","时候","真的",
            "一起","不要","没有","一个","一下","给","这儿","那儿","觉得","一起"]

def chat(model, prompt, user, max_tokens=200):
    body = json.dumps({"model":model,
        "messages":[{"role":"system","content":prompt},{"role":"user","content":user}],
        "max_tokens":max_tokens,"temperature":0.7}).encode()
    req = urllib.request.Request(BASE+"/chat/completions",data=body,method="POST")
    req.add_header("Authorization","Bearer "+key); req.add_header("Content-Type","application/json")
    t=time.time()
    try:
        with urllib.request.urlopen(req,timeout=50) as r:
            d=json.loads(r.read().decode())
        return d["choices"][0]["message"]["content"].strip(), time.time()-t, None
    except urllib.error.HTTPError as e:
        return "", time.time()-t, "HTTP %d %s"%(e.code,e.read().decode()[:120])
    except Exception as e:
        return "", time.time()-t, repr(e)[:120]

# 用最容易翻车的答疑+讲古来考
qs = [("3","点解天会落雨㗎？"),("2","讲个短睡前古仔，唔好长。")]
for m in CANDIDATES:
    print("\n########## %s ##########" % m)
    total_hits=0; total_dt=0; ok=True
    for rid,q in qs:
        ans,dt,err = chat(m, role[rid]["prompt"], q, role[rid]["max_tokens"])
        if err:
            print("  [%s] 不可用: %s"%(rid,err)); ok=False; break
        hits=[w for w in MANDARIN if w in ans]
        total_hits+=len(hits); total_dt+=dt
        print("  [%s %s] %.1fs %s"%(rid,("⚠️"+",".join(hits)) if hits else "✅纯粤语",dt,""))
        print("     ",ans[:110].replace("\n"," "))
    if ok:
        print("  >> 合计普通话残留 %d 处, 平均 %.1fs/条"%(total_hits,total_dt/len(qs)))
print("\nDONE")
