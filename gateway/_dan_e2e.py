# -*- coding: utf-8 -*-
"""v1.28 生产真链路 E2E：打生产 8010，验证「单词」正音喺英文路径(4号键/1号auto)
同粤语路径都生效，且英文正文/音标/断句零影响、旧链路零回归。
★判定落喺网关返回文本：fix 后必须系「單词」(单已正音)、唔再有简体「单词」。
  本机 --noproxy 直达。部署 1.28 后先至跑(旧镜像会 FAIL)。"""
import json, re, sys, urllib.request

BASE = "http://127.0.0.1:8010/v1/chat/completions"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
AQING_SYS = "【角色:aqing_chat】\n你叫阿晴，20岁广州西关女仔。全程只用粤语，唔中英夹杂。"
ENG_SYS = ("【角色:english_teacher】\nYou are a patient and professional middle-school "
           "English teacher. 你是一位有耐心、专业的初中英语老师，用标准普通话 + 中英双语讲解，"
           "英文例句保留英文并附中文翻译。")
PHYS_SYS = "【角色:physics_teacher】\n你系初中物理老师，用粤语讲课，先联网核实知识，1000字内。"

def call(system, user, stream):
    payload = {"model": "Qwen/Qwen3-30B-A3B-Instruct-2507", "stream": stream,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    req = urllib.request.Request(BASE, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    deltas, frames, done = [], 0, False
    with _opener.open(req, timeout=150) as r:
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

OK = []
def ck(name, cond, extra=""):
    OK.append(bool(cond)); print("  %-4s %-30s %s" % ("PASS" if cond else "FAIL", name, extra))

# 引导模型一定用到「单词」呢个字，方便验正音；英文路径要求带英文例句/音标。
CASES = [
    ("4号键-流式-单词正音", ENG_SYS,
     "用中英双语解释 point 呢个单词嘅意思，俾两个英文例句同音标，再讲下点样背单词。", True),
    ("4号键-非流式-单词正音", ENG_SYS,
     "用中英双语讲下 vocabulary 同 word 嘅区别，各举一个英文例句同音标。提下记单词嘅方法。", False),
    ("1号键-auto英文-单词正音", AQING_SYS,
     "用英文介绍去上海旅行，列三个英文例句同中文翻译，再注明每个例句嘅关键词同音标。", True),
    ("1号键-粤语闲聊-单词正音", AQING_SYS,
     "用粤语同我讲下细路仔点样背单词会记得牢，顺便举两个英文单词做例子。", True),
    ("5号键-物理-旧链路零回归", PHYS_SYS,
     "用粤语讲下牛顿第二定律，写出公式同单位，讲个生活例子。", True),
]

for name, system, user, stream in CASES:
    print("\n== %s ==" % name)
    try:
        ans, frames, done = call(system, user, stream)
    except Exception as e:
        ck(name + " 请求", False, repr(e)[:90]); continue
    print("  回复:", repr(ans[:260]))
    print("  帧数=%d done=%s 字数=%d" % (frames, done, len(ans)))
    ck(name + " 到齐[DONE]", done and len(ans) > 0)
    is_eng = "english_teacher" in system or "auto" in name
    # 核心：任何出现「单词」嘅上下文，网关必须已正音成「單词」，唔留简体「单词」
    if "单词" in ans:
        ck(name + " 单词已正音(不留简体)", False, "仍有简体「单词」")
    else:
        ck(name + " 无简体单词残留", True, "(或模型未用该词)")
    # 正音命中迹象：回复里【出现「单」类字】就必须已正音成「單」；
    # 若模型根本没用该字（如只列例句/音标），则跳过呢条断言（非功能问题，避免误报）。
    has_dan = ("单" in ans) or ("單" in ans)
    ck(name + " 正音表有命中", (not has_dan) or ("單" in ans),
       "含單=%s 用到单类字=%s" % ("單" in ans, has_dan))
    if is_eng:
        en_words = re.findall(r"[A-Za-z]{2,}", ans)
        ck(name + " 英文例句完整(>=5词)", len(en_words) >= 5, "英文词=%d" % len(en_words))
        glued = [b for b in re.findall(r"[A-Za-z][A-Za-z'’\-]*", ans) if len(b) >= 16]
        ck(name + " 无英文粘词", not glued, "超长块=%s" % glued[:4])
        ck(name + " 断句\\n保留", "\n" in ans or "。" in ans)
    else:
        ck(name + " 粤语关键字", any(k in ans for k in ("系", "嘅", "我哋", "你", "咗", "啲", "唔", "讲")))

print("\n==== DAN_E2E: %d/%d %s ====" %
      (sum(OK), len(OK), "ALL_PASS" if all(OK) else "HAS_FAIL"))
sys.exit(0 if all(OK) else 1)
