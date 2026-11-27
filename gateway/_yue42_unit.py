# -*- coding: utf-8 -*-
"""v1.42 单元测试：「走过来/走過來」→「行過嚟」词级正音（真人耳 A/B 第3段选定）。

重点（项目铁律「宁可少改不可改错」）：
  A) 正音命中：简繁两写都转；输出锁死繁體「過」(主人验收字节)，唔好自作主张改简体。
  B) 幂等：fix 两遍唔变；「行過嚟」本身唔再被郁。
  C) 大规模误伤护字：「过/来/走」超高频，只锁完整三字「走过来」——护住
     走过去/走过/行走/走开/逃走/过来人/过来/过程/过去/不过/通过/后来/未来/原来 等。
  D) 组合链路 fix(polish(x))：polish 繁转简唔会令词级匹配失效；clean_tts_symbols
     唔会打回繁體「過」（无斜杠无 IPA 走快路径原样返回）。
  E) 全链路一致：粤语流式 = 粤语非流式 = 英文路径 都接同一 fixer，行为一致。

本地：PYTHONIOENCODING=utf-8 python3 _yue42_unit.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts_pron as t
import yue_polish as y

PASS = FAIL = 0
ANCHOR = "行過嚟"   # 主人 A/B 试听第3段 zg_m1 的确切字节（繁體過）


def ck(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("  OK   %-48s %s" % (name, got))
    else:
        FAIL += 1
        print("  FAIL %-48s got=%r want=%r" % (name, got, want))


def ck_in(name, got, *subs):
    global PASS, FAIL
    miss = [s for s in subs if s not in got]
    if not miss:
        PASS += 1
        print("  OK   %-48s %s" % (name, got[:64]))
    else:
        FAIL += 1
        print("  FAIL %-48s 缺 %r | got=%r" % (name, miss, got[:90]))


def ck_not_in(name, got, *subs):
    global PASS, FAIL
    hit = [s for s in subs if s in got]
    if not hit:
        PASS += 1
        print("  OK   %-48s %s" % (name, got[:64]))
    else:
        FAIL += 1
        print("  FAIL %-48s 误含 %r | got=%r" % (name, hit, got[:90]))


def idem(name, fn, s):
    global PASS, FAIL
    a = fn(s)
    b = fn(a)
    if a == b:
        PASS += 1
        print("  OK   %-48s 幂等 %s" % (name, a[:48]))
    else:
        FAIL += 1
        print("  FAIL %-48s 不幂等 %r -> %r" % (name, a, b))


print("\n===== A) tts_pron.fix 正音命中（简繁两写 → 行過嚟）=====")
ck("简体 走过来→行過嚟", t.fix("走过来"), ANCHOR)
ck("繁体 走過來→行過嚟", t.fix("走過來"), ANCHOR)
ck("带语气 走过来啦", t.fix("走过来啦"), ANCHOR + "啦")
ck("带趋向 走过来坐", t.fix("走过来坐"), ANCHOR + "坐")
ck("句中 你慢慢走过来坐", t.fix("你慢慢走过来坐"), "你慢慢" + ANCHOR + "坐")
ck("两处都转", t.fix("走过来又走过去再走过来"), ANCHOR + "又走过去再" + ANCHOR)
ck("非 str 原样", t.fix(123), 123)
ck("None 原样", t.fix(None), None)

print("\n===== B) 幂等（fix 两遍 / 已粤语化唔再郁）=====")
idem("fix 幂等-走过来", t.fix, "走过来")
idem("fix 幂等-整句", t.fix, "你走过来，佢走過來，我行過嚟")
ck("已是行過嚟 唔再郁", t.fix(ANCHOR), ANCHOR)
ck("简体行过嚟 唔郁(未验证等价,唔自作主张)", t.fix("行过嚟"), "行过嚟")

print("\n===== C) 误伤护字：只锁完整三字「走过来」，唔碰其它含过/来/走嘅词 =====")
# ⚠️ v1.44 起「说来」归入全局「说→說」正音(说 syut3 该转)，唔再算 v1.42「走过来」护字；
#    呢条只验 v1.42 词级「走过来→行過嚟」唔误伤其它含「过/来/走」嘅词。
GUARD = [
    "走过去", "走过", "走开", "行走", "逃走", "走漏", "走马观花", "奔走相告",
    "过来", "过来人", "过来看", "过去", "过程", "不过", "通过", "经过", "错过",
    "后来", "未来", "原来", "以来", "以来", "从来", "起来", "出来", "进来",
    "看起来", "看来", "原来如此", "来龙去脉", "来往", "未来",
]
for w in GUARD:
    ck("护 %s 保持" % w, t.fix(w), w)
ck_not_in("护字串整体无「行過嚟」误伤", t.fix(" ".join(GUARD)), ANCHOR)
# 「过马路」安全教育高频，重点护
ck("护 过马路(安全教育)", t.fix("过马路唔好乱跑"), "过马路唔好乱跑")

print("\n===== D) 组合链路 fix(polish(x)) + clean 层不回退 =====")
def broadcast(s):
    nc, _ = y.polish(s, report=True)
    nc = t.fix(nc)
    return y.clean_tts_symbols(nc, report=False)
ck("polish 后仍匹配(简体)", broadcast("你慢慢走过来坐"), "你慢慢" + ANCHOR + "坐")
ck("polish 繁转简后仍匹配", broadcast("你慢慢走過來坐"), "你慢慢" + ANCHOR + "坐")
ck("clean 唔打回繁體過", broadcast("走过来"), ANCHOR)
ck_in("组合句 正音+粤语化共存", broadcast("而家走过来，我哋一齐过程讲下"),
      ANCHOR, "而家", "一齊", "过程")   # 一齐→一齊 系既有 v1.30「齐→齊」正音，非本版引入
ck_not_in("组合句 无「走过来」残留", broadcast("你走过来啦"), "走过来")
# ★幂等测法：生产链路 polish→fix→clean 只跑【一遍】，fix 输出唔会再入 polish。
#   故正确测法系「fix 层幂等」：对生产结果再 fix 必须唔变（繁體過唔会被郁）。
#   ⚠️唔好对 broadcast 成条链重复跑两遍：第二遍会先经 polish 繁转简(過→过)打回
#     「行过嚟」，嗰个系「fix 必须落 polish 之后」嘅反证，唔系生产 bug。
_1st = broadcast("你走过来，佢走過來")
ck("生产结果再 fix 幂等(繁體過唔被郁)", t.fix(_1st), _1st)
ck_not_in("生产结果一步到位(无走过来/走过來残留)", _1st, "走过来", "走過來")
ck("落点反证 polish 会打回繁過(故 fix 必须在后)", y.polish(ANCHOR), "行过嚟")

print("\n===== E) 全链路一致：英文路径 fixer 同样正音（唔伤 ASCII）=====")
en_out, _ = y.polish_english("Please come over 走过来 here.", report=True)
en_out = t.fix(en_out)
ck_in("英文路径 中文走过来转、ASCII 不动", en_out, ANCHOR, "Please", "come", "over")

print("\n" + "=" * 66)
print("YUE42_UNIT_%s  PASS=%d FAIL=%d" % ("ALL_PASS" if FAIL == 0 else "FAIL", PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
