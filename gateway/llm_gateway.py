#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿晴 · 联网增强 LLM 网关（OpenAI 兼容 /v1/chat/completions）

夹在 FoloToy 服务端(STT) 与 硅基流动 GLM-4-9B 之间，服务端零改动：
  .env 的 LLM_API_BASE 从 https://api.siliconflow.cn/v1 改指本网关 http://llm-gateway:8000/v1

职责：
  1) 【天气】问天气/气温/几度/落雨/台风 -> Open-Meteo 实时数值 API（真实气温/体感/湿度/风/降雨概率/未来3天）
     -> 转中文口语数值 -> 带硬指令注入，让模型照抄真实数值，唔好凭记忆乱作。
  2) 【新闻】问新闻/头条/热搜/时事 -> 抓活嘅 RSS（中新网滚动）+ Bing 网页搜索 RSS -> 注入真实标题。
  3) 【知识/事实】(2026-11-11 新增) 问介绍/定义/边度/几时/历史/人物/数据/点解 ->
     Bing 网页 RSS 抓真实摘要 -> 清洗(去英文/URL/广告) -> 带「照资料答、唔够坦白唔知、
     唔准凭记忆乱作」硬指令注入。寒暄/情绪/讲笑/自我认知/算术一律唔搜，秒回。
  4) 联网意图精准分流：天气走数值 API、新闻走 RSS、知识走 Bing 抓事实，交叉意图先到先得；其余透传。
  5) 长文意图（含「介绍 X」自动）-> 覆盖 max_tokens ~1600、放宽到 800~1000 字 + 讲解员身份锚定。
  6) 【换模型】MODEL_OVERRIDE 环境变量喺网关层覆盖 payload.model，大脑容器零改动、token 保住。
  7) 话题锚定：介绍非本地对象且历史讲过本地景点 -> 物理隔离旧轮次，防「问庐山讲成广州」。
  8) 返回文本做粤语化后处理 + 多音字 TTS 正音（请求侧人设/资料一概不碰）。
  9) OpenAI 兼容：支持 stream 与非 stream（真人玩具走 stream=True，E2E 探针用非 stream）。
 10) 【学科老师·2026-11-11 v1.22】7 角色=1闲聊+6学科老师(语文/数学/英语/物理/化学/历史)。
     - 靠 system prompt 里【角色:xxx】标记认身份；学科题先联网抓真实资料再答(照资料、唔乱编)。
     - 英语老师(english_teacher)：中英双语讲解，【整条豁免】粤语后处理+清英文+正音，用普通话讲解。
     - 全部角色回答硬上限 1000 字：覆盖 max_tokens 封顶 + system 尾钉字数铁律。
 11) 【对话记录·2026-11-11 v1.23】每轮问答(时间/角色/问题/回复全文/是否联网)落盘到持久化卷
     /data/conversations/YYYY-MM-DD.jsonl，按天分文件；网关同时提供 /chat 实时查看页 + /logs JSON API。
     - 落盘喺写响应之后、包 try/except；回复全文由处理后嘅 body 提取(stream 拼 delta.content)，
       写文件失败净系 log、绝不影响对话。Docker 日志有 20m×3 轮转，呢份卷先至持久。
     - VIEW_TOKEN 可选：设咗就要 /chat?t=xxx 或 X-View-Token 先至睇到(默认空=本机随便睇)。

实测依据（2026-11-11）：
  - Bing 新闻 RSS / 百度新闻 / Google News 容器内全部失效（返回 HTML 或超时）。
  - 可用源：中新网滚动 RSS（30 条）、Bing 网页搜索 RSS（format=rss，10 条）。
  - Open-Meteo forecast + geocoding 免 key 直连可用，带 realtime + 未来 3 日。

环境变量：
  UPSTREAM_BASE  默认 https://api.siliconflow.cn/v1
  UPSTREAM_KEY   硅基流动 key（从 .env 注入，不落盘）
  UPSTREAM_MODEL 默认 THUDM/GLM-4-9B-0414
  PORT           默认 8000
  FETCH_TIMEOUT  抓取超时 默认 6s
  CACHE_TTL      RSS/天气缓存秒数 默认 300
  LONG_MAX_TOKENS 长文 max_tokens 默认 1100
  CONVERSATIONS_DIR 对话记录落盘目录 默认 /data/conversations（compose 挂持久化卷）
  CONV_LOG   设 0 关闭对话落盘 默认开
  VIEW_TOKEN 查看页/API 访问口令 默认空(本机随便睇)
  CONV_KEEP_DAYS  对话至少保留几多日在线可查 默认 30（v1.31）；超期主文件移到 archive/ 仍可查、唔删
  CONV_PURGE_DAYS 真正删除归档嘅日数 默认 0=永不永久删除（要清理先显式开）
  X-No-Record:1（请求头）E2E/自检跳过落盘，避免测试稿污染真实记录（v1.31）

