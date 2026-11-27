# -*- coding: utf-8 -*-
"""v1.29 斜杠/音标清理单元回归（本机 gateway 目录跑）。
覆盖：IPA 音标块删除、公式斜杠转读法、URL/日期保护、英文/中文零误伤、
      流式 SSE 整段回填 concat 恒等、v1.27 公式白名单/v1.28 正音零回归。"""
import sys, json
import yue_polish as yp
import tts_pron

P = F = 0
def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1; print("  PASS", name)
    else:
        F += 1; print("  FAIL", name, extra)

def clean(t):
    return yp.clean_tts_symbols(t)

print("=== 1) IPA 音标块整段删除（含斜杠 + IPA 字母）===")
cases = [
    ("单词：point /pɔɪnt/ 点；要点", "单词：point 点；要点"),
    ("· 单词：tangyuan /ˈtæŋˌjwɑːn/ 汤圆", "· 单词：tangyuan 汤圆"),
    ("Bund /bʌnd/，Pudong /puːˈdoʊŋ/", "Bund，Pudong"),
    ("point /pɔɪnt/ 的同音词 main point /meɪn pɔɪnt/", "point 的同音词 main point"),
    ("音标：/ˈpleɪnɪŋ/ /ˈʃæŋˈhaɪ/ /trɪp/", ""),   # 空音标行整体清掉
    ("· 音标：/ˈlændˌmɑːks/ /bʌnd/", ""),
    ("单词 /wɜːrd/ 同 word /wɜːrd/ 唔同", "单词 同 word 唔同"),
]
for a, b in cases:
    got = clean(a)
    ok("clean %r" % a[:26], got == b, "-> %r (期望 %r)" % (got, b))

print("=== 1b) 引号内裸 IPA 串删除（无 '/' 都要清，E2E 实测补充）===")
bcases = [
    # 删裸 IPA 后，悬空嘅「读作/live 读作」提示一并清走（更自然，唔会留「读作。」）
    ("组合读作“pɔɪnt”。", "组合。"),
    ('"Road" 读作 "rəʊd"', '"Road"'),
    ('lively 的 "live" 读作 "laɪv"', 'lively 的 "live"'),
    # 句尾/标点前悬空「读作」清走；句中(后跟中文)保留轻微冗余，避免误伤正常教学句
    ("point /pɔɪnt/ 同 读作“pɔɪnt” 两处都要清", "point 同 读作 两处都要清"),
]
for a, b in bcases:
    got = clean(a)
    ok("bare %r" % a[:24], got == b, "-> %r (期望 %r)" % (got, b))
# 关键防误伤：纯英文正文（即使含空格/点/连字符）绝唔会被删
for safe in ("Could you please point to the bird?",
             "What's the main point of this story?",
             "present continuous tense", "Skyline at night.",
             "I visited the Bund in Shanghai."):
    ok("裸IPA 不误伤 %r" % safe[:30], clean(safe) == safe, "-> %r" % clean(safe))

print("=== 2) 公式/单位斜杠转中文读法 ===")
fcases = [
    ("单位系米每二次方秒（m/s²）", "单位系米每二次方秒（m每s²）"),
    ("a = F/m", "a = F除以m"),
    ("10N / 2kg = 5 m/s²", "10N除以2kg = 5 m每s²"),
    ("a = F/m = 10N / 2kg = 5 m/s²", "a = F除以m = 10N除以2kg = 5 m每s²"),
    ("N = ·m/s²", "N = ·m每s²"),
]
for a, b in fcases:
    got = clean(a)
    ok("formula %r" % a[:26], got == b, "-> %r (期望 %r)" % (got, b))

print("=== 3) URL / 日期保护（绝唔变「除以」）===")
ok("URL http://example.com/path", "http://example.com/path" in clean("详情睇 http://example.com/path"))
ok("URL https://a.cn/x", "https://a.cn/x" in clean("https://a.cn/x"))
ok("日期 2026/11/11 转年月日", "2026年11月11日" == clean("2026/11/11"))
ok("日期嵌句", "开会2026年11月11日见" == clean("开会2026/11/11见"))

print("=== 4) and/or 同英文正文零误伤 ===")
ok("and/or -> and or", clean("and/or") == "and or")
ok("英文例句断句保留",
   clean("I am planning to visit Shanghai.\nWe will see the Bund.") ==
   "I am planning to visit Shanghai.\nWe will see the Bund.")
ok("纯英文无斜杠原样", clean("present continuous tense") == "present continuous tense")
ok("纯中文无斜杠原样", clean("我哋今日去街市买餸。") == "我哋今日去街市买餸。")
ok("非 str 原样", clean(123) == 123 and clean(None) is None)
ok("空串原样", clean("") == "")

