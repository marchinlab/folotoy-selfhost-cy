# -*- coding: utf-8 -*-
"""v1.32 单元测试：时间→時间 / 儿子→兒子 正音 + 呢个嗰阵→呢个时期 / 想知定系唔知→想唔想知 措辞。
重点：防误伤 + 幂等（沿用项目「宁可少改不可改错」铁律）。

⚠️ 关键实现细节（勿"补全"！）：fix 只转 时→時、儿→兒，【不转「间」】。
   单字声学证明「间」gaan1 本就念对（间/間/艱 sz 全 7344、F0/F1F2 几乎全等），
   转「間」无益且可能引入新韵律（v1.30「过程」教训）。故 "时间" → "時间"（繁時+简间混合字形），
   edge-tts 按字形逐字查音：時→si4 正音锚、间→gaan1 正音，组合正确。
   火火兔系纯语音玩具、唔显示文字，混合字形零副作用。若后人"顺手"补全成「時間」即引入未验证改动。
本地：PYTHONIOENCODING=utf-8 python3 _yue32_unit.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tts_pron as t
import yue_polish as y

PASS = FAIL = 0


def ck(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("  OK   %-46s %s" % (name, got))
    else:
        FAIL += 1
        print("  FAIL %-46s got=%r want=%r" % (name, got, want))


def ck_in(name, got, *subs):
    global PASS, FAIL
    miss = [s for s in subs if s not in got]
    if not miss:
        PASS += 1
        print("  OK   %-46s %s" % (name, got[:60]))
    else:
        FAIL += 1
        print("  FAIL %-46s 缺 %r | got=%r" % (name, miss, got[:80]))


def ck_not_in(name, got, *subs):
    global PASS, FAIL
    hit = [s for s in subs if s in got]
    if not hit:
        PASS += 1
        print("  OK   %-46s %s" % (name, got[:60]))
    else:
        FAIL += 1
        print("  FAIL %-46s 误含 %r | got=%r" % (name, hit, got[:80]))


def idem(name, fn, s):
    global PASS, FAIL
    a = fn(s)
    b = fn(a)
    if a == b:
        PASS += 1
        print("  OK   %-46s 幂等 %s" % (name, a[:50]))
    else:
        FAIL += 1
        print("  FAIL %-46s 不幂等 %r -> %r" % (name, a, b))


print("\n===== A) tts_pron.fix 正音（时→時 / 儿→兒，「间」故意唔转）=====")
ck("时间→時间(只时变，间保留)", t.fix("时间"), "時间")
ck("儿子→兒子", t.fix("儿子"), "兒子")
ck_in("整句正音", t.fix("呢个时期你想唔想知儿子同时间"), "時期", "兒子", "時间")
ck("「时」全局一对一同音", t.fix("时候 小时 时代 时刻"), "時候 小時 時代 時刻")
ck("「儿」全局一对一同音", t.fix("儿女 幼儿 儿科 女儿"), "兒女 幼兒 兒科 女兒")
ck("「间」单字唔入表", t.fix("间"), "间")
ck("「间」喺词内都保留简体", t.fix("空间 期间 瞬间"), "空间 期间 瞬间")
# 护字：v1.28/1.30 旧映射 + 一对多唔误伤
ck("v1.28 单词→單词", t.fix("单词"), "單词")
ck("v1.28 机会→机會", t.fix("机会"), "机會")
ck("v1.28 地区→地區", t.fix("地区"), "地區")
ck("v1.30 净力→淨力", t.fix("净力"), "淨力")
ck("v1.30 文风→聞風(词级换字)", t.fix("文风"), "聞風")
ck("v1.30 发达→發達", t.fix("发达"), "發達")
ck("v1.30 听日→汀日", t.fix("听日"), "汀日")
ck("护字 头发唔变头發", t.fix("头发"), "头发")
ck("护字 发现唔变發現", t.fix("发现"), "发现")
ck("护字 语文/文化唔变語聞", t.fix("语文 文化"), "语文 文化")
ck("护字 过程 保持唔改", t.fix("过程"), "过程")
ck("非 str 原样", t.fix(123), 123)
idem("fix 幂等-时间儿子", t.fix, "时间同儿子喺呢个时期")
idem("fix 幂等-旧词", t.fix, "单词 机会 净力 文风 发达")

print("\n===== B) yue_polish.polish 措辞（呢个嗰阵→呢个时期 / 想知定系唔知→想唔想知）=====")
# 0a 顶部拦截：这个时候/呢个时候/这个时期 一律先收成「呢个时期」，早过「这个→呢个」+「时候→嗰阵」
for s in ("这个时候", "呢个时候", "这个时期", "呢个时期"):
    ck("拦 %s →呢个时期" % s, y.polish(s), "呢个时期")
# 6b 兜底：上游漏落/直接吐的病句
ck("兜底 呢个嗰阵→呢个时期", y.polish("呢个嗰阵"), "呢个时期")
ck_in("整句兜底", y.polish("喺呢个嗰阵度，我哋要小心"), "呢个时期")
ck_not_in("整句兜底无残留", y.polish("喺呢个嗰阵度，我哋要小心"), "呢个嗰阵")
# 想知定系唔知 → 想唔想知
ck("想知定系唔知→想唔想知", y.polish("想知定系唔知"), "想唔想知")
ck("你有啲想知定系唔知→你想唔想知", y.polish("你有啲想知定系唔知"), "你想唔想知")
ck_in("整句问答", y.polish("你有啲想知定系唔知？我话你知。"), "你想唔想知")
# 反向引用:换动词同样收敛
ck("想明定系唔明→想唔想明", y.polish("想明定系唔明"), "想唔想明")
ck("想去定系唔去→想唔想去", y.polish("想去定系唔去"), "想唔想去")
# 「知道」先经 RULES 变「知」，再落正则 → 想唔想知
ck("有啲想知道定系唔知道→想唔想知", y.polish("有啲想知道定系唔知道"), "想唔想知")
# 边界:前后动词唔同 → 唔收敛(宁漏勿改)
ck("前后唔同动词 唔郁", y.polish("想知定系唔明"), "想知定系唔明")

print("\n===== C) 防误伤：「定系」合法选择问 + 「嗰阵」合法用法 + 时候系列 =====")
ck("你去定系我去 保留", y.polish("你去定系我去"), "你去定系我去")
ck("食饭定系食面 保留", y.polish("食饭定系食面"), "食饭定系食面")
ck("想留定系想走(无唔X)保留", y.polish("你话系咪想留定系想走"), "你话系咪想留定系想走")
ck("那时候→嗰阵(远指合法)", y.polish("那时候"), "嗰阵")
ck("的时候→嘅嗰阵(合法)", y.polish("食饭的时候"), "食饭嘅嗰阵")
ck("有时候→间中", y.polish("有时候落雨"), "间中落雨")
ck("这时候→呢阵(合法)", y.polish("这时候"), "呢阵")
ck("古嗰阵/落山嗰阵 保留", y.polish("从古嗰阵到而家，太阳落山嗰阵"), "从古嗰阵到而家，太阳落山嗰阵")
ck("呢啲嗰啲 指代保留", y.polish("呢啲嗰啲都系我哋嘅"), "呢啲嗰啲都系我哋嘅")
ck("什么时候→几时(同源历史bug已修)", y.polish("什么时候嚟"), "几时嚟")
ck_not_in("唔会再出乜嗰阵", y.polish("你几时嚟？什么时候得闲？"), "乜嗰阵")
ck_in("这个/那个 指代仍转", y.polish("这个同那个"), "呢个", "嗰个")

print("\n===== D) 幂等（polish 两遍唔变）=====")
for s in ("这个时候你想唔想知", "你有啲想知定系唔知", "呢个嗰阵",
          "你去定系我去", "从古嗰阵到而家", "食饭的时候", "这时候", "那时候"):
    idem("polish 幂等", y.polish, s)

print("\n===== E) 组合链路：fix(polish(x)) 模拟播报稿 =====")
def broadcast(s):
    return t.fix(y.polish(s))
ck_in("综合句", broadcast("这个时候你有啲想知定系唔知儿子同时间呢个嗰阵"),
      "呢个時期", "你想唔想知", "兒子", "時间")
ck("综合句收敛", broadcast("呢个嗰阵想知定系唔知时间"), "呢个時期想唔想知時间")
ck_not_in("综合句无病句/未正音残留", broadcast("呢个嗰阵想知定系唔知时间儿子"),
          "定系", "嗰阵", "儿子", "时间")
idem("组合链路幂等", broadcast, "这个时候你有啲想知定系唔知儿子同时间")

print("\n" + "=" * 60)
print("YUE32_UNIT_%s  PASS=%d FAIL=%d" % ("ALL_PASS" if FAIL == 0 else "FAIL", PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
