#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打生产网关 HTTP 端口(8010->8000)，模拟 FoloToy 真实请求，验证固化后容器联网作答。"""
import json, urllib.request

URL = "http://127.0.0.1:8000/v1/chat/completions"
SYS = ("你系阿晴，20岁广州西关少女，温柔沉静、含蓄俏皮，慢语速，纯粤语口语。"
       "绝对唔准夹杂普通话、英文字母、繁体字、Markdown、emoji；短句；用「嘅㗎啦咯喎」等语气词。")

def ask(q):
    print("\n" + "=" * 55)
    print("问：", q)
    payload = {
        "model": "THUDM/GLM-4-9B-0414",
        "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": q}],
        "max_tokens": 420, "temperature": 0.6, "stream": False,
    }
    req = urllib.request.Request(URL, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=90)
        d = json.loads(r.read().decode("utf-8"))
        print("HTTP", r.status, "答：\n" + d["choices"][0]["message"]["content"])
    except Exception as e:
        print("FAIL", type(e).__name__, str(e)[:200])

ask("而家广州天气几度啊？")
ask("今日有咩新闻？")
