# -*- coding: utf-8 -*-
"""v1.26 单元测试：资料强制联网检测 is_fact_check_needed + 专名提取 _fact_subject。
本地跑，唔使联网/唔使网关。目标：
  · 正例（客观资料/专名/地标/数据）-> 必须 fact_needed=True 且抓准专名
  · 反例（寒暄/情绪/讲笑/算术/纯语言操练）-> 必须 False（唔好过度联网拖慢语音）
"""
import llm_gateway as G

OK = []
def ck(name, cond):
    OK.append(bool(cond))
    print("  %s %s" % ("OK  " if cond else "FAIL", name))

# (问句, 期望fact, 期望专名 or None)
POS = [
    ("东方明珠塔有几高", True, "东方明珠塔"),
    ("用英文同我讲东方明珠塔有几高，边年起好嘅", True, "东方明珠塔"),
    ("用英文介绍上海嘅标志性景点，特别要讲到东方明珠塔，每句附中文翻译", True, "东方明珠塔"),
    ("介绍庐山", True, "庐山"),
    ("讲下李白系边个", True, None),  # 人名无地标后缀：fact靠FACT_Q_WORDS，专名由_kb_subject兜
    ("广州塔有幾高", True, "广州塔"),
    ("埃菲尔铁塔系边度起嘅", True, "埃菲尔铁塔"),
    ("西游记嘅作者系谁", True, "西游记"),
    ("珠穆朗玛峰海拔几多", True, "珠穆朗玛峰"),
    ("港珠澳大桥几长", True, "港珠澳大桥"),
    ("北京大学建成年份", True, "北京大学"),
    ("用英文介绍下长城，比几个数据我", True, "长城"),
    ("唐太宗李世民系边个朝代", True, None),
    ("东方明珠塔高468米，系咪1994年建成", True, "东方明珠塔"),
    ("《红楼梦》嘅作者", True, "红楼梦"),
]
NEG = [
    "hello how are you",
    "用英文教我三个去上海旅行嘅例句",      # 纯语言操练：唔好搜
    "用英文解释下 present continuous 点用",  # 纯语法
    "帮我翻译呢句做英文",                    # 纯翻译
    "英文单词 example 点读",                 # 读音/单词
    "你而家系边个啊",                        # 自我认知
    "同我讲句笑话",                          # 讲笑
    "我好攰啊",                              # 情绪
    "1+1 等于几",                            # 算术
    "早晨，食咗饭未",                        # 寒暄
    "你中意饮茶定咖啡",                      # 意见
]

print("=== 正例：客观资料/专名/地标/数据 必须联网核查 ===")
for q, want, subj in POS:
    got = G.is_fact_check_needed(q)
    ck("%-40s fact=%s" % (q[:38], got), got is True)
    if subj:
        s = G._fact_subject(q)
        ck("    专名=%r（期望含 %s）" % (s, subj), subj in (s or ""))

print("=== 反例：非资料 -> 唔好过度联网 ===")
for q in NEG:
    got = G.is_fact_check_needed(q)
    ck("%-40s fact=%s（期望False）" % (q[:38], got), got is False)

print("=== 专名提取 purity（唔好带指令前缀）===")
for q, exp in [("用英文同我讲东方明珠塔有几高", "东方明珠塔"),
               ("详细同我介绍下庐山嘅历史", "庐山"),
               ("用普通话讲讲黄鹤楼", "黄鹤楼")]:
    s = G._fact_subject(q)
    ck("%r -> %r（期望 %s）" % (q[:30], s, exp), (s or "") == exp)

n = len(OK); p = sum(OK)
print("\n结果: %d/%d %s" % (p, n, "全绿" if p == n else "有FAIL"))
raise SystemExit(0 if p == n else 1)
