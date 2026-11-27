# -*- coding: utf-8 -*-
"""v1.27 单元回归：流式 SSE 整段清洗回填，保住英文词间空格 + \n 断句。
核心不变量：concat(流式回填后所有 delta.content) == polish_english(整段原文)。
部署前后都可跑（纯本地，唔打网络）。
"""
import json, re, sys
import yue_polish as Y
try:
    import tts_pron
except Exception:
    tts_pron = None

def make_sse(deltas):
    lines = []
    for c in deltas:
        d = {"id": "x", "object": "chat.completion.chunk",
             "choices": [{"index": 0, "delta": {"content": c}, "finish_reason": None}]}
        lines += ["data: " + json.dumps(d, ensure_ascii=False), ""]
    fin = {"id": "x", "object": "chat.completion.chunk",
           "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
    lines += ["data: " + json.dumps(fin, ensure_ascii=False), "", "data: [DONE]", ""]
    return "\n".join(lines).encode("utf-8")

def parse(body):
    out, frames, done = [], 0, False
    for line in body.decode("utf-8").split("\n"):
        st = line.strip()
        if st == "data: [DONE]":
            done = True; continue
        if not st.startswith("data:"):
            continue
        js = st[5:].strip()
        if not js: continue
        d = json.loads(js); frames += 1
        for ch in d.get("choices", []):
            out.append((ch.get("delta") or {}).get("content") or "")
    return "".join(out), frames, done

CASES = [
    ("纯英文例句", ["I ", "am ", "planning ", "to ", "visit ", "Shanghai ", "next ", "month."]),
    ("中英混排", ["例句：", "She ", "is ", "reading ", "a ", "book.", " ", "她", "正在", "读书", "。", "\n", "They ", "are ", "playing ", "football."]),
    ("引号短语", ['用"', "plan ", "to ", "do", '"表示将来，"', "be ", "famous ", "for", '"介绍特色。']),
    ("换行断句", ["第一句：", "Hello ", "world.", "\n", "第二句：", "Good ", "morning.", "\n\n", "完。"]),
    ("emoji+元话语", ["根据", "资料", "显示：", "✅", "👉", "I ", "love ", "English."]),
    ("多choice", None),   # 特殊构造，下面单独处理
]

OK = []
def ck(name, cond, extra=""):
    OK.append(bool(cond)); print("  %-4s %-30s %s" % ("PASS" if cond else "FAIL", name, extra))

for name, ds in CASES:
    if ds is None:
        continue
    body = make_sse(ds)
    whole = "".join(ds)
    expect = Y.polish_english(whole)
    got, frames, done = parse(Y.polish_english_sse(body)[0])
    ck(name + " concat==整段清洗", got == expect, repr(got[:60]))
    ck(name + " 保留[DONE]帧", done)
    ck(name + " 帧数不归零", frames >= 1, "frames=%d" % frames)
    if "hello" in whole.lower():
        ck(name + " 英文词间空格", "Hello world." in got and "Good morning." in got)
    if "planning" in whole:
        ck(name + " 无粘词", "I am planning to visit" in got and "Iamplanning" not in got)
    if "✅" in whole or "根据" in whole:
        ck(name + " emoji/元话语清除", "✅" not in got and "根据资料" not in got)

# 多 choice（理论上行，验证 ch_idx 回填正确）
multi = []
for c in ["I ", "am ", "happy."]:
    d = {"choices": [{"index": 0, "delta": {"content": "占位"}, "finish_reason": None},
                     {"index": 1, "delta": {"content": c}, "finish_reason": None}]}
    multi += ["data: " + json.dumps(d, ensure_ascii=False), ""]
multi += ["data: [DONE]", ""]
out_body = Y.polish_english_sse("\n".join(multi).encode("utf-8"))[0].decode("utf-8")
c0, c1 = [], []
for line in out_body.split("\n"):
    st = line.strip()
    if not st.startswith("data:") or st == "data: [DONE]":
        continue
    js = st[5:].strip()
    if not js: continue
    for ci, ch in enumerate(json.loads(js).get("choices", [])):
        (c0 if ci == 0 else c1).append((ch.get("delta") or {}).get("content") or "")
# choice[0] 占位应原样、choice[1] 三帧正文应拼成完整英文（索引回填精准、无粘词）
ck("多choice 第1路占位未误改", "".join(c0) == "占位占位占位", repr("".join(c0)))
ck("多choice 第2路正文完整", "".join(c1) == "I am happy.", repr("".join(c1)))

# 幂等：整段清洗结果再走一次 SSE 回填，应稳定
whole = "I am planning to visit Shanghai. 她打算去上海。"
b = make_sse(list(whole))
r1, _, _ = parse(Y.polish_english_sse(b)[0])
r2, _, _ = parse(Y.polish_english_sse(make_sse(list(r1)))[0])
ck("幂等(二次回填稳定)", r1 == r2)

# ---------- 粤语角色流式整段清洗（v1.27 同源修复：修流式漏粤语化）----------
print("\n---------- 粤语角色流式（polish_cantonese_sse）----------")
YUE_CASES = [
    ("词级粤语化", ["同", "学", "们", "，", "今", "天", "我", "们", "学", "习", "现", "在", "牛", "顿", "定", "律", "。"],
     ("我哋", "今日", "而家"), ("我们", "今天", "现在")),
    ("正音听日会区", ["听", "日", "我", "去", "越", "秀", "区", "，", "呢", "个", "机", "会", "好", "合", "适", "。"],
     ("汀日", "越秀區", "机會", "合適"), ()),
    ("英文乱码清除", ["呢", "个", "市", "场", "entry", "Set", "好", "乱", "，", "specifically", "咁", "讲", "。"],
     ("市场好乱",), ("entry", "specifically")),
    ("中文断句", ["第", "一", "，", "牛", "顿", "定", "律", "。", "\n", "第", "二", "，", "加速度", "系", "矢量", "。"],
     ("\n", "第二"), ()),
]
for name, ds, must_have, must_not in YUE_CASES:
    whole = "".join(ds)
    want = tts_pron.fix(Y.polish(whole)) if tts_pron else Y.polish(whole)
    got, frames, done = parse(Y.polish_cantonese_sse(make_sse(ds), poem=False, fixer=(tts_pron.fix if tts_pron else None))[0])
    ck("粤语·" + name + " 流式==非流式", got == want, repr(got[:50]))
    ck("粤语·" + name + " [DONE]保留", done)
    for w in must_have:
        ck("  含 %r" % w, w in got)
    for w in must_not:
        ck("  无 %r" % w, w not in got)
# 诗词模式逐字保留
pd = ["同", "是", "天", "涯", "沦", "落", "人", "，", "何", "必", "曾", "相", "识", "。"]
pwant = tts_pron.fix(Y.polish("".join(pd), poem=True)) if tts_pron else Y.polish("".join(pd), poem=True)
pgot, _, _ = parse(Y.polish_cantonese_sse(make_sse(pd), poem=True, fixer=(tts_pron.fix if tts_pron else None))[0])
ck("诗词模式逐字保留", pgot == pwant and "同是天涯沦落人" in pgot, repr(pgot))

# ---------- 学科公式符号白名单（v1.27：物理/化学老师讲公式唔好念丢变量）----------
print("\n---------- 学科公式符号保留 ----------")
FORMULA_KEEP = ["公式 ", "F=ma", "，", "力", "等于", "质量", "乘", "加速度", "。"]
fgot, _, _ = parse(Y.polish_cantonese_sse(make_sse(FORMULA_KEEP), fixer=(tts_pron.fix if tts_pron else None))[0])
ck("物理公式 F=ma 保留", "F=ma" in fgot, repr(fgot))
for tok, whole in [("pH", "pH 值小于 7 系酸性"), ("sin", "三角函数 sin cos tan"),
                   ("NaOH", "氢氧化钠 NaOH 系碱"), ("Ek", "动能 Ek 同势能 Ep")]:
    ck("公式符号 %s 保留" % tok, tok in Y.polish(whole), repr(Y.polish(whole)))
# 防误伤：扩白名单后真乱码仍须清掉
for g in ("giao", "entrySet", "specifically", "involve"):
    ck("真乱码 %s 仍清除" % g, g not in Y.polish("市场.entrySet，specifically involve giao 乱晒"))
# 流式公式同样保住（整段回填路径）
fgot2, _, _ = parse(Y.polish_cantonese_sse(make_sse(list("pH 系酸碱度，公式 F=ma 讲力。")),
                                            fixer=(tts_pron.fix if tts_pron else None))[0])
ck("流式公式 pH/F=ma 保留", "pH" in fgot2 and "F=ma" in fgot2, repr(fgot2))

n = len(OK); p = sum(OK)
print("\n===== 结果 %d/%d %s =====" % (p, n, "ALL PASS ✔" if p == n else "有FAIL ✘"))
sys.exit(0 if p == n else 1)