对话记录读取（v1.31）：聚合【当日主文件 + 所有同日 .bak-* 快照 + archive/ 归档】按 epoch 去重，
故旧版「清落盘」备份落嘅记录唔会再隐形；/logs 上限提到 5000，查看页显示保留天数。
"""
import os, re, json, time, html, asyncio, threading, shutil
import urllib.request, urllib.parse, ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import xml.etree.ElementTree as ET
import yue_polish  # 阿晴粤语化后处理（只作用于返回文本，不动请求/prompt）
import tts_pron    # 粤语多音字 TTS 正音（「区」-> 「區」读 keoi1，防念成「欧」）

UPSTREAM_BASE = os.getenv("UPSTREAM_BASE", "https://api.siliconflow.cn/v1").rstrip("/")
UPSTREAM_KEY = os.getenv("UPSTREAM_KEY", "")
UPSTREAM_MODEL = os.getenv("UPSTREAM_MODEL", "THUDM/GLM-4-9B-0414")
PORT = int(os.getenv("PORT", "8000"))
FETCH_TIMEOUT = float(os.getenv("FETCH_TIMEOUT", "6"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))
LONG_MAX_TOKENS = int(os.getenv("LONG_MAX_TOKENS", "1600"))
# 模型覆盖（2026-11-11）：网关层直接改 payload.model，大脑容器_zero改动、token 不动。
# 设成 Qwen/Qwen3-30B-A3B-Instruct-2507 即换大模型；留空=透传大脑原本 model（可回滚）。
MODEL_OVERRIDE = os.getenv("MODEL_OVERRIDE", "").strip()
# 对话记录（v1.23）：落持久化卷，按天 JSONL；Docker json-file 日志有 20m×3 轮转，会冲走旧记录。
CONVERSATIONS_DIR = os.getenv("CONVERSATIONS_DIR", "/data/conversations")
CONV_LOG_ENABLED = os.getenv("CONV_LOG", "1") != "0"
VIEW_TOKEN = os.getenv("VIEW_TOKEN", "").strip()
# v1.31 对话记录保留：至少保留 CONV_KEEP_DAYS 天（默认 30）在线可查；
# 超过保留期嘅【活跃主文件】会喺落盘时移到 archive/ 子目录（仍喺持久卷、仍可经 /logs?day= 查询），
# 默认【永不永久删除】——主人要求「全部记录至少保留 30 天」，归档只系移出活跃目录、数据不丢。
# 如要真正清理，显式设 CONV_PURGE_DAYS>0 才会删除超过 N 天嘅归档（默认 0=关）。
CONV_KEEP_DAYS = max(1, int(os.getenv("CONV_KEEP_DAYS", "30")))
CONV_PURGE_DAYS = max(0, int(os.getenv("CONV_PURGE_DAYS", "0")))
CONV_ARCHIVE_SUBDIR = "archive"

# ---- v1.47：1 号键 = 播电台/换台；对话键 = 开始/暂停（2026-11-15）------
# v1.46 实测问题：真机按 1 号键有时唔带【角色:aqing_chat】标记（日志显示
# 「普通阿晴」），而且停机时按 1 号键只会换台、唔会开播，主人报「没反应」。
# v1.47 改为**唔靠角色标记**：只要句入面有「电台」相关词一律开播；
# 1 号键停机时按一下就开播，播住先换台。
# 网关与 nginx 共享 /audio 卷；命令/状态文件 Windows 侧经 UNC 可读写。
# 回滚：容器环境变量 RADIO_BTN=0（两个键恢复原状），或还原
#       llm_gateway.py.bak-pre-1.47 重建 1.46 镜像。
RADIO_BTN_ENABLED  = os.getenv("RADIO_BTN", "1") != "0"
RADIO_TALK_ENABLED = os.getenv("RADIO_TALK_KEY", "1") != "0"
RADIO_CMD_PATH   = "/audio/radio_cmd.json"
RADIO_STATE_PATH = "/audio/radio_state.json"

# 换台顺序（Windows 侧循环只按 id 录源，唔需要第二份表）
RADIO_STATION_LIST = [
    ("rthk1",     "香港電台第一台"),
    ("rthk2",     "香港電台第二台"),
    ("rthk5",     "香港電台第五台"),
    ("rthkpth",   "香港普通話台"),
    ("bbcws",     "BBC 世界台"),
    ("classicfm", "古典音樂台"),
    ("npr",       "NPR 新聞台"),
    ("cnn",       "CNN 新聞台"),
]
RADIO_STATION_IDS   = [s for s, _ in RADIO_STATION_LIST]
RADIO_STATION_NAMES = dict(RADIO_STATION_LIST)


def radio_read_state():
    try:
        with open(RADIO_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def radio_write_cmd(payload):
    """写一条带 seq 嘅命令；桥接按 seq 幂等执行，绝唔重复。"""
    seq = int(time.time() * 1000)
    payload.update({"seq": seq, "ts": time.time()})
    tmp = RADIO_CMD_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, RADIO_CMD_PATH)
    return seq


def radio_write_state(running, station):
    """乐观更新状态（实际值由 Windows 侧 radio_cmd_bridge.py 执行后写回）。"""
    tmp = RADIO_STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"running": bool(running), "station": station,
                   "ts": time.time()}, f, ensure_ascii=False)
    os.replace(tmp, RADIO_STATE_PATH)


def radio_next_station():
    """1 号键：换下一个台。只改台号，唔停播、唔改 running。"""
    st = radio_read_state()
    cur = str(st.get("station") or "rthk1")
    running = bool(st.get("running"))
    try:
        idx = RADIO_STATION_IDS.index(cur)
    except ValueError:
        idx = -1
    nxt = RADIO_STATION_IDS[(idx + 1) % len(RADIO_STATION_IDS)]
    # want 带住当前 running：万一旧版桥接见到新 seq，最多重复开播，绝唔会误停
    seq = radio_write_cmd({"action": "set_station", "station": nxt,
                           "want": running})
    radio_write_state(running, nxt)
    log("RADIO_KEY1 next=%s running=%s seq=%s" % (nxt, running, seq))
    return nxt


def radio_play_toggle(q):
    """对话键：讲一句就喺开始/暂停之间切换；讲到明确词就按词执行。"""
    st = radio_read_state()
    running = bool(st.get("running"))
    station = str(st.get("station") or "rthk1")
    text = (q or "").strip()
    stop_words = ("暫停", "暂停", "停低", "停一停", "唔好播", "唔播", "停止",
                  "停播", "收聲", "收声", "靜音", "静音", "唔好聽", "关掉", "關掉")
    play_words = ("開始", "开始", "繼續", "继续", "播放", "播返", "開播",
                  "开播", "聽電台", "听电台", "開電台", "开电台")
    if any(w in text for w in stop_words):
        want = False
    elif any(w in text for w in play_words):
        want = True
    else:
        want = not running
    seq = radio_write_cmd({"action": "toggle", "want": want})
    radio_write_state(want, station)
    log("RADIO_TALK want=%s running(was)=%s q=%r seq=%s" %
        (want, running, text[:24], seq))
    return want


# ---- v1.47 关键词表 -------------------------------------------------------
# 停机时按 1 号键、或者讲「播电台」，都要即刻开播；唔好再靠角色标记碰运气。
RADIO_FORCE_PLAY_WORDS = (
    "電台", "电台", "播電台", "播电台", "聽電台", "听电台", "開電台", "开电台",
    "要聽", "要听", "播返", "繼續播", "继续播", "開播", "开播",
    "開始播", "开始播", "播放", "開始", "开始", "繼續", "继续",
)
RADIO_FORCE_STOP_WORDS = (
    "暫停", "暂停", "停低", "停一停", "停咗", "停了", "唔好播", "唔播", "停止",
    "停播", "收聲", "收声", "靜音", "静音", "唔好聽", "唔好听", "关掉", "關掉",
    "唔要電台", "唔要电台", "唔聽電台", "唔听电台", "電台停", "电台停", "關閉", "关闭",
)
RADIO_CHANGE_WORDS = ("換台", "换台", "轉台", "转台", "下一個台", "下一个台",
                      "切台", "轉去", "转去")
# 播报稿 / 早晚报 daemon 的文本特征：呢类内部请求绝对唔可以当按键拦截。
# 2026-11-15 18:00 早报就系被 v1.46 拦成「電台暫停咗」，稿只得 5 个字。
RADIO_SCRIPT_WORDS = ("新聞", "新闻", "天氣", "天气", "播報", "播报", "播報稿",
                      "播报稿", "講成", "讲成", "大約", "大约", "八百字", "百字",
                      "詳細啲講", "详细啲讲", "稿")


def radio_action(q, is_key1):
    """v1.47 统一决定按键动作，返回 (kind, reply)。

    优先级：停 > 开播（含「电台」泛词 / 1 号键停机）> 换台 / toggle。
    任何键讲「播电台」都强制开播，唔会喺播紧时被 toggle 切成暂停。
    """
    st = radio_read_state()
    running = bool(st.get("running"))
    station = str(st.get("station") or "rthk1")
    text = (q or "").strip()

    if any(w in text for w in RADIO_FORCE_STOP_WORDS):
        radio_write_cmd({"action": "toggle", "want": False})
        radio_write_state(False, station)
        log("RADIO_KEY stop q=%r running(was)=%s" % (text[:24], running))
        return "stop", "電台暫停咗"

    force_play = any(w in text for w in RADIO_FORCE_PLAY_WORDS)
    if force_play or (is_key1 and not running):
        radio_write_cmd({"action": "toggle", "want": True})
        radio_write_state(True, station)
        log("RADIO_KEY play q=%r running(was)=%s key1=%s force=%s" %
            (text[:24], running, is_key1, force_play))
        return "play", "電台開始播喇"

    # 1 号键播住先换台；讲明「换台」亦都一样
    if is_key1 or any(w in text for w in RADIO_CHANGE_WORDS):
        nxt = radio_next_station()
        return "station", "轉咗%s" % RADIO_STATION_NAMES.get(nxt, nxt)

    want = not running
    radio_write_cmd({"action": "toggle", "want": want})
    radio_write_state(want, station)
    log("RADIO_TALK want=%s running(was)=%s q=%r" % (want, running, text[:24]))
    return ("play" if want else "stop"), ("電台開始播喇" if want else "電台暫停咗")


def radio_reply(h, text, stream):
    """直接回一句短确认，兼容 stream / 非 stream，唔经上游、唔落对话记录。"""
    now = int(time.time())
    if stream:
        frames = [
            ("data: " + json.dumps({
                "id": "radio-btn", "object": "chat.completion.chunk",
                "created": now, "model": "radio-btn",
                "choices": [{"index": 0,
                             "delta": {"role": "assistant", "content": text},
                             "finish_reason": None}]},
                ensure_ascii=False) + "\n\n").encode("utf-8"),
            ("data: " + json.dumps({
                "id": "radio-btn", "object": "chat.completion.chunk",
                "created": now, "model": "radio-btn",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                ensure_ascii=False) + "\n\n").encode("utf-8"),
            b"data: [DONE]\n\n",
        ]
        h.send_response(200)
        h.send_header("Content-Type", "text/event-stream; charset=utf-8")
        h.send_header("Cache-Control", "no-cache")
        h.send_header("Transfer-Encoding", "chunked")
        h.end_headers()
        try:
            for fr in frames:
                h.wfile.write(("%X\r\n" % len(fr)).encode() + fr + b"\r\n")
            h.wfile.write(b"0\r\n\r\n")
            h.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
    else:
        h._json(200, {
            "id": "radio-btn", "object": "chat.completion", "created": now,
            "model": "radio-btn",
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })
    log("RADIO_BTN reply=%r stream=%s" % (text, stream))
_CONV_RETENTION_TS = 0.0       # 上次归档检查时间戳（节流，避免每条对话都 scan）
_CONV_RETENTION_INTERVAL = 3600  # 每小时最多做一次归档扫描
# 角色 key -> (按钮号, 中文名)：落盘同查看页用，令记录易读
ROLE_META = {
    "aqing_chat": ("1", "阿晴·闲聊"),
    "chinese_teacher": ("2", "语文老师"),
    "math_teacher": ("3", "数学老师"),
    "english_teacher": ("4", "英语老师"),
    "physics_teacher": ("5", "物理老师"),
    "chemistry_teacher": ("6", "化学老师"),
    "history_teacher": ("7", "历史老师"),
    "": ("1", "普通阿晴"),   # detect_role 认唔到标记时（旧缓存/闲聊），当闲聊记
}
CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ---------------- 学科老师 / 字数上限（2026-11-11 v1.22）----------------
# 全部角色回答的硬字数上限（中文字数）。prompt 已钉「唔好超过1000字」，
# 呢度再用 max_tokens 封顶 + system 尾注双保险，防 30B 长文收唔住。
HARD_MAX_CHARS = int(os.getenv("HARD_MAX_CHARS", "1000"))
# 1000 中文字 ≈ 1500~1800 token；封顶比 roles.json 的 max_tokens 更严时用呢个压住。
HARD_MAX_TOKENS = int(os.getenv("HARD_MAX_TOKENS", "1800"))
# 角色标记：FoloToy 把 roles.json 对应 prompt 放喺 system content，靠呢个认身份。
ROLE_MARKERS = {
    "aqing_chat": "【角色:aqing_chat】",
    "chinese_teacher": "【角色:chinese_teacher】",
    "math_teacher": "【角色:math_teacher】",
    "english_teacher": "【角色:english_teacher】",
    "physics_teacher": "【角色:physics_teacher】",
    "chemistry_teacher": "【角色:chemistry_teacher】",
    "history_teacher": "【角色:history_teacher】",
}
TEACHER_MARKERS = tuple(m for k, m in ROLE_MARKERS.items() if k.endswith("_teacher"))
# ---- v1.24 英语老师 system prompt 覆盖 ----
# 大脑容器缓存住旧粤语版 4 号 prompt（改文件要重启大脑才生效，重启会丢 token）。
# 网关改为：检测到 english_teacher 时，直接把 system content 整体换成下面份【纯普通话】
# prompt，实现「不重启大脑、不动 token」即时生效。优先读挂载卷 /config/roles.json 的 4 号
# （同 build_roles_aqing.py 生成，单一真相源）；读唔到就用内置兜底，保证永不开天窗。
# 优先读镜像内 /app/roles.json（构建时 COPY，单一真相源）；读唔到用内置兜底。
# 如要唔重建镜像热改，可挂载并设 ENGLISH_SYS_FILE=/config/roles.json 覆盖。
ENGLISH_SYS_FILE = os.getenv("ENGLISH_SYS_FILE", "/app/roles.json")
ENGLISH_SYSTEM_FALLBACK = (
    "【角色:english_teacher】\n"
    "You are a patient and professional middle-school English teacher. "
    "你是一位有耐心、专业的初中英语老师。\n"
    "【语言·最高铁律】你是在【用标准普通话上英语课】——想象你正站在北京的教室里，"
    "对着初中生讲课，字正腔圆、用词规范，跟中央电视台新闻播音员的普通话一样标准。"
    "你写下的每一句中文讲解、举例、过渡、追问，都是规范的普通话书面语，"
    "不掺任何方言口语。这一条贯穿全程，覆盖你回答的每一个字。\n"
    "【对话方式】学生用中文或英文提问你都接得住。讲解要明白透彻、循序渐进，"
    "让初中生一听就懂。\n"
    "【中英双语·解释清楚】解释文法、词义、句式、答题思路时【用普通话讲清楚】；"
    "但【关键字词、英文例句、完整英文句子、音标、发音要点一定要保留英文原文】，"
    "并且紧跟准确的中文翻译。格式示例：\n"
    "  · 单词：apple /ˈæpl/ 苹果\n"
    "  · 例句：She is reading a book.（她正在读一本书。）—— 用普通话讲清 present continuous 用法\n"
    "  · 对比：affect（动词，影响）vs effect（名词，效果）\n"
    "也就是说：中文负责解释清楚，英文负责给出原汁原味的词句，两者搭配；"
    "不要只讲中文不给英文，也不要只堆英文不解释。\n"
    "【先核实·铁律】学生问到任何字词释义、文法规则、出处、文化知识、例句，"
    "你【必须先看用户消息里有没有「联网查到的真实资料」】——有就照资料讲、"
    "不要凭记忆改释义和拼写；资料没覆盖就坦白说「这个词我暂时找不到确切资料」，不要编造。"
    "回答时直接讲知识本身，【不要说「根据资料」「资料显示」「资料确认」「据查到」这类元话语】，"
    "就当是你本来就懂，自然地讲。\n"
    "【语气】温柔、鼓励、有耐心，答完可以轻轻追问一句学生听懂没有；短句、清楚、不啰嗦。\n"
    "【字数铁律】无论问什么，回答【绝对不要超过 1000 字】；够清楚就收，不要重复啰嗦。\n"
    "【格式】不要用 emoji、不要用特殊符号（如勾号、箭头、手势），"
    "不要用复杂 Markdown（简单换行和「·」项目符号可以）、不要用表格；不要用夸张语气。"
)


def _load_english_system():
    """启动时读 roles.json 的 4 号纯普通话 prompt；失败用内置兜底。返回 (prompt, 来源)。"""
    try:
        with open(ENGLISH_SYS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        p = (d.get("4") or {}).get("prompt", "")
        # 校验：必须系英语老师 + 含强正向普通话锚定，唔系就当读错、用兜底
        if "english_teacher" in p and "标准普通话" in p:
            return p, ENGLISH_SYS_FILE
        log("ENGLISH_SYS_FILE 4号 prompt 未含普通话锚定，用内置兜底")
    except Exception as e:
        log("ENGLISH_SYS_FILE 读取失败（%s），用内置兜底" % repr(e)[:60])
    return ENGLISH_SYSTEM_FALLBACK, "builtin-fallback"
# 学科专项联网关键词：命中就强制走知识核实（即使泛问「点解/为什么」都搜），
# 并针对性组查询词（数学/物理/化学公式类靠 cn.bing + 百科，历史靠词条+年份）。
SUBJECT_HINTS = {
    "chinese_teacher": ("字词", "成语", "典故", "多音字", "古诗", "唐诗", "文言文", "古文", "实词", "虚词",
                        "修辞", "病句", "作文", "阅读理解", "作者", "出处", "译文", "朗诵", "作者系边个",
                        "文学常识", "名句", "诗句", "词牌", "课文"),
    "math_teacher": ("方程", "函数", "几何", "证明", "面积", "体积", "周长", "角度", "三角形", "圆",
                     "概率", "统计", "平均数", "方差", "一次", "二次", "根", "解", "求导", "公式",
                     "计算", "点解", "为什么", "几多", "多少", "化简", "因式分解", "不等式", "坐标系"),
    "physics_teacher": ("力", "压强", "浮力", "功", "功率", "能量", "动能", "势能", "热", "温度", "比热",
                        "光", "反射", "折射", "透镜", "电", "电路", "电压", "电流", "电阻", "磁", "电磁",
                        "运动", "速度", "加速度", "惯性", "公式", "单位", "实验", "点解", "为什么"),
    "chemistry_teacher": ("元素", "原子", "分子", "离子", "化学式", "方程式", "配平", "化合价", "溶液",
                          "浓度", "酸", "碱", "盐", "金属", "氧化", "还原", "燃烧", "气体", "实验", "现象",
                          "沉淀", "催化剂", "质量守恒", "点解", "为什么", "点样"),
    "history_teacher": ("朝代", "年代", "公元前", "世纪", "皇帝", "历史事件", "战争", "条约", "革命",
                        "变法", "人物", "唐朝", "宋朝", "明朝", "清朝", "秦", "汉", "近代", "现代", "世界史",
                        "背景", "意义", "影响", "原因", "经过", "谁", "边个", "几时", "点解", "为什么"),
}

# ---------------- 联网意图 ----------------
SEARCH_HINTS = [
    "新闻", "新闻", "最新", "头条", "热搜", "热闻", "时事", "资讯",
    "天气", "气温", "落雨", "下雨", "台风", "预报",
    "股价", "股票", "汇率", "油价", "金价", "楼市", "房价",
    "比分", "赛果", "赛事", "世界杯", "亚冠", "中超", "英超", "NBA",
    "搜索", "搜下", "查下", "查一下", "帮我查", "上网", "联网", "睇下",
    "今日", "今天", "而家", "现在", "最近", "这几日", "呢排",
]
SEARCH_SOFT = ["咩", "乜", "?", "？", "有没有", "有冇", "点样", "怎样"]
NEGATE_HINTS = ["我今日", "我今天", "寻日", "昨天", "记唔记得", "还记得", "你叫", "你係边", "你是谁", "讲笑", "笑话"]

# 天气意图：含粤语/繁体/简体常见讲法。注意唔好放裸「热/冷/雨」免误伤「热情/热门」。
WEATHER_HINTS = [
    "天气", "天氣", "天气预报", "天氣預報", "气温", "氣溫", "温度", "溫度",
    "几度", "幾度", "幾多度", "几多度", "几冻", "幾凍", "几热", "幾熱",
    "好冻", "好凍", "好热", "好熱", "冻到", "凍到", "热到", "熱到", "凉咗", "涼咗",
    "落雨", "下雨", "会落雨", "會落雨", "有冇雨", "有没有雨", "雨势", "雨勢",
    "台风", "颱風", "打风", "打風", "风球", "風球", "热带气旋", "熱帶氣旋",
    "预报", "預報", "湿度", "濕度", "风力", "風力", "风向", "風向", "风速", "風速",
    "降温", "降溫", "升温", "升溫", "冷空气", "冷空氣", "寒潮", "霜", "冰雹",
    "雷暴", "打雷", "天晴", "晴天", "阴天", "陰天", "多云", "多雲", "有雾", "有霧",
    "紫外线", "紫外線", "空气质素", "空氣質素", "带伞", "帶傘", "加衫", "穿衣",
]
# 新闻意图：问「发生咩事/有咩新闻」等都要联网。
NEWS_HINTS = [
    "新闻", "新聞", "头条", "頭條", "热搜", "熱搜", "时事", "時事", "资讯", "資訊",
    "最新消息", "发生咩事", "發生咩事", "有咩新闻", "有咩新聞", "有乜新闻", "有乜新聞",
    "边度发生", "邊度發生", "最近发生", "最近發生", "今日要闻", "今日要聞",
    "新闻联播", "新聞聯播", "社会新闻", "社會新聞", "国际新闻", "國際新聞",
    "本地新闻", "本地新聞", "广州新闻", "廣州新聞", "财经新闻", "財經新聞",
]

LONG_HINTS = [
    "详细", "详尽", "具体", "完整", "全部", "长啲", "长一点", "长篇",
    "讲耐啲", "讲久啲", "讲多啲", "多讲", "展开", "深入", "详细啲",
    "慢慢讲", "由头讲", "一整", "整段", "列举", "列下", "逐条", "几点",
    "说长", "讲长", "篇幅", "作文", "写篇", "篇文章", "故事", "讲古",
]

# 知识/事实类意图（2026-11-11）：呢类问题 MUST 先联网抓真实资料再答，唔准凭模型记忆乱作。
# 覆盖：介绍/讲下某对象、定义、边度/几时、历史、人物、数据(几高/几多/海拔)、点解/点样、对比。
# 明确排除：寒暄/情绪/陪伴/讲笑/自我认知/承诺/算术——呢类搜咗都系垃圾，仲拖慢语音。
KNOWLEDGE_Q_WORDS = (
    "系咩", "係咩", "系乜", "係乜", "咩系", "乜系", "系什么", "是什么", "是什",
    "什么是", "什么叫", "咩叫", "咩嘢", "乜嘢", "点解", "點解", "点样", "點樣",
    "为什么", "為什麼", "为何", "為何", "几时", "幾時", "边度", "邊度", "边个", "邊個",
    "几高", "幾高", "几多", "幾多", "几长", "幾長", "几大", "幾大", "几远", "幾遠",
    "几深", "幾深", "几重", "幾重", "几耐", "幾耐", "海拔", "高度", "面积", "面積",
    "多高", "多大", "多长", "多深", "多少", "历史", "歷史", "由嚟", "由来", "由來",
    "来历", "來歷", "背景", "起源", "定义", "定義", "意思", "含义", "含義",
    "边个省", "邊個省", "边个国家", "属于", "屬於", "位于", "位於", "坐落",
    "朝代", "生卒", "代表作", "作者", "发明", "發明", "发现", "發現", "建立",
    "成分", "组成", "組成", "原理", "区别", "區別", "唔同", "唔一样", "唔一樣",
    "定系", "定係", "定系边个",  # 对比：「A定B」（唔收裸「定」，会误伤「定一定」）
    # 普通话问句（STT 常转简体普通话，要接住）
    "有哪些", "有哪几", "哪几个", "哪些", "有哪", "是什么", "什么是",
)
# 见过即搜嘅实词尾（名词性对象 + 呢类后缀，多数系问事实）
KNOWLEDGE_NOUN_TAIL = (
    "嘅历史", "嘅歷史", "嘅由来", "嘅由來", "嘅故事", "嘅背景", "嘅定义", "嘅定義",
    "嘅意思", "嘅面积", "嘅面積", "嘅海拔", "嘅作者", "嘅成分", "嘅原理",
    "嘅区别", "嘅區別", "有咩玩", "有乜玩", "有咩睇", "有乜睇", "有咩特色",
)
# 明确唔搜（呢类联网无意义，仲可能搜出垃圾带偏阿晴）
KNOWLEDGE_BLOCK = (
    "笑话", "笑話", "讲笑", "講笑", "古仔", "讲古", "講古", "故事", "讲个故事",
    "我唔开心", "我唔開心", "唔开心", "唔開心", "我好攰", "攰", "寂寞", "陪我", "倾下", "傾下",
    "你叫咩名", "你係边个", "你係邊個", "你系边个", "你是谁", "你几多岁", "你幾多歲", "你几岁", "你几岁",
    "讲声", "講聲", "讲句", "講句", "再讲多次", "咩意思呀你", "你识唔识", "你識唔識",
    "1+1", "1 1", "加下", "数数", "數數", "出题", "出題",
    "早抖", "早唞", "早晨", "夜啦", " goodbye", "再见", "再見",
)
# 问「承诺/意见/感受」而非事实 -> 唔搜
KNOWLEDGE_OPINION = (
    "你觉唔觉", "你覺得", "你觉得", "你中意", "你鍾意", "你wise", "你话呢", "你話呢",
    "畀个意见", "俾个意见", "点睇", "點睇", " shores", "我应唔应该", "我應唔應該",
)

# ---------------- v1.35 史实锚点：修「讲唐朝开国嘅故事」被「故事」一刀切 ----------------
# 血泪背景（2026-11-11 晚）：主人问「讲唐朝开拓嘅故事」，因「故事」写死喺 KNOWLEDGE_BLOCK
# -> is_knowledge_intent / is_fact_check_needed / is_subject_question 一律 return False
# -> net=False，再撞 LONG_HINTS「故事」拉到 1800 token 长文 -> 30B 凭记忆将《礼记·礼运》
#    「天下为公」张冠李戴塞畀李渊。对照组「…唐朝开国嘅历史」带「历史」就 net=True、史实正确。
# 定版策略：带【明确史实锚点】嘅讲述一律当史实题、强制联网，唔受「故事/讲古」BLOCK 影响；
#           纯「讲个童话/古仔/笑话」冇锚点，照旧秒回、唔乱搜。宁愿多搜，唔好凭记忆乱作（主人铁律）。
# 只收【双字以上、日常对话几乎唔会误伤】嘅专名；裸单字朝代（唐/明/清/汉）会撞「明天/清明/汉化」，唔收。
HISTORY_ANCHORS = (
    # 朝代 / 时期
    "唐朝", "宋朝", "明朝", "清朝", "秦朝", "汉朝", "元朝", "隋朝", "晋朝", "周朝", "商朝", "夏朝",
    "北宋", "南宋", "西汉", "东汉", "东晋", "西晋", "三国", "南北朝", "五代十国", "春秋战国",
    "春秋时期", "战国时期", "唐代", "宋代", "明代", "清代", "秦代", "汉代", "武周",
    # 帝王 / 历史人物（含诸子，防思想归属张冠李戴）
    "李渊", "李世民", "唐高祖", "唐太宗", "武则天", "唐玄宗", "唐高宗", "秦始皇", "汉武帝",
    "刘邦", "项羽", "曹操", "刘备", "诸葛亮", "孙权", "司马懿", "隋文帝", "隋炀帝", "朱元璋",
    "明太祖", "明成祖", "朱棣", "成吉思汗", "忽必烈", "康熙", "乾隆", "雍正", "孙中山",
    "孔子", "孟子", "老子", "庄子", "荀子", "韩非子", "墨子", "司马迁", "班固", "屈原",
    "李白", "杜甫", "白居易", "苏轼", "曹雪芹", "岳飞", "文天祥", "霍去病", "卫青",
    # 历史事件 / 制度 / 工程
    "安史之乱", "贞观之治", "开元盛世", "康乾盛世", "辛亥革命", "鸦片战争", "甲午战争",
    "商鞅变法", "王安石变法", "洋务运动", "戊戌变法", "郑和下西洋", "丝绸之路", "赤壁之战",
    "官渡之战", "淝水之战", "长平之战", "陈桥兵变", "玄武门之变", "靖康之变", "崖山海战",
    "科举制度", "三省六部", "郡县制", "分封制", "禅让制", "均田制", "租庸调制", "大运河",
    # 史书 / 思想 / 名句归属（呢类最易被 30B 安错朝代）
    "天下为公", "大同思想", "礼记", "禮記", "论语", "論語", "道德经", "道德經",
    "史记", "史記", "资治通鉴", "資治通鑑", "诗经", "詩經", "尚书", "尚書",
    "儒家", "道家", "法家", "墨家", "兵家",
)
# 「讲 <专名> 嘅故事/历史/生平/事迹」受控泛化：覆盖表外人物（讲霍去病嘅故事），
# 但明确虚构（童话/寓言/神话/鬼故事/编/虚构）同第一人称（我/你/佢）一律唔当史实。
_STORY_FICTION = ("童话", "童話", "寓言", "神话", "神話", "科幻", "鬼故事", "讲笑", "講笑",
                  "笑话", "笑話", "编故事", "編故事", "虚构", "虛構", "杜撰", "幻想")
_STORY_PRONOUN = ("我嘅故事", "我的故事", "你嘅故事", "你的故事", "佢嘅故事", "大家嘅故事", "自己嘅故事")
_HISTORY_STORY_RE = re.compile(
    r"(?:讲|講|介绍|介紹|话我知|話我知|同我讲|同我講)\s*[\u4e00-\u9fff]{2,6}?"
    r"(?:嘅|的)?(?:故事|歷史|历史|生平|事跡|事迹|傳記|传记)")


def is_history_fact(q):
    """v1.35：呢条系咪【真实历史/人物/出处题】（要联网核实）？
    命中条件（二选一）：①含明确史实锚点（朝代/帝王/事件/史书/思想归属）；
    ②「讲<专名>嘅故事/生平」句式且唔系明确虚构、唔系第一人称。
    一旦命中 -> 无视「故事/讲古」KNOWLEDGE_BLOCK，强制走联网核查。
    纯「讲个童话故事」「讲个笑话」冇锚点 -> False，照旧秒回，唔拖慢、唔带偏。"""
    if not isinstance(q, str) or not q.strip():
        return False
    # 明确虚构 / 第一人称优先排除（「讲个李白嘅童话」「讲我嘅故事」唔当史实，唔好误搜）
    if any(f in q for f in _STORY_FICTION) or any(p in q for p in _STORY_PRONOUN):
        return False
    if any(a in q for a in HISTORY_ANCHORS):
        return True
    return bool(_HISTORY_STORY_RE.search(q))


def _history_search_subject(q):
    """攞最长匹配嘅史实锚点做搜索主词条（「讲唐朝开拓嘅故事」->「唐朝」），
    畀快懂百科/Bing 用干净专名查，唔带「讲/嘅故事」口语壳。冇锚点返 ''。"""
    hits = [a for a in HISTORY_ANCHORS if a in (q or "")]
    return max(hits, key=len) if hits else ""


# 诗词/古文朗读意图：识别到之后全程【口语化后处理豁免】，诗句逐字照原文读。
# 根因：粤语「是」书面/文言朗读读 si6，口语「係/系」读 hai6，是两套系统；
#       yue_polish 日常把「是→系」「然而→不过」「让→畀」，读诗会破坏原文。
# 触发词以「朗读动作 + 文体」为主，避免把「讲下李白嘅故事」这种普通问答误判。
POEM_VERB = ["读", "讀", "念", "誦", "诵", "背", "朗誦", "朗诵", "吟", "唱", "默", "译", "譯", "讲下", "講下"]
POEM_HINTS = [
    "诗", "詩", "唐诗", "唐詩", "古诗", "古詩", "诗词", "詩詞", "诗歌", "詩歌",
    "绝句", "絕句", "律诗", "律詩", "词牌", "詞牌", "古文", "文言文", "文言",
    "静夜思", "靜夜思", "将进酒", "將進酒", "望庐山", "春晓", "春曉", "登鹳雀",
    "琵琶行", "长恨歌", "長恨歌", "出塞", "赤壁", "岳阳楼记", "岳陽樓記", "桃花源记",
    # 高频诗句锚点：主人直接甩一句诗问「某字点读」时，未必讲出诗名
    "同是天涯", "床前明月", "疑是地上", "举头望月", "举头望明月", "低头思故乡",
    "春眠不觉晓", "处处闻啼鸟", "白日依山尽", "黄河入海流", "欲穷千里目",
    "谁知盘中餐", "粒粒皆辛苦", "海内存知己", "天涯若比邻", "会当凌绝顶",
    "一览众山小", "孤帆远影", "唯见长江", "山重水复", "柳暗花明", "人有悲欢离合",
]
# 明确「呢句/这句 + 系/是 + 点读」的读音咨询，也要按书面读（问「同是天涯沦落人嘅是点读」）
POEM_READ_HINTS = ["点读", "點讀", "点念", "點念", "点发音", "怎么读", "怎麼讀", "读音", "讀音", "边个音", "邊個音"]

# ---------------- 英文意图自动路由（v1.25）----------------
# 背景：主人习惯「1号闲聊键通吃」，用英文问嘢（12:06「i want to a travel to shanghai…」、
# 13:03「帮我用英文介绍去上海…」）全部落 role=aqing_chat，被 yue_polish 英文碎片清理
# 删到净系得返零星字母，TTS 冇英文可念 -> 主人听到「例句冇发音」。4号英语老师键本来
# 走 polish_english 豁免、英文完整，但主人唔系按 4 号键。故喺【闲聊键】加自动路由：
# 检测到明确英文学习/输出意图 -> 当英语老师处理（换普通话 system + 豁免清英文），
# 令「用英文问」无论按边个键都保住英文例句同发音。唔碰 6 个学科键，零回归面。
# 开关 AUTO_EN=0 可一键关，回滚到旧行为。
AUTO_EN = os.getenv("AUTO_EN", "1").strip().lower() not in ("0", "false", "no", "off")
# 明确要英文输出/英文教学嘅意图词（中英夹杂、简繁粤都收，唔收裸「英文」防误伤
# 「识唔识英文」呢类自我认知；要「用英文/讲英文/英文例句」呢类带动作或对象嘅组合）
EN_INTENT_WORDS = (
    "用英文", "用英語", "用英语", "讲英文", "講英文", "说英文", "說英文", "用英文讲", "用英語講",
    "英文介绍", "英文介紹", "英文讲解", "英文講解", "英文回答", "英文讲下", "英文講下",
    "讲下英文", "講下英文", "英文例句", "英文句子", "英文单词", "英文單詞", "英文字",
    "英文翻译", "英文翻譯", "译成英文", "譯成英文", "翻成英文", "翻译成英文", "翻譯成英文",
    "英文点讲", "英文點講", "英文点样讲", "英文怎麼說", "英文怎么说", "英文名",
    "教我英文", "教我英语", "學英文", "学英文", "学英语", "學英語", "练英文", "練英文", "练英语",
    "英文课", "英文課", "英语课", "英語課", "中英双语", "中英雙語", "中英文",
    "英文语法", "英文語法", "英语语法", "英語語法", "英文时态", "音标", "音標", "phonetic",
    "in english", "speak english", "teach me english", "english lesson", "english word",
    "english sentence", "example sentence", "translate to english", "grammar", "present continuous",
    "past tense", "how do you say", "what does", "mean in english",
)
# 主体系英文嘅判定：ASCII 字母够多 + 英文词数够多 + 中文占比唔高（区分「夹个 OK/NBA」）
_EN_WORD_RE = re.compile(r"[A-Za-z]+(?:['’\-][A-Za-z]+)*")
_EN_ALLOW = {"OK", "NBA", "CBA", "UFC", "AI", "GDP", "CEO", "PM", "GPS", "WIFI",
             "VIP", "DNA", "CPU", "APP", "VS", "PK", "TV", "PC", "LED", "HIV", "WHO"}
# 纯寒暄英文（hello how are you / thank you / good morning…）唔系要学英文，唔好切讲课模式。
_EN_SMALLTALK = {"hello", "hi", "hey", "how", "are", "you", "thank", "thanks", "thankyou",
                 "ok", "okay", "bye", "goodbye", "morning", "afternoon", "evening", "good",
                 "fine", "yes", "no", "please", "well", "nice", "sup", "yo", "today", "hey"}


def is_english_auto(q, role_key):
    """v1.25：闲聊键（role_key 空/aqing_chat）上，用户系咪明确要英文输出/英文教学？
    只喺呢两个 role 上判；6 个学科键（chinese/math/physics/chemistry/history）一律 False，
    唔抢人哋嘅粤语讲课。命中后 do_POST 会当英语老师处理，保住英文例句同 TTS 发音。"""
    if not AUTO_EN:
        return False
    if role_key not in ("", "aqing_chat"):
        return False
    if not isinstance(q, str) or not q.strip():
        return False
    s = q.lower()
    # ① 明确英文意图词（最长/最具体先，命中即返）
    for w in EN_INTENT_WORDS:
        if w.lower() in s:
            return True
    # ② 主体系英文：剔除白名单专名后英文实词 >=3，且【至少一个实词唔系纯寒暄】
    #    （防 "hello how are you" 纯打招呼被切去讲课），ASCII 字母占比 >= 50%。
    words = _EN_WORD_RE.findall(q)
    content_words = [w for w in words if w.upper() not in _EN_ALLOW]
    informative = [w for w in content_words if w.lower() not in _EN_SMALLTALK]
    if len(content_words) >= 3 and informative:
        ascii_letters = sum(1 for c in q if c.isascii() and c.isalpha())
        cjk = sum(1 for c in q if "\u4e00" <= c <= "\u9fff")
        if ascii_letters >= 8 and ascii_letters > cjk:
            return True
    return False

# ---------------- 天气：内置城市经纬度（免 geocoding 往返，覆盖常用）----------------
CITY_COORD = {
    "广州": (23.13, 113.26), "深圳": (22.54, 114.06), "珠海": (22.27, 113.58),
    "佛山": (23.02, 113.12), "东莞": (23.02, 113.75), "中山": (22.52, 113.39),
    "惠州": (23.11, 114.42), "汕头": (23.35, 116.68), "湛江": (21.27, 110.36),
    "肇庆": (23.05, 112.47), "江门": (22.58, 113.08), "清远": (23.68, 113.14),
    "韶关": (24.80, 113.60), "梅州": (24.29, 116.12), "揭阳": (23.55, 116.47),
    "潮州": (23.66, 116.62), "云浮": (22.93, 112.02), "茂名": (21.66, 110.92),
    "阳江": (21.86, 111.98), "河源": (23.73, 114.70), "汕尾": (22.78, 115.38),
    "香港": (22.32, 114.17), "澳门": (22.20, 113.54),
    "北京": (39.90, 116.41), "上海": (31.23, 121.47), "天津": (39.34, 117.36),
    "重庆": (29.56, 106.55), "成都": (30.57, 104.07), "武汉": (30.59, 114.31),
    "长沙": (28.23, 112.94), "杭州": (30.27, 120.15), "南京": (32.06, 118.80),
    "苏州": (31.30, 120.59), "西安": (34.34, 108.94), "郑州": (34.75, 113.63),
    "济南": (36.65, 117.00), "青岛": (36.07, 120.38), "大连": (38.91, 121.61),
    "沈阳": (41.80, 123.43), "长春": (43.82, 125.32), "哈尔滨": (45.80, 126.53),
    "昆明": (25.04, 102.72), "贵阳": (26.65, 106.63), "南宁": (22.82, 108.32),
    "海口": (20.04, 110.20), "三亚": (18.25, 109.51), "福州": (26.08, 119.30),
    "厦门": (24.48, 118.09), "南昌": (28.68, 115.86), "合肥": (31.82, 117.23),
    "太原": (37.87, 112.55), "石家庄": (38.04, 114.51), "兰州": (36.06, 103.83),
    "乌鲁木齐": (43.83, 87.62), "拉萨": (29.65, 91.12), "西宁": (36.62, 101.78),
    "银川": (38.49, 106.23), "呼和浩特": (40.84, 111.75), "台北": (25.03, 121.56),
    "东京": (35.68, 139.69), "大阪": (34.69, 135.50), "首尔": (37.57, 126.98),
    "新加坡": (1.35, 103.82), "曼谷": (13.76, 100.50), "伦敦": (51.51, -0.13),
    "纽约": (40.71, -74.01), "洛杉矶": (34.05, -118.24), "悉尼": (-33.87, 151.21),
}
DEFAULT_CITY = ("广州", 23.13, 113.26)   # 阿晴系广州西关女，问天气冇指定城市就默认广州
GEOCODE_API = "https://geocoding-api.open-meteo.com/v1/search?name={name}&count=1&language=zh&format=json"
FORECAST_API = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
    "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"
    "&timezone={tz}&forecast_days=3"
)
# WMO 天气代码 -> 中性中文（GLM 再用阿晴口吻转粤语）
WMO_DESC = {
    0: "天晴", 1: "大致天晴", 2: "局部多云", 3: "阴天",
    45: "有薄雾", 48: "有雾凇",
    51: "微细毛毛雨", 53: "毛毛雨", 55: "较密毛毛雨",
    56: "冻毛毛雨", 57: "较密冻毛毛雨",
    61: "微雨", 63: "落雨", 65: "大雨",
    66: "冻雨", 67: "强冻雨",
    71: "微雪", 73: "落雪", 75: "大雪", 77: "米雪",
    80: "零散阵雨", 81: "阵雨", 82: "强阵雨",
    85: "零散阵雪", 86: "强阵雪",
    95: "雷暴", 96: "雷暴伴细冰雹", 99: "雷暴伴强冰雹",
}

# ---------------- RSS 源（2026-11-11 实测：只有呢两个活着）----------------
RSS_NEWS = [
    ("中新网", "https://www.chinanews.com.cn/rss/scroll-news.xml"),
    ("新浪滚动", "https://rss.sina.com.cn/news/marquee/ddt.xml"),
]
# 用 cn.bing.com：实测 www.bing.com 对两字人名会拆词（「李白」->「李」字释义），
# cn 域名返回「李白（唐代诗人）_百度百科」，中文实体准确率高得多（新闻搜索同样受益）。
BING_WEB = "https://cn.bing.com/search?q={q}&format=rss&setlang=zh-cn"
# 快懂百科词条页：按【词条名】精确抓 meta description，唔靠搜索引擎分词。
# 实测 21/21 命中、人名/地名/概念极准；配 h1 校验可挡歧义词（西湖->昆明湖、故宫->景福宫）。
BAIKE_WEB = "https://www.baike.com/wiki/{q}"

# ---------------- 广州本地新闻源（2026-11-11 实测打通）----------------
# ① 广州广播电视台·广视网 官方 API（GET）：templateId=3 要闻 / =5 广州新闻联播
#    域名 gzbn.gztv.com:7443 是 app.js axios baseURL 挖出；字段 operateTitle/operateTime/publishName
GZTV_API = "https://gzbn.gztv.com:7443/media-cloud-manage-app/webPage/queryTemplateContentList"
GZTV_TPL = [("要闻", 3), ("广州新闻联播", 5)]
# ② 广州日报·新花城（花城+ 同属广报系，代表本地媒体/官微同源稿）静态 JSON，免参数
XINHUACHENG_JSON = "https://huacheng.gz-cmc.com/json/channel/yaowen/list.json"
# 说明：广州台「花城+」App(com.hcj.gznews) 无公开网页 API，其母台新闻=广视网同源，用 GZTV_API 代表。
# 微信公众号：搜狗微信实测返回陈年旧文（2022疫情等）、wechat2rss 需微信扫码订阅，均无法自动化取「今日」，
#            故以广视网+新花城嘅官媒同源稿覆盖；直连公众号限制见说明文档。

# 广州本地新闻意图：问「广州本地新闻/广州台/广视网/花城+」时优先抓上面三源
GZ_NEWS_HINTS = [
    "广州本地", "广州新闻", "广州台", "广视网", "花城+", "花城加", "广视新闻",
    "广州新闻联播", "广州日报", "新花城", "大洋网", "羊城", "穗城", "本地新闻",
    "广州发生", "广州嘅新闻", "广州有咩事", "广州要闻", "羊城晚报",
]

CACHE = {}
CACHE_LOCK = threading.Lock()


def log(*a):
    print("[gw]", time.strftime("%H:%M:%S"), *a, flush=True)


# ==================== 对话记录（v1.23）====================
# 每轮问答落持久化卷 /data/conversations/YYYY-MM-DD.jsonl，一行一条 JSON。
# 全部操作包 try/except：写记录失败净系 log，绝不影响对话主链路。
CONV_LOCK = threading.Lock()

def _conv_dir():
    try:
        os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
        return CONVERSATIONS_DIR
    except Exception as e:
        log("CONV_MKDIR_FAIL", repr(e)[:100])
        return None


def extract_answer_text(body, stream):
    """由网关处理后嘅 response body 提取回复全文（即真正播放畀用户听嘅文本）。
    非 stream: choices[0].message.content；stream: 拼所有 delta.content。失败返回 ''。"""
    try:
        s = body.decode("utf-8", "replace") if isinstance(body, (bytes, bytearray)) else str(body)
        if not stream:
            d = json.loads(s)
            parts = []
            for ch in d.get("choices", []):
                c = (ch.get("message") or {}).get("content")
                if isinstance(c, str):
                    parts.append(c)
            return "".join(parts)
        # stream: SSE，逐行 data: {...}
        parts = []
        for line in s.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                d = json.loads(payload)
            except Exception:
                continue
            for ch in d.get("choices", []):
                c = (ch.get("delta") or {}).get("content")
                if isinstance(c, str):
                    parts.append(c)
        return "".join(parts)
    except Exception as e:
        log("CONV_EXTRACT_FAIL", repr(e)[:80])
        return ""


def conv_record(q, answer, role_key, stream, wanted, model, dur, auto_en=False):
    """落一条对话记录。wanted 系 dict（各联网意图布尔），用于记低「有冇查过网」。
    auto_en=True（v1.25 英文自动路由）：真实按键系闲聊键，但走咗英语老师链路，
    显示名加后缀、落一个布尔字段，方便查看页一眼认出（role_key 仍记真实按键）。"""
    if not CONV_LOG_ENABLED:
        return
    d = _conv_dir()
    if not d:
        return
    try:
        btn, rname = ROLE_META.get(role_key, ROLE_META[""])
        if auto_en:
            rname = rname + "〔英文自动〕"
        now = time.time()
        lt = time.localtime(now)
        day = time.strftime("%Y-%m-%d", lt)
        net = any(bool(wanted.get(k)) for k in
                  ("weather", "gz", "news", "search", "kb", "subject"))
        rec = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S", lt),
            "epoch": round(now, 3),
            "btn": btn,
            "role": rname,
            "role_key": role_key or "aqing_chat",
            "q": q or "",
            "a": answer or "",
            "stream": bool(stream),
            "net": net,
            "model": model,
            "dur": round(dur, 2),
            "auto_en": bool(auto_en),
        }
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        path = os.path.join(d, day + ".jsonl")
        with CONV_LOCK:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        log("CONV_SAVED day=%s btn=%s q=%r a_len=%d net=%s auto_en=%s" %
            (day, btn, (q or "")[:24], len(answer or ""), net, bool(auto_en)))
    except Exception as e:
        log("CONV_WRITE_FAIL", repr(e)[:100])


# v1.31 对话记录「聚合读取 + 至少保留 30 天」——修「一刷新就全部唔见」。
# 历史坑：旧验证脚本每次部署将主 jsonl 清空、备份成 YYYY-MM-DD.jsonl.bak-*，
# 而旧 conv_dates 正则只认纯 .jsonl$、睇唔到备份 -> 查看页净系读到空档，真实记录「隐形」。
# 而家：① conv_dates/conv_read 聚合【主文件 + 同日所有 .bak-* 快照 + archive/ 归档】，
#       按 epoch 去重（快照重叠都唔会重复）；② 超保留期只移去 archive/ 仍可查、绝不静默删。
_DAY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl")   # 唔带 $：匹配 日期.jsonl 同 日期.jsonl.bak-*


def _rec_key(r):
    """去重键：优先 epoch（毫秒级唯一）；缺 epoch 退回 ts+q+答长度，避免旧/损坏记录误删。"""
    ep = r.get("epoch")
    if isinstance(ep, (int, float)):
        return ("ep", round(float(ep), 3))
    return ("fb", r.get("ts", ""), (r.get("q", "") or "")[:80], len(r.get("a", "") or ""))


def _day_files(d, day):
    """返回某日全部候选文件（活跃目录 + archive/ 子目录），文件名以 日期.jsonl 开头。
    顺序：活跃主文件优先，其次活跃备份，最后归档——即同 epoch 重复时，优先用活跃/较新嗰份。"""
    out = []
    for base in (d, os.path.join(d, CONV_ARCHIVE_SUBDIR)):
        try:
            names = os.listdir(base)
        except Exception:
            continue
        # 主文件（纯 日期.jsonl）排最前，备份/.bak 排后
        mains = [n for n in names if n == day + ".jsonl"]
        baks = sorted(n for n in names if _DAY_RE.match(n) and n.startswith(day + ".jsonl")
                      and n != day + ".jsonl")
        for n in mains + baks:
            p = os.path.join(base, n)
            if os.path.isfile(p):
                out.append(p)
    return out


def conv_dates():
    """有记录嘅日期列表（倒序）。v1.31：聚合活跃目录 + archive/，且认 .bak-* 后缀，
    所以历史备份文件嘅记录唔会再「隐形」。"""
    out = set()
    try:
        d = _conv_dir()
        if not d:
            return []
        for base in (d, os.path.join(d, CONV_ARCHIVE_SUBDIR)):
            try:
                names = os.listdir(base)
            except Exception:
                continue
            for n in names:
                m = _DAY_RE.match(n)
                if m:
                    out.add(m.group(1))
    except Exception as e:
        log("CONV_DATES_FAIL", repr(e)[:80])
    return sorted(out, reverse=True)


def conv_read(day="", role_key="", kw="", limit=200):
    """读记录（v1.31 聚合去重）：day=YYYY-MM-DD 或空=全部；聚合主文件+同日备份+归档，
    按 epoch 去重（快照重叠唔重复）、倒序返回最新 limit 条。role_key/kw 过滤照旧。"""
    rows = []
    try:
        d = _conv_dir()
        if not d:
            return rows
        days = [day] if day else conv_dates()
        seen = set()
        for dy in days:
            for p in _day_files(d, dy):
                try:
                    f = open(p, "r", encoding="utf-8")
                except Exception:
                    continue
                with f:
                    for ln in f:
                        ln = ln.strip()
                        if not ln:
                            continue
                        try:
                            r = json.loads(ln)
                        except Exception:
                            continue
                        k = _rec_key(r)
                        if k in seen:
                            continue
                        if role_key and r.get("role_key") != role_key:
                            continue
                        if kw and (kw not in r.get("q", "") and kw not in r.get("a", "")):
                            continue
                        seen.add(k)
                        rows.append(r)
        rows.sort(key=lambda x: x.get("epoch", 0), reverse=True)
        return rows[:limit]
    except Exception as e:
        log("CONV_READ_FAIL", repr(e)[:80])
        return rows


def conv_retention(force=False):
    """v1.31 保留策略：活跃目录净系留最近 CONV_KEEP_DAYS 天【主文件】；更早嘅移到 archive/
    （仍喺持久卷、conv_dates/conv_read 都读得到 -> 全部记录至少 30 天在线、默认永久可查）。
    .bak-* 快照一律保留（唔郁），因为佢哋系历史备份、可能系唯一数据。
    只有显式设 CONV_PURGE_DAYS>0 先至会删除超过 N 天嘅归档（默认 0=永不永久删除）。
    每次落盘调用，但每小时最多真正 scan 一次（节流）。包 try/except，绝不影响对话。"""
    global _CONV_RETENTION_TS
    now = time.time()
    if not force and (now - _CONV_RETENTION_TS) < _CONV_RETENTION_INTERVAL:
        return
    _CONV_RETENTION_TS = now
    d = _conv_dir()
    if not d:
        return
    try:
        today = time.localtime(now)
        # 保留期截止日（呢日之前嘅主文件先至归档）；用日期字符串比较，安全过 epoch
        cutoff = time.strftime("%Y-%m-%d", time.localtime(now - CONV_KEEP_DAYS * 86400))
        arc = os.path.join(d, CONV_ARCHIVE_SUBDIR)
        moved = 0
        for fn in os.listdir(d):
            m = re.match(r"^(\d{4}-\d{2}-\d{2})\.jsonl$", fn)   # 净系主文件，唔郁 .bak
            if not m or m.group(1) >= cutoff:
                continue
            try:
                os.makedirs(arc, exist_ok=True)
                src, dst = os.path.join(d, fn), os.path.join(arc, fn)
                if os.path.exists(dst):   # 归档已存在：唔覆盖，改成带时间戳名并存
                    dst = os.path.join(arc, fn + ".arch" + str(int(now)))
                shutil.move(src, dst)
                moved += 1
            except Exception as e:
                log("CONV_ARCHIVE_ONE_FAIL", fn[:24], repr(e)[:60])
        if moved:
            log("CONV_RETENTION archived=%d cutoff=%s keep=%d" % (moved, cutoff, CONV_KEEP_DAYS))
        # 可选真正清理：只有 CONV_PURGE_DAYS>0 才会删归档超期文件
        if CONV_PURGE_DAYS > 0 and os.path.isdir(arc):
            purge_cut = time.strftime("%Y-%m-%d", time.localtime(now - CONV_PURGE_DAYS * 86400))
            for fn in os.listdir(arc):
                m = _DAY_RE.match(fn)
                if m and m.group(1) < purge_cut:
                    try:
                        os.remove(os.path.join(arc, fn))
                        log("CONV_PURGE removed=%s" % fn[:24])
                    except Exception as e:
                        log("CONV_PURGE_FAIL", repr(e)[:60])
    except Exception as e:
        log("CONV_RETENTION_FAIL", repr(e)[:80])


def token_ok(handler):
    """VIEW_TOKEN 空=放行；否则要 query ?t= 或 header X-View-Token。"""
    if not VIEW_TOKEN:
        return True
    try:
        if handler.headers.get("X-View-Token", "").strip() == VIEW_TOKEN:
            return True
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
        return qs.get("t", [""])[0] == VIEW_TOKEN
    except Exception:
        return False


CHAT_HTML = r"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>火火兔 · 对话记录</title>
<style>
  :root{
    --paper:#fbf7ef; --card:#fffdf8; --ink:#4a4036; --sub:#8a7d6d;
    --line:#e8dfd0; --brand:#c4794f; --brand2:#a85f3a; --user:#f0e6d6;
    --net:#e7f0e4; --netink:#5c7a52; --accent:#f6ead8;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);
    font-family:-apple-system,"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;
    line-height:1.7;font-size:15px}
  header{position:sticky;top:0;z-index:9;background:rgba(251,247,239,.94);
    backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 20px}
  .h1{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
  .h1 b{font-size:20px;color:var(--brand2);letter-spacing:.5px}
  .h1 span{font-size:12px;color:var(--sub)}
  .bar{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;align-items:center}
  select,input,button{font:inherit;color:var(--ink);background:var(--card);
    border:1px solid var(--line);border-radius:10px;padding:8px 11px;outline:none}
  select:focus,input:focus{border-color:var(--brand)}
  input[type=search]{flex:1;min-width:160px}
  button{cursor:pointer;background:var(--brand);color:#fff;border-color:var(--brand);font-weight:600}
  button:hover{background:var(--brand2)}
  button.ghost{background:var(--card);color:var(--brand2)}
  .progress{height:3px;background:var(--line);border-radius:3px;margin-top:12px;overflow:hidden;display:none}
  .progress.on{display:block}
  .progress i{display:block;height:100%;background:var(--brand);width:40%;animation:slide 1s ease-in-out infinite}
  @keyframes slide{0%{margin-left:-40%}100%{margin-left:100%}}
  main{max-width:820px;margin:0 auto;padding:20px}
  .stat{font-size:12px;color:var(--sub);margin:4px 0 16px}
  .row{background:var(--card);border:1px solid var(--line);border-radius:14px;
    padding:16px 18px;margin-bottom:14px;box-shadow:0 2px 10px rgba(120,90,50,.04)}
  .meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px;font-size:12px;color:var(--sub)}
  .btn-no{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;
    border-radius:7px;background:var(--brand);color:#fff;font-weight:700;font-size:12px}
  .role{font-weight:600;color:var(--brand2)}
  .net{background:var(--net);color:var(--netink);border-radius:20px;padding:2px 9px;font-size:11px}
  .who{font-size:11px;font-weight:700;color:var(--sub);margin:8px 0 3px}
  .bubble{border-radius:12px;padding:10px 13px;white-space:pre-wrap;word-break:break-word}
  .q{background:var(--user);border-top-left-radius:3px}
  .a{background:var(--accent);border-top-left-radius:3px}
  .a.long{max-height:220px;overflow:hidden;position:relative}
  .a.long::after{content:"";position:absolute;left:0;right:0;bottom:0;height:42px;
    background:linear-gradient(transparent,var(--accent))}
  .more{display:inline-block;margin-top:6px;font-size:12px;color:var(--brand2);cursor:pointer;user-select:none}
  .empty{text-align:center;color:var(--sub);padding:60px 20px}
  .empty b{display:block;color:var(--ink);font-size:17px;margin-bottom:6px}
  footer{text-align:center;color:var(--sub);font-size:12px;padding:24px}
  .err{background:#fbe9e7;color:#a33;border:1px solid #f3c7c2;border-radius:10px;padding:10px 14px;margin-bottom:14px}
</style>
</head>
<body>
<header>
  <div class="h1"><b>火火兔 · 对话记录</b><span id="sub">加载中…</span></div>
  <div class="bar">
    <select id="day" aria-label="日期"><option value="">全部日期</option></select>
    <select id="role" aria-label="角色">
      <option value="">全部角色</option>
      <option value="aqing_chat">1 阿晴·闲聊</option>
      <option value="chinese_teacher">2 语文老师</option>
      <option value="math_teacher">3 数学老师</option>
      <option value="english_teacher">4 英语老师</option>
      <option value="physics_teacher">5 物理老师</option>
      <option value="chemistry_teacher">6 化学老师</option>
      <option value="history_teacher">7 历史老师</option>
    </select>
    <input id="kw" type="search" placeholder="搜问题或回答关键词…">
    <button class="ghost" id="auto">自动刷新：关</button>
    <button id="refresh">刷新</button>
  </div>
  <div class="progress" id="pg"><i></i></div>
</header>
<main>
  <div class="stat" id="stat"></div>
  <div id="list"></div>
</main>
<footer>记录存于本机持久化卷 · 只在此机/局域网可见 · 刷新即取最新</footer>
<script>
const $ = s => document.querySelector(s);
const TOKEN = new URLSearchParams(location.search).get('t') || '';
let autoTimer = null;
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function api(){
    const p = new URLSearchParams({day:$('#day').value, role:$('#role').value,
    kw:$('#kw').value.trim(), limit:'1000'});
  if(TOKEN) p.set('t',TOKEN);
  return '/logs?'+p.toString();
}
function bubble(cls,txt){
  const long = txt.length>240;
  return '<div class="bubble '+cls+(long?' long':'')+'">'+esc(txt)+'</div>'+
    (long?'<span class="more">▾ 展开全文</span>':'');
}
function render(items){
  const box=$('#list');
  if(!items.length){box.innerHTML='<div class="empty"><b>呢度仲未有记录</b>对玩具讲句话，记录就会自动出现喺呢度。</div>';return;}
  box.innerHTML=items.map(r=>{
    const dur=r.dur?(' · '+r.dur+'s'):'';
    return '<article class="row"><div class="meta">'+
      '<span class="btn-no">'+esc(r.btn)+'</span>'+
      '<span class="role">'+esc(r.role)+'</span>'+
      '<span>'+esc(r.ts)+dur+'</span>'+
      (r.net?'<span class="net">联网核实</span>':'')+
      '</div>'+
      '<div class="who">你问</div>'+bubble('q',r.q)+
      '<div class="who">阿晴答</div>'+bubble('a',r.a)+
      '</article>';
  }).join('');
  box.querySelectorAll('.more').forEach(el=>el.onclick=()=>{
    const b=el.previousElementSibling;
    if(b.classList.contains('long')){b.classList.remove('long');el.textContent='▴ 收起';}
    else{b.classList.add('long');el.textContent='▾ 展开全文';}
  });
}
function load(){
  $('#pg').classList.add('on');
  fetch(api()).then(r=>r.json()).then(d=>{
    $('#pg').classList.remove('on');
    if(d.error){$('#list').innerHTML='<div class="err">'+esc(d.error)+'</div>';return;}
    const sel=$('#day'), cur=sel.value;
    sel.innerHTML='<option value="">全部日期</option>'+d.dates.map(x=>
      '<option value="'+esc(x)+'">'+esc(x)+'</option>').join('');
    sel.value=cur&&d.dates.includes(cur)?cur:'';
    $('#stat').textContent='显示 '+d.count+' 条 · 共 '+d.dates.length+' 日有记录 · 记录至少保留 '+(d.keep_days||30)+' 天（超期归档仍可查） · 最新在前';
    render(d.items);
  }).catch(e=>{
    $('#pg').classList.remove('on');
    $('#list').innerHTML='<div class="err">读取失败：'+esc(e)+'</div>';
  });
}
$('#day').onchange=$('#role').onchange=load;
let deb; $('#kw').oninput=()=>{clearTimeout(deb);deb=setTimeout(load,300);};
$('#refresh').onclick=load;
$('#auto').onclick=()=>{
  if(autoTimer){clearInterval(autoTimer);autoTimer=null;$('#auto').textContent='自动刷新：关';}
  else{autoTimer=setInterval(load,15000);$('#auto').textContent='自动刷新：开';}
};
load();
</script>
</body></html>"""


