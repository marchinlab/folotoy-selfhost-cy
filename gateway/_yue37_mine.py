# -*- coding: utf-8 -*-
"""v1.37 语料挖掘：从生产真实播报稿提取汉字字频，筛「普通话G2P劫持高风险」字。
高风险 = 普通话声母 zh/ch/sh/r/j/q/x/y/w（HK声库易按普通话查音）且粤语声母/韵不同，
且【未】在本项目 tts_pron.FIXES / yue_polish._T2S / 本轮已测清单内。
纯文本统计，宿主 python3 跑即可，唔使 edge-tts。
"""
import json, glob, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")

CONV = "/opt/folotoy/conversations"

# 本轮已测(v1 C段 28对) + 项目已收 FIXES + 已验证同形/无病 -> 排除
ALREADY = set("会适区单质净陈齐组队药风儿时亚华车识说计长种进机声东为举万转经讲无实众界日政人")
ALREADY |= set("文发达听")

# 普通话 zh/ch/sh/r/j/q/x/y/w 声母高频字池（粤语读音常与普通话差异大）
# 只列广东话播报会出现的；按拼音首字母分组便于核对
RISK = set(
    # zh
    "之中种众终转政整证真珍诊阵振震占站战张章长涨掌障账丈仗招找照兆赵哲折这着"
    "知直值植殖职指止址纸志制治质秩智置众舟州洲粥轴宙昼皱注住助著专砖传船喘串"
    "庄装壮状撞追准卓桌浊资子自字综总纵走奏足组祖阻最罪醉尊遵作坐座做左"
    # ch
    "车长场厂唱超朝潮吵炒车沉晨称成城程诚承吃持尺赤冲虫重充宠抽愁丑出初除处"
    "川穿传船串窗床创吹垂直春纯蠢词此刺次从丛凑粗促醋催脆存错"
    # sh
    "声说书识实十时石拾食蚀使史始士世事市式试事收手守首瘦书叔舒熟暑属数术束"
    "树刷摔甩帅双爽水睡顺瞬说朔硕司丝私死四寺松宋送苏诉速塑算虽随岁碎孙损缩"
    "说勺少绍社射舍深身神审甚慎升生绳省圣剩师诗狮施湿十拾使"
    # r
    "人日入忍认任仍扔肉如儒乳辱瑞锐rán燃染讓让"
    # j
    "机计讲进经举际鸡几及即急级集几己记寄纪阶接节结解姐届界借今金斤紧尽进晋"
    "京经精睛井静镜净句具俱剧据卷决绝均军君峻"
    # q
    "七期欺其奇骑起气汽器千签前钱浅欠抢强桥巧切且亲侵勤青清情请庆秋球区曲取"
    "全泉权劝却群"
    # x
    "西吸希息悉习席喜系细下夏先仙鲜弦现县限线相香乡详想向项小晓笑些协邪斜写"
    "械谢新心辛欣信兴星型形行醒姓幸兄胸雄熊休修秀袖需须许序叙宣选靴学雪血寻"
    "询训讯迅"
    # y
    "一衣医依移以已意义益亿亦异因音印英应营影硬拥永用优幽悠尤由油游有又右幼"
    "于予余与雨语玉元园原远院愿约月乐越云匀允运韵"
    # w
    "万晚碗湾玩完顽挽湾王网忘往望危威微为围伟尾味温文闻问稳翁我握屋无五午舞"
    "务物误雾夕吸希希"
)
# 去掉误入的非汉字/重复
RISK = {c for c in RISK if re.match(r"[\u4e00-\u9fff]", c)}

freq = {}
ndoc = 0
for f in glob.glob(CONV + "/*.jsonl"):
    for line in open(f, encoding="utf-8", errors="ignore"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        ndoc += 1
        a = d.get("a") or ""
        if not isinstance(a, str):
            continue
        for ch in a:
            if re.match(r"[\u4e00-\u9fff]", ch):
                freq[ch] = freq.get(ch, 0) + 1

print("对话条数 %d, 不同汉字 %d, 汉字总频次 %d" % (ndoc, len(freq), sum(freq.values())))
print()
# 高风险 ∩ 语料 ∩ 未处理，按字频降序
cand = [(c, n) for c, n in freq.items() if c in RISK and c not in ALREADY]
cand.sort(key=lambda x: -x[1])
print("=== 高风险候选（普通话卷舌/舌面/零声母 ∩ 真实语料 ∩ 未处理），按频次 ===")
print("共 %d 字：" % len(cand))
# 每行 12 个：字(频)
for i in range(0, len(cand), 12):
    print("  " + "  ".join("%s(%d)" % (c, n) for c, n in cand[i:i+12]))
print()
print("=== 全部高频字 top 60（供人工留意简繁异音）===")
top = sorted(freq.items(), key=lambda x: -x[1])[:60]
for i in range(0, len(top), 12):
    print("  " + "  ".join("%s(%d)" % (c, n) for c, n in top[i:i+12]))
