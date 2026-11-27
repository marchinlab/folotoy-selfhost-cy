#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿晴 · 粤语化后处理（普通话残留 -> 地道粤语）

背景：GLM-4-9B 的粤语输出已 ~90% 到位，但即使 system prompt 明令「他们→佢哋、
现在→而家」，仍会偶发漏几个普通话/书面词（实测：让/他们/多点/现在/例如/借助）。
光靠 prompt 压不住，故在网关返回给服务端之前做一次【确定性、高置信、零误伤】的
词级替换。服务端编译代码零改动，对话 + 定时播报两条链路自动覆盖。

设计原则（血泪教训：宁可少改，不可改错）：
  1. 只做「普通话虚词/代词/高频动词」-> 粤语；粤语本身也用的词（因为/所以/如果/
     可以/需要/希望/大家/目的/其实/当然/以前/以后/正在）一律不动，避免过度与生硬。
  2. 单字高危替换（是/给/让/没/吧/他/它）先用「保护词表」把复合词占位，再替换，
     最后还原，杜绝 「不是->不系」「酒吧->酒啦」「其他->其佢」「没有->冇有」 这类误伤。
  3. 有歧义的词【不做】（如「还是」既是「仍然(仲系)」又是「选择(定系)」），宁可漏不可错。
  4. 「的/了/在/和/着/把/被/不」这类误伤率极高的字【不做单字替换】；GLM 本身
     已能用好 嘅/咗/喺/同/住/畀/唔（真实稿验证），交给模型即可。
  5. 规则有序（长词先、复合先于单字），替换结果不含任何规则左端 => 天然幂等。
  6. YUE_POLISH=0 可一键关闭回滚。

