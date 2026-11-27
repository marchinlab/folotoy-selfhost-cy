# -*- coding: utf-8 -*-
"""v1.24 英语老师普通话化单元回归：polish_english / system 加载 / 路由隔离。"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yue_polish as yp

OK = []
def ck(name, cond, extra=""):
    OK.append(bool(cond))
    print("  %s %s %s" % ("PASS" if cond else "FAIL", name, extra))

print("== A. polish_english 清洗项 ==")
s = "✅ 记住口诀：**A for Action** 👉 例句：She is reading a book. 根据资料，资料确认 affect 系动词。"
o = yp.polish_english(s)
print("   ->", repr(o))
ck("去emoji(✅👉)", "✅" not in o and "👉" not in o)
ck("去装饰几何符号(▶★→)", yp.polish_english("▶ 小技巧 ★ 重点 → 看这里") == "小技巧 重点 看这里")
ck("去Markdown(**)", "**" not in o)
ck("去元话语(根据资料/资料确认)", "根据资料" not in o and "资料确认" not in o)
ck("英文原句保留", "She is reading a book." in o and "affect" in o and "Action" in o)
ck("系动词术语保留(linking verb,不转是动词)", "系动词" in o)

print("== B. 中英双语绝不误伤 ==")
samples = [
    "present continuous（现在进行时）：be + doing",
    "affect /əˈfekt/（动词）vs effect /ɪˈfekt/（名词）",
    "The rain affected our plans. （雨影响了我们的计划。）",
    "used to 后面接【动词原形】，例如 I used to play football.",
    "单词 abundant /əˈbʌndənt/ 大量的；be abundant in 富于……",
]
for x in samples:
    y = yp.polish_english(x)
    # 关键：英文字母/音标/整句不能被清掉
    letters = [w for w in x.split() if any(c.isascii() and c.isalpha() for c in w)]
    lost = [w for w in letters if w.strip(".,（）()") not in y]
    ck("英文不丢 %r" % x[:22], not lost, "lost=%s" % lost if lost else "")

print("== C. 串味粤字兜底回退 ==")
for a, b in [("影响咗我哋嘅计划", "影响了我们的计划"),
             ("这度讲紧一个词", "这里讲紧一个词"),
             ("明唔明呀", "明白吗呀"),
             ("有冇试下", "有没有试试"),
             ("而家讲下", "现在讲讲")]:
    y = yp.polish_english(a)
    ck("回退 %s -> %s" % (a, b), y == b, "got %r" % y)
# 「系」单字一律唔转：系动词(linking verb)/关系/系统/系列 都可能系规范词，宁漏勿错
ck("单字'系'不全局转(护住系动词/关系/系统)",
   yp.polish_english("系动词系一种关系，系统系列都唔转") ==
   "系动词系一种关系，系统系列都不转")

print("== D. 幂等（跑两次结果一致）==")
s = "✅ **根据资料** 资料显示 affect 系动词，我哋嚟睇下 👉 She is reading."
y1 = yp.polish_english(s); y2 = yp.polish_english(y1)
ck("幂等", y1 == y2, "y1=%r y2=%r" % (y1, y2))

print("== E. 关闭开关（YUE_POLISH=0 时 polish_english 仍安全）==")
# polish_english 不依赖 ENABLED，是英语老师专用恒开管线；确认无全局副作用
ck("polish_english 不调用粤语化", "影响咗" not in yp.polish_english("影响咗我哋") )

print("== F. 系统 prompt 加载（内置兜底含普通话锚定、零粤语指令）==")
import llm_gateway as g
ck("兜底 prompt 含标准普通话锚定", "标准普通话" in g.ENGLISH_SYSTEM_FALLBACK)
ck("兜底 prompt 含北京课堂锚定", "北京" in g.ENGLISH_SYSTEM_FALLBACK)
ck("兜底 prompt 无粤语指令字(唔系/即系/唔好)", not any(w in g.ENGLISH_SYSTEM_FALLBACK for w in ("唔系", "即系", "唔好", "你系")))
ck("兜底 prompt 含角色标记", "【角色:english_teacher】" in g.ENGLISH_SYSTEM_FALLBACK)
ck("启动已加载到 ENGLISH_SYSTEM", bool(g.ENGLISH_SYSTEM) and "标准普通话" in g.ENGLISH_SYSTEM,
   "src=%s" % g.ENGLISH_SYSTEM_SRC)

print("== G. 英语老师显式联网判定 ==")
def explicit(q):
    return any(w in q for w in ("上网", "联网", "搜索", "搜下", "查下", "查一下", "帮我查"))
ck("普通问句不联网", not explicit("affect 同 effect 有乜唔同？"))
ck("英文问句不联网", not explicit("What's the difference between affect and effect?"))
ck("显式'上网查'才联网", explicit("上网查下 affect 嘅词源"))

print("== H. detect_role 仍能认英语老师 ==")
msgs = [{"role": "system", "content": g.ENGLISH_SYSTEM}, {"role": "user", "content": "hi"}]
ck("替换后仍能 detect english_teacher", g.detect_role(msgs) == "english_teacher")

print("== I. english_ref 剥粤语资料头 ==")
fake_kb = ("【头等指令·先据真实资料答】用户问紧知识/事实题，啱啱联网查到下面呢批真实资料\n"
           "【联网查到嘅真实资料】\n"
           "· affect 主要用作动词，意思是影响\n"
           "· effect 作名词，指结果或效果\n"
           "【点样答】用阿晴地道广州西关粤语口语，先直接答中问题核心\n"
           "【语言铁律】全程净系简体中文地道粤语口语、短句；唔准念英文字母")
er = g.english_ref(fake_kb)
print("   ->", repr(er))
ck("剥掉阿晴/粤语指令", "阿晴" not in er and "粤语" not in er and "唔准" not in er)
ck("保留事实条目", "affect" in er and "effect" in er and "动词" in er)
ck("普通话包装", "普通话" in er and "中英双语" in er)
ck("唔提资料字眼指令", "不要提到" in er)

n = sum(OK)
print("\n===== 总结: %d/%d %s =====" % (n, len(OK), "ALL_PASS" if n == len(OK) else "有FAIL"))
sys.exit(0 if n == len(OK) else 1)