def render_chat_page():
    return CHAT_HTML


def cache_get(k, ttl=None):
    with CACHE_LOCK:
        v = CACHE.get(k)
        if v and time.time() - v[0] < (ttl if ttl is not None else CACHE_TTL):
            return v[1]
    return None


def cache_set(k, val):
    with CACHE_LOCK:
        CACHE[k] = (time.time(), val)


def strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def fetch(url, timeout=None):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout or FETCH_TIMEOUT, context=CTX).read()


def fetch_parallel(jobs, timeout=None):
    """v1.36：多个独立 URL 并行抓取，缩「联网抓取」等待（原串行 3 源最坏 24s）。
    jobs = [(key, url), ...]；返回 [(key, bytes_or_None), ...]，【顺序同 jobs 一致】
    （保住下游「百科定义第一行 / 广州相关排前」等顺序语义）。任一失败就位 None，
    绝不影响其它源，亦唔抛异常出门。线程池最多 6，够用且唔会打爆对方。
    """
    from concurrent.futures import ThreadPoolExecutor
    def _one(item):
        key, url = item
        try:
            return key, fetch(url, timeout=timeout)
        except Exception as e:
            log("FETCH_PAR_FAIL", key, repr(e)[:80])
            return key, None
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(jobs)))) as ex:
        return list(ex.map(_one, jobs))


