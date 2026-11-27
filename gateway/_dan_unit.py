# -*- coding: utf-8 -*-
"""v1.28 单元回归：单->單 正音 + 英文路径接 fixer（唔伤英文/音标/断句）+ 旧链路零回归。
纯本地 import，唔打网络。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts_pron, yue_polish

P = F = 0
def ok(name, cond):
    global P, F
    if cond:
        P += 1
    else:
        F += 1
        print("  FAIL:", name)

print("=== 1) tts_pron.fix 正音表（只转易误读字，非全繁简表）===")
# 注意：fix 只替换 FIXES 表中的易误读字，其他字（词/机/简/名）保持原样，
# 唔好误当全繁简转换表写断言（v1.25 踩过同类坑：断言写死写错，非功能 bug）。
cases = [
    ("单词", "單词"), ("单位", "單位"), ("简单", "简單"), ("名单", "名單"),
    ("单元", "單元"), ("单字", "單字"), ("背单词", "背單词"),
    ("机会", "机會"), ("合适", "合適"), ("地区", "地區"), ("听日", "汀日"),
]
for a, b in cases:
    ok("fix %s->%s" % (a, b), tts_pron.fix(a) == b)
ok("fix 非str 原样", tts_pron.fix(123) == 123 and tts_pron.fix(None) is None)
ok("fix 幂等", tts_pron.fix(tts_pron.fix("背单词去单位")) == "背單词去單位")

print("=== 2) polish_english 非流式 + fixer：中文正音、英文/音标零影响 ===")
raw = "· 单词：tangyuan /ˈtæŋˌjwɑːn/ 汤圆（象征团圆）\nWe walked along the Bund and saw the skyline."
cleaned = yue_polish.polish_english(raw, report=True)[0]
fixed = tts_pron.fix(cleaned)
ok("英文路径 单词->單词(单已正音)", "單词" in fixed and "单词" not in fixed)
ok("英文正文逐字保留", "We walked along the Bund and saw the skyline." in fixed)
ok("音标逐字保留", "/ˈtæŋˌjwɑːn/" in fixed)
ok("中文汤圆未被正音表误伤", "汤圆" in fixed)
ok("断句 \\n 保留", "\n" in fixed)
for tok in ("tangyuan", "Bund", "skyline", "walked"):
    ok("英文词 %s 未粘损" % tok, tok in fixed)

print("=== 3) polish_english_sse 流式 + fixer：concat 恒等、帧结构不变、正音生效 ===")
def sse(pieces, extra=None):
    lines = []
    for i, p in enumerate(pieces):
        d = {"choices": [{"delta": {"content": p}, "finish_reason": None}]}
        lines.append("data: " + json.dumps(d, ensure_ascii=False))
        lines.append("")
    if extra:
        lines.append(extra)
    lines.append("data: [DONE]")
    return ("\n".join(lines)).encode("utf-8")

pieces = ["· 单", "词：tangyuan ", "/ˈtæŋˌjw", "ɑːn/ 汤圆。\n", "We walked ", "along the Bund."]
body = sse(pieces)
outb, hits = yue_polish.polish_english_sse(body, fixer=tts_pron.fix)
outs = outb.decode("utf-8")
# 逐帧 concat == 整段清洗结果
out_lines = [l for l in outs.split("\n") if l.startswith("data:") and l != "data: [DONE]"]
conc = "".join(json.loads(l[5:].strip())["choices"][0]["delta"].get("content", "") for l in out_lines)
whole_clean = tts_pron.fix(yue_polish.polish_english("".join(pieces)))
ok("流式 concat == 整段清洗(含正音)", conc == whole_clean)
ok("流式 单词->單词(单已正音)", "單词" in conc and "单词" not in conc)
ok("流式 英文词完整", all(t in conc for t in ("We walked", "along the Bund.", "tangyuan", "/ˈtæŋˌjwɑːn/")))
ok("流式 断句 \\n 保留", "\n" in conc)
ok("流式 帧数不变", len(out_lines) == len(pieces))
ok("流式 [DONE] 保留", outs.rstrip().endswith("data: [DONE]"))
# 唔传 fixer 时行为=旧版（向后兼容）
outb2, _ = yue_polish.polish_english_sse(body)
c2 = "".join(json.loads(l[5:].strip())["choices"][0]["delta"].get("content", "")
             for l in outb2.decode("utf-8").split("\n")
             if l.startswith("data:") and l != "data: [DONE]")
ok("流式 fixer 默认None 向后兼容(单词保持简体)", "单词" in c2)

print("=== 4) 粤语路径流式 fixer 仍生效（零回归）===")
body2 = sse(["我", "哋听", "日去越秀", "区见，呢个机", "会好合适。"])
outb3, _ = yue_polish.polish_cantonese_sse(body2, fixer=tts_pron.fix)
c3 = "".join(json.loads(l[5:].strip())["choices"][0]["delta"].get("content", "")
             for l in outb3.decode("utf-8").split("\n")
             if l.startswith("data:") and l != "data: [DONE]")
ok("粤语流式 听日->汀日", "汀日" in c3)
ok("粤语流式 区->區", "區" in c3)
ok("粤语流式 会->會 适->適", "會" in c3 and "適" in c3)

print("=== 5) 公式符号白名单零回归（v1.27）===")
for expr, tokens in [("F = ma", ("F", "ma")), ("pH 值", ("pH",)), ("Ek", ("Ek",)),
                     ("NaOH", ("NaOH",)), ("H2O", ("H2O",))]:
    got = tts_pron.fix(yue_polish.polish(expr))
    ok("公式 %s 符号保留(实得 %s)" % (expr, got), all(tok in got for tok in tokens))

print("\nUNIT_DAN: %d PASS / %d FAIL  %s" % (P, F, "ALL_PASS" if F == 0 else "HAS_FAIL"))
sys.exit(1 if F else 0)
