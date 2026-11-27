# -*- coding: utf-8 -*-
"""v1.41 兜底：yue_polish.polish() 加「指令腔元评论」整句清理。
只删最高置信一条：评价资料写得清楚 + 命令唔好改 的整句（主人点名那句）。
繁简通吃，不依赖 translate。宁漏勿错删：自我叮嘱「唔好乱打/我唔好乱估」
常嵌在诚实坦白里，交治本 system 尾钉，兜底不碰。
断言式：两处 anchor 各唯一命中才写回。
"""
P = "/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/yue_polish.py"
raw = open(P, "rb").read()
assert b"\r\n" not in raw, "unexpected CRLF"
txt = raw.decode("utf-8")

assert "_clean_meta_instruction" not in txt, "v1.41 polish 已存在，勿重复"
assert "指令腔元评论清理" not in txt, "v1.41 hits 已存在，勿重复"

# ---- 替换1：在 v1.39 规则定义之后、def polish 之前，插入 v1.41 正则+函数 ----
anchor1 = r'''def _clean_filler(text):
    """返回 (清理后文本, 命中次数)。只做上面两条高置信清理。"""
    n = 0
    text, a = _FILLER_LEAD.subn("", text); n += a
    text, b = _FILLER_TAIL_Q.subn("", text); n += b
    # 删口后可能留低句首/句尾孤立逗号或空行，收敛一次
    if n:
        text = re.sub(r"(?m)^[ \t]*[，,]\s*", "", text)
        text = re.sub(r"[ \t]+(?=[，。！？、；：）]|$)", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, n


def polish(text, report=False, poem=False):'''
assert txt.count(anchor1) == 1, "anchor1 count=%d" % txt.count(anchor1)

insert1 = r'''def _clean_filler(text):
    """返回 (清理后文本, 命中次数)。只做上面两条高置信清理。"""
    n = 0
    text, a = _FILLER_LEAD.subn("", text); n += a
    text, b = _FILLER_TAIL_Q.subn("", text); n += b
    # 删口后可能留低句首/句尾孤立逗号或空行，收敛一次
    if n:
        text = re.sub(r"(?m)^[ \t]*[，,]\s*", "", text)
        text = re.sub(r"[ \t]+(?=[，。！？、；：）]|$)", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, n


# ============ v1.41 指令腔元评论清理（治本兜底，2026-11-12）============
# 模型写长文时会把【约束自己点样用资料】的核查指令当正文复述——
#   「呢个時间点，资料讲得清清楚楚，唔好乱改。」（落盘 2026-11-12 真实）
# 呢类句零知识、纯元评论，主人明确要去掉。兜底只收【最高置信一条】：
#   [资料] + [讲得/写得清清楚楚] + [唔好(乱)改] 三者同句先删，可带前导
#   「呢个時间点，」。繁简通吃（時/时、間/间、點/点、資/资、講/讲、亂/乱）。
# 【硬防误伤】必须同时命中三者，故以下全部不碰：
#   - 「远望得清清楚楚」       （无「资料」、无「唔好改」= 正常描写）
#   - 「过马路唔好乱跑/唔好乱爬」（无「资料」、无「清楚」= 安全教育）
#   - 「我搵唔到确切资料，唔敢乱作」（无「清楚」、无「唔好改」= 诚实坦白）
# 其余自我叮嘱（「唔好乱打」「我唔好乱估」）常嵌诚实声明，交 v1.41 治本
#   system 尾钉令模型根本唔生成，兜底宁漏勿错删。poem 朗读模式豁免。
_META_DOC = re.compile(
    r"\s*(?:呢[个個]\s*[时時][间間][点點]\s*[，,]\s*)?"
    r"[资資]料[^。！？!?\n]{0,16}?"
    r"(?:清清楚楚|讲得清楚|講得清楚|写得清楚|寫得清楚|好清楚)"
    r"[^。！？!?\n]{0,14}?"
    r"(?:唔好|不要|唔准|别)\s*[乱亂]?改"
    r"[^。！？!?\n]{0,6}\s*[。.！!]?"
)


def _clean_meta_instruction(text):
    """返回 (清理后文本, 命中次数)。只删上面一条最高置信元评论整句。"""
    work, n = _META_DOC.subn("", text)
    if n:
        work = re.sub(r"(?m)^[ \t]*[，,]\s*", "", work)
        work = re.sub(r"[ \t]{2,}", " ", work)
        work = re.sub(r"\n{3,}", "\n\n", work).strip()
    return work, n


def polish(text, report=False, poem=False):'''
txt = txt.replace(anchor1, insert1, 1)
print("[patch] 1/2 规则定义插入 ok")

# ---- 替换2：在 v1.39 调用之后、return 之前，插入 v1.41 调用 ----
anchor2 = r'''    # 11) v1.39 填充口头禅清理（治本兜底，只收高置信两条；poem 朗读唔郁）
    if not poem:
        work, n_filler = _clean_filler(work)
        if n_filler:
            hits["填充口头禅清理"] = n_filler

    return (work, hits) if report else work'''
assert txt.count(anchor2) == 1, "anchor2 count=%d" % txt.count(anchor2)

insert2 = r'''    # 11) v1.39 填充口头禅清理（治本兜底，只收高置信两条；poem 朗读唔郁）
    if not poem:
        work, n_filler = _clean_filler(work)
        if n_filler:
            hits["填充口头禅清理"] = n_filler

    # 12) v1.41 指令腔元评论清理（只收「资料讲得清清楚楚+唔好改」一条，宁漏勿错）
    if not poem:
        work, n_meta = _clean_meta_instruction(work)
        if n_meta:
            hits["指令腔元评论清理"] = n_meta

    return (work, hits) if report else work'''
txt = txt.replace(anchor2, insert2, 1)
print("[patch] 2/2 polish 调用插入 ok")

open(P, "wb").write(txt.encode("utf-8"))
print("[patch] WRITTEN ok, bytes=%d" % len(txt.encode("utf-8")))
print("[patch] _clean_meta_instruction count:", txt.count("def _clean_meta_instruction"))
print("[patch] 指令腔元评论清理 count:", txt.count("指令腔元评论清理"))
