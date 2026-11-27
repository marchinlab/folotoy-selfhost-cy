#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓一段长文，打印所有含 Markdown/英文/乱码的行，用于定位净化规则。"""
import json, re, urllib.request

body = {
    "model": "THUDM/GLM-4-9B-0414",
    "messages": [
        {"role": "system", "content": "你系广州西关阿晴，全程简体中文地道粤语口语。"},
        {"role": "user", "content": "详细啲讲下今日天气同生活小贴士"},
    ],
    "max_tokens": 700,
}
req = urllib.request.Request("http://127.0.0.1:8000/v1/chat/completions",
                             data=json.dumps(body, ensure_ascii=False).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
t = json.loads(urllib.request.urlopen(req, timeout=80).read().decode())["choices"][0]["message"]["content"]
print("=== 全文 ===")
print(t)
print("\n=== 可疑行 ===")
for i, line in enumerate(t.splitlines()):
    if re.search(r"[A-Za-z\u0370-\u04ff]{2,}|\*\*|^[#>\-]|\x60", line):
        print("L%d: %s" % (i, line[:140]))
