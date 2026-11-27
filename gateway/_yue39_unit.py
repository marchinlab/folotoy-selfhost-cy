# -*- coding: utf-8 -*-
"""v1.39 单测：填充口头禅兜底清理。用真实落盘语料 + 反向防误伤断言。
正向=该删的删；反向=真问句/知识内容一字唔删；幂等=跑两次结果一样。"""
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

print("=== A) 句首转场「你知唔知，」清除（真实语料）===")
A = [
    ("你知唔知，点解李渊可以喺晋阳起兵？", "点解李渊可以喺晋阳起兵？"),
    ("你知唔知，唐朝开国之后，最紧要嘅一步，系稳住局面。", "唐朝开国之后，最紧要嘅一步，系稳住局面。"),
    ("而家你知唔知，点解唐朝可以咁开放？", "点解唐朝可以咁开放？"),
    ("而家你知唔知，点解今日嘅中国，仲會提起唐朝？", "点解今日嘅中国，仲会提起唐朝？"),  # 會→会 系 polish 固有繁转简
    ("你知唔知，李世民做皇帝之后，最紧要嘅一件事，就系点样处理外族关系。",
     "李世民做皇帝之后，最紧要嘅一件事，就系点样处理外族关系。"),
]
for s, want in A:
    got = clean(s)
    ck("删句首填充: %s => %s" % (s[:16], got[:20]), got == want)

print("=== B) 整句客套追问「你明唔明？」清除（真实语料）===")
B = [
    ("你明唔明呢个画面呀？", ""),
    ("你听明唔明？", ""),
    ("你明唔明？", ""),
    # 句中夹带（前面有正文、问句独立成句）
    ("好似你站喺江边望对面，啲树影好清楚。你明唔明？", "好似你站喺江边望对面，啲树影好清楚。"),
]
for s, want in B:
    got = clean(s)
    ck("删客套追问: |%s| => |%s|" % (s[:20], got[:24]), got == want)

print("=== C) 反向·真问句必须保留（防误伤，最关键）===")
C = [
    "你知唔知「天可汗」呢个称号？",          # 无逗号、带宾语＝真问
    "你知唔知李渊系边个？",                  # 无逗号、带宾语＝真问
    "老师问你明唔明呢道题点解咁做？",        # 明唔明做宾语从句，非客套追问句
    "如果想知多啲，你知唔知可以去边度查？",
]
for s in C:
    got = clean(s)
    ck("真问句保留: |%s| => |%s|" % (s[:22], got[:26]), got == s)

print("=== D) 反向·知识内容一字唔删 ===")
D = [
    "贞观之治系唐太宗开创嘅，国家安定，经济恢复，百姓安居乐业。",
    "公式 F=ma 入面，F 代表力，m 代表质量，a 代表加速度。",
    "呢句诗出自唐代诗人崔颢嘅《黄鹤楼》，原文逐字照抄。",
]
for s in D:
    got = clean(s)
    ck("知识保留: |%s|" % s[:22], got == s)

print("=== E) 整段混合：真实语料多句一齐清，内容不丢 ===")
mixed = (
    "好，我继续讲。你知唔知，唐朝开国之后，最紧要嘅一步，系稳住局面，唔好再乱。"
    "而家你知唔知，点解唐朝可以咁开放？因为李世民相信包容。你明唔明？"
)
got = clean(mixed)
ck("清后无「你知唔知，」转场", "你知唔知，" not in got)
ck("清后无「你明唔明？」客套", "你明唔明" not in got)
ck("知识点保留: 稳住局面/包容", "稳住局面" in got and "李世民相信包容" in got)
print("    清后全文: %s" % got)

print("=== F) 幂等：clean(clean(s)) == clean(s) ===")
for s in [A[2][0], B[3][0], mixed]:
    once = clean(s); twice = clean(once)
    ck("幂等: %s" % s[:14], once == twice)

print("=== G) poem 朗读模式唔清（口头禅规则唔碰诗词）===")
s = "你知唔知，床前明月光，疑是地上霜。"
got = y.polish(s, report=False, poem=True)
ck("poem 模式保留「你知唔知，「逐字", got == s)

print("\n===== RESULT pass=%d fail=%d =====" % (P, F))
sys.exit(1 if F else 0)
