# -*- coding: utf-8 -*-
"""v1.29 生产真链路 E2E：打生产 8010，验证斜杠/IPA 音标清理生效。
★判定落喺【网关返回畀大脑嘅播报文本】：绝无任何 '/'、无 IPA 乱码、英文例句/断句完整、
  公式转中文读法、旧链路(粤语化/正音/英文)零回归。另验证 /logs 落盘保留完整音标(双轨)。
  本机 --noproxy 直达。部署 1.29 后先至跑(旧镜像会 FAIL)。"""
import json, re, sys, urllib.request

BASE = "http://127.0.0.1:8010/v1/chat/completions"
LOGS = "http://127.0.0.1:8010/logs"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
AQING_SYS = "【角色:aqing_chat】\n你叫阿晴，20岁广州西关女仔。全程只用粤语，唔中英夹杂。"
ENG_SYS = ("【角色:english_teacher】\nYou are a patient and professional middle-school "
           "English teacher. 你是一位有耐心、专业的初中英语老师，用标准普通话 + 中英双语讲解，"
           "英文例句保留英文并附国际音标 /.../ 同中文翻译。")
PHYS_SYS = "【角色:physics_teacher】\n你系初中物理老师，用粤语讲课，先联网核实知识，1000字内。"

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

OK = []
def ck(name, cond, extra=""):
    OK.append(bool(cond)); print("  %-4s %-32s %s" % ("PASS" if cond else "FAIL", name, extra))

# IPA 专用字符（播报文本绝唔应该再出现）
IPA_CHARS = re.compile("[\u0250-\u02af\u1d00-\u1dff\u02b0-\u02ffˈˌːˑʼɑɒæʌɔɜəɪʊøœɐɯɤɵʃʒŋθðçʝɲɳɽɾʔ]")

CASES = [
    ("4号键-流式-音标斜杠", ENG_SYS,
     "用中英双语解释 point 呢个单词嘅意思，俾两个英文例句同国际音标，再讲下点样背单词。", True),
    ("4号键-非流式-音标斜杠", ENG_SYS,
     "用中英双语讲下 vocabulary 同 word 嘅区别，各举一个英文例句同音标。", False),
    ("1号键-auto英文-音标斜杠", AQING_SYS,
     "用英文介绍去上海旅行，列三个英文例句同中文翻译，再注明每个例句嘅关键词同音标。", True),
    ("1号键-粤语闲聊-零回归", AQING_SYS,
     "用粤语同我讲下细路仔点样背单词会记得牢，顺便举两个英文单词做例子。", True),
    ("5号键-物理公式斜杠", PHYS_SYS,
     "用粤语讲下牛顿第二定律，写出公式同单位（例如 m/s²），讲个生活例子。", True),
]

for name, system, user, stream in CASES:
    print("\n== %s ==" % name)
    try:
        ans, frames, done = call(system, user, stream)
    except Exception as e:
        ck(name + " 请求", False, repr(e)[:100]); continue
    print("  播报:", repr(ans[:300]))
    ck(name + " 到齐", done and len(ans) > 0, "帧=%d 字=%d" % (frames, len(ans)))
    # 核心 1：播报文本绝无斜杠
    ck(name + " 播报无 '/'" , "/" not in ans, "残留=%s" % re.findall(r".{0,6}/.{0,6}", ans)[:3])
    # 核心 2：播报文本绝无 IPA 乱码
    ipa_hit = IPA_CHARS.findall(ans)
    ck(name + " 播报无 IPA 乱码", not ipa_hit, "IPA=%s" % ipa_hit[:10])
    is_eng = ("english_teacher" in system) or ("auto英文" in name) or ("闲聊" in name)
    if is_eng:
        en_words = re.findall(r"[A-Za-z]{2,}", ans)
        ck(name + " 英文词完整(>=5)", len(en_words) >= 5, "英文词=%d" % len(en_words))
        glued = [b for b in re.findall(r"[A-Za-z][A-Za-z'’\-]*", ans) if len(b) >= 16]
        ck(name + " 无英文粘词", not glued, "超长块=%s" % glued[:4])
        ck(name + " 英文词间空格保留", " " in ans or "\n" in ans)
    else:
        ck(name + " 粤语关键字", any(k in ans for k in ("系", "嘅", "我哋", "你", "咗", "啲", "唔", "讲")))
        if "物理" in name:
            ck("物理 单位转「每」", "每" in ans, "含每=%s" % ("每" in ans))

# 双轨验证：落盘 /logs 要保留完整音标（含 '/'），家长睇到教学稿
print("\n== 双轨：落盘保留完整音标 ==")
try:
    with _opener.open(LOGS, timeout=30) as r:
        logs = json.loads(r.read().decode("utf-8", "replace"))
    items = logs.get("items", [])
    a_with_ipa = [x for x in items if "/" in (x.get("a") or "") and
                  IPA_CHARS.search(x.get("a") or "")]
    ck("落盘有含音标的完整教学稿", bool(a_with_ipa),
       "含音标记录=%d / 总=%d" % (len(a_with_ipa), len(items)))
    if a_with_ipa:
        sample = a_with_ipa[0]["a"]
        ck("落盘音标未被删(双轨)", "/" in sample and bool(IPA_CHARS.search(sample)),
           "样例=%r" % sample[:120])
except Exception as e:
    ck("落盘 /logs 读取", False, repr(e)[:100])

n_ok = sum(OK)
print("\n==== SLASH_E2E: %d/%d %s ====" % (n_ok, len(OK), "ALL_PASS" if n_ok == len(OK) else "HAS_FAIL"))
sys.exit(0 if n_ok == len(OK) else 1)