def parse_rss(xml_bytes, limit=12):
    """解析 RSS/Atom，返回 [(title, desc), ...]，容错。"""
    out = []
    try:
        txt = xml_bytes.decode("utf-8", "replace")
        root = ET.fromstring(txt)
    except Exception:
        txt = xml_bytes.decode("utf-8", "replace")
        for m in re.finditer(r"<item[^>]*>(.*?)</item>", txt, re.S | re.I):
            t = re.search(r"<title[^>]*>(.*?)</title>", m.group(1), re.S | re.I)
            d = re.search(r"<description[^>]*>(.*?)</description>", m.group(1), re.S | re.I)
            if t:
                out.append((strip_html(t.group(1)), strip_html(d.group(1)) if d else ""))
        return out[:limit]
    for item in root.iter():
        if item.tag.split("}")[-1].lower() not in ("item", "entry"):
            continue
        title = desc = ""
        for ch in item:
            tag = ch.tag.split("}")[-1].lower()
            if tag == "title" and not title:
                title = strip_html(ch.text or "")
            elif tag in ("description", "summary", "content") and not desc:
                desc = strip_html(ch.text or "")
        if title:
            out.append((title, desc))
        if len(out) >= limit:
            break
    return out[:limit]


def is_weather_intent(q):
    # 明确问过去/回忆/玩笑且无天气时效词 -> 唔查（Open-Meteo 只有而家+未来）
    if any(n in q for n in ("寻日", "昨天", "上年", "记得", "记唔记得", "讲笑", "笑话")):
        if not any(h in q for h in ("天气", "天氣", "气温", "氣溫", "预报", "預報", "台风", "颱風")):
            return False
    return any(h in q for h in WEATHER_HINTS)


def is_news_intent(q):
    return any(h in q for h in NEWS_HINTS)


def is_gz_news_intent(q):
    """问广州本地新闻/广州台/广视网/花城+ -> 优先抓广州本地三源。"""
    # 「本地新闻」若同时明确讲緊广州先算；单讲「本地新闻」唔知边个城市，交返通用新闻
    if any(h in q for h in ("广州本地", "广州新闻", "广州台", "广视网", "花城+", "花城加",
                            "广视新闻", "广州新闻联播", "广州日报", "新花城", "大洋网",
                            "广州发生", "广州嘅新闻", "广州有咩事", "广州要闻", "羊城晚报")):
        return True
    if "本地新闻" in q and any(c in q for c in ("广州", "羊城", "穗")):
        return True
    return False


def is_search_intent(q):
    if any(n in q for n in NEGATE_HINTS):
        if not any(s in q for s in ("新闻", "天气", "最新", "热搜", "帮我查", "搜索")):
            return False
    hit = any(h in q for h in SEARCH_HINTS)
    if hit:
        return True
    soft = any(s in q for s in SEARCH_SOFT)
    timely = any(t in q for t in ("而家", "现在", "最近", "呢排", "这几日", "今日边", "今天几"))
    return soft and timely


def is_knowledge_intent(q):
    """知识/事实类 -> 先联网抓真实资料再答，杜绝 30B/9B 凭记忆乱作。
    保守策略：命中实词问句且唔落排除词先至搜；寒暄/情绪/讲笑/自我认知一律透传。
    天气/新闻/广州新闻由各自更高优先级意图处理，呢度唔重复。
    v1.35：史实锚点优先于「故事/讲古」BLOCK —— 「讲唐朝开国嘅故事」照要查。"""
    if any(b in q for b in KNOWLEDGE_BLOCK) and not is_history_fact(q):
        return False
    if any(o in q for o in KNOWLEDGE_OPINION):
        return False
    # 「介绍/讲下 X」本来就系知识介绍（除非 X 系笑话/故事，已喺 BLOCK 排除）
    if is_intro_place(q):
        return True
    if any(h in q for h in KNOWLEDGE_NOUN_TAIL):
        return True
    if any(w in q for w in KNOWLEDGE_Q_WORDS):
        return True
    return False


# ---------------- 资料强制联网核查（v1.26·主人铁律）----------------
# 背景（2026-11-11 血泪）：主人问「用英文介绍上海嘅标志性景点，特别讲到东方明珠塔」，
# 4号键/英文auto路由全部 net=False（凭 30B 记忆乱作），把「东方明珠塔」讲成「上海塔」。
# 三重叠加根因：①英语老师被 v1.24 默认压制联网；②「用英文介绍…景点」句式唔落
# is_knowledge_intent；③_kb_split 把「用英文同我讲」当搜索词条，查都查唔准。
# 主人新铁律：【每个角色讲嘅资料，都必须经网络搜索核查清楚先至答】。
# 策略：呢个函数专抓【客观资料/专名/地标/数据】——命中就强制 want_kb，无论边个角色
# （含英语老师同 1 号闲聊键）。但保留 BLOCK/OPINION：寒暄/情绪/讲笑/算术/纯语言操练
# （「用英文教我三个例句」「present continuous 点用」）唔系资料，照旧唔搜，避免拖慢同带偏。
# 专名 = 汉字前缀(1~10) + 地标/机构/作品后缀。多字后缀排前面（交替首匹配优先）。
_FACT_SUFFIX = (
    r"广播电视塔|东方明珠|博物馆|纪念馆|美术馆|体育馆|大剧院|音乐厅|国际机场|图书馆|"
    r"水电站|水库|大坝|广场|公园|机场|车站|码头|"
    r"大学|学院|中学|医院|公司|集团|王朝|朝代|帝国|共和国|王国|铁路|高速|公路|地铁|号线|"
    r"半岛|海峡|沙漠|草原|森林|峡谷|"
    r"塔|楼|阁|亭|寺|庙|观|殿|宫|城|堡|桥|"
    r"山|岭|峰|湖|江|河|溪|瀑|泉|岛|湾|港|"
    r"记|传|志|史|书|集|词|诗|曲|剧"
)
# 明确嘅「事实问法」：就算问句无专名后缀，带呢啲疑问词都系要核实嘅客观资料
# （人名/王朝如「李白系边个」「唐太宗边个朝代」冇地标后缀，靠呢个兜，专名交返 _kb_subject）
FACT_Q_WORDS = (
    "几高", "幾高", "多高", "海拔", "几长", "幾長", "几深", "幾深", "几大", "幾大",
    "几多", "幾多", "多少", "面积", "面積", "人口", "建于", "建於", "建成", "始建于", "始建於",
    "位于", "位於", "坐落", "地处", "地處", "属于", "屬於", "哪个省", "哪個省", "哪个国家",
    "几时建", "幾時建", "边年起", "邊年起", "哪年起", "有几年", "有幾年", "多远", "多遠",
    "代表作", "作者系", "作者是", "作者係", "出生", "逝世", "生卒", "夺冠", "奪冠", "世界第",
    "最高", "最长", "最長", "最大", "最早", "第一", "首座", "首创", "首創",
    "系边个", "係邊個", "是誰", "是谁", "边个朝", "邊個朝", "朝代", "哪个朝", "哪個朝",
    "边度人", "邊度人", "哪里人", "哪裡人", "籍贯", "籍貫",
)
# 引用/作品名（书名号、引号包住）-> 事实/原文，必须核实
FACT_QUOTE_RE = re.compile(r"[《〈「”\"]([^\》〉」”\"]{2,20})[\》〉」”\"]")
# 后缀含呢啲字 = 指代/疑问/量词，唔系真专名（呢个塔/座山/边个湖）
_FACT_BAD_PRE = "呢嗰这那哪咩乜我你佢座個个间間只隻某每啥嗰啲些边邊"
# 从后缀左侧【按序剥走】指令/引导词（长词优先），剩低嘅先系实质专名
_FACT_SUB_CUT = (
    "详细介绍", "用英文同我讲", "用英文同我講", "用英文介绍", "用英文介紹", "用英文讲", "用英文講",
    "用英语介绍", "用英語介紹", "详细讲下", "詳細講下", "详细", "詳尽", "詳盡", "详尽", "详尽",
    "讲解下", "講解下", "介绍下", "介紹下", "介绍下", "介绍一下", "介紹一下", "同我讲", "同我講",
    "用英文", "用英語", "用英语", "用英語", "用普通话", "用普通話", "用粤语", "用粵語",
    "介绍", "介紹", "讲解", "講解", "讲到", "講到", "讲下", "講下", "讲讲", "講講",
    "同我", "帮我", "幫我", "教我", "关于", "關於", "特别", "特別", "要", "讲", "講",
    "嘅", "的", "同", "和", "與", "与", "及", "最", "有", "去", "喺", "在", "到", "下", "吓",
    "係", "系", "把", "將", "将", "比", "埋", "畀", "俾", "一", "个", "個",
    "，", ",", "、", " ", "—", "-", "(", ")", "（", "）",
)
# 语言学习元词/学科名 -> 唔系「要联网核实嘅专名」（「单词点读」「历史系咩」唔好当地标搜）
_FACT_STOP = ("单词", "單詞", "生词", "詞典", "词典", "字典", "词性", "詞性", "词组", "詞組",
              "例句", "语法", "語法", "时态", "時態", "语态", "語態", "音标", "音標", "发音", "發音",
              "翻译", "翻譯", "造句", "作文", "历史", "歷史", "地理", "数学", "數學", "物理",
              "化学", "化學", "语文", "語文", "英语", "英語", "中文", "粤语", "粵語", "普通话",
              "文學", "文学", "作品", "小说", "散文", "诗歌", "古仔", "故事", "笑话", "笑話")


def _fact_subject(q):
    """从问句抓最像【专名/地标/作品】嘅一段做搜索主词条（东方明珠塔/庐山/故宫/红楼梦…）。
    算法：①书名号/引号内内容最高优先，整体返回；②逐个后缀位置零宽定位（唔吞前缀，
    避免 finditer 非重叠漏词），只取后缀【左侧紧邻】连续汉字，再按序剥走指令引导词，
    剩低嘅实质名词 + 后缀就系专名。抓唔到或净系元词/指代就返回 ''。
    人名/王朝（李白/唐朝）冇地标后缀 -> 返 ''，由 is_fact_check_needed 嘅 FACT_Q_WORDS 兜联网，
    专名交返 _kb_subject（介绍句式）处理。"""
    m = FACT_QUOTE_RE.search(q or "")
    if m:
        inner = m.group(1).strip(" 啊呀呢咯喎噉嘅的")
        if len(inner) >= 2:
            return inner
    best = ""
    for sm in re.finditer("(?=" + _FACT_SUFFIX + ")", q or ""):
        end = sm.start()
        suf_m = re.match(_FACT_SUFFIX, q[end:])
        if not suf_m:
            continue
        suf = suf_m.group(0)
        # 只取后缀左侧紧邻嘅连续汉字（最多10个）
        left = re.search(r"([\u4e00-\u9fff]{1,10})$", q[max(0, end - 10):end])
        seg = left.group(1) if left else ""
        # 从左按序剥走指令引导词
        changed = True
        while changed and seg:
            changed = False
            for c in _FACT_SUB_CUT:
                if seg.startswith(c) and len(seg) > len(c):
                    seg = seg[len(c):]
                    changed = True
                    break
        cand = seg + suf
        if len(cand) < 2 or len(cand) > 10:
            continue
        if any(x in cand for x in _FACT_BAD_PRE):
            continue
        # 净化：剥完指令后仍以动词/介词/虚字开头，或夹「嘅/的/性/化」修饰字 -> 唔系净专名，弃用
        if seg and seg[0] in "讲到去喺在到把将比系係同和":
            continue
        if any(x in cand for x in "嘅的性化们們"):
            continue
        if any(stop in cand for stop in _FACT_STOP):
            continue
        if len(cand) > len(best):
            best = cand
    return best


FACT_CHECK = os.getenv("FACT_CHECK", "1").strip().lower() not in ("0", "false", "no", "off")


def is_fact_check_needed(q):
    """v1.26 主人铁律：呢条问题会唔会涉及【要核实嘅客观资料/专名/地标/数据】？
    命中 -> do_POST 强制 want_kb=True（各角色共用，英语老师走 english_ref 普通话包装）。
    排除：寒暄/情绪/讲笑/算术/自我认知（BLOCK/OPINION），同埋【纯语言操练】——
    「用英文教我三个例句」「present continuous 点用」「翻译呢句」呢类唔系资料，唔搜。
    FACT_CHECK=0 可一键关，回滚到 v1.25 行为。"""
    if not FACT_CHECK:
        return False
    if not isinstance(q, str) or not q.strip():
        return False
    # v1.35：史实题（朝代/人物/事件/思想归属）唔好畀「故事」BLOCK 挡住——
    #        「讲唐朝开国嘅故事」要联网核实，唔好凼 30B 凭记忆砌，张冠李戴塞「天下为公」。
    if any(b in q for b in KNOWLEDGE_BLOCK) and not is_history_fact(q):
        return False
    if any(o in q for o in KNOWLEDGE_OPINION):
        return False
    if is_history_fact(q):
        return True
    # ⓪ 自我认知/人称问句唔系客观资料（「你而家系边个」「我系谁」「佢係邊個」）——
    #    要喺 FACT_Q_WORDS「系边个」之前挡，否则会误搜。名词主语（李白系边个）就放行。
    if re.search(r"\d*[\u4e00-\u9fff]{0,2}(你|您|我|佢|他|她|大家|自己)[\u4e00-\u9fff]{0,3}"
                 r"(系边个|係邊個|是谁|是誰|系谁|係誰|系边度|係邊度|做咩|叫咩名)", q):
        return False
    # ① 明确事实问法（几高/位于/建于/代表作/最高/系边个…）
    if any(w in q for w in FACT_Q_WORDS):
        return True
    # ② 引用/作品名（书名号、引号）
    if FACT_QUOTE_RE.search(q):
        return True
    # ③ 专名/地标后缀（_fact_subject 已排除「呢个塔/座山」呢类指代，支持庐山/故宫 2 字词）
    if _fact_subject(q):
        return True
    # ④ 阿拉伯数字 + 事实单位（468米、1994年、1238公里、5A）
    if re.search(r"\d+\s*(?:米|公尺|公里|千米|年|月|日|层|層|岁|歲|人|亿|億|万|萬|"
                 r"公顷|公頃|平方公里|吨|噸|度|%|％|A级|A級)", q):
        return True
    return False


def is_long_intent(q):
    return any(h in q for h in LONG_HINTS)


def is_poem_intent(q):
    """朗读诗词/古文，或问诗句某字点读 -> True：整段豁免口语化后处理，逐字照原文。
    主线要「朗读动作/读音咨询」+「文体词」同时出现，避免「讲下李白嘅故事」被误判。
    但「直接甩一句诗问某字点读」「把某句读出来」呢类，本身冇诗名，故开两个窄口。"""
    has_style = any(h in q for h in POEM_HINTS)
    if has_style:
        if any(v in q for v in POEM_VERB):        # 读首诗/念古诗/背静夜思/朗诵/讲下呢首词
            return True
        if any(r in q for r in POEM_READ_HINTS):  # 「呢句诗嘅是点读/读音」
            return True
        if any(x in q for x in ("俾我听", "畀我听", "我听下", "我聽下", "听下", "聽下")):
            return True
    # 窄口 1：明确「把/将 <引用> 读/念/背 出来」——即使引用唔系已知诗名
    if any(k in q for k in ("读出来", "讀出來", "念出来", "唸出來", "背出来", "背出來",
                            "读下", "讀下", "念下", "唸下")):
        return True
    # 窄口 2：问「某字 点读/读音/边个音」且引用咗【文言/书面特征】或【引号原文】——
    # 读音咨询，书面字要读 si6 而非口语 hai6。纯口语字（天气嘅气、呢个字）唔算，防误伤。
    if any(r in q for r in POEM_READ_HINTS) and (
            any(w in q for w in ("是", "然而", "之", "乎", "者", "也", "矣", "焉", "其", "乃", "则", "於", "于"))
            or ("「" in q or "《" in q or "\"" in q)):
        return True
    return False


# ---------------- 话题锚定：防「问庐山讲成广州」类历史话题污染 ----------------
# 根因（2026-11-11 实测）：介绍类问答若前文带着几轮同句式历史（如连问「介绍广州塔/
# 陈家祠/沙面」），9B 会形成「介绍X→讲广州景点」的 in-context 惯性，把「介绍庐山」
# 也套进广州模板，或先蹦一句「个名唔系广州嘅」再纠正；高温度玩具端概率更高。
# 治本策略：仅当【当前是介绍某地的问句】【抓得到明确地名】【地名唔系广州/广东】
#           【且历史里讲过广州/广东景点】四条件同时成立，才丢掉旧轮次 + 注入轻量正向锚定。
#           其余（闲聊/承接追问/广州本地题/含明确城市嘅问句）一律原样透传，保住对话记忆。
# 注意：唔用「唔好讲广州」呢类负面指令——实测会反向激活广州 token（渗出「俯瞰珠江」），
#       改用「专注讲【X】本身」嘅正向隔离，仲要物理移走旧话题源。
INTRO_VERBS = ("介绍", "介紹", "讲下", "講下", "讲讲", "講講", "介绍一下", "介紹一下",
               "介绍下", "介紹下", "讲一讲", "講一講", "话我知", "話我知", "讲讲", "講講")
# 问句里出现呢啲字眼 = 明确带咗地名/物件，唔好当泛问处理
LOCAL_TOKENS = ("广州", "廣州", "羊城", "穗城", "西关", "西關", "荔湾", "荔灣", "越秀",
                "海珠", "天河", "白云山", "白雲山", "沙面", "陈家祠", "陳家祠", "广州塔",
                "廣州塔", "小蛮腰", "珠江新城", "广东", "廣東", "岭南", "嶺南", "省城")
# 人名/名人/非地名介绍对象：呢类唔系「问某地」，但同样可能受历史污染，一并纳管
PLACE_TAIL = ("有咩玩", "有乜玩", "点样", "點樣", "嘅历史", "嘅歷史", "嘅风景", "嘅風景",
              "嘅故事", "嘅由来", "嘅由來", "嘅文化", "嘅交通", "嘅特产", "嘅特產",
              "有咩睇", "有乜睇", "有咩", "有乜", "系点", "係點")


def _strip_lead(q, v):
    """剥掉动词前缀同句中引导词，攞到介绍对象。"""
    s = q.split(v, 1)[-1]
    for lead in ("同我", "帮我", "幫我", "一下", "一吓", "下", "吓", "嘅", "的",
                 "呢个", "呢個", "嗰个", "嗰個", "一个", "一個"):
        if s.startswith(lead):
            s = s[len(lead):]
    for tail in PLACE_TAIL:
        if s.endswith(tail):
            s = s[:-len(tail)]
    return s.strip(" 呀啊呢咯喎噉啦吗喽啰，。！？、,?!? ")


def extract_intro_place(q):
    """抓「介绍/讲下 X」里嘅介绍对象 X；抓唔到或唔似地名就返回 ''。
    只认 2~10 字、唔含疑问语气、唔系纯指代嘅名词短语，避免误伤「讲下个笑话」。"""
    for v in INTRO_VERBS:
        if v in q:
            place = _strip_lead(q, v)
            if not (2 <= len(place) <= 10):
                return ""
            if any(c in place for c in "乜咩点怎啊呀呢吗吧呀谁"):
                return ""
            if any(p in place for p in ("笑话", "笑話", "故事", "古仔", "游戏", "遊戲",
                                        "自己", "你", "我", "嘢", "东西", "東西")):
                return ""
            return place
    return ""


def is_intro_place(q):
    return bool(extract_intro_place(q))


def is_place_anchor_needed(q, msgs):
    """判断要唔要隔离旧历史：介绍非本地地点 + 历史里讲过本地景点，两条同时成立先做。
    历史扫 system 之外所有 user/assistant 文本，命中本地景点词即认定存在惯性源。"""
    place = extract_intro_place(q)
    if not place or any(t in place for t in LOCAL_TOKENS):
        return False
    hist = " ".join(
        (str(m.get("content", "")) for m in (msgs or [])
         if m.get("role") in ("user", "assistant"))
    )
    return any(t in hist for t in LOCAL_TOKENS)