print("=== 5) 无非音标斜杠时 hits 为空（幂等/零副作用）===")
no_slash = "我哋今日去街市。"
c, h = yp.clean_tts_symbols(no_slash, report=True)
ok("无斜杠零命中", c == no_slash and h == {}, "hits=%s" % h)
once = clean("point /pɔɪnt/ 点")
ok("幂等", clean(once) == once, "once=%r twice=%r" % (once, clean(once)))

print("=== 6) v1.27 公式符号白名单零回归（polish 后仍保留）===")
for expr in ("F = ma", "pH 值", "Ek", "NaOH", "H2O"):
    kept = tts_pron.fix(yp.polish(expr))
    ok("公式符号 %r 保留" % expr, all(tok in kept for tok in expr.split()),
       "-> %r" % kept)

print("=== 7) v1.28 正音零回归（单->單 等）===")
ok("单词->單词", tts_pron.fix("单词") == "單词")
ok("机会->机會", tts_pron.fix("机会") == "机會")
ok("地区->地區", tts_pron.fix("地区") == "地區")
ok("正音+斜杠串行不打架", clean(tts_pron.fix("單词：point /pɔɪnt/ 点")) == "單词：point 点")

print("=== 8) 非流式 body 封装（改播报 message.content）===")
d = {"choices": [{"message": {"role": "assistant", "content": "单词：point /pɔɪnt/ 点"}}]}
nb, nh = yp.clean_tts_symbols_body(json.dumps(d, ensure_ascii=False).encode("utf-8"), stream=False)
nd = json.loads(nb.decode("utf-8"))
ok("body 播报稿删音标", nd["choices"][0]["message"]["content"] == "单词：point 点",
   "-> %r" % nd["choices"][0]["message"]["content"])
ok("body 保留 role 字段", nd["choices"][0]["message"]["role"] == "assistant")
ok("body hits 有命中", bool(nh), "hits=%s" % nh)
ok("body 非 200 结构空 choices 不炸",
   yp.clean_tts_symbols_body(json.dumps({"choices": []}).encode(), stream=False)[1] == {})
ok("坏 body 原样透传",
   yp.clean_tts_symbols_body(b"not-json", stream=False)[0] == b"not-json")

print("=== 9) 流式 SSE 整段回填：concat 恒等 + 帧结构不变 ===")
frames = [
    "data: " + json.dumps({"choices": [{"delta": {"content": "单词："}, "index": 0}]}, ensure_ascii=False),
    "data: " + json.dumps({"choices": [{"delta": {"content": "point /pɔɪ"}, "index": 0}]}, ensure_ascii=False),
    "data: " + json.dumps({"choices": [{"delta": {"content": "nt/ 点、意思"}, "index": 0}]}, ensure_ascii=False),
    "data: " + json.dumps({"choices": [{"delta": {"content": "系要点。"}, "index": 0}]}, ensure_ascii=False),
    "data: " + json.dumps({"choices": [], "finish_reason": "stop", "index": 0}),
    "data: [DONE]",
]
sse_body = ("\n".join(frames) + "\n\n").encode("utf-8")
new_sse, sse_hits = yp.clean_tts_symbols_body(sse_body, stream=True)
txt = new_sse.decode("utf-8")
# 拼所有 delta.content
parts = []
for line in txt.splitlines():
    st = line.strip()
    if not st.startswith("data:") or st == "data: [DONE]":
        continue
    try:
        dj = json.loads(st[5:].strip())
    except Exception:
        continue
    for ch in dj.get("choices", []):
        c = (ch.get("delta") or {}).get("content")
        if isinstance(c, str):
            parts.append(c)
conc = "".join(parts)
expect = clean("单词：point /pɔɪnt/ 点、意思系要点。")
ok("SSE concat == 整段清洗结果", conc == expect, "-> %r (期望 %r)" % (conc, expect))
ok("SSE 绝无残留斜杠", "/" not in conc and "IPA" not in conc, "conc=%r" % conc)
ok("SSE 帧数不变", sum(1 for l in txt.splitlines() if l.strip().startswith("data:")) == 6)
ok("SSE [DONE] 保留", "data: [DONE]" in txt)
ok("SSE finish_reason 保留", '"finish_reason": "stop"' in txt or '"finish_reason":"stop"' in txt)
ok("SSE hits 有命中", bool(sse_hits), "hits=%s" % sse_hits)

print("\n=== 结果：%d PASS / %d FAIL ===" % (P, F))
sys.exit(1 if F else 0)
