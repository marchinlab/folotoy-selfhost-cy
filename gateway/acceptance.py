#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最终验收：多题材真实联网问答，扫描四类残留是否清零。"""
import json, re, urllib.request

QS = ["详细啲讲下今日新闻", "今日天气点样？详细啲讲", "详细讲下进博会同经济", "讲下生活小贴士，详细啲"]
SYS = "你系广州西关阿晴，20岁，全程用简体中文地道粤语口语，短句，唔好夹英文字母同Markdown。"
# 只列「粤语绝不会用原形」的普通话词；「因为/所以/如果/可以/需要/希望/大家/目的」等
# 粤语本身也用，不算残留（强转反而生硬），故不列入。
MAND = ["他们", "她们", "我们", "你们", "现在", "这个", "这些", "那个", "这里", "那里",
        "什么", "怎么", "为什么", "哪些", "多少", "没有", "很", "而且", "知道", "马上", "立刻"]
TRAD = "進會華係讓國場歷們屆緊時陰醫藥達維標點遊戲點櫃檯臺麵鬆瞭總氣親舊舉"
# 白名单字母词（广州人口语真会讲、且无简洁中文替代）：不算残留
KEEP_EN = {"UFC", "NBA", "AI", "APP", "GDP", "GDP", "5G", "PM", "COVID", "WHO", "AQI"}

def ask(q):
    body = {"model": "THUDM/GLM-4-9B-0414",
            "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": q}],
            "max_tokens": 700}
    req = urllib.request.Request("http://127.0.0.1:8000/v1/chat/completions",
                                 data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=85).read().decode())["choices"][0]["message"]["content"]

all_clean = True
for q in QS:
    t = ask(q)
    mand = [w for w in MAND if w in t]
    trad = sorted(set(re.findall("[" + TRAD + "]", t)))
    en = [w for w in re.findall(r"[A-Za-zÀ-ɏ\u0370-\u04ff]{2,}", t) if w.upper() not in KEEP_EN]
    md = re.findall(r"\*\*|\x60|^\s*#{1,6}\s|^\s*[-*+]\s|^\s*\d+\.\s", t, re.M)
    ok = not (mand or trad or en or md)
    all_clean &= ok
    print("\n=== %s ===" % q)
    print("字数=%d  普通话=%s  繁体=%s  英文=%s  Markdown=%s  -> %s" % (
        len(t), mand or "无", trad or "无", en or "无", md or "无", "干净 ✓" if ok else "有残留 ✘"))
    print(t[:200])

print("\n=== 总结: %s ===" % ("全部题材四类残留清零 ✔" if all_clean else "仍有残留需修 ✘"))