def apply_place_anchor(payload, q, want_poem):
    """命中就：丢掉旧对话轮次（只留 system）+ 贴一条正向「本轮主题」尾注到当前 user。
    返回 True 表示改过 payload。诗/联网/长文由调用方先排除，唔会入呢度。"""
    place = extract_intro_place(q)
    msgs = list(payload.get("messages") or [])
    last = max((i for i, m in enumerate(msgs) if m.get("role") == "user"), default=-1)
    if last < 0:
        return False
    sys_msgs = [dict(m) for m in msgs if m.get("role") == "system"]
    if not sys_msgs:
        log("PLACE_ANCHOR_SKIP 请求无 system 人设消息，放弃隔离以保住人设")
        return False
    cur = dict(msgs[last])
    uc = cur.get("content", "")
    uc = uc if isinstance(uc, str) else str(uc)
    cur["content"] = (
        uc
        + "\n\n【本轮提问·请专注】我呢一句问嘅系【%s】，请直接讲【%s】本身："
        "佢喺边、有咩睇、有咩值得讲，讲唔知就坦率讲唔知，唔好凭旧印象乱作。"
        "我哋头先倾过嘅其他话题，无论讲过边个城市、边啲景点，同呢一题都唔相干，"
        "唔好引用、唔好拎嚟比较，直接由【%s】讲起。"
        "照旧全程简体中文地道粤语口语、短句。"
        % (place, place, place)
    )
    # 隔离生效 => 顺手压低 temperature 到 0.6：介绍类知识问答唔使高温随机发挥，
    # 高温度系 9B 写长文时偶尔蹦「老广/珠江」身份词同事实胡编嘅根源。
    # 只针对呢个窄场景（介绍非本地地点 + 历史讲过本地景点），闲聊/讲笑/陪伴仍用原温度。
    try:
        payload["temperature"] = min(float(payload.get("temperature", 0.7)), 0.6)
    except (TypeError, ValueError):
        payload["temperature"] = 0.6
    payload["messages"] = sys_msgs + [cur]
    log("PLACE_ANCHOR -> %r，隔离旧轮次 %d 条" % (place, len(msgs) - len(sys_msgs) - 1))
    return True


def extract_query(q):
    """从问句里剥出检索关键词。"""
    s = q
    for w in ("帮我查", "查一下", "查下", "搜下", "搜索", "联网", "上网", "睇下",
              "最新嘅", "最新的", "今日", "今天", "而家", "现在", "最近", "呢排",
              "有冇", "有没有", "有咩", "有乜", "俾我听", "畀我听", "讲下", "讲吓",
              "系咩", "是什", "点啊", "点样啊", "嘅新闻", "的新闻"):
        s = s.replace(w, " ")
    # 剥句末/句首孤立语气词，令搜索词更干净（只动两端，唔会伤中间嘅字）
    s = s.strip("啊呀呢咯喎噉嘅啦吗喽啰，。！？、,?!? ")
    s = re.sub(r"[，。！？、,?!?\s]+", " ", s).strip()
    for a, b in (("广州", "广州"), ("天气", "天气"), ("新闻", "新闻"),
                 ("台风", "台风"), ("股价", "股价")):
        s = s.replace(a, b)
    return (s or q)[:40]


def extract_city(q):
    """从问句抽城市：内置表优先，冇命中就 geocoding 兜底，再冇就默认广州。"""
    for name in sorted(CITY_COORD, key=len, reverse=True):
        if name in q:
            la, lo = CITY_COORD[name]
            return name, la, lo
    m = re.search(r"([\u4e00-\u9fa5]{2,4})(?:市|嘅|的)?(?:今日|今天|而家|现在)?(?:天气|气温|几度|落雨|下雨)", q)
    if m:
        name = m.group(1)
        geo = geocode(name)
        if geo:
            return name, geo[0], geo[1]
    return DEFAULT_CITY


def geocode(name):
    try:
        d = json.loads(fetch(GEOCODE_API.format(name=urllib.parse.quote(name))))
        r = (d.get("results") or [None])[0]
        if r:
            return (float(r["latitude"]), float(r["longitude"]))
    except Exception as e:
        log("GEOCODE_FAIL", name, repr(e)[:70])
    return None


