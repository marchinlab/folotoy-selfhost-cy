# -*- coding: utf-8 -*-
"""v1.41 单测：指令腔元评论兜底清理。真实落盘语料 + 反向防误伤 + 幂等 + poem。
正向=「资料讲得清清楚楚+唔好改」元评论删；反向=正常描写/安全教育/诚实坦白/
自我叮嘱一字唔删；嵌段=只删那句、知识零丢；幂等；poem 豁免；v1.39 共存。"""
import sys
sys.path.insert(0, "/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway")
import yue_polish as y

P = F = 0
def ck(tag, cond):
    global P, F
    if cond:
        P += 1; print("  [OK]   " + tag)
    else:
        F += 1; print("  [FAIL] " + tag)

def clean(s):
    return y.polish(s, report=False)

def hit(s):
    return y.polish(s, report=True)[1].get("指令腔元评论清理", 0)

print("=== A) 正向·元评论整句清除（今日真实 + 繁简变体）===")
A = [
    ("呢个時间点，资料讲得清清楚楚，唔好乱改。", ""),          # 今日落盘（繁時）
    ("呢個時間點，資料講得清清楚楚，唔好亂改。", ""),          # 全繁
    ("呢个时间点，资料讲得清清楚楚，唔好乱改。", ""),          # 全简
    ("资料写得清清楚楚，唔好改。", ""),                        # 无前导
    ("资料讲得清楚，唔好乱改。", ""),                          # 讲得清楚
    ("呢个年份唔好记错，就系资料清清楚楚写明嘅。", ""),        # v1.41b E2E 漏网变体（唔带「唔好改」）
    ("就系资料清清楚楚写明嘅。", ""),                          # v1.41b 纯评价资料
    ("年份系资料清清楚楚写明嘅，唔好改。", ""),                # v1.41b 带年份前缀
]
for s, want in A:
    got = clean(s)
    ck("删元评论: %s => |%s|" % (s[:20], got[:20]), got == want)

print("=== B) 嵌段·只删那一句，前后知识一字不动（今日真实全文）===")
full = (
    "唐朝开国，系由李渊喺晋阳起兵，618年称帝，定都长安。呢个時间点，资料讲得清清楚楚，唔好乱改。"
    "唐朝从618年开始，到907年朱温篡唐为止，共二百八十九年，系中国历史上一个非常关键嘅大一统王朝。"
)
got = clean(full)
ck("元评论句消失", "清清楚楚" not in got and "唔好乱改" not in got)
ck("前句保留(李渊起兵/定都长安)", "李渊" in got and "定都长安" in got)
ck("后句保留(907年/二百八十九年)", "907年" in got and "二百八十九年" in got)
ck("命中计数=1", hit(full) == 1)

print("=== C) 反向·正常描写必须保留（防误伤，最关键之一）===")
C = [
    "好似你站喺江边望对面，啲树影映在水里，远望得清清楚楚。",  # 历史真实语料（无资料）
    "个字写得好清楚，一眼就睇明。",                            # 无资料
    # v1.41b 强绑定防误伤：有「资料」但无「清楚」= 正常引用，绝唔删
    "资料讲到嘅事实，人名、地名、年份，一律照原样讲。",
    "批资料入面有啲系全国时政，要照实讲。",
    "唐太宗唔单止打仗厉害，仲识得用人，资料讲到嘅都照讲。",
    # 有「清楚」但无「资料」= 正常论述
    "但唔好以为唐朝就唔好，中后期嘅治理对后世都有贡献。",
]
for s in C:
    ck("描写/引用保留: %s" % s[:20], clean(s) == s and hit(s) == 0)

print("=== D) 反向·安全教育/规矩必须保留（防误伤，最关键之二）===")
D = [
    "过马路唔好乱跑，唔好乱爬细路。",
    "做功课唔好乱写，要逐字对清楚。",
    "小朋友唔好玩火，唔好掂电制。",
]
for s in D:
    ck("教育保留: %s" % s[:20], clean(s) == s and hit(s) == 0)