独立自测：  python3 yue_polish.py
"""
import os, re, json

ENABLED = os.getenv("YUE_POLISH", "1").strip().lower() not in ("0", "false", "no", "off")
# 繁体->简体：9B 偶发冒繁体（進博會/華人/歷史/係），且繁体的「讓/現在」会让下游简体规则
# 匹配不上。故必须最先做。只收明确一一对应的高频新闻字；粤语本字（喺啲嘅咗唔佢哋嘢㗎）
# 本就不在繁简表内，绝不会被误转。繁简是同一字的不同写法，零语义风险。
T2S_ENABLED = os.getenv("YUE_T2S", "1").strip().lower() not in ("0", "false", "no", "off")
# 英文碎片清理：9B 超长联网回答会吐出被中文紧贴包围的乱码英文（giao 流 / 市场.entrySet /
# kéo 起嚟 / involve 嗰）。只清「中文紧贴 + 非白名单 + 非纯合法专名」的碎片，绝不动独立英文词。
EN_CLEAN_ENABLED = os.getenv("YUE_EN_CLEAN", "1").strip().lower() not in ("0", "false", "no", "off")
_EN_KEEP = {"AI", "UFC", "NBA", "CBA", "WHO", "WTO", "UN", "GDP", "CPI", "CEO", "CFO",
            "5G", "PM", "PM25", "COVID", "HIV", "AQI", "ATM", "GPS", "WIFI", "OK", "PK", "VS",
            "NASA", "FIFA", "ATP", "WTA", "VR", "AR", "APP", "PDF", "USB", "CPU", "LED",
            # v1.27 学科老师公式符号（小写按 .upper() 命中）：物理/数学/化学老师讲到
            # F=ma / pH / Ek / sin 时，呢啲短符号唔可以被当「中文夹乱码」清走，否则 TTS
            # 念成「F 等于。」「值小于 7」，公式变量凭空消失。精确枚举、唔放宽通用逻辑，
            # 新闻播报嘅乱码清理（giao/entrySet/specifically…）完全唔受影响。
            "MA", "MG", "PH", "EK", "EP",          # F=ma / mg / pH / Ek(动能) / Ep(势能)
            "SIN", "COS", "TAN", "COT", "LOG", "LN", "LIM", "MAX", "MIN",  # 数学函数
            "NAOH", "NACL", "HCL", "H2SO4", "HNO3", "CACO3", "NA2CO3"}  # 常见化学式（含数字项双保险）
# 9B 解码崩坏会吐任意非中文书写系统的碎片：拉丁扩展、希腊、西里尔、阿拉伯（含变音符号
# ً U+064B / ، U+060C）、希伯来、日文假名、韩文。凡「中文语境里夹的这类字符序列」都清掉。
# 左右边界排除「字母或数字」，保护 5G 的 G、PM2.5、32度 等（数字紧贴字母时不误切）。
_EN_CHARS = (r"A-Za-zÀ-ɏ"          # 拉丁 + 拉丁扩展（含 kéo 的重音）
             r"\u0370-\u03ff"      # 希腊
             r"\u0400-\u04ff"      # 西里尔
             r"\u0590-\u06ff"      # 希伯来 + 阿拉伯（含变音符号，实测ً،)
             r"\u3040-\u30ff"      # 日文假名
             r"\uac00-\ud7af")     # 韩文
_BOUND = r"A-Za-z0-9\u0370-\u06ff\u3040-\u30ff\uac00-\ud7af"
_EN_PHRASE = re.compile(
    r"(?<![" + _BOUND + r"])"
    r"(?P<en>[" + _EN_CHARS + r"]+(?:[ \t'\u2019\-]+[" + _EN_CHARS + r"]+){0,5})"
    r"(?![" + _BOUND + r"])"
)


def _clean_en_fragments(text):
    """删掉散落在中文里的英文/乱码短语；白名单专名、单字母、数字紧贴的缩写保留。
    迭代到不动点（上限3轮），确保删除后新形成的相邻结构也能被清掉、且幂等。
    返回 (新文本, 删除词数)。"""
    total = 0
    for _ in range(3):
        removed = [0]

        def _repl(m):
            en = m.group("en")
            words = [w for w in re.split(r"[ \t'\u2019\-]+", en) if w]
            # 单字母（a/I/x…）保留，避免误伤单位、变量、缩写残片
            if len(words) == 1 and len(words[0]) == 1:
                return m.group(0)
            # 非拉丁乱码（希腊/西里尔/阿拉伯/假名/韩文）绝不可能在白名单，直接判删
            if any(re.search(r"[^\x00-\x7f]", w) for w in words):
                removed[0] += len(words)
                return ""
            if any(w.upper() in _EN_KEEP for w in words):
                return m.group(0)
            removed[0] += len(words)
            return ""

        out = _EN_PHRASE.sub(_repl, text)
        out = re.sub(r"[\t ]{2,}", " ", out)
        out = re.sub(r"([，。！？、；：])\s*\1+", r"\1", out)
        # 清理删除后残留的悬空括号/空格：（）及其中的空格
        out = re.sub(r"[ \t]*（[ \t]*）", "", out)
        out = re.sub(r"[ \t]+([，。！？、；：])", r"\1", out)
        total += removed[0]
        if out == text or removed[0] == 0:
            text = out
            break
        text = out

    # 循环结束后统一做排版收敛（不受迭代 break 影响）
    text = re.sub(r"(?<=[\u4e00-\u9fff，。！？、；：])[ \t]+(?=[\u4e00-\u9fff（，。！？、；：])", "", text)
    text = re.sub(r"[ \t]+(?=[，。！？、；：）])", "", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\.(?=[\u4e00-\u9fff，。！？、；：（）]|$)", "", text)
    # 中文之间夹的孤立半角标点碎片（英文删词残留，如「电子 , . 产品」）；
    # 用中文前后断言，绝不碰 PM2.5 / 3.14 这类数字间小数点
    text = re.sub(r"(?<=[\u4e00-\u9fff])[ \t]*(?:[,.;:][ \t]*)+(?=[\u4e00-\u9fff])", "", text)
    return text, total


# 9B 长文退化时偶造的伪粤语助词/乱码字（硬黑名单，务必确认非合法粤字才加入）。
# 合法粤字 㗎 U+35CE / 㖞 U+359E / 㷫 U+3DEB / 㞗 U+3797 绝不在此列。
_GARBLE_CHARS = "\u35cd\u56cd"  # 㗍(伪助词,刷屏) 囍(乱码)


def _clean_markdown(text):
    """清掉口语稿里绝不该出现的 Markdown 标记 + 空括号 + 伪助词乱码字。返回 (文本, 计数)。"""
    n = 0
    text, a = re.subn(r"\*\*|__|\x60{1,3}", "", text); n += a               # ** __ ` ```
    text, b = re.subn(r"(?m)^[ \t]*(?:#{1,6}[ \t]*|>[ \t]*|[-*+][ \t]+|\d+\.[ \t]+)", "", text); n += b  # 行首标题/列表
    text, c = re.subn(r"(?<!\w)\*(?!\s)|(?<!\w)_(?!\s)", "", text); n += c    # 零散 * _
    text, d = re.subn(r"\(\s*\)|（\s*）", "", text); n += d                   # 空括号 () （）
    for ch in _GARBLE_CHARS:                                                   # 伪助词/乱码字
        text, e = re.subn(re.escape(ch), "", text); n += e
    return text, n
# 每对「繁+简」两字连写，逐字映射；重复繁键无害（后者覆盖）。
_T2S_STR = (
    "係系進进會会華华脈脉講讲關关經经濟济場场國国際际貿贸醫医"
    "設设備备發发現现東东馬马來来亞亚攝摄時时裡里裏里齊齐樣样"
    "點点幾几種种對对當当為为無无與与並并選选舉举辦办處处聲声"
    "稱称報报導导體体傳传統统計计數数據据優优勢势廠厂務务業业"
    "條条項项靈灵應应變变動动靜静環环護护膚肤濕湿乾干預预書书"
    "視视頻频機机電电腦脑絡络訊讯過过運运輸输鐵铁車车門门灣湾"
    "島岛陸陆區区縣县鎮镇鄉乡農农資资漲涨價价減减長长積积極极"
    "規规協协議议約约簽签執执飛飞證证邊边檢检療疗藥药臨临試试"
    "驗验風风險险戰战競竞爭争聯联團团隊队組组織织構构劃划實实"
    "監监評评審审測测顯显準准範范後后餘余勝胜質质達达徑径潤润"
    "節节產产銷销費费貼贴錢钱銀银貨货買买賣卖貴贵賠赔債债帳账"
    "冊册僑侨採采訪访惡恶復复甦苏興兴"
    "讓让們们屆届歷历歸归還还過过還还餘余幾几幫帮"
    "緊紧懸悬憑凭盡尽慶庆舊旧舉举親亲產产黨党氣气"
    "櫃柜檯台枱台臺台麵面鬆松瞭了傢家總总"
    # 2026-11-11 补：9B 粤语播报实测冒出嘅高频繁体（「一單大事件」「嚇到」等）
    "單单嚇吓純纯樓楼雲云陽阳陳陈陣阵隱隐"
    "傘伞曬晒涼凉凍冻熱热悶闷財财聞闻"
    "間间帶带應应側侧壓压幫帮鐘钟醬酱湯汤"
    # 2026-11-11 再补：换 30B 后实测冒出嘅繁体（「唔敢亂讲」「最新測量結果」）
    "亂乱結结測测內内問问寫写讀读聽听說说話话語语"
)
assert len(_T2S_STR) % 2 == 0, "繁简表长度必须为偶数（每对两字）"
_T2S = {}
for _i in range(0, len(_T2S_STR), 2):
    _f, _j = _T2S_STR[_i], _T2S_STR[_i + 1]
    assert _f != _j, "繁简表第 %d 对繁简相同（无效）: %s" % (_i // 2, _f)
    _T2S[ord(_f)] = _j

# ---- 保护词：含单字替换目标、但不该被改的复合词（占位 -> 最后原样还原）----
PROTECT = [
    # 给
    "给予", "供给", "给与", "给以", "自给自足", "自给", "补给", "配给", "给养",
    # 让
    "让步", "退让", "谦让", "让利", "让座", "让位", "让开", "让路", "让贤",
    "转让", "割让", "让与", "让渡", "推让", "揖让",
    # 没
    "没落", "沉没", "埋没", "淹没", "覆没", "出没", "没入", "没世", "没齿",
    # 吧
    "酒吧", "网吧", "吧台", "吧凳", "吧唧", "吧嗒", "氧吧", "吧主", "茶吧", "水吧", "书吧", "清吧",
    # 他 / 它 单字保护（避免「其他->其佢」「利他->利佢」）
    "其他", "其它", "利他", "利他主义", "排他", "他乡", "他日", "他年",
    "他杀", "他律", "他者", "他人", "无他", "自他",
    # 是（含「是」但不该被单字 是->系 拆开的复合词；拆了会出「还系/便系」等非地道粤语）
    "还是", "便是", "纵是", "定是", "自是", "硬是", "横是", "终是", "究是", "倒是",
    "是非", "自以为是", "唯利是图", "是故", "是日", "是时", "莫不是", "可不是",
    "端的是", "然则是", "抑或是", "果是", "是则",
    # 专名/专有机构（防御未来加规则时误伤）
    "中国天气网", "干燥指数", "进博会", "内蒙古", "京津冀", "第九届",
    "家乡好物", "供港出海", "西关", "中新网", "新浪",
]
_PROT_RE = re.compile("|".join(re.escape(w) for w in sorted(PROTECT, key=len, reverse=True)))

# ---- 有序替换规则：长词 / 复合词在前，单字在最后 ----
RULES = [
    # 0a) v1.32：堵病句「呢个嗰阵」——根因系「这个时候」先被下面「这个->呢个」拆成
    #    「呢个时候」，再被「时候->嗰阵」兜成「呢个嗰阵」：「呢个」(近指)撞「嗰阵」(远指过去)，
    #    自相矛盾唔通。主人指定改「呢个时期」。必须早过「这个->呢个」同「时候->嗰阵」两步，
    #    任何一步抢先都拦唔住；终态「呢个时期」唔含任何左端 => 幂等。
    #    ⚠️「嗰阵」其他正确用法一律唔郁：那时候->嗰阵、的时候->嘅嗰阵、古嗰阵、落山嗰阵。
    ("这个时候", "呢个时期"), ("这个时期", "呢个时期"), ("呢个时候", "呢个时期"),
    # 0a-2) v1.32 顺带修同源历史 bug：「什么时候」旧位置(6组)排喺「什么->乜」之后，
    #   实跑永远先被拆成「乜时候」再兜成【病句「乜嗰阵」】(同「呢个嗰阵」根因)。提到最顶先至保得住。
    ("什么时候", "几时"),
    # 0) 最长优先：「这/那+是」复合词必须早过「就是->即系」「是->系」，
    #    否则「这就是」会被拆成「这即系」。30B 高频冒呢类词，故置顶。
    ("这就是", "呢个就系"), ("那就是", "嗰个就系"),
    ("这是喺", "呢个系喺"), ("那是喺", "嗰个系喺"),
    ("这是", "呢个系"), ("那是", "嗰个系"),
    # 1) 含「是」复合词（必须先于单字 是->系）；有歧义的「还是」故意不收
    ("是不是", "系唔系"), ("是否", "系咪"), ("是的", "系呀"),
    ("不是", "唔系"), ("但是", "不过"), ("可是", "不过"), ("然而", "不过"),
    ("就是", "即系"), ("只是", "净系"),
    ("要是", "如果"), ("若是", "如果"), ("于是", "跟住"), ("即使", "就算"),
    ("既是", "既然系"), ("凡是", "凡系"), ("总是", "总系"), ("或是", "或者系"), ("即是", "即系"),
    # 2) 疑问 / 否定 / 代词（先于单字 他/她/它、没）
    ("为什么", "点解"), ("怎么样", "点样"), ("知不知道", "知唔知"), ("不知道", "唔知"),
    ("有没有", "有冇"), ("没有", "冇"), ("能不能", "能唔能"), ("可不可以", "可唔可以"),
    ("行不行", "得唔得"), ("好不好", "好唔好"),
    ("怎么", "点样"), ("怎样", "点样"),
    ("我们", "我哋"), ("你们", "你哋"), ("他们", "佢哋"), ("她们", "佢哋"), ("它们", "佢哋"),
    ("什么", "乜"), ("别人", "人哋"), ("人家", "人哋"),
    ("这个", "呢个"), ("这些", "呢啲"), ("这里", "呢度"), ("这儿", "呢度"),
    ("那个", "嗰个"), ("那些", "嗰啲"), ("那里", "嗰度"), ("那儿", "嗰度"),
    ("哪个", "边个"), ("哪里", "边度"), ("哪儿", "边度"), ("多少", "几多"),
    # 2b) 指量 / 程度指代（高频，且无歧义）
    ("这种", "呢种"), ("这次", "呢次"), ("这边", "呢边"),
    ("那种", "嗰种"), ("那次", "嗰次"), ("那边", "嗰边"),
    ("这么", "咁"), ("那么", "咁"), ("这样", "咁样"), ("那样", "嗰样"),
    # 3) 时间 / 时序（只收粤语不会自然用原词、且无歧义的）
    ("今天", "今日"), ("明天", "听日"), ("昨天", "寻日"), ("前天", "前日"), ("后天", "后日"),
    ("现在", "而家"), ("刚才", "头先"), ("刚刚", "头先"),
    ("马上", "即刻"), ("立刻", "即刻"), ("立即", "即刻"), ("赶紧", "快啲"), ("赶快", "快啲"),
    ("将要", "就快"), ("即将", "就快"),
    # 4) 程度 / 范围 / 数量
    ("有点儿", "有啲"), ("有点", "有啲"), ("一点儿", "一啲"), ("一点点", "一啲啲"),
    # 注意：「一点」不可做裸 str.replace——会误伤小数点(二十一点四)、时间点(十一点/一点钟)、
    #       序数(第三点)。已移至下方 REGEX_RULES 用带边界的正则安全处理。
    ("一些", "一啲"), ("很多", "好多"), ("许多", "好多"), ("大量", "好多"),
    ("差点儿", "差啲"), ("差点", "差啲"), ("一起", "一齐"), ("一块儿", "一齐"),
    ("一同", "一齐"), ("只有", "净系"), ("仅仅", "净系"), ("帮忙", "帮手"),
    # 5) 连词 / 介词 / 高频动词（含真实稿漏网词）
    ("然后", "跟住"), ("以及", "同埋"), ("还有", "仲有"), ("而且", "加埋"),
    ("通过", "透过"), ("对于", "对"), ("借助", "靠"), ("例如", "好似"), ("比如", "譬如"),
    ("多点", "多啲"), ("喜欢", "钟意"), ("认为", "觉得"), ("知道", "知"),
    ("孩子", "细路"), ("小孩", "细路"), ("便宜", "平"),
    # 6) 「时候」系列：含「时候」的复合词全部先处理，最后才轮到单字「时候」
    #    ⚠️「什么时候」已移到 0a-2 顶部（放呢度会被「什么->乜」抢先拆成「乜时候」->「乜嗰阵」）
    ("这时候", "呢阵"), ("那时候", "嗰阵"),
    ("有时候", "间中"), ("的时候", "嘅嗰阵"), ("时候", "嗰阵"),
    # 6b) v1.32 兜底：万一「呢个时候」由更上游路径漏落（例如先被别条规则动过），
    #     落到这里已经变成「呢个嗰阵」，再收一次返「呢个时期」。幂等、唔影响上面正确用法。
    ("呢个嗰阵", "呢个时期"),
]
# 7) 单字高危替换（保护词已占位；放在最末）
SINGLE_RULES = [
    ("他", "佢"), ("她", "佢"), ("它", "佢"),
    ("是", "系"), ("给", "畀"), ("让", "畀"), ("没", "冇"), ("吧", "啦"),
    ("很", "好"), ("吗", "呀"), ("啊", "呀"), ("哦", "噢"),
]
_ALL = RULES + SINGLE_RULES

# 8) 零误伤正则（在 str.replace 全部跑完后执行；负向前/后视排除非目标词）
REGEX_RULES = [
    # 在 + 指代方位 -> 喺（排除 现在/正在/实在/存在/自在/而在）
    (re.compile(r"(?<![现正实存自而])在(?=呢|嗰|边|度)"), "喺"),
    # 被 + 人称/泛指 -> 畀（排除 被动/被告/被单/被子）
    (re.compile(r"被(?=我|你|佢|人|大家|人哋)"), "畀"),
    # 「一点」->「一啲」只在此处安全处理：用负向断言排除
    #   小数点(二十一点四)、时间点(十一点/一点钟/一点半/一点多)、序数(第一点)。
    #   裸 str.replace 会把「二十一点四度」误伤成「二十一啲四度」，故从 RULES 移出。
    (re.compile(r"(?<![零一二三四五六七八九十百千万两0-9第])一点(?![零一二三四五六七八九0-9钟点半刻整多到至正左])"), "一啲"),
    # v1.32：别扭正反问「(有啲)想X定系唔X」-> 地道「想唔想X」。
    #   主人实测「你有啲想知定系唔知」应系「你想唔想知」：想知又唔知，前后矛盾，地道讲法系「想唔想知」。
    #   ⚠️「定系」本身系【合法】选择问连词（你去定系我去 / 食饭定系食面），绝唔可以全局删改；
    #     只喺【想 + X(1~3汉字) + 定系唔 + 同一个X】呢个完整矛盾句式先至重构。
    #     反向引用 \1 锁死前后动词一致 + X 长度上限 3，双重挡住跨句/合法句误伤。
    #     (?:有啲)? 令「想知定系唔知」(无有啲) 都收敛；「有点」会先经 RULES 变「有啲」再落到呢度。
    #     幂等：结果「想唔想知」唔含「定系」，二次 polish 唔再命中。
    (re.compile(r"(?:有啲)?想([\u4e00-\u9fff]{1,3}?)定系唔\1"), r"想唔想\1"),
]


# ============ v1.39 填充口头禅清理（治本兜底，2026-11-12）============
# 模型喺人设「口语化」同老师 prompt「讲完追问明唔明」引导下，自己加咗大量
# 无信息量嘅填充（落盘实测「你知唔知」一日 18 次）。治本落咗网关 system 尾钉，
# 呢层只防漏，故【只收无歧义、零误伤】两条，宁漏勿错删知识内容：
#   A) 句首转场「你知唔知，」「而家你知唔知，」——带逗号＝铺垫，删；
#      【保留】无逗号直接带宾语嘅真问句，如「你知唔知「天可汗」呢个称号？」
#   B) 整句客套追问「你明唔明？」「明唔明呀？」「你听明唔明？」——短、无知识，删。
# 流式句子级 polish 下 B 会删成空串：玩具端 `if c:` 忽略空 delta、落盘 "".join
# 空串无害，故安全。A 保留句首位置（句首删后系逗号，需去掉多余逗号）。
_FILLER_LEAD = re.compile(r"(?:^|(?<=[。！？!?；;\n]))\s*(?:而家)?你知唔知[，,]\s*")
_FILLER_TAIL_Q = re.compile(r"(?:^|(?<=[。！？!?；;\n]))\s*(?:你听)?(?:你)?明唔明(?:呢个画面)?(?:呀|啊|吗|呢)?\s*[？?！!。.]?\s*(?=$|[。！？!?；;\n])")


def _clean_filler(text):
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
#   「呢个年份唔好记错，就系资料清清楚楚写明嘅。」（E2E 实测变体，唔带「唔好改」）
# 呢类句零知识、纯【评价资料来源本身】，主人明确要去掉。v1.41b 增强：
#   【整句删除】——整句必须【同时】含「资料/資料」+「(讲/写)得清清楚楚 /
#   清清楚楚写明 / 写得清楚」等评价词，先至删【成个句】（含可选前缀
#   「呢个時间点，」「呢个年份唔好记错，就系」同句末标点），删净唔留残句。
#   繁简通吃（時/时、間/间、點/点、資/资、講/讲、寫/写）。
# 【硬防误伤】「资料」同「清楚」必须【同句强绑定】且以句末标点为界，故不碰：
#   - 「远望得清清楚楚」        （无「资料」= 正常描写）
#   - 「资料讲到嘅事实，人名…一律照原样讲」（有「资料」无「清楚」= 正常引用）
#   - 「过马路唔好乱跑/唔好乱爬」  （无「资料」无「清楚」= 安全教育）
#   - 「我搵唔到确切资料，唔敢乱作」（有「资料」无「清楚」= 诚实坦白）
#   - 「但唔好以为唐朝就唔好」    （无「资料」无「清楚」= 正常论述）
# 其余自我叮嘱（「唔好乱打」「我唔好乱估」）常嵌诚实声明，交 v1.41 治本
#   system 尾钉令模型根本唔生成，兜底宁漏勿错删。poem 朗读模式豁免。
_META_DOC = re.compile(
    r"(?:^|(?<=[。！？!?；;\n]))"            # 句首边界（唔跨句）
    r"\s*[^。！？!?；;\n]{0,24}?"             # 可选前缀（呢个時间点，/ 呢个年份唔好记错，就系）
    r"[资資]料[^。！？!?；;\n]{0,12}?"
    r"(?:清清楚楚|写得清楚|寫得清楚|讲得清楚|講得清楚|写得好清楚|寫得好清楚)"
    r"[^。！？!?；;\n]{0,16}?"                # 后缀（，唔好乱改 / 写明嘅）
    r"[。！？!?]"                             # 句末标点（必有＝删整句）
)


def _clean_meta_instruction(text):
    """返回 (清理后文本, 命中次数)。只删上面一条最高置信元评论整句。"""
    work, n = _META_DOC.subn("", text)
    if n:
        work = re.sub(r"(?m)^[ \t]*[，,]\s*", "", work)
        work = re.sub(r"[ \t]{2,}", " ", work)
        work = re.sub(r"\n{3,}", "\n\n", work).strip()
    return work, n


def polish(text, report=False, poem=False):
    """返回粤语化后的文本；report=True 时返回 (文本, {规则:命中次数})。
    poem=True（朗读诗词/古文）：【跳过全部口语化替换】，只保留繁→简统一 +
    Markdown/英文乱码清洁，令诗句逐字照原文。因为粤语「是」书面/文言朗读读 si6，
    口语「係/系」读 hai6，是两套系统；读「同是天涯沦落人」必须 si6，唔可以变「同系」。
    只由网关识别出朗读意图时开启；日常对话 poem=False，行为与之前完全一致。
    """
    if not ENABLED or not isinstance(text, str) or not text:
        return (text, {}) if report else text

    hits = {}
    # 0) 繁->简最先做：既统一语体，又让下游简体规则能命中原本是繁体的「讓/現在/他們」
    if T2S_ENABLED:
        n_t2s = sum(1 for ch in text if ord(ch) in _T2S)
        if n_t2s:
            text = text.translate(_T2S)
            hits["繁→简"] = n_t2s

    protected = {}

    def _stash(m):
        key = "\ue000%d\ue001" % len(protected)
        protected[key] = m.group(0)
        return key

    work = _PROT_RE.sub(_stash, text)
    # ★ 诗词朗读模式：唔落任何口语化映射，诗句逐字保留原文。
    #   「是/然而/让/只是/不是」等喺诗里要照字面读（si6 等），
    #   唔好转成「系/不过/畀/净系/唔系」。占位照 stash/还原（恒等，无害）。
    if not poem:
        for a, b in _ALL:
            if a in work:
                c = work.count(a)
                work = work.replace(a, b)
                if c:
                    hits[a + "→" + b] = c
        for pat, b in REGEX_RULES:
            work, n = pat.subn(b, work)
            if n:
                hits["re:" + pat.pattern[:8] + "→" + b] = n
    for key, val in protected.items():
        work = work.replace(key, val)

    # 8b) 单字替换可能撞出叠字（让+给 -> 畀畀；给+給 等），收敛掉
    work = re.sub(r"畀畀+", "畀", work)

    # 9) Markdown 标记清理（口语稿绝不该有 ** / ` / ## / 列表）
    work, n_md = _clean_markdown(work)
    if n_md:
        hits["Markdown清理"] = n_md

    # 10) 英文/乱码短语清理（还原占位后做，避免碰被保护词）；白名单专名保留
    if EN_CLEAN_ENABLED:
        work, n_en = _clean_en_fragments(work)
        if n_en:
            hits["英文乱码清理"] = n_en

    # 11) v1.39 填充口头禅清理（治本兜底，只收高置信两条；poem 朗读唔郁）
    if not poem:
        work, n_filler = _clean_filler(work)
        if n_filler:
            hits["填充口头禅清理"] = n_filler

    # 12) v1.41 指令腔元评论清理（只收「资料讲得清清楚楚+唔好改」一条，宁漏勿错）
    if not poem:
        work, n_meta = _clean_meta_instruction(work)
        if n_meta:
            hits["指令腔元评论清理"] = n_meta

    return (work, hits) if report else work


# ============ 英语老师专用轻量后处理（v1.24）============
# 背景：英语老师要用【普通话 + 中英双语】讲解，必须【整条豁免】普通话->粤语化、
# 英文碎片清理、多音字正音（否则 She/present continuous 会被清光）。但 v1.22 的
# skip=True 是「裸透传」，连 emoji / Markdown 星号 / 「根据资料」元话语都放过，
# 实测输出混进 ✅ 👉 **加粗** 「资料确认：」，违反人设。故单独给一条轻量管线：
#   做：繁->简、清 Markdown/emoji/特殊符号、清「根据资料」类元话语、粤语字回退普通话
#   不做：普通话->粤语化替换、英文碎片清理、正音（这三样会毁掉中英双语）
# 设计仍是「宁可少改不可改错」：粤语字回退只收【粤语专用、普通话几乎不用】的高置信字。
_EN_META = re.compile(
    r"(?:根据|据|依据|按照|透过|通过)\s*(?:上面|以上|上述|啱啱|刚刚|联网)?\s*"
    r"(?:查到|搜到|检索到|找到|提供)?\s*(?:嘅|的)?\s*"
    r"(?:真实)?(?:资料|数据|信息|来源|新闻|内容)"
    r"|(?:\S{0,6})(?:资料(?:显示|确认|表明|指出|提到|讲到|入面|里面|冇|没有|未)|"
    r"据(?:资料|查|搜)|联网查到(?:嘅|的)?|上面(?:啱啱|刚刚)?联网)"
    r"|According\s+to[^\n。，,]{0,40}"
)
# emoji / 装饰符号：杂项符号、竖排、transport、faces、hand、commit 等常见区段
_EN_EMOJI = re.compile(
    "[\u2190-\u21ff\u2300-\u23ff\u2460-\u24ff\u25a0-\u25ff\u2600-\u27bf"
    "\u2b00-\u2bff\U0001f000-\U0001faff\uFE0F\u200D]"
)
# 高置信「粤语专用字 -> 普通话」回退：仅在英语老师链路用。这些字普通话正文几乎不出现，
# 30B 冒出来基本就是串味。刻意【不收】「系/唔/啲/咗/嘅」这类会误伤的音近/高频字组合，
# 只收语义唯一、形状特殊的粤字，宁可漏不可错。
_EN_YUE_BACK = (
    ("唔该", "谢谢"), ("唔好意思", "不好意思"), ("明唔明", "明白吗"),
    ("知唔知", "知道吗"), ("系咪", "是不是"), ("有冇", "有没有"),
    ("我哋", "我们"), ("你哋", "你们"), ("佢哋", "他们"), ("人哋", "别人"),
    ("呢个", "这个"), ("呢啲", "这些"), ("呢度", "这里"),
    ("嗰个", "那个"), ("嗰啲", "那些"), ("嗰度", "那里"),
    ("而家", "现在"), ("头先", "刚才"), ("而家", "现在"),
    ("点解", "为什么"), ("点样", "怎么样"), ("几时", "什么时候"),
    ("边个", "谁"), ("边度", "哪里"), ("几多", "多少"),
    ("钟意", "喜欢"), ("睇下", "看看"), ("试下", "试试"), ("讲下", "讲讲"),
    ("这度", "这里"), ("嗰度", "那里"),
    ("好嘅", "好的"), ("系呀", "是的"), ("唔系", "不是"), ("冇", "没有"),
    ("嘅", "的"), ("㗎", "的"), ("咗", "了"), ("啲", "些"),
    ("嚟", "来"), ("喺", "在"), ("畀", "给"), ("佢", "他"),
    ("哋", "们"), ("嘢", "东西"), ("咩", "什么"), ("乜", "什么"),
    ("唔", "不"), ("啦", "了"), ("咯", "了"), ("嘞", "了"),
)


def polish_english(text, report=False):
    """英语老师（中英双语·普通话）专用轻量清洗。返回 (文本, {规则:次数}) 或 文本。
    与 polish() 完全独立：绝不做普通话->粤语化、绝不清英文、绝不正音。"""
    if not isinstance(text, str) or not text:
        return (text, {}) if report else text
    hits = {}
    # 1) 繁->简（复用现成表，零语义风险）
    if T2S_ENABLED:
        n = sum(1 for ch in text if ord(ch) in _T2S)
        if n:
            text = text.translate(_T2S)
            hits["繁→简"] = n
    # 2) 元话语：「根据资料 / 资料显示 / According to ...」清掉，唔好念来源
    text, n = _EN_META.subn("", text)
    if n:
        hits["元话语清理"] = n
    # 3) emoji / 装饰符号（✅👉➡★ 等），唔好入 TTS
    text, n = _EN_EMOJI.subn("", text)
    if n:
        hits["emoji清理"] = n
    # 4) Markdown（** ` ## 行首列表 / 空括号 / 伪助词），复用现成件
    text, n = _clean_markdown(text)
    if n:
        hits["Markdown清理"] = n
    # 5) 高置信粤语字回退普通话（30B 万一串味时兜底；宁漏勿错）
    n = 0
    for a, b in _EN_YUE_BACK:
        if a in text:
            c = text.count(a)
            text = text.replace(a, b)
            n += c
    if n:
        hits["粤→普回退"] = n
    # 6) 排版收敛：删除后残留的多余空格/重复标点/空行
    text = re.sub(r"[\t ]{2,}", " ", text)
    text = re.sub(r"([，。！？、；：])\s*\1+", r"\1", text)
    text = re.sub(r"[ \t]+([，。！？、；：）])", r"\1", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])[ \t]*\n[ \t]*(?=\S)", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return (text, hits) if report else text


def _sse_whole_clean(body, cleaner):
    """v1.27 通用骨架：SSE【流式整段清洗回填】，英语老师同粤语角色共用。

    背景：网关 forward() 已用 r.read() 把上游整段流式响应读全，polish_response 收到的
    body 是【完整 SSE 文本】。旧流式实现逐 delta 调清洗函数，两大伤害：
      · 英语老师：polish_english 末尾 .strip()/空格压缩食咗每个 token 前导空格 ->
        英文粘词 Iamplanningto、'\\n' 断句飞晒（真链路 39 词塌成 7 词）。
      · 粤语角色：polish 嘅词级替换（我们->我哋/现在->而家/听日->汀日）喺单字 token 上
        根本匹配唔到 -> 流式漏粤语化（主人早期「有部分文本冇粤语化」嘅真凶）；跨 token
        英文乱码亦清唔干净。
    修法：收集所有 data 帧 delta.content 拼【整段原文】-> 对整段调一次 cleaner（整段
    清洗，词级/正音/emoji/元话语跨 token 模式全部命中，且唔伤英文词间空格同 '\\n'）-> 按
    【原帧各自长度比例】切片回填，尾帧吸收余量，保证 concat == cleaner(整段原文)、
    帧数/帧序/finish_reason/usage/[DONE] 全部原样、大脑端零感知。
    cleaner(whole) -> (清洗后文本, hits_dict)。任何异常原样透传，绝唔令对话挂掉。
    """
    try:
        raw_text = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)
        lines = raw_text.split("\n")          # 保留空行（SSE 帧以空行分隔）
        # 1) 收集：记录每个含 content 嘅 data 帧嘅 行号 / 完整 json / choice 索引 / 原 content
        slots = []          # (line_idx, d, ch_idx, original_content)
        pieces = []
        for li, line in enumerate(lines):
            st = line.strip()
            if not st.startswith("data:") or st == "data: [DONE]":
                continue
            js = st[5:].strip()
            if not js:
                continue
            try:
                d = json.loads(js)
            except Exception:
                continue                      # 解析唔到嘅帧原样透传
            for ci, ch in enumerate(d.get("choices", [])):
                delta = ch.get("delta") or {}
                c = delta.get("content")
                if isinstance(c, str) and c:
                    slots.append((li, d, ci, c))
                    pieces.append(c)
        if not slots:
            return body, {}                   # 无正文，原样
        whole = "".join(pieces)
        cleaned, hits = cleaner(whole)        # ★整段一次清洗（关键）
        # 2) 回填：按各帧【原长度比例】分配清洗后文本，尾帧吸收全部余量，concat 恒等
        total_orig = sum(len(c) for _, _, _, c in slots)
        n = len(slots)
        pos = 0
        for i, (li, d, ci, _c) in enumerate(slots):
            orig_len = len(_c)
            if i == n - 1:
                seg = cleaned[pos:]            # 尾帧吃光余量（无论清洗后变长/变短）
            elif total_orig > 0:
                want = int(round(len(cleaned) * orig_len / float(total_orig)))
                want = max(0, min(want, len(cleaned) - pos))
                seg = cleaned[pos:pos + want]
            else:
                seg = ""
            pos += len(seg)
            d["choices"][ci]["delta"]["content"] = seg
            lines[li] = "data: " + json.dumps(d, ensure_ascii=False)
        return "\n".join(lines).encode("utf-8"), hits
    except Exception:
        return body, {}                       # 任何异常原样透传，绝唔因后处理令对话挂掉


def polish_english_sse(body, fixer=None):
    """英语老师【流式】整段清洗：保住英文词间空格 + '\\n' 断句（v1.27）。
    v1.28 加 fixer：正音（如 单->單）喺整段 polish_english 之后先至跑——polish_english
    第1步系繁->简，若先正音会被打回简体；fixer 只替换中文字符、唔碰 ASCII 英文/音标/数字，
    所以英文正文同断句零影响，但英文老师讲「单词」会被修正念 daan1(唔再系「善」)。"""
    def _clean(t):
        out, hits = polish_english(t, report=True)
        if fixer:
            out = fixer(out)
        return out, hits
    return _sse_whole_clean(body, _clean)


def polish_cantonese_sse(body, poem=False, fixer=None):
    """粤语角色【流式】整段清洗：令词级粤语化 + 正音 + 中文断句喺流式下全部生效（v1.27）。
    poem=True 诗词朗读逐字照原文；fixer 系 TTS 正音函数（如 tts_pron.fix），喺整段 polish
    之后先至跑，避免「區/會」被繁转简打回简体。行为=非流式分支，流式唔再漏粤语化。
    """
    def _clean(t):
        out, hits = polish(t, report=True, poem=poem)
        if fixer:
            out = fixer(out)
        return out, hits
    return _sse_whole_clean(body, _clean)


# ============ v1.29 TTS 斜杠/音标清理（播报专用，唔落盘）============
# 背景：主人实测「斜杠符号都读出来」——edge-tts 把 ASCII '/' 念成「斜杠」，并把
#   英语老师/英文自动路由输出嘅国际音标 /pɔɪnt/ 入面嘅 IPA 字母（p ɔ ɪ n t）逐个念成乱码。
#   声学铁证（zh-HK-HiuMaanNeural，同 rate）：point / 点 = 1.80s vs point 点 = 1.44s
#   （多出 0.36s 就系「斜杠」两字）；point /pɔɪnt/ 点 = 2.74s，连【只删斜杠留裸 IPA】
#   嘅 point pɔɪnt 点 都要 1.90s——即系 IPA 字母本身都会被念，必须【整段 /…/ 删】。
# 落盘 30 种成对斜杠块，28 种系 IPA（含 ɔ ɪ ˈ ˌ ː ʃ ŋ æ ʌ ɑ ə ʊ 等 IPA 专用字符），
#   净低 2 种系物理公式（m/s²、F/m）。故分两类处理，且【只改播报稿、唔改落盘/查看页】
#   （双轨：家长喺 /chat 睇到完整音标教学稿，细路听到嘅系干净语音）：
#   1) IPA 音标块：/ 开头 + 含 IPA 字符 + / 结尾 -> 整段删（含两侧斜杠同 IPA 内容）。
#      判据用「块内有无 IPA 专用字符」，天然唔会误伤 2026/11/11（纯数字）、
#      and/or（纯 ASCII）、http://（URL）。删后清理孤立「音标：」空标签同残留空格。
#   2) 公式/单位斜杠（非音标）：m/s² -> m每s²、F/m -> F除以m、10N / 2kg -> 10N除以2kg；
#      and/or -> and or（唔破坏英文）。兜底：任何残留 '/' 一律删，保证绝念唔出「斜杠」。
#   3) 呢个 cleaning 跑喺 polish/正音【之后】、发畀大脑【之前】，唔碰 ASCII 英文正文/
#      中文/断句/v1.27 公式白名单（F=ma 主体同 ² 全部保留），只针对 '/' 同音标块。

# IPA 专用字符：拉丁扩展 IPA 区 + IPA 补充符号 + 重音/长音符号（ˈ ˌ ː ˑ ʼ）
_IPA_CHAR = re.compile(
    "[\u0250-\u02af\u1d00-\u1dff\u02b0-\u02ff"
    "\u02c8\u02cc\u02d0\u02d1\u02bc"          # ˈ ˌ ː ˑ ʼ
    "ɑɒæʌɔɜəɪʊøœɐɯɤɵʃʒŋθðçʝɲɳɽɾʔ]"
)
# 成对斜杠块（不含换行、不含 '/'）：先粗抓，再按「块内含 IPA 字符」判定系咪音标
_IPA_BLOCK = re.compile(r"/([^/\n]{1,80})/")
# 裸 IPA 串（v1.29 E2E 实测补充）：模型解释发音时会用引号包【无斜杠】嘅音标，
#   如 组合读作“pɔɪnt”、"Road" 读作 "rəʊd"、lively "live" 读作 "laɪv"。
#   呢啲冇 '/'，入口 if '/' not in text 会漏。判据：连续串（ASCII字母/IPA字符/重音符/
#   空格/点/连字符）内【至少含 1 个 IPA 字符】先至删 —— 纯英文 point/road 一律唔会命中。
_BARE_IPA = re.compile(r"[A-Za-z\u0250-\u02af\u1d00-\u1dff\u02b0-\u02ffˈˌːˑʼɑɒæʌɔɜəɪʊøœɐɯɤɵʃʒŋθðçʝɲɳɽɾʔ.\- ]{2,40}")


def _ipa_block_repl(m):
    """成对斜杠块：含 IPA 字符 -> 整段删（音标）；否则原样（留给公式/兜底处理）。"""
    return "" if _IPA_CHAR.search(m.group(1)) else m.group(0)


def _bare_ipa_repl(m):
    """裸 IPA 串：含 IPA 字符 -> 整段删；纯 ASCII 英文原样（保住 point/road 等正文）。"""
    return "" if _IPA_CHAR.search(m.group(0)) else m.group(0)


# 公式/单位斜杠：两侧【完整】字母/数字串，中间一个 '/'
# 用函数按语境决定读法：右侧带上标(²³)=单位「每」；and/or 类纯英文=空格；其余=「除以」
_FORMULA_SLASH = re.compile(r"([A-Za-z0-9²³]+)\s*/\s*([A-Za-z0-9²³]+)")
# URL 同日期优先占位保护（避免 com/path -> com除以path、2026/11/11 -> 2026除以11）
_URL_PROT = re.compile(r"https?://[^\s，。；、）]+", re.I)
_DATE_PROT = re.compile(r"(?<!\d)(\d{4})/(\d{1,2})/(\d{1,2})(?!\d)")
_SENTINEL = "\x00"   # TTS 文本绝不会出现 NUL，做占位符前缀


def _formula_slash_repl(m):
    left, right = m.group(1), m.group(2)
    if right.endswith("²") or right.endswith("³") or right in ("2", "3"):
        return left + "每" + right        # m/s² -> m每s²（单位：每）
    if (left.lower(), right.lower()) in (("and", "or"), ("or", "and"), ("w", "o"), ("n", "a")):
        return left + " " + right         # and/or -> and or（唔破坏英文短语）
    return left + "除以" + right          # F/m -> F除以m、10N / 2kg -> 10N除以2kg


def clean_tts_symbols(text, report=False):
    """TTS 播报专用符号清理：删 IPA 音标块 + 公式斜杠转中文读法 + 兜底删残留 '/'。

    只改要发畀 edge-tts 嘅文本，绝唔落盘（落盘用 extract_answer_text 从【清理前】body 抽）。
    设计「宁可少改不可改错」：靠 IPA 字符判据精确定位音标，唔靠「凡 /.../ 都删」，
    故 2026/11/11、and/or、http:// 一律安全。返回 (文本, {规则:次数}) 或 文本。
    """
    if not isinstance(text, str) or not text:
        return (text, {}) if report else text
    # 快路径：无 '/' 亦无 IPA 字符 -> 原样（避免每段都跑全套正则）
    if "/" not in text and not _IPA_CHAR.search(text):
        return (text, {}) if report else text
    hits = {}
    out = text
    # 0) URL / 日期先占位保护（呢两样唔郁，或转成自然读法，绝唔好变「除以」）
    prot = []
    def _stash(kind, raw, repl):
        prot.append(repl)
        return _SENTINEL + str(len(prot) - 1) + _SENTINEL
    out = _URL_PROT.sub(lambda m: _stash("url", m.group(0), m.group(0)), out)
    out = _DATE_PROT.sub(lambda m: _stash("date", m.group(0),
                          m.group(1) + "年" + m.group(2) + "月" + m.group(3) + "日"), out)
    # 1) 整段删 IPA 音标块（/pɔɪnt/、/ˈpleɪnɪŋ/、/meɪn pɔɪnt/ 等）
    n_ipa = sum(1 for m in _IPA_BLOCK.finditer(out) if _IPA_CHAR.search(m.group(1)))
    out = _IPA_BLOCK.sub(_ipa_block_repl, out)
    if n_ipa:
        hits["IPA音标块删除"] = n_ipa
    # 1b) 删引号内【裸 IPA 串】（无 '/'，如 读作“pɔɪnt”、"rəʊd"）——E2E 实测补充
    n_bare = sum(1 for m in _BARE_IPA.finditer(out) if _IPA_CHAR.search(m.group(0)))
    out = _BARE_IPA.sub(_bare_ipa_repl, out)
    if n_bare:
        hits["裸IPA串删除"] = n_bare
        # 清掉删裸 IPA 后残留嘅空引号同「读作/发」等悬空提示尾
        out = re.sub(r"[“”‘’\"][ \t]*[“”‘’\"]", "", out)   # 空引号对
        # 「读作/念作」后嘅发音对象(裸 IPA)已删 -> 悬空提示一并清（只收最稳嘅句尾/标点前，
        # 宁可留低轻微冗余如「读作 两处」，都唔好误伤正常教学句「这个字读作平声」）。
        out = re.sub(r"(?:读作|念作|发音是|發音係)[ \t]*[：:]?[ \t]*(?=[，。；、\n]|$)", "", out)
    # 2) 公式/单位斜杠转中文读法（净低嘅非音标 '/'）
    n_form = len(_FORMULA_SLASH.findall(out))
    out = _FORMULA_SLASH.sub(_formula_slash_repl, out)
    if n_form:
        hits["公式斜杠转读法"] = n_form
    # 3) 兜底：任何残留 '/' 一律删（保证绝念唔出「斜杠」；覆盖孤立 / 同跨块残留）
    n_slash = out.count("/")
    if n_slash:
        out = out.replace("/", "")
        hits["残留斜杠删除"] = n_slash
    # 4) 清理删音标后残留嘅「音标：」「发音：」空标签同多余空格
    #    ⚠️ v1.29 血泪：千祈唔好删「中文<->英文」之间嘅单空格（point 点 / 同 word 唔同），
    #       嗰啲系合法停顿，删咗会令 TTS 粘读（同 v1.27 英文粘词同源）。只收：
    #       ① 行首「· 音标：」「音标：」「发音：」空标签（成行无内容）；
    #       ② 删块后留低嘅【双空格】收敛成单空格；
    #       ③ 标点/行尾前嘅空格；④ 行首「· 」后若空则连「· 」一并去掉。
    before = out
    out = re.sub(r"(?m)^[ \t]*(?:[·•]\s*)?(?:音标|發音|发音|IPA|音標)\s*[：:][ \t]*$", "", out)
    out = re.sub(r"[\t ]{2,}", " ", out)
    out = re.sub(r"[ \t]+(?=[，。！？、；：）\n]|$)", "", out)
    out = re.sub(r"(?m)^[ \t]*[·•][ \t]*$", "", out)   # 净低嘅空列表点
    if out != before:
        hits["音标残留清理"] = 1
    # 5) 还原 URL / 日期占位
    for i, raw in enumerate(prot):
        out = out.replace(_SENTINEL + str(i) + _SENTINEL, raw)
    return (out, hits) if report else out


def clean_tts_symbols_body(body, stream=False):
    """对网关 response body 做 TTS 符号清理（播报稿）。非流式改 message.content，
    流式走 v1.27 整段回填骨架（concat 恒等、帧数/结构/时序唔变，大脑端零感知）。
    任何解析失败原样透传，绝唔令对话挂掉。返回 (新body, hits)。"""
    try:
        if not stream:
            d = json.loads(body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body)
            hits = {}
            for ch in d.get("choices", []):
                msg = ch.get("message") or {}
                c = msg.get("content")
                if isinstance(c, str) and c:
                    nc, h = clean_tts_symbols(c, report=True)
                    msg["content"] = nc
                    for k, v in h.items():
                        hits[k] = hits.get(k, 0) + v
            return json.dumps(d, ensure_ascii=False).encode("utf-8"), hits
        # 流式：整段清洗回填（复用 v1.27 骨架；斜杠/音标块可能跨 token，逐帧清洗会漏）
        return _sse_whole_clean(body, lambda t: clean_tts_symbols(t, report=True))
    except Exception:
        return body, {}


def _selftest():
    real_script = (
        "各位街坊，阿晴同你讲下今日嘅新闻。首先，系关于第九届进博会嘅。呢次进博会好多人关注，"
        "唔单止国内企业参与，连外企都好热闹。不过有份报章话，有啲外企好似开始“用脚投票”咁，"
        "可能系因为佢哋觉得合作环境唔再似以前咁好，呢个系要大家留意嘅。另外，进博会仲搞咗一个活动，"
        "系让海外华文媒体去上海，目的系想他们多点了解上海嘅侨史文脉，同时捕捉进博会有咩机遇。"
        "睇嚟，国家系好希望借助进博会，加强同海外华人嘅联系。仲有，沪港之间都借进博会搞咗一个新行动，"
        "叫做“家乡好物·供港出海”，意思系鼓励上海嘅产品，特别是啲家乡好味，可以经香港去到海外市场。"
        "呢个系善用香港优势嘅好例子。讲返天气方面，中国天气网出咗一张干燥指数地图，"
        "话现在全国好多个省份，例如内蒙古、山西、京津冀等等，都好干燥。北方系晴朗升温，"
        "但系要小心皮肤干燥，饮多水。唔好唔注意，干燥咗会唔舒服。呢啲资讯系阿晴从网度抓到嘅，"
        "希望对大家有帮到。大家记得保持水分，天气干燥要小心。今日就讲咁多，阿晴先去休息啦，拜拜。"
    )
    samples = {
        "真实播报稿": real_script,
        "答疑漏网": "因为空气托不起飞机，他们需要给这儿做个实验，你现在看，这种事情是很危险的。",
        "讲古漏网": "他们那时候还很开心，后来下起雨来的时候，大家都没带伞，只好在那儿等着。",
        "代词与没有(防误伤)": "他没有来，其他人都到了，利他主义冇意思，It 是它的，她和她都好。",
        "误伤防护": "目的地的的士费给了酒吧老板，让步之后他给予补给，潜艇沉没了，是非自有公论，那时候他在场。",
        "专名保护": "中国天气网发布干燥指数地图，第九届进博会在上海举行，涉及内蒙古、山西同京津冀。",
        "粤语原文(不该改)": "我系阿晴，喺西关长大，呢啲街坊嘅嘢我好熟，唔单止识讲，仲识听㗎。",
        "歧义词(应保留)": "你还是去啦，我以前喺呢度住，佢正在睇书，大约三点到。",
        "方位被动正则": "佢现在在这里，我记得被人家闹过，被告唔关佢事，被动句式唔好咁用。",
        "繁体混杂(9B偶发)": "第九屆進博會喺上海舉行，華人社群嘅歷史文脈，係文化交流好機會；"
                        "讓佢哋現在就去，他們知道之後會很高興。",
        "英文乱码(实测超长回答)": "世界識Federal朋友嚟giao流，市场.entrySet，涉及到ymmetric唔少國家，"
                          "可以kéo起嚟，specifically投入改造，有啲archeology爭相言談文化spread，"
                          "Foreign同本國人一齊out talk，唔知點樣involve嗰。",
        "合法英文(不该删)": "佢系UFC个总栽，用AI分析数据，睇NBA直播。",
        "西里尔混排(实测)": "成日быδοґject大似话，讲唔清就唔好再讲多啦。",
        "Markdown+英文短语(实测)": "**新闻方面：** 呢个就好重要嘅，好点子喺呢度 cropped up（出现）㗎。"
                            "French women 都噉讲，bok opinion you ask 真系乱晒龙。",
        "数字缩写(不该删)": "气温32度，用5G网络，PM2.5超标，睇NBA，UFC比赛，用AI分析。",
    }
    all_ok = True
    for name, s in samples.items():
        out, hits = polish(s, report=True)
        idem = polish(out) == out
        if not idem:
            all_ok = False
        print("\n===== %s =====" % name)
        print("IN :", s)
        print("OUT:", out)
        print("HITS:", hits if hits else "（无改动）")
        print("幂等:", "OK" if idem else "!! FAIL !!")

    # 关键正确性断言
    assert "没有" not in polish("没有"), "没有 应转 冇"
    assert "冇有" not in polish("没有"), "不可出现 冇有"
    assert "其佢" not in polish("其他"), "其他 不可被误伤"
    assert "利佢" not in polish("利他主义"), "利他 不可被误伤"
    assert "酒啦" not in polish("酒吧"), "酒吧 不可被误伤"
    assert "不系" not in polish("不是"), "不是 应转 唔系"
    keep = polish("你还是去啦，我以前喺呢度住，佢正在睇书，大约三点到。")
    for w in ("还是", "以前", "正在", "大约"):
        assert w in keep, "歧义/中性词应保留: " + w
    rg = polish("佢现在在这里，我记得被人家闹过，被告唔关佢事，被动句式唔好咁用。")
    assert "被告" in rg and "被动" in rg, "被告/被动 不可被误伤"
    assert "喺呢度" in rg, "在+指代 应转 喺"
    assert "畀人" in rg, "被+人称 应转 畀"
    tw = polish("第九屆進博會喺上海舉行，係文化交流；讓佢哋現在就去，他們知道後會很高興。")
    assert "进博会" in tw and "系文化" in tw, "繁体应先转简: " + tw
    assert "讓" not in tw and "現在" not in tw and "他們" not in tw, "繁体转简后应被粤语规则命中: " + tw
    assert "而家" in tw and "佢哋" in tw, "繁体让/现在/他们 应转 畀/而家/佢哋: " + tw
    assert "喺" in tw, "粤语本字喺不该被繁简转换破坏: " + tw
    en = polish("世界識Federal朋友嚟giao流，市场.entrySet，涉及到ymmetric唔少國家，"
                "可以kéo起嚟，specifically投入，有啲archeology爭相言談文化spread，"
                "Foreign同本國人一齊out talk，唔知點樣involve嗰。")
    for g in ("giao", "entrySet", "ymmetric", "kéo", "specifically", "archeology", "spread", "Foreign", "involve"):
        assert g not in en, "英文乱码应被清理: " + g + " -> " + en
    legit = polish("佢系UFC个总栽，用AI分析数据，睇NBA直播。")
    for w in ("UFC", "AI", "NBA"):
        assert w in legit, "合法专名不该被删: " + w + " -> " + legit
    cyr = polish("成日быδοґject大似话，讲唔清就唔好再讲多啦。")
    assert "бы" not in cyr and "ject" not in cyr, "西里尔混排乱码应被清理: " + cyr
    md = polish("**新闻方面：** 好点子喺呢度 cropped up（出现）㗎。French women 都噉讲，bok opinion you ask 乱晒龙。")
    for g in ("**", "cropped", "French", "women", "bok", "opinion"):
        assert g not in md, "Markdown/英文短语应被清理: " + g + " -> " + md
    assert "新闻方面" in md and "出现" in md, "括号里的中文注释应保留: " + md
    assert "呢度（出现）" in md, "删英文后中文间空格应收敛: " + md
    dot = polish("市场.entrySet，涉及到ymmetric唔少。")
    assert "市场，" in dot and "." not in dot, "孤立英文句点/残留应清掉: " + dot
    ar = polish("先可以 ً، 冇得闷熟，个家櫃啲嘢。")
    assert "ً" not in ar and "،" not in ar, "阿拉伯变音符号乱码应清掉: " + ar
    assert "家柜" in ar, "繁体櫃应转柜: " + ar
    punct = polish("纸张、电子 , . 产品、仪器呀，各式各样。")
    assert "电子产品" in punct, "中文间孤立半角标点应清掉: " + punct
    dec = polish("PM2.5超标，气温32.5度，睇NBA。")
    for w in ("PM2.5", "32.5", "NBA"):
        assert w in dec, "数字小数点/缩写不该被误删: " + w + " -> " + dec
    garb = polish("我话下啲饮食㗍囍啦，嘅㗎㖞㷫㞗都系合法粤字，咪好()饮啦，想知边间（地区）睇下。")
    for g in ("㗍", "囍", "()"):
        assert g not in garb, "伪助词/空括号应清掉: " + g + " -> " + garb
    for w in ("嘅", "㗎", "㖞", "㷫", "㞗", "（地区）"):
        assert w in garb, "合法粤字/非空括号不该被删: " + w + " -> " + garb
    num = polish("气温32度，用5G网络，PM2.5超标，睇NBA，UFC比赛，用AI分析。")
    for w in ("32度", "5G", "PM2.5", "NBA", "UFC", "AI"):
        assert w in num, "数字/缩写不该被误伤: " + w + " -> " + num

    comb = polish(real_script + samples["专名保护"])
    for n in ("进博会", "中国天气网", "干燥指数", "内蒙古", "京津冀", "第九届", "家乡好物", "供港出海"):
        if n not in comb:
            print("\n!! 专名被误伤:", n)
            all_ok = False
    print("\n===== 总结: %s =====" % ("全部通过 ✔" if all_ok else "存在问题 ✘"))


if __name__ == "__main__":
    print("YUE_POLISH enabled =", ENABLED)
    _selftest()
