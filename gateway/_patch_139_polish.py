# -*- coding: utf-8 -*-
"""v1.39 兜底：yue_polish.polish() 清模型自加填充口头禅（高置信、零误伤）。
治本已落 llm_gateway system 尾钉，呢层只防漏；故只收【无歧义】两条：
  A) 句首转场「你知唔知，」「而家你知唔知，」（逗号为界；保留无逗号带宾语嘅真问句
     如「你知唔知『天可汗』呢个称号？」）
  B) 整句客套追问「你明唔明？」「明唔明呀？」「你听明唔明？」（短、无知识内容）
开头铺垫（好，我同你讲…）交畀治本，兜底唔硬删，避免误伤。
断言式：old 唯一命中先写回。
"""
P = "/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/yue_polish.py"
raw = open(P, "rb").read()
assert b"\r\n" not in raw, "unexpected CRLF"
txt = raw.decode("utf-8")


def sub_once(txt, old, new, tag):
    n = txt.count(old)
    assert n == 1, "PATTERN %s count=%d (expect 1)" % (tag, n)
    print("[patch] %s : ok (1 hit)" % tag)
    return txt.replace(old, new, 1)


# ---- 1) 在 REGEX_RULES 定义后、polish() 定义前，加 v1.39 清理规则 + 编译 ----
anchor1 = "\ndef polish(text, report=False, poem=False):"
block1 = '''
# ============ v1.39 填充口头禅清理（治本兜底，2026-11-12）============
# 模型喺人设「口语化」同老师 prompt「讲完追问明唔明」引导下，自己加咗大量
# 无信息量嘅填充（落盘实测「你知唔知」一日 18 次）。治本落咗网关 system 尾钉，
# 呢层只防漏，故【只收无歧义、零误伤】两条，宁漏勿错删知识内容：
#   A) 句首转场「你知唔知，」「而家你知唔知，」——带逗号＝铺垫，删；
#      【保留】无逗号直接带宾语嘅真问句，如「你知唔知「天可汗」呢个称号？」
#   B) 整句客套追问「你明唔明？」「明唔明呀？」「你听明唔明？」——短、无知识，删。
# 流式句子级 polish 下 B 会删成空串：玩具端 `if c:` 忽略空 delta、落盘 "".join
# 空串无害，故安全。A 保留句首位置（句首删后系逗号，需去掉多余逗号）。
_FILLER_LEAD = re.compile(r"(?:^|(?<=[。！？!?；;\\n]))\\s*(?:而家)?你知唔知[，,]\\s*")
_FILLER_TAIL_Q = re.compile(r"(?:^|(?<=[。！？!?；;\\n]))\\s*(?:你听)?(?:你)?明唔明(?:呢个画面)?(?:呀|啊|吗|呢)?\\s*[？?！!。.]?\\s*(?=$|[。！？!?；;\\n])")


def _clean_filler(text):
    """返回 (清理后文本, 命中次数)。只做上面两条高置信清理。"""
    n = 0
    text, a = _FILLER_LEAD.subn("", text); n += a
    text, b = _FILLER_TAIL_Q.subn("", text); n += b
    # 删口后可能留低句首/句尾孤立逗号或空行，收敛一次
    if n:
        text = re.sub(r"(?m)^[ \\t]*[，,]\\s*", "", text)
        text = re.sub(r"[ \\t]+(?=[，。！？、；：）]|$)", "", text)
        text = re.sub(r"\\n{3,}", "\\n\\n", text).strip()
    return text, n


def polish(text, report=False, poem=False):'''
txt = sub_once(txt, anchor1, block1, "v1.39-rules")

# ---- 2) 在 polish() 返回前调用：放在英文乱码清理之后、return 之前 ----
anchor2 = (
    "    # 10) 英文/乱码短语清理（还原占位后做，避免碰被保护词）；白名单专名保留\n"
    "    if EN_CLEAN_ENABLED:\n"
    "        work, n_en = _clean_en_fragments(work)\n"
    "        if n_en:\n"
    "            hits[\"英文乱码清理\"] = n_en\n"
    "\n"
    "    return (work, hits) if report else work"
)
block2 = (
    "    # 10) 英文/乱码短语清理（还原占位后做，避免碰被保护词）；白名单专名保留\n"
    "    if EN_CLEAN_ENABLED:\n"
    "        work, n_en = _clean_en_fragments(work)\n"
    "        if n_en:\n"
    "            hits[\"英文乱码清理\"] = n_en\n"
    "\n"
    "    # 11) v1.39 填充口头禅清理（治本兜底，只收高置信两条；poem 朗读唔郁）\n"
    "    if not poem:\n"
    "        work, n_filler = _clean_filler(work)\n"
    "        if n_filler:\n"
    "            hits[\"填充口头禅清理\"] = n_filler\n"
    "\n"
    "    return (work, hits) if report else work"
)
txt = sub_once(txt, anchor2, block2, "v1.39-call")

open(P, "wb").write(txt.encode("utf-8"))
print("[patch] WRITTEN ok, bytes=%d" % len(txt.encode("utf-8")))