print("=== E) 反向·诚实坦白 + 自我叮嘱（归治本，兜底不删）===")
E = [
    ("呢部分我搵唔到确切资料，唔敢乱作，唔好意思。", "唔敢乱作"),     # 诚实坦白
    ("成件事一啲都唔好乱讲，年份同地名要照旧，唔好改。", "年份同地名"), # 历史自我叮嘱
    ("呢啲资料冇讲火藥真正出世年份，我唔好乱估。", "我唔好乱估"),      # 历史自我叮嘱
]
for s, keep in E:
    # 含繁体嘅句 polish 会固有繁转简（火藥→火药），故唔强求全等，只验：
    #   ① 元评论规则零命中 ② 关键内容一字未删（防止误删整句/片段）
    ck("坦白/叮嘱不误删: %s" % s[:20], hit(s) == 0 and keep in clean(s))

print("=== F) 反向·知识内容一字唔删 ===")
Fk = [
    ("贞观之治系唐太宗开创嘅，国家安定，经济恢复，百姓安居乐业。", "贞观之治"),
    ("公式 F=ma 入面，F 代表力，m 代表质量，a 代表加速度。", "F=ma"),
    ("唐朝定都长安，即系而家西安，系当時世界上最大嘅国际化城市。", "定都长安"),  # 含「当時」会固有繁转简
]
for s, keep in Fk:
    ck("知识保留: %s" % s[:22], hit(s) == 0 and keep in clean(s))

print("=== G) 幂等 clean(clean(s)) == clean(s) ===")
for s in [full, A[0][0], "呢个時间点，资料讲得清清楚楚，唔好乱改。唐高祖李渊称帝。"]:
    once = clean(s); twice = clean(once)
    ck("幂等: %s" % s[:14], once == twice)

print("=== H) poem 朗读模式豁免（元评论规则唔碰诗词）===")
s = "床前明月光，疑是地上霜。资料讲得清清楚楚，唔好乱改。"
got = y.polish(s, report=False, poem=True)
ck("poem 模式保留逐字", got == s)

print("=== I) 与 v1.39 口头禅清理共存（三类一齐清，知识不丢）===")
mix = (
    "你知唔知，唐朝开国系李渊起兵。呢个時间点，资料讲得清清楚楚，唔好乱改。"
    "佢618年称帝。你明唔明？"
)
got = clean(mix)
ck("清「你知唔知，」转场", "你知唔知，" not in got)
ck("清「你明唔明？」客套", "你明唔明" not in got)
ck("清元评论", "清清楚楚" not in got and "唔好乱改" not in got)
ck("知识保留: 李渊起兵/618称帝", "李渊起兵" in got and "618年称帝" in got)
print("    清后全文: %s" % got)

print("=== J) 流式切分下元评论句完整落在一帧 → 逐句拼接 == 整段（真机路径）===")
SENT_END = "。！？!?；;"
def _split(t):
    out, buf = [], ""
    for ch in t:
        buf += ch
        if (ch in SENT_END and len(buf) >= 8) or len(buf) >= 90:
            out.append(buf); buf = ""
    if buf: out.append(buf)
    return out
stream_doc = (
    "唐朝开国，系由李渊喺晋阳起兵，618年称帝，定都长安。呢个時间点，资料讲得清清楚楚，唔好乱改。"
    "呢个年份唔好记错，就系资料清清楚楚写明嘅。唐朝从618年开始，到907年朱温篡唐为止。"
)
whole = clean(stream_doc)
streamed = "".join(clean(seg) for seg in _split(stream_doc))
ck("流式拼接==整段（元评论句不跨帧残留）", whole == streamed)
ck("流式后无元评论残留", "清清楚楚" not in streamed and "唔好乱改" not in streamed and "写明嘅" not in streamed)
ck("流式后知识完整", "李渊" in streamed and "907年" in streamed)
print("    流式清后: %s" % streamed)

print("\n===== RESULT pass=%d fail=%d =====" % (P, F))
sys.exit(1 if F else 0)