def _int_cn(n):
    """整数转中文口语（本场景 0~100 为主）。"""
    d = "零一二三四五六七八九"
    if n < 10:
        return d[n]
    if n < 20:
        return "十" + (d[n - 10] if n > 10 else "")
    if n < 100:
        return d[n // 10] + "十" + (d[n % 10] if n % 10 else "")
    return "".join(d[int(c)] for c in str(n))


def num_to_yue(x):
    """数值转中文口语念法：13.8 -> 十三点八；0 -> 零。避免 TTS 念「℃」同埋小数点误伤。"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    neg = v < 0
    v = abs(v)
    integer = int(v)
    frac = int(round((v - integer) * 10)) % 10
    s = _int_cn(integer)
    if frac:
        s += "点" + "零一二三四五六七八九"[frac]
    return ("负" if neg else "") + s


def wmo_desc(code):
    try:
        return WMO_DESC.get(int(code), "天气有变化")
    except (TypeError, ValueError):
        return "天气有变化"


def gather_weather(query="", raw_q=""):
    """问天气 -> Open-Meteo 真实数值 -> 带硬指令嘅粤语参考文本。失败返回 None。"""
    city, lat, lon = extract_city(raw_q or query or "")
    key = "weather:%.3f,%.3f" % (lat, lon)
    cached = cache_get(key, ttl=600)   # 天气 10 分钟缓存够
    if cached:
        log("WEATHER_CACHE", city)
        return cached
    url = FORECAST_API.format(lat=lat, lon=lon, tz=urllib.parse.quote("Asia/Shanghai"))
    try:
        d = json.loads(fetch(url, timeout=FETCH_TIMEOUT + 3))
    except Exception as e:
        log("WEATHER_FAIL", city, repr(e)[:90])
        return None
    cur = d.get("current") or {}
    day = d.get("daily") or {}
    if cur.get("temperature_2m") is None:
        log("WEATHER_NO_DATA", city)
        return None

    t = num_to_yue(cur.get("temperature_2m"))
    feels = num_to_yue(cur.get("apparent_temperature"))
    hum = num_to_yue(cur.get("relative_humidity_2m"))
    wind = num_to_yue(cur.get("wind_speed_10m"))
    desc = wmo_desc(cur.get("weather_code"))
    obs = (cur.get("time") or "")[11:16] or "而家"
    lines = ["【%s · 而家（%s）实况】气温%s度，体感%s度，湿度百分之%s，风速每小时%s公里，%s。"
             % (city, obs, t, feels or "?", hum or "?", wind or "?", desc)]

    labels = ["今日", "听日", "后日"]
    days = day.get("time") or []
    for i, date in enumerate(days[:3]):
        hi = num_to_yue((day.get("temperature_2m_max") or [None] * 3)[i])
        lo = num_to_yue((day.get("temperature_2m_min") or [None] * 3)[i])
        pop = (day.get("precipitation_probability_max") or [None] * 3)[i]
        wd = wmo_desc((day.get("weather_code") or [None] * 3)[i])
        label = labels[i] if i < len(labels) else date
        pop_s = ("落雨机会百分之%s" % num_to_yue(pop)) if (pop is not None and int(pop) > 0) else "落雨机会好低"
        lines.append("【%s】最低%s度、最高%s度，%s，%s。"
                     % (label, lo or "?", hi or "?", pop_s, wd))

    ref = (
        "【头等指令·必须遵守】啱啱联网查到咗【%s·真实、此刻】嘅天气数值喺下面，"
        "你 MUST 全部依据呢批真实数值嚟答，唔好讲「唔知」「冇资料」，千祈唔好凭记忆乱作天气。\n"
        "【实时天气资料（唯一事实来源）】\n%s\n"
        "【范围】只有而家同埋未来三日，更远嘅日子冇数据，唔好乱讲。\n"
        "【点样答】用你阿晴嘅地道广州西关口语、温柔沉静噉讲：先讲而家几冻几热同体感，"
        "再讲今日同听日要点，末后加句街坊贴士（例如落雨带遮、冻就加衫、热就饮多啲水）。"
        "数字照上面讲，唔好改、唔好额外杜撰；唔好念 URL、编号、来源名、英文字母或温度符号，"
        "讲「度」唔好讲「摄氏度」。\n"
        "【语言铁律】全程净系用简体中文嘅地道粤语口语；绝对唔准夹杂任何英文字母、外语或乱码；"
        "外国人名、机构名一律用中文讲法，讲唔出就跳过唔提。\n"
    ) % (city, "\n".join(lines))
    cache_set(key, ref)
    log("WEATHER", city, "lines=%d len=%d" % (len(lines), len(ref)))
    return ref


def gather_news(query=""):
    """问新闻/时事 -> 抓真实资讯 -> 带硬指令嘅粤语参考文本。失败返回 None。"""
    key = "news:" + query
    cached = cache_get(key)
    if cached:
        log("NEWS_CACHE", repr(query))
        return cached

    items = []
    # ★v1.36：RSS 各源 + Bing【并行】抓（原串行 N×FETCH_TIMEOUT -> ≈单次超时）。
    # 结果按 jobs 顺序收返，append 顺序同旧版一致，故去重/截断/头条排序语义唔变。
    q = query or "今日要闻"
    want_rss = (not query) or is_news_intent(query) or any(
        k in query for k in ("新闻", "最新", "头条", "时事", "资讯", "热搜"))
    jobs = []
    rss_used = []
    if want_rss:
        for name, url in RSS_NEWS:
            rss_used.append(name)
            jobs.append(("rss:" + name, url))
    jobs.append(("bing", BING_WEB.format(q=urllib.parse.quote(q))))
    fetched = dict(fetch_parallel(jobs))

    # A. 滚动头条（中新网实测 30 条，主力；新浪容错）
    for name in rss_used:
        try:
            raw = fetched.get("rss:" + name)
            got = parse_rss(raw) if raw else []
            log("RSS", name, len(got))
            for t, d in got[:10]:
                items.append((name, t, d))
        except Exception as e:
            log("RSS_FAIL", name, repr(e)[:80])

    # B. 按关键词 Bing 网页搜索（format=rss 实测 10 条可用；替代失效嘅 Bing 新闻端点）
    try:
        got = parse_rss(fetched.get("bing")) if fetched.get("bing") else []
        log("BING_WEB", q, len(got))
        for t, d in got[:8]:
            items.append(("网络搜索", t, d))
    except Exception as e:
        log("BING_WEB_FAIL", repr(e)[:80])

    # 去重 + 截断
    seen, lines = set(), []
    for src, t, d in items:
        if not t or t in seen:
            continue
        seen.add(t)
        line = "- %s" % t
        if d and d not in t:
            line += "：" + d[:90]
        lines.append(line)
        if len(lines) >= 12:
            break

    if not lines:
        return None
    # 9B 小模型会「抓住人设、丢掉资料」，硬指令 + 资料贴近生成端，杜绝「冇新闻」乱答。
    headlines = "；".join(l.split("：")[0].lstrip("- ").strip() for l in lines[:6])
    ref = (
        "【头等指令·必须遵守】啱啱联网抓到咗下面呢批【真实、今日】嘅资讯，你 MUST 依据佢哋嚟答，"
        "唔好讲「冇新闻」「唔知」，亦唔好凭记忆乱作。批资料就系你今次答案嘅唯一事实来源。\n"
        "【可用真实新闻标题】" + headlines + "\n"
        "【资料明细】\n" + "\n".join(lines) + "\n"
        "【点样答】用你阿晴嘅地道广州西关口语，从上面挑 2~4 条同问题最贴嘅，"
        "讲清楚「咩事、发生喺边、点解值得知」，加少少街坊感觉；"
        "千祈唔好念 URL、编号、来源名、英文、日期戳；唔好额外杜撰资料以外嘅细节。\n"
        "【语言铁律】全程净系用简体中文嘅地道粤语口语；绝对唔准夹杂任何英文字母、外语"
        "或乱码（连 giao/entrySet/kéo/involve 呢啲碎字都唔准出现）；"
        "外国人名、机构名、技术名一律用中文译名或改用中文讲法讲清楚，讲唔出就跳过唔提。\n"
    )
    cache_set(key, ref)
    log("NEWS", repr(query), "lines=%d len=%d" % (len(lines), len(ref)))
    return ref


# 疑问词边界：喺呢啲字之前嘅系专名，之后嘅系问法。攞专名加引号，逼 Bing 精确匹配。
KB_Q_CUT = (
    "系边个", "係边个", "系边啲", "係边啲", "是什么", "系什么", "係什么", "是什",
    "系咩", "係咩", "系乜", "係乜", "咩系", "乜系", "什么是", "什么叫", "咩叫",
    "有几高", "有幾高", "有几多", "有幾多", "有几长", "有幾長", "有几大", "有幾大",
    "几高", "幾高", "几多", "幾多", "几长", "幾長", "几大", "幾大", "几深", "幾深",
    "几重", "幾重", "几耐", "幾耐", "几时", "幾時", "在哪", "喺边", "喺邊", "边度", "邊度",
    "有哪些", "有哪些", "有哪几", "哪些", "点解", "點解", "为什么", "為什麼", "为何", "為何",
    "嘅历史", "嘅歷史", "的历史", "嘅由来", "嘅由來", "嘅背景", "嘅定义", "嘅定義",
    "嘅原理", "嘅意思", "嘅面积", "嘅面積", "嘅海拔", "嘅作者", "嘅区别", "嘅區別",
    "有咩玩", "有乜玩", "有咩睇", "有乜睇", "有咩特色", "系点", "係点", "点样", "點樣",
)


# 词头/程度修饰：会在介绍动词前，要先剥，否则「详细讲下黄山」->「详细 黄山」搜错
KB_LEAD = ("详细介绍", "详细说说", "详细讲下", "详细講下", "详细", "详尽", "具体", "完整",
           "全面", "深入", "好好", "同我", "帮我", "幫我", "麻烦", "痲煩", "请你", "請你",
           "可唔可以", "可不可以", "交代下", "介绍下", "介紹下", "讲解下", "講解下",
           # v1.26：英语老师/英文auto路由句式嘅指令前缀（唔剥会当「用英文同我讲东方明珠塔」
           # 成个塞去快懂百科/Bing，查都查唔准 -> 老师冇资料 -> 凭记忆将东方明珠塔讲成上海塔）
           "用英文介绍", "用英文介紹", "用英语介绍", "用英語介紹", "用英文讲", "用英文講",
           "用英语讲", "用英語講", "用英文同我讲", "用英文同我講", "用英文同我",
           "用英文", "用英語", "用英语", "用英語", "用普通话", "用普通話", "用粤语", "用粵語",
           "讲英文", "講英文", "用英文教我", "用英文教", "教我", "讲解", "講解", "解释下", "解釋下",
           "同我讲", "同我講", "同我介绍", "同我介紹", "讲下", "講下")


def _kb_split(q):
    """返回 (主词条head, 问法tail)。先剥词头修饰同介绍动词，再按疑问词切。"""
    s = extract_query(q)
    for _ in range(3):                      # 最多剥 3 层（「详细同我介绍下」）
        changed = False
        for v in KB_LEAD:
            if s.startswith(v):
                s = s[len(v):]
                changed = True
                break
        for v in sorted(INTRO_VERBS, key=len, reverse=True):  # 长词优先：「介绍下」先于「介绍」
            if s.startswith(v):
                s = s[len(v):]
                changed = True
                break
        if not changed:
            break
    # 兜底剥残留嘅单个「下/吓/一下」（「介绍下」长词已处理，呢度治「同我介绍下」留底）
    for lead in ("一下", "一吓", "下", "吓"):
        if s.startswith(lead) and len(s) > len(lead) + 1:
            s = s[len(lead):]
            break
    s = s.strip(" 呀啊呢咯喎噉啦吗喽啰，。！？、,?!? ")
    cut = len(s)
    for w in KB_Q_CUT:
        i = s.find(w)
        if 0 < i < cut:
            cut = i
    head = s[:cut].strip(" 呀啊呢咯喎噉啦吗，。！？、,?!? ")
    tail = s[cut:].strip()
    if not (2 <= len(head) <= 14) or any(c in head for c in "咩乜点怎边几谁吗啊呀呢系係详详介"):
        head = ""
    return head, tail


def _kb_subject(q):
    """攞知识题嘅【主词条】：疑问词之前、介绍动词之后嘅专名。
    例「介绍庐山」->庐山；「李白系边个」->李白；「详细讲下黄山」->黄山。"""
    head, _ = _kb_split(q)
    return head


def _kb_search_query(q):
    """cn.bing.com 补充查询词：主词条 + 事实向尾巴（攞细节喂长文）。
    v1.35：史实题用【干净锚点词 + 讲述向尾巴】查，唔好攞「讲唐朝开拓嘅故事」成串去搜；
           顺带确保喂返嚟嘅资料围绕朝代/人物本身，够料支撑 800~1000 字长文。"""
    hs = _history_search_subject(q)
    if hs:
        if any(k in q for k in ("开国", "開國", "建立", "建国", "建國", "称帝", "稱帝", "起兵")):
            return (hs + " 开国 建立 历史 简介")[:40]
        if any(k in q for k in ("开拓", "開拓", "扩张", "擴張", "外交", "对外", "對外")):
            return (hs + " 开拓 对外交流 历史")[:40]
        return (hs + " 历史 简介 人物 事件")[:40]
    head, tail = _kb_split(q)
    if not head:
        return extract_query(q)[:40]
    q_tail = " 简介"
    if any(k in tail for k in ("几高", "幾高", "海拔", "几多", "幾多", "多少", "几长", "幾長")):
        q_tail = " 海拔 高度"
    elif any(k in tail for k in ("边个省", "邊個省", "边度", "邊度", "位于", "位於", "在哪")):
        q_tail = " 位于 哪个省"
    elif any(k in tail for k in ("历史", "歷史", "由来", "由來", "朝代")):
        q_tail = " 历史 简介"
    return (head + q_tail)[:40]


def _baike_definition(subject):
    """快懂百科按词条名直取权威定义。返回 (定义, h1) 或 (None, None)。
    h1 校验：h1 唔同 subject -> 歧义词（西湖->昆明湖/故宫->景福宫），废弃以免答错。"""
    try:
        h = fetch(BAIKE_WEB.format(q=urllib.parse.quote(subject)), timeout=8).decode("utf-8", "replace")
    except Exception as e:
        log("BAIKE_FAIL", repr(e)[:80])
        return None, None
    if len(h) < 3000:
        return None, None
    m = re.search(r'<meta\s+name="description"\s+content="([^"]{20,})"', h, re.I) or \
        re.search(r'<meta\s+content="([^"]{20,})"\s+name="description"', h, re.I)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S | re.I)
    h1t = strip_html(h1.group(1)) if h1 else ""
    if not m:
        return None, h1t
    desc = strip_html(m.group(1))
    # 歧义校验 v2（2026-11-11 修子串漏洞）：
    # 旧逻辑 `subject not in h1t` 会放行「唐朝」->「唐朝乐队」（因「唐朝」系「唐朝乐队」子串），
    # 实测将朝代讲成 1988 年重金属乐队。故：若 h1 比 subject 长，且多出部分系明显实体/领域后缀，
    # 一律判歧义弃用。「牛顿」->「艾萨克·牛顿」呢类【前缀式全名】照放行（多出嘅系人名前缀）。
    AMBIG_SUFFIX = ("乐队", "电影", "电视剧", "纪录片", "综艺", "歌曲", "专辑", "小说", "漫画",
                    "动画", "游戏", "app", "APP", "软件", "网站", "公司", "集团", "大学", "学院",
                    "中学", "小学", "医院", "机场", "车站", "酒店", "广场", "公园", "球队", "俱乐部",
                    "星球", "卫星", "元素", "单位", "符号", "型号", "教程", "题库", "真题")
    if h1t and subject not in h1t and h1t not in subject:
        log("BAIKE_AMBIG", repr(subject), "-> h1=", repr(h1t))
        return None, h1t
    if h1t and h1t.startswith(subject) and len(h1t) > len(subject):
        tail = h1t[len(subject):].strip("（）() ·-—")
        if any(suf in tail for suf in AMBIG_SUFFIX):
            log("BAIKE_AMBIG_SUFFIX", repr(subject), "-> h1=", repr(h1t), "tail=", repr(tail))
            return None, h1t
    return desc, h1t


def gather_knowledge(query="", raw_q=""):
    """知识/事实题 -> 【快懂百科精确定义 + cn.bing 补充细节】-> 带硬指令嘅参考文本。
    2026-11-11 换源：www.bing.com 对两字人名拆词（李白->李字释义）救唔到，
    改用 www.baike.com 按词条名直取权威 meta（21/21 命中、配 h1 挡歧义），
    cn.bing.com 补多条细节喂长文。失败/资料太薄 -> None，畀模型坦白唔知，唔兜乱作。"""
    key = "kb:" + (query or raw_q)
    cached = cache_get(key)
    if cached:
        log("KB_CACHE", repr(query))
        return cached

    raw = raw_q or query
    # v1.26：优先用 _fact_subject 抓准专名（「用英文同我讲东方明珠塔有几高」-> 东方明珠塔），
    # 治旧版 _kb_split 把「用英文同我讲」当词条、查唔准 -> 老师冇资料 -> 凭记忆乱作。
    # 抓唔到专名先退回 _kb_subject（「介绍庐山」-> 庐山）。
    # v1.35：史实题优先用【干净朝代/人物锚点】做词条（「讲唐朝开拓嘅故事」->「唐朝」），
    # 唔好攞「讲唐朝开拓嘅故事」呢类带口语壳嘅长串去查，否则百科/Bing 查唔准 -> 冇资料 -> 乱作。
    subject = _history_search_subject(raw) or _fact_subject(raw) or _kb_subject(raw)
    log("KB_SUBJECT raw=%r -> %r" % (raw[:30], subject))
    EN = re.compile(r"[A-Za-z]{3,}")
    AD = ("攻略", "知乎", "小红书", "携程", "去哪儿", "马蜂窝", "点击", "购买", "优惠",
          "价目", "门票", "预订", "电话", "关注我", "收藏", "评论", "广告", "推广",
          "招聘", "官网", "下载", "下载", "排行榜", "十大", "推荐")
    lines, seen = [], set()

    def add(text, limit=170):
        text = strip_html(text)
        text = EN.sub("", text)
        text = re.sub(r"https?://\S+", "", text).strip()
        if len(text) < 10:
            return
        text = text[:limit]
        k = text[:22]
        if k in seen:
            return
        seen.add(k)
        lines.append(text)

    # ★v1.36：百科主源 + Bing 辅源【并行】抓（原串行最坏 8+7=15s -> max(8,7)≈8s）。
    # 两源互不依赖；结果按【固定槽位】收返，保持「百科定义第一行、Bing 细节跟后」语义。
    from concurrent.futures import ThreadPoolExecutor
    sq = _kb_search_query(raw)

    def _baike_job():
        return _baike_definition(subject) if subject else (None, None)

    def _bing_job():
        try:
            return parse_rss(fetch(BING_WEB.format(q=urllib.parse.quote(sq)), timeout=7), limit=10)
        except Exception as e:
            log("KB_BING_FAIL", repr(e)[:80])
            return []

    with ThreadPoolExecutor(max_workers=2) as ex:
        fb = ex.submit(_baike_job)
        fbing = ex.submit(_bing_job)
        (desc, h1), got = fb.result(), fbing.result()

    # A. 主源：快懂百科按词条名精确定义（人名/地名最准，唔靠分词）
    if desc:
        log("BAIKE_HIT", repr(subject), "len=%d" % len(desc))
        add(desc, limit=260)
    elif subject:
        log("BAIKE_SKIP", repr(subject), "h1=%r" % h1)
    # B. 辅源：cn.bing.com 搜主词条，攞多条细节（生卒/代表作/地貌/历史）喂 1000 字长文
    log("KB_BING", sq, len(got))
    for t, d in got:
        t, d = strip_html(t), strip_html(d)
        if any(a in t for a in AD):   # 攻略/论坛/广告整条丢，防「我见过啲攻略」假经历
            continue
        # 标题带「XX百科」/正文够实在先收；优先摘要，其次标题
        if d and len(d) >= 12:
            add(d)
        elif len(t) >= 12:
            add(t)

    # 兜底：资料太薄 -> 宁愿唔注入，畀 30B 坦白讲唔知，好过攞垃圾落去乱讲
    if len(lines) < 1:
        log("KB_EMPTY", repr(sq), "subject=%r" % subject)
        return None
    facts = "\n".join("· " + l for l in lines[:9])
    ref = (
        "【头等指令·先据真实资料答】用户问紧知识/事实题，啱啱联网查到下面呢批真实资料"
        "（第一行系百科权威定义，跟住系补充细节）。\n"
        "【联网查到嘅真实资料】\n" + facts + "\n"
        "【点样用资料·分两层】\n"
        "① 资料讲到嘅事实——人名、地名、年份、数字、位置、定义、代表作——【一律照资料原样讲】，"
        "千祈唔好凭记忆改数字、改年份、加料或者脑补。\n"
        "①b【地名人名一字唔改·血泪教训】资料写边度就照讲边度、一个字都唔好换：实测过将"
        "「今四川绵阳江油」串成「广东江油」呢类错。你熟识广州、西关、广东，但呢一答啲地名"
        "同你熟唔熟冇关系——资料写四川就讲四川、写安徽就讲安徽、写西域就讲西域，照抄原字，"
        "唔好掉换、唔好改做本地、唔好攞本地地方嚟注释。人名同年份数字同理。\n"
        "② 资料冇覆盖、但系好基本、你同资料都肯定嘅常识，可以自然噉讲多少少令段嘢通顺；"
        "但凡要砌【具体数字、精确年份、人名、事件】而资料冇讲过，就千祈唔好作，"
        "坦白讲「呢部分我搵唔到确切资料，唔敢乱讲」好过乱估。\n"
        "【点样答】用阿晴地道广州西关粤语口语，先直接答中问题核心，再顺住资料有条理噉展开；"
        "唔好念 URL、来源名、编号或者「据资料显示」呢类字眼，就当係你识嘅噉自然讲。\n"
        "【语言铁律】全程净系简体中文地道粤语口语、短句；唔准念 URL、来源名、编号、"
        "英文字母、外语或者乱码；外国名/专名用中文讲法；唔好列表、Markdown、emoji。\n"
    )
    cache_set(key, ref)
    log("KB", repr(sq), "lines=%d len=%d" % (len(lines), len(ref)))
    return ref


def _recent_day(s, days=2):
    """留最近 days 日嘅条目（按 Asia/Shanghai）；日期戳唔正规就当可用，交由去重同截断。"""
    try:
        d = (s or "")[:10]
        if len(d) == 10 and d[4] == "-":
            cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 8 * 3600 - days * 86400))
            return d >= cutoff
    except Exception:
        pass
    return True


def gather_gz_news(query=""):
    """问广州本地新闻 -> 抓 广视网要闻/联播 + 新花城要闻 三源，按日期过滤注入。失败回退 None。"""
    key = "gznews:" + (query or "")
    cached = cache_get(key)
    if cached:
        log("GZ_NEWS_CACHE")
        return cached

    items = []   # (来源, 标题, 时间, 简介)

    # ★v1.36：广视网 2 源 + 新花城 1 源【并行】抓（原串行最坏 3×8=24s -> ≈8s）。
    # fetch_parallel 保证返回顺序同 jobs 一致，故下游 append 顺序、去重、排前逻辑完全唔变。
    gz_jobs = [("gz:" + label, "%s?templateId=%d&pageNum=1&pageSize=12" % (GZTV_API, tid))
               for label, tid in GZTV_TPL]
    gz_jobs.append(("xhc", XINHUACHENG_JSON))
    fetched = dict(fetch_parallel(gz_jobs, timeout=FETCH_TIMEOUT + 2))

    # ① 广州广播电视台·广视网 API（GET，templateId=3 要闻 / 5 联播）
    for label, tid in GZTV_TPL:
        try:
            raw = fetched.get("gz:" + label)
            d = json.loads(raw.decode("utf-8", "replace")) if raw else {}
            recs = ((d.get("data") or {}).get("records") or [])
            n = 0
            for r in recs:
                title = str(r.get("operateTitle") or "").strip()
                tm = str(r.get("operateTime") or r.get("createTime") or "")[:16]
                if not title or not _recent_day(tm):
                    continue
                intro = str(r.get("title") or "").strip()
                src = str(r.get("publishName") or label).strip()
                items.append(("广州广播电视台·" + label, title, tm, intro))
                n += 1
                if n >= 8:
                    break
            log("GZTV", label, n)
        except Exception as e:
            log("GZTV_FAIL", label, repr(e)[:80])

    # ② 广州日报·新花城（本地官媒/公众号同源稿）静态 JSON
    try:
        raw = fetched.get("xhc")
        d = json.loads(raw.decode("utf-8", "replace")) if raw else {}
        n = 0
        for it in (d.get("list") or []):
            dd = it.get("data") or {}
            title = str(dd.get("title") or "").strip()
            tm = str(dd.get("publishTime") or "")[:16]
            if not title or not _recent_day(tm):
                continue
            desc = str(dd.get("description") or "").strip()
            src = str(dd.get("sourceName") or "新花城").strip()
            items.append(("新花城·" + src, title, tm, desc))
            n += 1
            if n >= 8:
                break
        log("XINHUACHENG", n)
    except Exception as e:
        log("XINHUACHENG_FAIL", repr(e)[:80])

    if not items:
        return None

    # 广州本地强相关优先排前，全国/国际时政排后（9B 会优先抓前面，减少「乱绑广州」）
    GZ_MARK = ("广州", "羊城", "穗", "南沙", "天河", "越秀", "荔湾", "海珠", "白云", "黄埔",
               "番禺", "花都", "增城", "从化", "广船", "南粤", "珠江", "联播", "花城号")
    def rank(it):
        src, title, tm, intro = it
        blob = title + intro
        return 0 if any(k in blob for k in GZ_MARK) else 1
    items.sort(key=rank)

    # 去重（按标题）+ 剔栏目名/过短无意义标题 + 截断
    JUNK = ("省市领导", "新闻24小时", "首页", "更多", "专题", "视频", "要闻", "公告")
    seen, lines = set(), []
    for src, title, tm, intro in items:
        if not title or title in seen or title.strip("【】 ") in JUNK or len(title.strip()) < 5:
            continue
        seen.add(title)
        line = "- 【%s】%s" % (src, title)
        if intro and intro not in title and len(intro) <= 90:
            line += "：" + intro
        lines.append(line)
        if len(lines) >= 16:
            break

    ref = (
        "【头等指令·必须遵守】啱啱联网去【广州本地官方媒体】抓到咗下面呢批【真实、今日/琴日】嘅广州本地新闻，"
        "你 MUST 依据佢哋嚟答，唔好讲「冇新闻」「唔知」，千祈唔好凭记忆乱作。批资料就系你今次答案嘅唯一事实来源。\n"
        "【来源】广州广播电视台（广视网·要闻/广州新闻联播）、广州日报新花城（本地官媒同公众号同源稿）。\n"
        "【可用真实新闻】\n" + "\n".join(lines) + "\n"
        "【点样答】用你阿晴嘅地道广州西关口语、温柔沉静噉讲，从上面挑 3~5 条最贴题嘅广州本地新闻，"
        "讲清楚「咩事、发生喺广州边度、点解街坊值得知」，加少少西关心态嘅街坊感觉；"
        "【实情铁律】批资料入面有啲系全国/国际时政（例如进博会、俄乌），呢啲唔系发生喺广州，"
        "千祈唔好讲成「广州举办」「广州发生」；要讲就老实讲系全国/国际事，或者索性唔提，"
        "净系挑标题同简介明确同广州、羊城、穗、南沙、各区、广州台有关嘅本地事嚟重点讲。\n"
        "数字照资料讲，唔好改、唔好额外杜撰；唔好念 URL、编号、来源英文、日期戳或者来源机构全名；"
        "讲「广州台」「本地媒体」呢啲中文讲法就够。\n"
        "【语言铁律】全程净系用简体中文嘅地道粤语口语；绝对唔准夹杂任何英文字母、外语或乱码；"
        "机构名、人名一律用中文，讲唔出就跳过唔提。\n"
    )
    cache_set(key, ref)
    log("GZ_NEWS", "lines=%d len=%d" % (len(lines), len(ref)))
    return ref


def normalize_roles_json(messages):
    """把 FoloToy 传来的 messages 原样留着，仅返回最后一条 user 文本。"""
    last_user = ""
    for m in reversed(messages or []):
        if m.get("role") == "user":
            last_user = m.get("content", "")
            if isinstance(last_user, list):  # 多模态 content
                last_user = " ".join(str(x.get("text", "")) for x in last_user if isinstance(x, dict))
            break
    return last_user or ""


def detect_role(messages):
    """从 system prompt 里嘅【角色:xxx】标记认出当前角色 key；认唔到返回 ''（当普通阿晴处理）。"""
    for m in messages or []:
        if m.get("role") != "system":
            continue
        c = m.get("content", "")
        if isinstance(c, str):
            for key, mark in ROLE_MARKERS.items():
                if mark in c:
                    return key
    return ""


def is_subject_question(q, role_key):
    """学科老师收到嘅问题，系咪要强制联网核实？
    学科题（尤其史实/数据/公式/出处）一定要先搜真实资料，唔好靠 30B 记忆乱作。
    闲聊/打招呼/问「你系边个」呢类透传，唔搜。"""
    if role_key not in SUBJECT_HINTS:
        return False
    # 明显闲聊/寒暄/自我认知 -> 唔搜
    # v1.35：史实锚点优先于「故事」BLOCK（历史老师讲「唐朝开国嘅故事」都要查资料）
    if any(b in q for b in KNOWLEDGE_BLOCK) and not is_history_fact(q):
        return False
    if any(o in q for o in KNOWLEDGE_OPINION):
        return False
    if is_history_fact(q):
        return True
    if any(w in q for w in SUBJECT_HINTS[role_key]):
        return True
    # 兜底：带问号/疑问词又系学科老师，都当要核实（宁可搜唔好乱作）
    if any(w in q for w in ("点解", "點解", "为什么", "為什麼", "为何", "點樣", "点样",
                            "几多", "幾多", "多少", "系咩", "係咩", "是什么", "什么是",
                            "几时", "幾時", "边个", "邊個", "?", "？")):
        return True
    return False


def _subject_anchors(q, role_key):
    """攞问题嘅【核心专名/概念】做相关性闸门锚点。
    cn.bing RSS 对数学/化学查询污染严重（「一元二次方程」->设备验收单、QQ邮箱），
    所以抓到嘅资料必须同问题核心词有交集先至敢注入，宁缺毋滥。"""
    s = extract_query(q)
    # 去掉疑问词/语气词/泛动词，留低实体概念
    noise = ("点解", "點解", "为什么", "為什麼", "为何", "點樣", "点样", "怎样", "如何",
             "系咩", "係咩", "是什么", "什么是", "几多", "幾多", "多少", "几时", "幾時",
             "边个", "邊個", "边度", "邊度", "嘅", "既", "呀", "呢", "吗", "咩", "乜",
             "同", "和", "定", "与", "有", "冇", "冇", "讲下", "講下", "介绍", "介绍一下",
             "以下", "下列", "老师", "同学", "请问", "問", "问", "? ", "？", "？", ".", "。")
    for n in noise:
        s = s.replace(n, " ")
    s = re.sub(r"[\s，,。.？?！!、「」\"'（）()：:]+", " ", s).strip()
    # 2字以上嘅中文片断 + 数字/字母公式（例如 2H2O、I=U/R、x²）
    anchors = re.findall(r"[\u4e00-\u9fff]{2,8}", s)
    anchors += re.findall(r"[A-Za-z]{1,4}\s*=\s*[A-Za-z0-9/²³]+|[0-9]+[A-Za-z]?[²³]?", s)
    # 补充 2~3 字短锚点：长专名（「唐朝建立于公元」）要拆到「唐朝」先撞得中百科
    for a in list(anchors):
        if len(a) > 3:
            anchors.append(a[:2])
            anchors.append(a[:3])
    seen = set()
    uniq = []
    for a in anchors:
        if len(a) >= 2 and a not in seen:
            seen.add(a)
            uniq.append(a)
    return uniq[:12]


def _subject_baike_term(q, role_key):
    """攞【短主词条】查快懂百科：朝代/定律/物质/概念嘅 2~6 字专名。
    避免用「唐朝建立于公元」呢类被疑问词污染嘅长串（会 404 或撞歧义）。"""
    s = extract_query(q)
    # 疑问/描述尾巴一律切掉，只留最前嘅专名核心
    cut = ("建立", "成立", "发明", "发现", "产生", "发生", "开始", "结束", "死亡", "去世",
           "生卒", "几多年", "几多年", "公元", "朝代", "公式", "定律", "定义", "意思",
           "方程式", "化学式", "点解", "为什么", "系乜", "系咩", "是什么", "边个", "几时")
    for c in cut:
        if c in s:
            s = s.split(c, 1)[0]
            break
    s = re.sub(r"[\s，,。.？?！!、（）():：]+", "", s).strip()
    return s[:6] if len(s) >= 2 else ""


def subject_search_query(q, role_key):
    """学科题搜索词：概念词放前、去广告词，学科限定放后。
    实测 cn.bing 对「数学/化学+一堆限定词」污染严重，故尽量短、概念前置。"""
    s = extract_query(q)[:40] or q[:40]
    # 学科限定改为更贴百科嘅「_百度百科」风格，唔用会引新闻嘅「解法/图表」等
    subject_tail = {
        "chinese_teacher": " 释义",
        "math_teacher": "",
        "physics_teacher": " 定律",
        "chemistry_teacher": " 化学式",
        "history_teacher": " 历史",
    }.get(role_key, "")
    base = (s + subject_tail).strip()
    return base[:60]


def gather_subject(q, role_key):
    """学科题联网抓真实资料：cn.bing + 快懂百科，过【相关性闸门】先注入。
    抓到嘅资料若同问题核心词完全无关（典型：数学题抓到QQ邮箱）-> 当冇资料，
    宁可唔注入、畀老师用确定嘅教材基础常识仔细答，好过攞垃圾落去带偏。"""
    subject = _subject_baike_term(q, role_key) or _kb_subject(q)
    anchors = _subject_anchors(q, role_key)
    lines, seen = [], set()
    EN = re.compile(r"[A-Za-z]{3,}")
    AD = ("攻略", "知乎", "小红书", "试题", "试卷", "答案", "题库", "下载", "广告", "推广",
          "购买", "优惠", "招聘", "直播", "网课", "培训", "真题", "分数线", "招生",
          "邮箱", "登录", "官网", "下载", "模板", "验收", "打字", "豆包", "app", "APP")
    # 相关性闸门：一条资料至少要撞中一个核心锚点（2字片断）先至收
    def relevant(text):
        if not anchors:
            return False
        return any(a in text for a in anchors)

    # ★v1.36：百科 + Bing【并行】抓（原串行最坏 15s -> ≈8s），结果处理顺序完全唔变。
    from concurrent.futures import ThreadPoolExecutor
    sq = subject_search_query(q, role_key)
    do_baike = subject and role_key in (
        "chinese_teacher", "history_teacher", "physics_teacher", "chemistry_teacher", "math_teacher")

    def _baike_job():
        return _baike_definition(subject) if do_baike else (None, None)

    def _bing_job():
        try:
            return parse_rss(fetch(BING_WEB.format(q=urllib.parse.quote(sq)), timeout=7), limit=10)
        except Exception as e:
            log("SUBJ_BING_FAIL", repr(e)[:80])
            return []

    with ThreadPoolExecutor(max_workers=2) as ex:
        fbk = ex.submit(_baike_job)
        fbg = ex.submit(_bing_job)
        (desc, h1), got = fbk.result(), fbg.result()

    # 百科精确定义（最准，优先）——用概念短语，失败就静默
    if do_baike:
        # 歧义闸门：「唐朝」查到 h1「唐朝乐队」-> 弃用，唔好畀模型将朝代讲成乐队
        h1_ok = True
        if h1 and subject not in h1 and h1 not in subject:
            h1_ok = False
            log("SUBJ_BAIKE_AMBIG", role_key, repr(subject), "->", repr(h1))
        if desc and h1_ok:
            clean = EN.sub("", strip_html(desc))
            clean = re.sub(r"https?://\S+", "", clean).strip()[:260]
            if len(clean) >= 12 and (relevant(clean) or subject in clean):
                lines.insert(0, clean)
                log("SUBJ_BAIKE_HIT", role_key, repr(subject))

    # cn.bing 主源
    log("SUBJ_BING", role_key, sq, len(got))
    for t, d in got:
        t, d = strip_html(t), strip_html(d)
        if any(a in t for a in AD):
            continue
        text = d if (d and len(d) >= 12) else t
        if len(text) < 12:
            continue
        if not relevant(text):        # 相关性闸门：拦住「一元二次方程->设备验收单」呢类垃圾
            continue
        text = EN.sub("", text)
        text = re.sub(r"https?://\S+", "", text).strip()[:180]
        k = text[:22]
        if k in seen:
            continue
        seen.add(k)
        lines.append(text)

    if len(lines) < 1:
        log("SUBJ_EMPTY", role_key, repr(sq), "anchors=%s" % anchors)
        return None
    facts = "\n".join("· " + l for l in lines[:8])
    return (
        "【头等指令·先据真实资料答】学生问紧学科知识，啱啱联网查到下面呢批真实资料。"
        "【联网查到嘅真实资料】\n" + facts + "\n"
        "【点样用】①资料讲到嘅事实——定义、公式、单位、年代、人名、数据、出处、"
        "诗文原文、方程式——【一律照资料原样讲】，千祈唔好凭记忆改数字、改公式、改年份、改系数。\n"
        "②资料冇覆盖、但你同资料都肯定嘅基础常识，可以自然讲多少少令解释通顺；"
        "但凡要砌【具体数字、公式、年份、人名、原文】而资料冇讲过，就千祈唔好作，"
        "坦白讲「呢部分老师暂时搵唔到确切资料，唔敢乱讲」好过乱估。\n"
        "③照资料答，但唔好念 URL、来源名、编号或者「据资料显示」呢类字眼，"
        "就当係你本身识噉自然讲解。"
    )


def forward(payload, stream=False):
    """转发到硅基流动，返回 (status, body_bytes)。"""
    url = UPSTREAM_BASE + "/chat/completions"
    # 换大模型：网关层覆盖 model，大脑 roles.json 唔使改、容器唔使重启、token 保住。
    if MODEL_OVERRIDE:
        old = payload.get("model")
        payload = dict(payload)
        payload["model"] = MODEL_OVERRIDE
        if old != MODEL_OVERRIDE:
            log("MODEL_OVERRIDE %r -> %r" % (old, MODEL_OVERRIDE))
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + UPSTREAM_KEY,
    })
    try:
        r = urllib.request.urlopen(req, timeout=75, context=CTX)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 502, json.dumps({"error": {"message": str(e)}}).encode()


# ==================== v1.36 真流式透传（句子级缓冲，治「开口前干等」）====================
# 背景（2026-11-11 生产实测）：上游硅基流动对 stream=True 系【真流式】——
#   长文 559 字：首 token 2.06s、首句 3.43s、全文 26.77s、509 帧逐个 token 吐。
#   但旧 forward() 用 r.read() 把 509 帧全憋到 26.77s 先一次过回填，玩具（小智系，
#   实测一次长文切 7 个 mp3 逐句播）要等全文到齐先开始切句 TTS -> 主人干等 26 秒。
# 修法：句子级缓冲增量吐帧。逐帧读上游 delta.content -> 累积到句子缓冲 -> 凑够一句
#   （句末标点 or 兜底字数）就对该句跑【整段 polish + 正音 + 清符号】-> 即刻 yield 一帧畀
#   玩具。玩具收到第一句（约 3s）即刻 TTS 开播，其余句子边生成边补。总时长唔变，但
#   「开口前沉默」由 26s -> 约 3s。
# 质量铁证：_verify_stream_quality.py 用生产 11 条真实答复稿验证，粤语链路
#   【逐句 polish 拼接 == 整段 polish】逐字一致 11/11（0 差异），故保住 v1.27 质量。
# 适用边界：只畀【粤语角色】走；英语老师/诗词(E2E 探针 stream=False)保留旧整段路径——
#   polish_english 有跨 \n 收敛规则(406-407 行)，逐句切会丢空行，唔值得为速度冒险。
STREAM_ENABLED = os.getenv("GW_STREAMING", "1").strip().lower() not in ("0", "false", "no", "off")
STREAM_SENT_END = "。！？!?；;"
STREAM_FLUSH_CHARS = int(os.getenv("GW_STREAM_FLUSH_CHARS", "90"))  # 无句末标点时长句兜底切
STREAM_MIN_CHARS = int(os.getenv("GW_STREAM_MIN_CHARS", "8"))       # 句末太短（如 emoji/语气词）先攒住唔单独成帧


def _sse_frame(template, content):
    """由上游首帧 template 复制一个 OpenAI 兼容 SSE content 帧，只换 delta.content。"""
    d = json.loads(template)
    for ch in d.get("choices", []):
        ch["delta"] = {"content": content}
        ch.pop("finish_reason", None)
    d.pop("usage", None)
    return ("data: " + json.dumps(d, ensure_ascii=False) + "\n\n").encode("utf-8")


def _stream_sentences(text):
    """增量句子切分（确定性：只依赖 text 本身，故 mock 逐帧推进 == 全文一次切）。
    遇句末标点切（标点归前句）；太短（< MIN）唔单独成帧，继续攒落去；
    无标点超 FLUSH_CHARS 兜底切。返回 (可吐的句子列表, 残余 buf)。
    """
    out, buf = [], ""
    for ch in text:
        buf += ch
        at_end = ch in STREAM_SENT_END
        if at_end and len(buf) >= STREAM_MIN_CHARS:
            out.append(buf)
            buf = ""
        elif len(buf) >= STREAM_FLUSH_CHARS:
            out.append(buf)
            buf = ""
    return out, buf


def forward_stream(payload, sink):
    """真流式转发上游 SSE：句子级缓冲 polish 后逐句 yield 字节帧。
    sink 系 dict，函数会写回：
      sink['full_clean']  = 清理后播报全文（供落盘 ans 对照 / 诊断）
      sink['full_raw']    = polish 前原文全文（供落盘双轨 ans_cn：保留音标教学稿）
      sink['hits']        = polish 命中统计
      sink['frames_out']  = 吐出帧数
    任何异常：把剩余缓冲【原文】兜底吐出，绝唔令对话挂掉；返回的生成器自然结束。
    """
    payload = dict(payload)
    payload["stream"] = True
    if MODEL_OVERRIDE:
        payload["model"] = MODEL_OVERRIDE
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        UPSTREAM_BASE + "/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + UPSTREAM_KEY},
    )
    sink.setdefault("full_clean", []); sink.setdefault("full_raw", [])
    sink.setdefault("hits", {}); sink["frames_out"] = 0
    buf = ""            # 未够一句的原文缓冲（polish 前）
    template = None     # 首个 content 帧，用作复制帧骨架
    finished = False

    def polish_sentence(seg):
        # 与整段链路【完全同一顺序】：polish -> 正音 -> 清 TTS 符号
        nc, h = yue_polish.polish(seg, report=True)
        nc = tts_pron.fix(nc)
        # ★落盘双轨（v1.29）：ans_cn 落【clean 前】的完整稿（保留音标教学稿畀家长睇），
        #   播报 body 落【clean 后】（删音标/斜杠）。旧链路 ans_cn = extract(polish_response
        #   后 body) = fix(polish(全文))，故呢度必须存 nc(clean 前)，唔好存 seg(原文)。
        sink["full_raw"].append(nc)       # 落盘用：fix(polish) 后、clean 前（保留音标教学稿）
        nc = yue_polish.clean_tts_symbols(nc, report=False)
        sink["full_clean"].append(nc)     # 播报用：清理后（删音标/斜杠）
        for k, v in h.items():
            sink["hits"][k] = sink["hits"].get(k, 0) + v
        return nc

    try:
        r = urllib.request.urlopen(req, timeout=75, context=CTX)
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                # 收尾：清掉剩余缓冲，再透传 [DONE]
                if buf:
                    sink["frames_out"] += 1
                    yield _sse_frame(template or '{"choices":[{"delta":{}}]}', polish_sentence(buf))
                    buf = ""
                yield b"data: [DONE]\n\n"
                finished = True
                break
            try:
                d = json.loads(data)
            except Exception:
                continue
            # 非正文控制帧（finish_reason / usage）：先清空缓冲再放行，保证顺序
            piece = ""
            for ch in d.get("choices", []):
                delta = ch.get("delta") or {}
                c = delta.get("content")
                if isinstance(c, str) and c:
                    piece += c
                if ch.get("finish_reason"):
                    piece = None   # 标记控制帧
                    break
            if piece is None or (not piece and d.get("usage")):
                if buf:
                    sink["frames_out"] += 1
                    yield _sse_frame(template or '{"choices":[{"delta":{}}]}', polish_sentence(buf))
                    buf = ""
                yield ("data: " + json.dumps(d, ensure_ascii=False) + "\n\n").encode("utf-8")
                continue
            if not piece:
                continue
            if template is None:
                template = data
            buf += piece
            sents, buf = _stream_sentences(buf)
            for s in sents:
                sink["frames_out"] += 1
                yield _sse_frame(template, polish_sentence(s))
        # urlopen 迭代自然结束（无 [DONE]）也要清尾
        if not finished and buf:
            sink["frames_out"] += 1
            yield _sse_frame(template or '{"choices":[{"delta":{}}]}', polish_sentence(buf))
            yield b"data: [DONE]\n\n"
    except Exception as e:
        log("STREAM_FAIL 原样兜底", repr(e)[:100])
        if buf:
            sink["frames_out"] += 1
            yield _sse_frame(template or '{"choices":[{"delta":{}}]}', buf)
        yield b"data: [DONE]\n\n"


def english_ref(ref):
    """v1.24：英语老师显式联网时，剥掉 gather_knowledge 嘅粤语指令头，
    只保留事实条目（· 开头行），用【普通话】重新包装，防止资料头把老师带跑成粤语/自称阿晴。"""
    if not ref:
        return ref
    facts = []
    for line in ref.splitlines():
        s = line.strip()
        # 净系要事实条目（· / - 开头），去掉所有【头等指令】【点样用】【语言铁律】等粤语段落
        if s.startswith(("· ", "- ", "• ")) and len(s) > 3:
            facts.append(s.lstrip("·-• ").strip())
    if not facts:
        # 冇到「· 」格式就保守返回原文（交由后处理兜底），唔好令联网资料凭空消失
        log("ENGLISH_REF 无事实条目，原样返回")
        return ref
    body = "\n".join("· " + f[:160] for f in facts[:8])
    return ("【联网查到的真实资料（供你参考）】\n" + body + "\n"
            "【怎么用】这些是刚查到的客观资料。请照着讲、不要凭记忆改拼写或释义；"
            "但【全程仍用标准普通话 + 中英双语】讲解，保留关键英文词句与例句并附中文翻译。"
            "不要提到「资料」「来源」「据查到」这类字眼，就当是自己懂，自然讲出来。\n"
            "【专名/地标名/数字一字不改·最高铁律】资料里的地名、地标名、景点名、建筑名、"
            "人名、机构名、年份、高度、数字，必须【逐字照资料原样】讲，绝不许凭记忆改写、"
            "简写、换个叫法或编一个别名：实测过把「东方明珠塔」讲成「上海塔」、把"
            "「468米」改数字，都属严重错误。地标名一律用资料里的完整正式名称，"
            "不确定就照抄资料、或只讲资料明确提到的部分，绝不自己换名或加料。")


def polish_response(body, stream=False, poem=False, skip=False):
    """对上游返回的文本做粤语化后处理；只动 choices[].message/delta.content，
    请求侧（人设 prompt、注入资料）一概不碰。返回 (新body, 命中统计dict)。
    poem=True（朗读诗词/古文）：传给 yue_polish 跳过口语化替换，逐字照原文读。
    skip=True（英语老师 v1.24）：豁免粤语化/清英文（保住中英双语），
    但走 polish_english 轻量清洗——只清 emoji/Markdown/元话语/繁体/串味粤字，唔碰正文。
    v1.28 起：英文路径亦接 tts_pron 正音——fixer 只替换中文易误读字（单->單/会->會/
    适->適/区->區/听日->汀日），唔碰 ASCII 英文/音标/数字，英文正文同断句零影响；
    修 4号键讲「单词」被念成「善」(sin6)。任何解析失败都原样返回，绝不令对话挂掉。"""
    if skip:
        log("POLISH_ENGLISH english_teacher（中英双语轻量清洗+正音，唔粤语化/唔清英文）")
        hits = {}
        try:
            if not stream:
                d = json.loads(body.decode("utf-8"))
                for ch in d.get("choices", []):
                    msg = ch.get("message") or {}
                    c = msg.get("content")
                    if isinstance(c, str) and c:
                        nc, h = yue_polish.polish_english(c, report=True)
                        # ★v1.28：英文路径接正音（单->單 等），喺 polish_english 繁->简之后跑，
                        #   避免「單」被打回简体；fixer 只改中文字、唔碰英文/音标/数字。
                        nc = tts_pron.fix(nc)
                        msg["content"] = nc
                        for k, v in h.items():
                            hits[k] = hits.get(k, 0) + v
                return json.dumps(d, ensure_ascii=False).encode("utf-8"), hits
            else:
                # ★v1.27 修英文粘词/断句丢失：呢个 body 系 forward() r.read() 读全嘅完整
                #   SSE，旧实现逐 delta 调 polish_english(c)，其末尾 .strip()/空格压缩会
                #   食掉每个 token 嘅前导空格（英文靠空格分词）-> Iamplanningto 粘成渣、\n
                #   断句飞晒。改为整段收集 -> 整段清洗一次 -> 按原帧长度回填，concat 恒等
                #   整段清洗结果，帧数/结构/时序一律唔变，大脑端零感知。
                #   （真正流式唔逐 token 处理：上游本来就一次过读全，冇实时性损失。）
                log("POLISH_ENGLISH_SSE 整段清洗回填（修流式英文粘词 v1.27 + 正音 v1.28）")
                return yue_polish.polish_english_sse(body, fixer=tts_pron.fix)
        except Exception as e:
            log("POLISH_ENGLISH_FAIL 原样透传", repr(e)[:80])
            return body, {}
    if not yue_polish.ENABLED:
        return body, {}
    hits = {}
    try:
        if not stream:
            d = json.loads(body.decode("utf-8"))
            for ch in d.get("choices", []):
                msg = ch.get("message") or {}
                c = msg.get("content")
                if isinstance(c, str) and c:
                    nc, h = yue_polish.polish(c, report=True, poem=poem)
                    nc = tts_pron.fix(nc)   # 正音在 polish 之后：避免「區」被繁转简打回「区」
                    msg["content"] = nc
                    for k, v in h.items():
                        hits[k] = hits.get(k, 0) + v
            return json.dumps(d, ensure_ascii=False).encode("utf-8"), hits
        else:
            # ★v1.27 修粤语角色流式漏粤语化：旧实现逐 delta 调 polish(c)，词级替换
            #   （我们->我哋/现在->而家/听日->汀日）喺单字 token 上匹配唔到，跨 token 英文
            #   乱码亦清唔净。改为整段 polish + 正音一次，按原帧回填（同英语老师共用骨架），
            #   令流式行为 = 非流式，帧数/结构/时序唔变，大脑端零感知。
            log("POLISH_CANTONESE_SSE 整段粤语化+正音回填（修流式漏粤语化，v1.27）")
            return yue_polish.polish_cantonese_sse(body, poem=poem, fixer=tts_pron.fix)
    except Exception as e:
        log("POLISH_FAIL 原样透传", repr(e)[:80])
        return body, {}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/health", "/"):
            self._json(200, {"ok": True, "model": MODEL_OVERRIDE or UPSTREAM_MODEL,
                             "upstream": UPSTREAM_BASE, "ts": time.time(),
                             "conv_log": CONV_LOG_ENABLED, "conv_dir": CONVERSATIONS_DIR})
        elif path in ("/logs", "/chat", "/chat/"):
            if not token_ok(self):
                self._json(403, {"error": "forbidden: bad view token"}); return
            if path == "/logs":
                try:
                    qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                    day = qs.get("day", [""])[0]
                    role = qs.get("role", [""])[0]
                    kw = qs.get("kw", [""])[0]
                    try:
                        # v1.31：默认上限提到 5000（30 天对话可能数千条，唔好再净系畀睇 200 条）
                        limit = max(1, min(5000, int(qs.get("limit", ["1000"])[0])))
                    except Exception:
                        limit = 1000
                    rows = conv_read(day, role, kw, limit)
                    self._json(200, {"ok": True, "dates": conv_dates(),
                                     "count": len(rows), "items": rows,
                                     "keep_days": CONV_KEEP_DAYS,
                                     "total_days": len(conv_dates())})
                except Exception as e:
                    self._json(500, {"error": str(e)})
            else:
                b = render_chat_page().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    self.wfile.write(b)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": "not found"}); return
        t0 = time.time()   # v1.23 对话记录：计耗时
        try:
            n = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception as e:
            self._json(400, {"error": {"message": "bad json: %s" % e}}); return

        msgs = payload.get("messages", [])
        q = normalize_roles_json(msgs)
        stream = bool(payload.get("stream"))
        role_key = detect_role(msgs)
        # ★v1.25 英文意图自动路由：主人习惯 1 号闲聊键通吃，用英文问会被粤语化清英文，
        #   TTS 冇英文可念（「例句冇发音」）。闲聊键上检测到明确英文意图时，当英语老师
        #   处理——下游 v1.24 全链路（普通话 system / 豁免清英文 / 唔乱联网）自动复用。
        #   role_key 保持真实按键（aqing_chat），只额外用一个标志位控制落盘显示。
        auto_en = is_english_auto(q, role_key)
        is_english = (role_key == "english_teacher") or auto_en
        if auto_en and role_key != "english_teacher":
            log("EN_AUTO_ROUTE q=%r role=%r -> 英语老师链路（保住英文例句/TTS发音）" %
                (q[:40], role_key or "普通阿晴"))
        is_teacher = role_key in TEACHER_MARKERS
        log("REQ q=%r stream=%s role=%r" % (q[:40], stream, role_key or "普通阿晴"))

        # === v1.47：1 号键 = 播电台(停机)/换台(播住)；对话键 = 开始暂停 =====
        # 唔再纯靠角色标记：真机 1 号键有时显示为「普通阿晴」。
        # 句入面有「电台」一律开播；长文本 / 播报稿探针放行，避免拦低早晚报。
        # 想临时停用两个键：容器环境变量 RADIO_BTN=0（唔使改代码）。
        _q = q or ""
        is_script = any(w in _q for w in RADIO_SCRIPT_WORDS)
        is_talk_key = (role_key == "" and len(_q) <= 60 and not is_script)
        if RADIO_BTN_ENABLED and (
                (role_key == "aqing_chat") or (RADIO_TALK_ENABLED and is_talk_key)):
            try:
                _kind, reply = radio_action(_q, role_key == "aqing_chat")
            except Exception as e:
                log("RADIO_BTN_FAIL %r" % e)
                reply = "收到"
            radio_reply(self, reply, stream)
            return
        # 诊断开关：DUMP_MSG=1 时打印 messages 角色序列（唔打印内容/key），用于核对真实链路结构
        if os.getenv("DUMP_MSG"):
            log("DUMP_MSG roles=%s n=%d" %
                ([m.get("role") for m in msgs], len(msgs or [])))

        want_weather = is_weather_intent(q)
        want_gz = is_gz_news_intent(q)
        want_news = is_news_intent(q)
        want_search = is_search_intent(q)
        want_poem = is_poem_intent(q)
        # ★v1.26 主人铁律：任何角色讲到【客观资料/专名/地标/数据】都要先联网核查。
        #   fact_needed 补踢 is_knowledge_intent 漏判嘅句式（「用英文介绍上海嘅标志性景点」
        #   旧版 kb=False -> 唔搜 -> 30B 凭记忆把东方明珠塔讲成上海塔）。
        fact_needed = is_fact_check_needed(q)
        if fact_needed and not is_knowledge_intent(q):
            log("FACT_CHECK intent（知识意图漏判兜底）q=%r" % q[:40])
        # 知识题：只有喺无更高优先级嘅天气/新闻/广州新闻意图先至搜（避免重复抓料）
        want_kb = (not want_weather and not want_gz and not want_news and
                   (is_knowledge_intent(q) or fact_needed))
        # 学科老师：学科题强制联网核实（连泛问「点解/为什么」都搜），唔好靠模型记忆乱作。
        #   英语老师排除：佢行通用知识链路（english_ref 普通话包装），唔行学科抓料。
        want_subject = (is_teacher and role_key != "english_teacher" and
                        is_subject_question(q, role_key))
        if want_subject:
            want_kb = False   # 走学科专用抓料，唔好重复用通用知识链路
            log("SUBJECT intent role=%s q=%r" % (role_key, q[:40]))

        # ★v1.24 英语老师专项：
        #  ①【整段替换 system】大脑缓存住旧粤语 prompt，网关直接换成纯普通话版，
        #     不重启大脑、不动 token 即时生效（ENGLISH_SYSTEM 启动时加载）。
        #  ②【v1.26 改：资料题必须联网】主人新铁律「每个角色讲嘅资料都要联网核查」，
        #     撤销 v1.24「默认全关」。英语老师问到【客观资料/专名/地标/数据】（fact_needed）
        #     或学生显式讲「上网查/联网」-> 放行 want_kb，走 gather_knowledge -> english_ref
        #     普通话包装（已内置「专名/地标名/数字一字不改」铁律，唔会带跑粤语）。
        #     纯语言操练（造句/语法/翻译/读音，fact_needed=False）照旧唔搜，保速度、唔带偏。
        _ENGLISH_EXPLICIT_NET = False   # 默认；is_english 分支会按问题重设
        _ENGLISH_FACT_NET = False       # v1.26：资料核查需要（含专名/地标/数据）
        if is_english:
            msgs = list(msgs)
            _sys_i = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)
            if _sys_i is not None:
                msgs[_sys_i] = dict(msgs[_sys_i])
                msgs[_sys_i]["content"] = ENGLISH_SYSTEM
                payload["messages"] = msgs
            log("ENGLISH_SYS_OVERRIDE applied（src=%s）" % ENGLISH_SYSTEM_SRC)
            # 显式联网词：学生明讲「上网查/搜索/联网」-> 放行联网。
            _ENGLISH_EXPLICIT_NET = any(
                w in q for w in ("上网", "联网", "搜索", "搜下", "查下", "查一下", "帮我查"))
            # ★v1.26：客观资料/专名/地标/数据题 -> 都要联网核查（english_ref 普通话包装）
            _ENGLISH_FACT_NET = fact_needed
            if fact_needed:
                log("ENGLISH FACT-NET q=%r -> 放行 want_kb 核实专名/资料" % q[:40])
        # 知识介绍类自动当长文：用户问「介绍庐山」要 800~1000 字，唔好净系回几十字
        want_long = is_long_intent(q) or is_intro_place(q)
        if want_long:
            log("LONG auto q=%r（is_long=%s intro=%s）" %
                (q[:30], is_long_intent(q), is_intro_place(q)))

        # ★v1.26 英语老师联网策略（撤销 v1.24「默认全关」，改「资料题必查」）：
        #  · 纯语言操练（造句/语法/翻译/读音，fact_needed=False）-> 照旧全关，靠 30B 答，保速度。
        #  · 客观资料/专名/地标/数据题（fact_needed=True）-> 放行 want_kb 走 english_ref
        #    普通话包装（内置专名一字不改铁律），杜绝「东方明珠塔讲成上海塔」呢类记忆乱作。
        #  · 显式「上网查/联网」-> 照旧放行 want_search。
        if is_english and not (_ENGLISH_EXPLICIT_NET or _ENGLISH_FACT_NET):
            log("ENGLISH no-net: 纯语言操练，压掉联网/长文（无资料/无显式联网词）")
            want_weather = want_gz = want_news = want_search = False
            want_kb = want_subject = want_long = want_poem = False
        elif is_english and _ENGLISH_FACT_NET and not _ENGLISH_EXPLICIT_NET:
            # 资料核查题：只放 want_kb，其它干扰意图照压（英语老师唔讲天气/新闻/诗词）
            log("ENGLISH FACT-NET 生效：保 want_kb，压 weather/gz/news/search/poem")
            want_weather = want_gz = want_news = want_search = False
            want_subject = want_poem = False
            want_kb = True

        # --- 联网分流：天气走实时数值API，广州本地新闻走本地官方三源，其余新闻走RSS+搜索 ---
        # 读诗/古文系照原文朗读，唔使联网；且要确保阿晴唔会攞新闻资料去「改写」诗句。
        if want_poem:
            want_weather = want_gz = want_news = want_search = want_kb = False
            want_long = False
            log("POEM intent -> q=%r（口语化后处理豁免，逐字照原文）" % q[:40])
        refs = []
        if want_weather:
            log("WEATHER intent -> q=%r" % q[:40])
            ref = gather_weather(extract_query(q), q)
            if not ref:                       # 天气 API 失败 -> 退而求其次搜网页
                log("WEATHER_FALLBACK_SEARCH")
                ref = gather_news(extract_query(q))
            if ref:
                refs.append(ref)
        if want_gz:
            log("GZ_NEWS intent -> q=%r" % q[:40])
            ref = gather_gz_news(extract_query(q))
            if not ref:                       # 本地源失败 -> 回退通用新闻，保证有嘢讲
                log("GZ_NEWS_FALLBACK")
                ref = gather_news(extract_query(q))
            if ref:
                refs.append(ref)
        elif want_news or (want_search and not want_weather):
            qy = extract_query(q)
            log("SEARCH intent -> query=%r" % qy)
            ref = gather_news(qy)
            if ref:
                refs.append(ref)

        if want_kb and not refs:
            log("KNOWLEDGE intent -> q=%r" % q[:40])
            ref = gather_knowledge(extract_query(q), q)
            if ref:
                refs.append(ref)
            elif is_history_fact(q):
                # ★v1.35 史实题联网抓唔到 -> 唔好裸奔透传畀 30B 凭记忆砌。
                # 【反粉红大象】只落【正向】行为指令（讲有把握嘅、冇把握就坦白），
                # 千祈唔好喺 prompt 度写出任何具体错答案/错归属性名，否则会反向激活佢。
                msgs = list(msgs)
                last_user_i = max((i for i, m in enumerate(msgs) if m.get("role") == "user"),
                                  default=len(msgs))
                guard = (
                    "\n（【史实答题铁律·呢条系历史/人物/出处题，但联网暂时搵唔到对口资料】"
                    "你只可以讲你同权威记载都一致确认嘅事实；凡系【边个朝代、边个人、出自边本书、"
                    "某种思想或者名言归属边个】呢类要核实嘅嘢，冇十足把握就坦白讲「呢部分我暂时"
                    "搵唔到确切资料，唔敢乱讲」，千祈唔好凭印象将一个时代嘅嘢安去另一个时代。除咗"
                    "要核实嘅归属之外，你确定嘅基础常识可以照常自然讲，唔好令段嘢变生硬。）")
                msgs[last_user_i] = dict(msgs[last_user_i])
                uc = msgs[last_user_i].get("content", "")
                msgs[last_user_i]["content"] = (uc if isinstance(uc, str) else str(uc)) + guard
                payload["messages"] = msgs
                log("HISTORY_NO_REF -> 注入正向史实兜底（联网抓唔到，唔好凭记忆砌）")

        # 学科老师：抓到资料后，英语老师要【唔清英文】嘅版本（普通资料会剔英文，唔适用）
        if want_subject and not refs:
            ref = gather_subject(q, role_key)
            if ref:
                refs.append(ref)
                log("SUBJECT_INJECT role=%s ref_len=%d" % (role_key, len(ref)))
            else:
                # 抓唔到资料 -> 按学科分层兜底，唔好一刀切叫老师「唔知」：
                #  · 历史/语文（事实会变、有出处）：严格坦白，唔好凭记忆砌年份出处原文。
                #  · 数学/物理/化学（稳定教材知识）：可以用你确定嘅基础原理/公式仔细推导，
                #    但必须分步验算、唔确定嘅具体数字/系数就坦白，千祈唔好硬砌答案。
                msgs = list(msgs)
                last_user_i = max((i for i, m in enumerate(msgs) if m.get("role") == "user"),
                                  default=len(msgs))
                if role_key == "history_teacher":
                    unknown = ("\n（呢条问题联网暂时搵唔到确切资料：涉及年份、朝代、人名、"
                               "事件经过同先后顺序，唔好凭记忆乱讲；"
                               "唔确定就坦白讲「呢部分老师暂时搵唔到确切资料」，唔好砌。）")
                elif role_key == "chinese_teacher":
                    unknown = ("\n（呢条问题联网暂时搵唔到对口资料：作者、出处、文学常识呢类"
                               "稳定知识，你确定就可以照实讲（例如作者同篇名）；"
                               "但【要逐字引用嘅诗文原文】唔确定就唔好乱背，"
                               "坦白讲「原文老师唔敢肯定，唔想背错畀你」，也唔好凭印象改字。）")
                elif role_key == "english_teacher":
                    unknown = ("\n（No reliable source was found online for this. "
                               "请用标准普通话讲清楚你确定的基础文法/词义，关键英文保留并附中文翻译；"
                               "不确定的释义或拼法就坦白说，不要编造。）")
                else:
                    unknown = ("\n（呢条问题联网暂时搵唔到对口资料：数学/物理/化学系稳定嘅教材知识，"
                               "你可以用你确定嘅基础原理同公式【分步推导、逐步验算】嚟答，"
                               "讲清楚每一步点解；但唔确定嘅具体数字、系数、单位或者实验数据，"
                               "就坦白讲「呢个数值老师唔敢确定」，千祈唔好硬砌一个错答案。）")
                msgs[last_user_i] = dict(msgs[last_user_i])
                uc = msgs[last_user_i].get("content", "")
                msgs[last_user_i]["content"] = (uc if isinstance(uc, str) else str(uc)) + unknown
                payload["messages"] = msgs
                log("SUBJECT_NO_REF role=%s -> 注入分层兜底" % role_key)

        if refs:
            ref = "\n\n".join(refs)
            # ★v1.24：英语老师联网时，资料头系粤语指令（会用阿晴身份/粤语带跑老师），
            # 剥成纯事实 + 普通话包装。默认英语老师唔联网，只有显式「上网查」先至行到呢度。
            if is_english:
                _raw_len = len(ref)
                ref = english_ref(ref)
                log("ENGLISH_REF 重写 ref %d -> %d（剥粤语指令头）" % (_raw_len, len(ref)))
            msgs = list(msgs)
            # 插到「最后一条 user 之前」作为独立 user 消息，紧邻问题（9B 贴近生成端遵守率高）。
            last_user_i = max((i for i, m in enumerate(msgs) if m.get("role") == "user"),
                              default=len(msgs))
            msgs.insert(last_user_i, {"role": "user", "content": ref})
            if last_user_i + 1 < len(msgs):
                kind = ("今日实时天气同广州本地新闻" if (want_weather and want_gz)
                        else ("广州本地官方媒体新闻" if want_gz
                              else ("今日实时天气同真实新闻资料" if (want_weather and want_news)
                                    else ("今日实时天气数据" if want_weather
                                          else ("联网查到嘅真实知识资料" if want_kb
                                                else ("联网查到嘅真实学科资料" if want_subject else "今日真实新闻"))))))
                msgs[last_user_i + 1] = dict(msgs[last_user_i + 1])
                uc = msgs[last_user_i + 1].get("content", "")
                # 知识长文：额外要求讲够字数、按资料有条理分段展开（治「净系讲 600 字就收线」）
                len_note = ("呢一答要讲够 800 至 1000 字，围绕资料分几个段落有条理噉展开，"
                            "唔好未讲完就收线。") if (want_long and want_kb) else ""
                if is_english:
                    _kind_m = ("联网查到的真实知识资料" if want_kb
                               else ("联网查到的真实学科资料" if want_subject else "真实资讯"))
                    tail = ("\n（请用标准普通话解释清楚，并根据上面刚查到的【%s】作答；"
                            "关键英文词句、例句保留英文并附中文翻译。具体拼写、"
                            "文法规则不得凭记忆改动，没有把握就坦白说。"
                            "【专名/地标/数字照资料逐字讲】地名、地标名、景点名、年份、"
                            "高度、数字一律照资料原样，绝不许换成别的叫法或自己编，"
                            "例如不要把「东方明珠塔」说成「上海塔」。全程普通话，"
                            "不要提「资料」「来源」这类字眼。%s）"
                            % (_kind_m, ("讲清楚即止，不超 1000 字。" if want_long else "")))
                else:
                    tail = ("\n（记得：一定要根据上面啱啱联网查到嘅【%s】嚟答，数字照抄、唔好讲冇、唔好凭记忆乱作。%s）"
                            % (kind, len_note))
                msgs[last_user_i + 1]["content"] = (
                    (uc if isinstance(uc, str) else str(uc)) + tail
                )
            payload["messages"] = msgs
            log("INJECT ref_len=%d at user_idx=%d" % (len(ref), last_user_i))

        # --- 长文：覆盖 max_tokens，并软化人设里的字数上限 ---
        if want_long:
            payload["max_tokens"] = max(int(payload.get("max_tokens") or 0), LONG_MAX_TOKENS)
            msgs = list(payload["messages"])
            sys_i = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)
            if is_english:
                # 英语老师：普通话、允许并保留英文（中英双语），唔落「唔准冒英文」铁律
                addon = ("\n\n【用户想听详细版】这次讲详细一点，约 800 至 1000 字，"
                         "用普通话有条理地展开，讲清楚即止。全程保持标准普通话；"
                         "关键字词、英文例句、完整英文句子照原样保留并附中文翻译，"
                         "不要因为讲得长就丢掉英文原句。回答绝对不超过 1000 字。")
            else:
                addon = ("\n\n【用户想听详细版】呢次讲长啲，大约 800 至 1000 字，"
                         "有条理噉展开，唔好咁快收线；但依然全程简体中文粤语口语、短句、唔好书面长句。"
                         "越讲长越要守语言铁律：唔准冒英文字母、外语或乱码，专有名词用中文译名，"
                         "唔确定就讲中文意思，千祈唔好乱砌英文。"
                         "【保持讲解员身份】你今次净系一个介绍紧呢个对象嘅讲解员，全程围绕佢本身展开，"
                         "唔好讲你自己系边度人、唔好讲西关、广州、老广、广东，亦唔好攞你熟落嘅本地"
                         "景点或者本地生活嚟做比较同举例——就好似你净系介绍紧眼前呢样嘢噉。（呢条净系"
                         "管今次呢一答嘅内容，唔影响你平时嘅人设同街坊语气。）")
            if sys_i is not None:
                msgs[sys_i] = dict(msgs[sys_i])
                msgs[sys_i]["content"] = str(msgs[sys_i].get("content", "")) + addon
            else:
                msgs = [{"role": "system", "content": addon.strip()}] + msgs
            payload["messages"] = msgs
            log("LONG -> max_tokens=%d" % payload["max_tokens"])

        # --- 全局字数硬上限（v1.22）：全部角色回答唔好超过 HARD_MAX_CHARS 字 ---
        # 双保险：①max_tokens 封顶（长文想用 1600 都要压返落嚟）；②system 尾钉字数铁律。
        # 英语老师用普通话措辞，其余用粤语；唔覆盖人设，只加一条最高优先级限制。
        if HARD_MAX_TOKENS > 0:
            want = int(payload.get("max_tokens") or 0)
            if want > HARD_MAX_TOKENS:
                payload["max_tokens"] = HARD_MAX_TOKENS
                log("HARD_MAX_TOKENS 压顶 %d -> %d" % (want, HARD_MAX_TOKENS))
        msgs = list(payload.get("messages") or [])
        if is_english:
            cap_addon = ("\n\n【最高优先级·字数上限】无论学生问什么，你的回答【绝对不要超过 "
                         "%d 字】；解释清楚就停，不要为了凑字数重复啰嗦。全程普通话。"
                         % HARD_MAX_CHARS)
        else:
            cap_addon = ("\n\n【最高优先级·字数上限】无论答乜，回答【绝对唔好超过 %d 字】；"
                         "讲清楚就收，唔好为咗长而长、唔好重复啰嗦。" % HARD_MAX_CHARS)
        sys_i = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)
        if sys_i is not None:
            msgs[sys_i] = dict(msgs[sys_i])
            cur = str(msgs[sys_i].get("content", ""))
            if "最高优先级·字数上限" not in cur:   # 防重复注入
                msgs[sys_i]["content"] = cur + cap_addon
        else:
            msgs = [{"role": "system", "content": cap_addon.strip()}] + msgs
        payload["messages"] = msgs

        # --- v1.39 禁填充口头禅（治本，2026-11-12 主人「取消自己加嘅口头禅」）---
        # 背景：落盘实测「你知唔知」一日冒 18 次左右——模型喺人设「口语化/
        # 娓娓道来」同老师 prompt「讲完轻轻追问一句，睇下学生明唔明」引导下，
        # 自己加咗大量无信息量嘅填充开场、客套追问。治本落生成端：网关层向
        # system 尾钉一条【最高优先级】约束，令模型根本唔好生成呢啲口头禅。
        # 只加一条 system addon，唔覆盖人设、唔改大脑 roles.json、唔重启大脑。
        # 英语老师用普通话措辞；其余 6 个粤语角色用粤语。保留防重复注入标记。
        if not is_english:
            filler_addon = (
                "\n\n【最高优先级·讲话唔好加填充口头禅】直接讲内容，唔好加任何无意思"
                "嘅开场白同客套追问，尤其【千祈唔好】讲：句首「你知唔知，」「你知唔知啊，」"
                "「唔好意思讲，」「咁讲啦，」「其实呢，」；开场「好，我同你讲」「好，"
                "我继续同你讲」「唔好急，慢慢讲」「一句一句讲清楚」；句尾「你明唔明？」"
                "「明唔明呀？」「你知唔知？」「系咪先？」呢类追问一律唔好讲。开头第一句"
                "就直接入正题答中问题，唔好铺垫；中间唔好插「你知唔知」做转场；讲完就收，"
                "唔好加「你明唔明」之类收尾互动。（呢条净系管讲话方式，知识内容、步骤、"
                "例子一字都唔删唔改。）"
            )
        else:
            filler_addon = (
                "\n\n【最高优先级·不要加填充口头禅】直接讲内容，不要加任何无意义的开场白"
                "和客套追问，尤其【不要】说：句首「你知道吗，」「其实呢，」；开场「好，"
                "我给你讲」「别急，慢慢讲」；句尾「你明白吗？」「懂了吗？」「是不是？」"
                "这类追问一律不要说。第一句就直接切入正题，中间不要插「你知道吗」做过渡，"
                "讲完就停，不要加互动收尾。（这条只管说话方式，知识内容、步骤、例句一字不改。）"
            )
        msgs = list(payload.get("messages") or [])
        sys_i = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)
        if sys_i is not None:
            msgs[sys_i] = dict(msgs[sys_i])
            cur = str(msgs[sys_i].get("content", ""))
            if "最高优先级·讲话唔好加填充口头禅" not in cur and "最高优先级·不要加填充口头禅" not in cur:
                msgs[sys_i]["content"] = cur + filler_addon
        else:
            msgs = [{"role": "system", "content": filler_addon.strip()}] + msgs
        payload["messages"] = msgs
        log("V1.39_FILLER_BAN injected (is_english=%s)" % is_english)

        # --- v1.41 禁复述核查/资料指令（治本，2026-11-12 主人「资料讲得清清楚楚
        #     唔好乱改 呢句话好奇怪，去掉这种自己加的语句」）---
        # 背景：落盘实测 30B 写长文时会把【约束自己】的核查指令当正文复述，
        #   如「呢个時间点，资料讲得清清楚楚，唔好乱改。」「成件事一啲都唔好乱讲，
        #   年份同地名要照旧，唔好改。」「呢啲资料冇讲…我唔好乱估。」——全部系模型
        #   自我叮嘱/评价资料，零知识，唔系网关替换表造、唔系内容错。
        # 治本落生成端：加一条【最高优先级】system 尾钉，令模型根本唔好生成
        #   呢类「讲规则/自我叮嘱」嘅元话语；只加一条 addon，唔覆盖人设、
        #   唔改大脑 roles.json、唔重启大脑、唔郁已验证嘅资料核查逻辑。
        # ★关键边界：只禁【约束自己点样用资料】嘅自我叮嘱；对小朋友讲安全/
        #   规矩（「过马路唔好乱跑」「唔好乱爬」）系 legit 教育内容，照常可讲。
        if not is_english:
            meta_addon = (
                "\n\n【最高优先级·规则系畀你遵守，唔系讲出口】你答复嘅内容净系讲知识"
                "本身，【千祈唔好】将以下呢类【约束你自己】嘅内部规则、自我叮嘱或者"
                "对资料嘅评价，当正文讲出嚟：评价资料「讲得清清楚楚」「写得好清楚」；"
                "自我叮嘱「唔好乱改」「唔好乱打」「唔好乱讲」「唔好乱估」「唔敢乱作」"
                "「年份地名要照旧」；或者讲「据资料显示」「资料冇讲…我唔敢讲」呢类"
                "元话语。呢啲全部只系管住你唔好乱作，唔系答案内容，直接讲事实就得，"
                "讲完就收。（重要例外：如果系教小朋友安全、规矩、做人道理，例如"
                "「过马路唔好乱跑」「唔好乱爬」「做功课唔好乱写」，呢类对听者嘅"
                "正当叮嘱照常讲，唔受呢条限制。史实、数字、人名、步骤、例句一字"
                "都唔删唔改。）"
            )
        else:
            meta_addon = (
                "\n\n【最高优先级·rules are for you to follow, not to say aloud】"
                "Your answer must contain only the knowledge itself. 【Do NOT】say aloud "
                "any of these internal self-reminders or comments about the source: praising "
                "the material (the sources make it very clear), reminding yourself "
                "(don't change it, don't guess, I won't make things up), or "
                "meta phrases like according to the sources / the sources don't say. "
                "These only constrain you from fabricating; they are not answer content. Just "
                "state the facts and stop. (Important exception: legitimate advice to a child "
                "about safety or rules, e.g. don't run into the road, is fine. Do not "
                "remove or change any facts, numbers, names, steps, or examples.)"
            )
        msgs = list(payload.get("messages") or [])
        sys_i = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)
        if sys_i is not None:
            msgs[sys_i] = dict(msgs[sys_i])
            cur = str(msgs[sys_i].get("content", ""))
            if "最高优先级·规则唔好讲出口" not in cur and "rules are for you to follow" not in cur:
                msgs[sys_i]["content"] = cur + meta_addon
        else:
            msgs = [{"role": "system", "content": meta_addon.strip()}] + msgs
        payload["messages"] = msgs
        log("V1.41_META_BAN injected (is_english=%s)" % is_english)

        # --- 诗词/古文朗读：正文逐字照原文，唔好将书面字改做口语字 ---
        # 阿晴人设要求「纯粤语口语」，会令 9B 把诗句「是/然而」写成「係/不过」；
        # 呢度用更高优先级硬指令覆盖：引用嘅诗句/原文一字唔郁，串场讲解先至用阿晴口语。
        if want_poem:
            msgs = list(payload["messages"])
            poem_addon = (
                "\n\n【用户要听朗读/原文，最高优先级】如果你要引用或读出诗句、古文、"
                "名人名言、歌词等【原文内容】，必须【逐字照原文一字唔改】噉输出："
                "尤其「是」就写「是」（千祈唔好写做「係」或「系」）、「然而」唔好写「不过」、"
                "「让」唔好写「畀」、「不是」唔好写「唔系」。原文里面嘅标点同用字全部保留。"
                "只有喺原文【之外】你同街坊讲嘅串场、解释、问候，先至用返阿晴嘅地道粤语口语。"
                "唔好自行翻译、改写或者将诗句改成白话。"
            )
            sys_i = next((i for i, m in enumerate(msgs) if m.get("role") == "system"), None)
            if sys_i is not None:
                msgs[sys_i] = dict(msgs[sys_i])
                msgs[sys_i]["content"] = str(msgs[sys_i].get("content", "")) + poem_addon
            else:
                msgs = [{"role": "system", "content": poem_addon.strip()}] + msgs
            payload["messages"] = msgs
            log("POEM -> 注入逐字照原文硬指令")

        # --- 话题锚定（防「问庐山讲成广州」）：无联网资料、非诗时，
        #     若当前系介绍非本地地点且历史讲过广州景点 -> 物理隔离旧轮次 + 正向专注尾注。
        #     必须放喺所有 refs 注入之后：有资料注入就唔隔离，避免删走天气/新闻资料消息。
        #     长文(详细讲下X)同样要隔离——实测「详细介绍下庐山」唔隔离会 3/6 蹦广州；
        #     长文 addon 系加喺 system，apply_place_anchor 保留全部 system，故两者兼容。
        if not refs and not want_poem:
            if is_place_anchor_needed(q, payload.get("messages") or []):
                apply_place_anchor(payload, q, want_poem)
                log("TOPIC_ISOLATE q=%r long=%s" % (q[:40], want_long))

        # === v1.36 真流式判定 ===
        # 条件：客户端要 stream + 总开关开 + 粤语角色(非英语老师/非自动英文/非诗词)。
        # 英语老师/诗词保留旧整段路径（polish_english 跨 \n 规则、诗词逐字豁免，唔冒险）。
        # E2E 探针 stream=False 亦走旧路径（保住非流式契约同 CONV_SAVED 校验）。
        use_stream = bool(
            STREAM_ENABLED and stream and not is_english and not want_poem
        )
        ans_cn = ""
        resp_bytes = 0
        if use_stream:
            sink = {}
            log("STREAM_ON q=%r（句子级缓冲增量吐，治开口前干等）" % q[:30])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")   # 关 nginx 缓冲，真流式到玩具
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                for frame in forward_stream(payload, sink):
                    resp_bytes += len(frame)
                    self.wfile.write(("%X\r\n" % len(frame)).encode() + frame + b"\r\n")
                    self.wfile.flush()     # ★关键：每句即刻推，唔畀内核缓冲
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            ans_cn = "".join(sink.get("full_raw") or [])
            if sink.get("hits"):
                log("POLISH %s" % sink["hits"])
            log("RESP 200 bytes=%d frames_out=%d（流式）" % (resp_bytes, sink.get("frames_out", 0)))
            code = 200
        else:
            code, body = forward(payload, stream)
            # === 粤语化后处理：只改输出文本，重算长度 ===
            # 英语老师(skip=True)：中英双语，整条豁免粤语化/清英文/正音，原样透传。
            if code == 200:
                body, phits = polish_response(body, stream, poem=want_poem, skip=is_english)
                if phits:
                    log("POLISH %s" % phits)
            # === v1.29 TTS 斜杠/音标清理（双轨）===
            # 落盘/查看页要保留完整音标教学稿（家长睇），播报畀细路听嘅先至删音标块同转斜杠。
            # 故【先】用清理前 body 抽 ans_cn，【后】先至 clean_tts_symbols_body 改播报 body。
            if code == 200 and CONV_LOG_ENABLED:
                try:
                    ans_cn = extract_answer_text(body, stream)
                except Exception as e:
                    log("CONV_EXTRACT_PRE_FAIL", repr(e)[:80])
            if code == 200:
                body, shits = yue_polish.clean_tts_symbols_body(body, stream)
                if shits:
                    log("TTS_SYMBOLS %s" % shits)
            log("RESP %s bytes=%d" % (code, len(body)))
            self.send_response(code)
            if stream:
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            else:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        # === 对话记录（v1.23）：写响应之后落盘，包 try/except 绝不影响对话 ===
        # v1.29 双轨：ans_cn 系【斜杠/音标清理前】嘅完整稿（保留音标教学），
        # 播报 body 已删音标；查看页落盘用 ans_cn，家长睇到嘅先系完整教学稿。
        # v1.31：X-No-Record:1（E2E/自检用）跳过落盘——测试稿唔再污染主人嘅真实对话记录，
        # 从根本唔使再「清落盘」，杜绝记录被清空/隐形。
        no_record = (self.headers.get("X-No-Record", "") == "1")
        if code == 200 and CONV_LOG_ENABLED and not no_record:
            try:
                wanted = {"weather": want_weather, "gz": want_gz, "news": want_news,
                          "search": want_search, "kb": want_kb, "subject": want_subject,
                          "poem": want_poem}
                conv_record(q, ans_cn, role_key, stream, wanted,
                            MODEL_OVERRIDE or UPSTREAM_MODEL, time.time() - t0,
                            auto_en=auto_en)
                conv_retention()   # v1.31：落盘后顺带做保留检查（内部每小时节流）
            except Exception as e:
                log("CONV_RECORD_FAIL", repr(e)[:100])


# 英语老师纯普通话 system prompt：启动时加载一次（roles.json 优先，兜底内置）
ENGLISH_SYSTEM, ENGLISH_SYSTEM_SRC = _load_english_system()


def main():
    log("start", "port=%d upstream=%s model=%s" % (PORT, UPSTREAM_BASE, UPSTREAM_MODEL))
    log("upstream_key_set=%s" % bool(UPSTREAM_KEY))
    log("ENGLISH_SYSTEM src=%s len=%d" % (ENGLISH_SYSTEM_SRC, len(ENGLISH_SYSTEM)))
    log("CONV keep=%d purge=%d dates=%s" % (CONV_KEEP_DAYS, CONV_PURGE_DAYS, conv_dates()[:5]))
    conv_retention(force=True)   # v1.31：启动即做一次保留检查（超期主文件移 archive/，仍可查）
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.serve_forever()


if __name__ == "__main__":
    main()
