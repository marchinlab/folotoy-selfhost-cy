# -*- coding: utf-8 -*-
"""v1.30 生产真链路 E2E：打生产 8010，验证 9 词正音喺粤语路径全部落地 + 一对多零误伤。
★判定落喺网关返回文本（fix 后）：
  - 净力→淨力、陈桥→陳桥、发达→發達、质量→質量、一齐→一齊、
    组队→組隊、火药→火藥、文风→聞風。
  - 一对多零误伤：头发/发现/语文/文化/课程/过程 保持原样。
  - 旧链路：单词→單词、机会→机會、机会/合适 等 v1.24~v1.28 全在。
模型输出有随机性，正音断言用「若出现简体目标则 FAIL，否则视为模型未用该词」；
但一对多护字断言恒严格（出现错转即 FAIL）。本机 --noproxy 直达。"""
import json, sys, urllib.request

BASE = "http://127.0.0.1:8010/v1/chat/completions"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
AQING = "【角色:aqing_chat】\n你叫阿晴，20岁广州西关女仔。全程只用粤语，唔中英夹杂，唔用 emoji/Markdown。"
PHYS = "【角色:physics_teacher】\n你系初中物理老师，用粤语讲课，先联网核实知识，1000字内。"
HIST = "【角色:history_teacher】\n你系初中历史老师，用粤语讲课，先联网核实史实，1000字内。"
CHINESE = "【角色:chinese_teacher】\n你系初中语文老师，用粤语讲课，先联网核实知识，1000字内。"

# (name, system, user, stream, 必含简体则FAIL 的目标词列表)
CASES = [
    ("物理-净力质量", PHYS,
     "用粤语准确讲下牛顿第二定律，务必讲清楚「净力」同「质量」两个概念，写出 F=ma。", True,
     [("净力", "淨力"), ("质量", "質量")]),
    ("物理-一齐", PHYS,
     "用粤语解释下点解力、质量同加速度要「一齐」考虑，举生活例子。", True,
     [("一齐", "一齊")]),
    ("历史-陈桥火药", HIST,
     "用粤语讲下北宋历史，务必提到「陈桥兵变」同「火药」，讲下佢哋嘅影响。", True,
     [("陈桥", "陳桥"), ("火药", "火藥")]),
    ("历史-组队发达过程", HIST,
     "用粤语讲王安石变法同北宋商业，务必用到「组队」「发达」同「过程」呢几个词。", False,
     [("组队", "組隊"), ("发达", "發達")]),
    ("语文-文风", CHINESE,
     "用粤语讲下北宋「文风」鼎盛，点解唐宋八大家有六位出喺北宋，务必用到「文风」呢个词。", True,
     [("文风", "聞風")]),
    ("闲聊-一对多护字", AQING,
     "用粤语讲下：毛发、发现、语文、文化、课程、过程 呢几个词嘅意思，各讲一句。", True,
     []),  # 只验护字，下面单独查
    ("闲聊-旧链路零回归", AQING,
     "用粤语讲下：机会、合适、地区、单词、简单 呢几个词，各举一个用法。", True,
     []),
]

# 一对多/双关：这些词出现简体形态【本就正确】，若被误转成繁即 FAIL
PROTECT = [("头发", "头發"), ("发现", "發现"), ("语文", "語聞"), ("文化", "聞化"),
           ("课程", "課cheng"), ("过程", "過程"), ("好听", "好聽"), ("看见", "看見")]


def call(system, user, stream):
    payload = {"model": "Qwen/Qwen3-30B-A3B-Instruct-2507", "stream": stream,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    req = urllib.request.Request(BASE, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    deltas, frames, done = [], 0, False
    with _opener.open(req, timeout=180) as r:
        if not stream:
            d = json.loads(r.read().decode("utf-8", "replace"))
            return (d["choices"][0]["message"].get("content") or ""), 1, True
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if line == "data: [DONE]":
                done = True; break
            if not line.startswith("data:"):
                continue
            js = line[5:].strip()
            if not js: continue
            try: d = json.loads(js)
            except Exception: continue
            frames += 1
            for ch in d.get("choices", []):
                c = (ch.get("delta") or {}).get("content")
                if c: deltas.append(c)
    return "".join(deltas), frames, done


RES = []
def ck(name, cond, extra=""):
    RES.append(bool(cond)); print("  %-4s %-34s %s" % ("PASS" if cond else "FAIL", name, extra))


ALL = ""
for name, system, user, stream, targets in CASES:
    print("\n== %s ==" % name)
    try:
        ans, frames, done = call(system, user, stream)
    except Exception as e:
        ck(name + " 请求", False, repr(e)[:90]); continue
    ALL += "\n" + ans
    print("  回复:", repr(ans[:240]))
    print("  帧数=%d done=%s 字数=%d" % (frames, done, len(ans)))
    ck(name + " 到齐[DONE]", done and len(ans) > 0)
    for simp, trad in targets:
        if simp in ans:
            ck(name + " 「%s」须正音" % simp, False, "仍留简体「%s」" % simp)
        else:
            ck(name + " 「%s」无残留" % simp, True, "(模型未用或已正音)")

print("\n== 一对多/双关护字（全文扫描，恒严格）==")
for keep, wrong in PROTECT:
    if wrong in ALL:
        ck("护 %s 唔变 %s" % (keep, wrong), False, "检测到误转「%s」" % wrong)
    else:
        ck("护 %s 无误转" % keep, True)

print("\n== 旧链路正音（若模型用到则须落地）==")
for simp, trad in [("单词", "單词"), ("机会", "机會"), ("合适", "合適"), ("地区", "地區")]:
    if simp in ALL:
        ck("旧链 「%s」须正音" % simp, False, "仍留简体「%s」" % simp)
    else:
        ck("旧链 「%s」无残留" % simp, True)

p = sum(RES)
print("\n=== DAN30_E2E: %d/%d %s ===" % (p, len(RES), "ALL_PASS" if p == len(RES) else "HAS_FAIL"))
sys.exit(0 if p == len(RES) else 1)
