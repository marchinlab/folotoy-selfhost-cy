#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""落地后端到端：读角色1阿晴prompt -> LLM生成粤语回复 -> 包装器慢语速粤语合成。
在 folotoy 容器内跑。"""
import os, json, urllib.request, subprocess, time

BASE = "https://api.siliconflow.cn/v1"
key  = os.environ["OPENAI_OPENAI_KEY"]
role = json.load(open("/config/roles.json", encoding="utf-8"))["1"]

# 1) 大脑：阿晴人格生成粤语回复
body = json.dumps({
    "model": role["model"],
    "messages": [{"role": "system", "content": role["prompt"]},
                 {"role": "user", "content": "你好呀，你系边个？"}],
    "max_tokens": role["max_tokens"], "temperature": role["temperature"],
}).encode()
req = urllib.request.Request(BASE + "/chat/completions", data=body, method="POST")
req.add_header("Authorization", "Bearer " + key)
req.add_header("Content-Type", "application/json")
t = time.time()
with urllib.request.urlopen(req, timeout=40) as r:
    reply = json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()
print("[1] 阿晴回复(%.2fs): %s" % (time.time()-t, reply))

# 2) 嘴巴：包装器(慢语速) 用角色音色合成
out = "/tmp/e2e_aqing.mp3"
subprocess.run(["edge-tts", "--voice", role["voice_name"], "--text", reply,
                "--write-media", out], check=True)
print("[2] 慢语速粤语合成 OK: %d B, voice=%s" % (os.path.getsize(out), role["voice_name"]))

# 3) 对比：.real 无 rate vs 包装器有 rate，验证慢速真生效（同一文本）
txt = "你好，我系阿晴，广州西关女仔，今日天气好，我哋慢慢倾下偈啦。"
subprocess.run(["edge-tts.real", "--voice", role["voice_name"], "--text", txt,
                "--write-media", "/tmp/e2e_normal.mp3"], check=True)
subprocess.run(["edge-tts", "--voice", role["voice_name"], "--text", txt,
                "--write-media", "/tmp/e2e_slow.mp3"], check=True)
n = os.path.getsize("/tmp/e2e_normal.mp3"); s = os.path.getsize("/tmp/e2e_slow.mp3")
print("[3] 语速对比: 常规 %d B -> 慢速 %d B (+%.0f%%，越大越慢)" % (n, s, (s-n)*100.0/n))

# 4) 确认包装器记录了服务端真实调用参数
log = open("/tmp/edge-tts-calls.log", encoding="utf-8", errors="replace").read().strip().split("\n")
print("[4] edge-tts 调用日志(最近3条):")
for line in log[-3:]:
    print("   ", line)
print("\nE2E_DONE")
