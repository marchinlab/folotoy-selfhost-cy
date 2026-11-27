#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""粤语闭环探针：edge-tts 合成两个粤语女声 -> SenseVoice STT 识别回文字。
在 folotoy 容器内跑（环境变量自动继承）：
  docker cp yue_probe.py <container>:/tmp/ && docker exec <container> python3 /tmp/yue_probe.py
"""
import os, json, urllib.request, urllib.error, subprocess, uuid

TXT = "你好，我系阿晴，广州西关人，今日想同你倾下偈，慢慢讲都唔紧要。"
VOICES = ["zh-HK-HiuMaanNeural", "zh-HK-HiuGaaiNeural"]

base  = os.environ["OPENAI_WHISPER_API_BASE"].rstrip("/")
key   = os.environ["OPENAI_WHISPER_KEY"]
model = os.environ["OPENAI_WHISPER_MODEL"]
print("BASE=%s\nMODEL=%s" % (base, model))

def synth(voice, text, out):
    subprocess.run(["edge-tts", "--voice", voice, "--text", text,
                    "--write-media", out], check=True)
    return os.path.getsize(out)

def stt(path):
    data = open(path, "rb").read()
    b = "----probe" + uuid.uuid4().hex
    body = b""
    body += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"a.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n" % b).encode()
    body += data + b"\r\n"
    body += ("--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n%s\r\n"
             % (b, model)).encode()
    body += ("--%s--\r\n" % b).encode()
    req = urllib.request.Request(base + "/audio/transcriptions", data=body, method="POST")
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "multipart/form-data; boundary=" + b)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return "HTTP %d %s" % (e.code, e.read().decode("utf-8", "replace")[:300])
    except Exception as e:
        return "ERR " + repr(e)[:200]

for v in VOICES:
    f = "/tmp/%s.mp3" % v
    try:
        n = synth(v, TXT, f)
        print("\n[%s] synth OK %d B" % (v, n))
    except Exception as e:
        print("\n[%s] synth FAIL %r" % (v, e))
        continue
    print("[%s] STT => %s" % (v, stt(f)))

print("\nDONE")
