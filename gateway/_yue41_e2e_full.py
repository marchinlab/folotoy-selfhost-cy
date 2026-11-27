# -*- coding: utf-8 -*-
"""抓 E2E A 完整答复，定位全部「评价资料/自我叮嘱」元评论变体（不落盘）。"""
import sys, json, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
body = json.dumps({
    "model": "Qwen/Qwen3-30B-A3B-Instruct-2507", "stream": False,
    "messages": [
        {"role": "system", "content": "【角色:history_teacher】\n你系一位耐心嘅初中历史老师，用纯正广州粤语口语讲课。讲完可以轻轻追问一句，睇下学生明唔明。"},
        {"role": "user", "content": "同我讲下唐朝开国嘅历史，讲详细啲。"},
    ],
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/v1/chat/completions", data=body,
    headers={"Content-Type": "application/json", "X-No-Record": "1"})
a = json.loads(urllib.request.urlopen(req, timeout=120).read())["choices"][0]["message"]["content"]

print("=== 完整答复（%d 字）===" % len(a))
print(a)
print("\n=== 逐句扫描含「资料/清楚/唔好/乱/敢/照」嘅元话语候选 ===")
import re
for i, seg in enumerate(re.split(r"(?<=[。！？\n])", a)):
    if re.search(r"资料|資料|清楚|唔好|唔敢|乱|亂|照|据|據|来源|来源|写明", seg):
        print("  [%d] %s" % (i, seg.strip()))
