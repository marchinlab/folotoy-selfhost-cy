#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测硅基流动 key 的 LLM / STT 可用性，定位 402 是模型级还是账户级。"""
import os, json, urllib.request, urllib.error

key = os.environ.get("OPENAI_WHISPER_KEY") or os.environ.get("OPENAI_OPENAI_KEY")
BASE = "https://api.siliconflow.cn/v1"

def post(path, body, ctype="application/json"):
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]
    except Exception as e:
        return -1, repr(e)[:200]

def get(path):
    req = urllib.request.Request(BASE + path, method="GET")
    req.add_header("Authorization", "Bearer " + key)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:
        return -1, repr(e)[:200]

print("== /user/info (账户余额) ==")
s, b = get("/user/info")
print(s, b[:500])

print("\n== /chat/completions Qwen2.5-7B ==")
body = json.dumps({"model": "Qwen/Qwen2.5-7B-Instruct",
                   "messages": [{"role": "user", "content": "讲句粤语问候"}],
                   "max_tokens": 30}).encode()
s, b = post("/chat/completions", body)
print(s, b[:400])

print("\n== /audio/transcriptions SenseVoiceSmall (最小 mp3) ==")
# 复用已生成的粤语 mp3
p = "/tmp/zh-HK-HiuMaanNeural.mp3"
if os.path.exists(p):
    import uuid
    bd = "----q" + uuid.uuid4().hex
    data = open(p, "rb").read()
    body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n" % bd).encode()
            + data + b"\r\n"
            + ("--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nFunAudioLLM/SenseVoiceSmall\r\n" % bd).encode()
            + ("--%s--\r\n" % bd).encode())
    s, b = post("/audio/transcriptions", body, "multipart/form-data; boundary=" + bd)
    print(s, b[:400])
else:
    print("no mp3, skip")
