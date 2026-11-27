# -*- coding: utf-8 -*-
"""复现：用 4 号英语老师真实 prompt 走生产 8010，打印当前实际双语输出。
测试记录会写进落盘卷，跑完单独清理。"""
import json, urllib.request, time, subprocess

GW = "http://127.0.0.1:8010/v1/chat/completions"
roles = json.load(open("/opt/folotoy/config/roles.json", encoding="utf-8"))
p4 = roles["4"]["prompt"]
p1 = roles["1"]["prompt"]

cases = [
    ("4号·纯英文文法", p4, "What's the difference between affect and effect?", False),
    ("4号·中英混合", p4, "affect 同 effect 有乜唔同？", False),
    ("4号·时态讲解", p4, "present continuous 点用？举两个例句。", False),
    ("4号·英文问答", p4, "How do I use 'used to' in a sentence?", False),
    ("4号·单词释义", p4, "abundant 呢个词咩意思？", False),
    ("1号·纯英文(对照)", p1, "What's the difference between affect and effect?", False),
]

for name, prompt, q, stream in cases:
    body = {
        "model": "THUDM/GLM-4-9B-0414",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": q},
        ],
        "stream": stream,
        "max_tokens": 1800,
    }
    req = urllib.request.Request(
        GW, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=90)
        d = json.loads(r.read().decode("utf-8", "replace"))
        ans = d["choices"][0]["message"]["content"]
    except Exception as e:
        ans = "ERR %s %s" % (type(e).__name__, e)
    dur = time.time() - t
    # 粗判：是否含粤语口音字、英文、字数
    yue = [c for c in "嘅唔系佢哋啲噉嘢唔好畀讲下呀啦咯嘞" if c in ans]
    en = sum(1 for w in ans.split() if any(ch.isascii() and ch.isalpha() for ch in w))
    print("=" * 72)
    print("[%s] q=%r  %.1fs  字数=%d  英文词=%d  粤语字=%r"
          % (name, q, dur, len(ans), en, "".join(yue)))
    print(ans)
    print()

print("#" * 72)
print("=== 网关本次判定日志 ===")
lg = subprocess.run(
    "docker logs --since 3m folotoy_llm_gateway_1 2>&1 | "
    "grep -E 'REQ |POLISH|SUBJECT|KNOWLEDGE|INJECT|CONV_SAVED|HARD_MAX|MODEL_OVERRIDE' | tail -60",
    shell=True, capture_output=True, text=True, errors="replace").stdout
print(lg or "(无)")
