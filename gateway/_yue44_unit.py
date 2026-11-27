# -*- coding: utf-8 -*-
"""v1.44 单元测试：说→說 / 渐→漸（全局单字）+ 称帝→清帝（词级）。

判据（v1.44 弃用切词内字 F0，只认整词字节碰撞 + 单字指纹，见 tts_pron docstring）：
  A) 正音命中：说/說、渐/漸 简繁两写都转；称帝/稱帝→清帝。
  B) 幂等：fix 两遍唔变；已正音嘅「說/漸/清帝」唔再被郁。
  C) 大规模误伤护字：
     - 「说」全局：护住唔该转嘅唔郁(其实全部 syut3 词都该转)，重点验「游说→游說」字形成立
       (音素字节 7776 全同，固定咗全局唔会带偏 seoi3)；护英文/ASCII、非中文。
     - 「渐」全局：护「惭/渐」无关字(unsigned 只换「渐」这个字)，验所有含渐词都转。
     - 「称帝」词级：护 称王(无效映射唔改)/对称/相称/称职/称呼/声称/名称/简称/称赞/堪称/
       称心/称意/称雄/称霸 全部原样——呢个系本版最重要嘅护字(超高频「称」)。
  D) 组合链路 fix(polish(x))：polish 繁转简唔令匹配失效；clean 唔打回。
  E) 全链路一致：英文路径 fixer 同样正音、唔伤 ASCII。

本地：PYTHONIOENCODING=utf-8 python3 _yue44_unit.py
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
        print("  OK   %-52s %s" % (name, got))
    else:
        FAIL += 1
        print("  FAIL %-52s got=%r want=%r" % (name, got, want))


def ck_in(name, got, *subs):
    global PASS, FAIL
    miss = [s for s in subs if s not in got]
    if not miss:
        PASS += 1
        print("  OK   %-52s %s" % (name, got[:70]))
    else:
        FAIL += 1
        print("  FAIL %-52s 缺 %r | got=%r" % (name, miss, got[:100]))


def ck_not_in(name, got, *subs):
    global PASS, FAIL
    hit = [s for s in subs if s in got]
    if not hit:
        PASS += 1
        print("  OK   %-52s %s" % (name, got[:70]))
    else:
        FAIL += 1
        print("  FAIL %-52s 误含 %r | got=%r" % (name, hit, got[:100]))


def idem(name, fn, s):
    global PASS, FAIL
    a = fn(s)
    b = fn(a)
    if a == b:
        PASS += 1
        print("  OK   %-52s 幂等 %s" % (name, a[:52]))
    else:
        FAIL += 1
        print("  FAIL %-52s 不幂等 %r -> %r" % (name, a, b))


print("\n===== A) tts_pron.fix 正音命中 =====")
# 说→說 全局单字（⚠️fix 只换目标字「说」，相邻「话/明/说」等各自独立；「話/话」单字同音
#   6768 全同，故 fix 产物「說话」发音 = 正音锚「說話」=8208，唔需要整词转繁）。
ck("简体 说→說", t.fix("说"), "說")
ck("说话→說话(單字fix,音=說話8208)", t.fix("说话"), "說话")
ck("说明→說明(明无简繁差)", t.fix("说明"), "說明")
ck("带语气 说话啦", t.fix("说话啦"), "說话啦")
ck("句中 佢说话好大声", t.fix("佢说话好大声"), "佢說话好大声")
ck("多处都转", t.fix("说话、说明、小说"), "說话、說明、小說")
# 游说：字形转繁(音素字节不变，固定全局唔带偏 seoi3)
ck("游说→游說(字形转,音素不变)", t.fix("游说"), "游說")
ck("遊說 已是繁体 唔再郁", t.fix("遊說"), "遊說")
# 渐→漸 全局单字
ck("简体 渐→漸", t.fix("渐"), "漸")
ck("渐渐→漸漸", t.fix("渐渐"), "漸漸")
ck("逐渐→逐漸", t.fix("逐渐"), "逐漸")
ck("渐进→漸进(單字fix,进/進同音7344)", t.fix("渐进"), "漸进")
ck("渐变→漸变(單字fix)", t.fix("渐变"), "漸变")
# 称帝→清帝 词级（简繁两写）
ck("称帝→清帝", t.fix("称帝"), "清帝")
ck("稱帝→清帝(繁)", t.fix("稱帝"), "清帝")
ck("带语气 称帝啦", t.fix("称帝啦"), "清帝啦")
ck("句中 朱元璋称帝", t.fix("朱元璋称帝"), "朱元璋清帝")
ck("称帝+称王 只转前者", t.fix("称帝称王"), "清帝称王")
# 非 str
ck("非 str 原样", t.fix(123), 123)
ck("None 原样", t.fix(None), None)

print("\n===== B) 幂等（fix 两遍 / 已正音唔再郁）=====")
for s in ["说话", "渐渐", "称帝", "游说", "你说话渐渐大声，朱元璋称帝称王"]:
    idem("fix 幂等 %s" % s[:12], t.fix, s)
ck("已正音 說/漸/清帝 唔再郁", t.fix("說話漸漸清帝"), "說話漸漸清帝")

print("\n===== C1) 误伤护字：称帝词级 —— 全部其他含称词原样(本版最重要) =====")
GUARD_CHENG = [
    "称王", "对称", "相称", "称职", "称心", "称意", "称雄", "称霸", "称臣", "称谓",
    "称呼", "声称", "名称", "简称", "称赞", "堪称", "号称", "宣称", "声称", "统称",
    "爱称", "昵称", "美称", "全称", "简称", "对称", "相称", "自称", "人称", "尊称",
]
for w in GUARD_CHENG:
    ck("护 %s 保持" % w, t.fix(w), w)
ck_not_in("含称护字串整体无「清帝」误伤", t.fix(" ".join(GUARD_CHENG)), "清帝")
# 特别钉死：称王 坚决唔改(换字字节不变=无效映射)
ck("★称王 坚决唔改(8640全同,无效映射)", t.fix("称王"), "称王")
ck("★稱王 坚决唔改", t.fix("稱王"), "稱王")
ck("称王称霸 只可能转含称帝先", t.fix("称王称霸"), "称王称霸")

print("\n===== C2) 误伤护字：说/渐 全局 —— 形近字／唔相关字／英文零伤 =====")
# 「说/渐」只换呢两个字形本身，其他字(包括形近字)一字唔郁。
# ⚠️「走过来/时间/儿子/机会/净力/质量/过程」唔列护字：佢哋系 v1.28~v1.42【既有】正音，
#    本版照旧会转，属既有行为、非本版误伤；本表只验「本版新增两条唔会波及唔相关字」。
GUARD_OTHER = [
    "悦", "阅", "脱", "锐", "税", "惭", "暂", "斩", "崭", "浙", "淅", "晰",
    "说客", "游说",  # 含「说」但全局就该转(游说→游說)；单独验音素，唔当护字
]
for w in GUARD_OTHER:
    if w == "游说":
        ck("游说→游說(全局命中,音素7776不变)", t.fix(w), "游說")
    elif w == "说客":
        ck("说客→說客(全局命中)", t.fix(w), "說客")
    else:
        ck("护 %s 保持(形近/唔相关)" % w, t.fix(w), w)
ASCII = "Please say hello, 30% done, TCP/IP, 2026-11-12."
ck("纯 ASCII 原样", t.fix(ASCII), ASCII)
ck("中英混排 只转中文正音", t.fix("please 说话 slowly 渐渐"), "please 說话 slowly 漸漸")

print("\n===== D) 组合链路 fix(polish(x)) + clean 层不回退 =====")
def broadcast(s):
    nc, _ = y.polish(s, report=True)
    nc = t.fix(nc)
    return y.clean_tts_symbols(nc, report=False)

ck("polish 后仍匹配(说)", broadcast("你说话大声啲"), "你說话大声啲")
ck("polish 后仍匹配(渐)", broadcast("逐渐习惯啦"), "逐漸习惯啦")
ck("polish 繁转简后仍匹配(称帝)", broadcast("朱元璋稱帝"), "朱元璋清帝")
ck("clean 唔打回 說/漸", broadcast("说话渐渐"), "說话漸漸")
ck_in("组合句 三条正音共存", broadcast("佢说话渐渐大声，朱元璋称帝称王，对称要相称"),
      "說话", "漸漸", "清帝", "称王", "对称", "相称")
ck_not_in("组合句 无「称帝」残留(但称王保留)", broadcast("朱元璋称帝称王"), "称帝")
ck_in("组合句 称王保留", broadcast("朱元璋称帝称王"), "称王")
# fix 层幂等(生产链路 polish→fix→clean 只跑一遍，fix 输出唔会再入 polish)
_1st = broadcast("你说话渐渐大声，朱元璋称帝")
ck("生产结果再 fix 幂等", t.fix(_1st), _1st)
ck("落点反证 polish 会打回繁說(故 fix 必须在后)", y.polish("說話"), "说话")

print("\n===== E) 全链路一致：英文路径 fixer 同样正音（唔伤 ASCII）=====")
en_out, _ = y.polish_english("Please explain 说话 and 渐渐 clearly.", report=True)
en_out = t.fix(en_out)
ck_in("英文路径 中文正音、ASCII 不动", en_out, "說话", "漸漸", "Please", "explain", "clearly")
ck_not_in("英文路径 无简体「说/渐」残留", en_out, "说", "渐")

print("\n" + "=" * 70)
print("YUE44_UNIT_%s  PASS=%d FAIL=%d" % ("ALL_PASS" if FAIL == 0 else "FAIL", PASS, FAIL))
sys.exit(0 if FAIL == 0 else 1)
