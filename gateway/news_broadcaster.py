#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿晴 · 主动定时播报 + 即时播报

不按玩具，到点主动开口。走 iwantplay 协议（官方文档已验证）：
  PUBLISH /sys/folotoy/$sn/thing/command/call
  {"msgId":N,"identifier":"iwantplay","inputParams":{"url":"http://<host>:8082/<file>.mp3"}}
  url 优先于 text；玩具经 nginx(8082) 下载播放。

长文策略（绕开 edge-tts 整段慢合成）：
  把粤语稿按句切成 N 段 -> 多进程并行 edge-tts -> ffmpeg concat 成一个 MP3
  -> 落到 /audio（nginx 挂载）-> 发 url 指令。1000 字从 ~40s 压到 ~15s。

v1.33 出声确认（两层，2026-11-11）：
  网关层（本文件）：MQTT 由 qos=0 火并忘记 -> qos=1 等 PUBACK + 订阅 callAck
    确认设备真收到 iwantplay；make_script 请求加 X-No-Record:1，杜绝播报稿落盘污染。
  ⚠️ 网关层只证明「设备收到指令」，唔等于「真出声」。设备下载完整 + 真出声由
    宿主层 _broadcast_verified.sh 盯 nginx access.log(bytes==size) + 失败重推 + 保活确认
    （WSL 命令间隙会冷停机、容器内 daemon 活唔到整点，故确认主力放宿主层）。
  callAck 超时只记 WARN 唔阻断：设备休眠可能唔即时回执，最终以宿主层完整下载为准，
    避免偶尔无回执就误杀播报。

用法（容器/WSL 内）：
  python3 news_broadcaster.py once            # 立即播一期广州新闻
  python3 news_broadcaster.py daemon          # 常驻，按 SCHEDULE 定时播
  python3 news_broadcaster.py say "阿晴讲嘢"  # 播指定文字
  python3 news_broadcaster.py url <mp3url>    # 播指定已有链接

环境变量：
  MQTT_HOST          默认 emqx
  SN                 玩具序列号 默认 DEVICEKEY_REDACTED
  AUDIO_DIR          默认 /audio（与 nginx 共享）
  AUDIO_BASE_URL     默认 http://YOUR_SERVER_IP:8082
  LLM_GATEWAY        默认 http://llm-gateway:8000/v1
  SCHEDULE           默认 "08:00,18:00"（每天这几个点播报）
  TZ                 Asia/Shanghai
  PARALLEL           并行合成段数 默认 4
  NEWS_QUERY         播报主题 默认 "广州今日新闻天气"
  NEWS_RATE          播报语速 默认 +0%（1.0 正常速，不快不慢）；只影响定时/即时播报，
                     同 7 键答话语速（folotoy 容器 edge-tts wrapper 的 +20%）完全独立。
                     edge-tts rate 是相对正常语速的百分比：+0%=1.0倍，+20%=1.2倍，-20%=0.8倍。
"""
import os, sys, json, time, re, hashlib, subprocess, tempfile, urllib.request, urllib.parse, ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
import yue_polish  # 播报稿本地兜底粤语化（网关已处理，此处双保险，直连上游时仍生效）
import tts_pron    # 粤语多音字 TTS 正音（「区」keoi1 非 au1；在 polish 之后、合成之前）

MQTT_HOST = os.getenv("MQTT_HOST", "emqx")
SN = os.getenv("SN", "DEVICEKEY_REDACTED")
AUDIO_DIR = os.getenv("AUDIO_DIR", "/audio")
AUDIO_BASE = os.getenv("AUDIO_BASE_URL", "http://YOUR_SERVER_IP:8082").rstrip("/")
LLM_GW = os.getenv("LLM_GATEWAY", "http://llm-gateway:8000/v1").rstrip("/")
SCHEDULE = os.getenv("SCHEDULE", "08:00,18:00")
PARALLEL = int(os.getenv("PARALLEL", "4"))
NEWS_QUERY = os.getenv("NEWS_QUERY", "广州今日新闻同天气")
VOICE = os.getenv("VOICE", "zh-HK-HiuMaanNeural")
NEWS_RATE = os.getenv("NEWS_RATE", "+0%")   # 播报语速，默认 1.0 正常速；只管播报，不影响 7 键答话
CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0"}

TOPIC_CMD = "/sys/folotoy/%s/thing/command/call" % SN
TOPIC_ACK = "/sys/folotoy/+/thing/command/callAck"   # v1.33 设备回执 topic
ACK_WAIT = float(os.getenv("ACK_WAIT", "8"))         # 等 callAck 秒数；设备休眠可能唔即时回


def log(*a):
    print("[bc]", time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------- MQTT 发布（v1.33: qos=1 等 PUBACK + 订阅 callAck）----------------
def mqtt_publish(payload, want_ack=True):
    """发 iwantplay 指令。qos=1 保证 broker 层送达，订阅 callAck 确认设备真收到。
    返回 dict: {puback, ack, ack_payload}。ack 只做信号、唔阻断；真出声由宿主层确认。"""
    import paho.mqtt.client as mqtt
    got = []

    def on_message(c, u, m):
        p = (m.payload or b"").decode("utf-8", "replace")
        got.append((m.topic, p))
        log("CALLACK", m.topic, p[:160])

    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="bc-pub-%d" % (time.time() % 1e6))
    except AttributeError:
        c = mqtt.Client(client_id="bc-pub-%d" % (time.time() % 1e6))
    c.on_message = on_message
    c.connect(MQTT_HOST, 1883, 30)
    if want_ack:
        c.subscribe(TOPIC_ACK, qos=0)
    c.loop_start()
    time.sleep(0.3)
    info = c.publish(TOPIC_CMD, json.dumps(payload, ensure_ascii=False), qos=1)
    puback = False
    try:
        puback = bool(info.wait_for_publish(timeout=5))
    except Exception:
        pass
    # 等 callAck（有就收，冇就记 WARN，唔阻断）
    deadline = time.time() + (ACK_WAIT if want_ack else 0)
    while want_ack and time.time() < deadline and not got:
        time.sleep(0.2)
    c.loop_stop()
    c.disconnect()
    ack, ack_payload = (got[0] if got else (None, None))
    log("PUB qos=1 puback=%s callack=%s" % (puback, "YES" if ack else "WARN-NONE"), TOPIC_CMD)
    return {"puback": puback, "ack": bool(ack), "ack_payload": ack_payload}


def play_url(url, msgid=None, want_ack=True):
    payload = {"msgId": msgid or int(time.time()) % 1000000,
               "identifier": "iwantplay", "inputParams": {"url": url}}
    return mqtt_publish(payload, want_ack=want_ack)


def play_text(text, msgid=None, want_ack=True):
    payload = {"msgId": msgid or int(time.time()) % 1000000,
               "identifier": "iwantplay", "inputParams": {"role": 1, "text": text}}
    return mqtt_publish(payload, want_ack=want_ack)


# ---------------- 生成粤语播报稿（经网关 -> 已联网抓资料 + 阿晴人设）----------------
SYS_PROMPT = (
    "你系广州西关土生土长嘅阿晴，20岁，用纯正地道广州西关口语讲嘢，温柔沉静带少少含蓄俏皮。"
    "呢次系【电台晨间/间时播报】，你要像街坊电台主持咁，把真实资讯讲畀听众听。"
    "要求：全程粤语口语；短句、有停顿感；开头一句亲切开场（例如「各位街坊，阿晴同你讲下今日」）；"
    "内容分几条讲，重点讲清楚；结尾一句温柔收尾；"
    "唔好念 URL、编号、英文、日期戳、来源名；唔好加 emoji、括号、Markdown；"
    "全程净系用简体中文嘅地道粤语口语，绝对唔准夹杂英文字母、外语或乱码，"
    "外国人名同机构名一律用中文译名，讲唔出就跳过；唔知就坦率话唔知，千祈唔好作大。"
)


def make_script(topic=NEWS_QUERY):
    body = {
        "model": os.getenv("UPSTREAM_MODEL", "THUDM/GLM-4-9B-0414"),
        "messages": [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": topic + "，详细啲讲，大约八百字，讲成一段电台播报稿。"},
        ],
        "max_tokens": 1200, "temperature": 0.7, "stream": False,
    }
    req = urllib.request.Request(LLM_GW + "/chat/completions",
                                 data=json.dumps(body, ensure_ascii=False).encode(),
                                 # v1.33: 播报稿系程序内部生成，唔系玩具真对话，禁止落盘污染记录
                                 headers={"Content-Type": "application/json", "X-No-Record": "1"},
                                 method="POST")
    log("生成播报稿 via gateway ...")
    r = urllib.request.urlopen(req, timeout=90, context=CTX)
    d = json.loads(r.read().decode())
    text = d["choices"][0]["message"]["content"].strip()
    text, phits = yue_polish.polish(text, report=True)  # 兜底：确保播报稿零普通话残留
    if phits:
        log("稿粤语化 %s" % phits)
    log("稿成 字数=%d" % len(text))
    return text


# ---------------- 长文分段并行 TTS + ffmpeg 拼接 ----------------
def split_sentences(text, maxlen=110):
    parts = re.split(r"(?<=[。！？!?；;])", text)
    segs, buf = [], ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) <= maxlen:
            buf += p
        else:
            if buf:
                segs.append(buf)
            while len(p) > maxlen:
                segs.append(p[:maxlen]); p = p[maxlen:]
            buf = p
    if buf:
        segs.append(buf)
    return [s for s in segs if s.strip()]


def tts_segment(args):
    idx, text, tmpdir = args
    out = os.path.join(tmpdir, "seg%03d.mp3" % idx)
    cmd = ["/usr/local/bin/edge-tts.real", "--voice", VOICE,
           "--rate=" + NEWS_RATE, "--text", text, "--write-media", out]  # NEWS_RATE 默认 +0%(1.0正常速)；旧 +20%(1.2)/一度 -20%(0.8)/更早 -10%
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=90)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 500:
            return idx, out, None
        return idx, None, (r.stderr or b"").decode("utf-8", "replace")[:120]
    except Exception as e:
        return idx, None, repr(e)[:120]


def synth_long(text):
    text = tts_pron.fix(text)   # 粤语多音字正音：「区」-> 「區」读 keoi1，避免念成「欧」
    segs = split_sentences(text)
    log("长文切片 段数=%d (并行%d)" % (len(segs), PARALLEL))
    with tempfile.TemporaryDirectory() as td:
        results = {}
        with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
            futs = [ex.submit(tts_segment, (i, s, td)) for i, s in enumerate(segs)]
            for f in as_completed(futs):
                i, out, err = f.result()
                if out:
                    results[i] = out
                else:
                    log("SEG_FAIL", i, err)
        if not results:
            raise RuntimeError("所有分段合成失败")
        ordered = [results[i] for i in sorted(results)]
        # 缺失段用静音顶上，保持顺序（极少发生）
        for i in range(len(segs)):
            if i not in results:
                log("补静音 段", i)
                silent = os.path.join(td, "silent%03d.mp3" % i)
                subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                                "-t", "1.5", "-q:a", "9", silent], capture_output=True)
                ordered.insert(i, silent)
        listfile = os.path.join(td, "list.txt")
        with open(listfile, "w", encoding="utf-8") as f:
            for p in ordered:
                f.write("file '%s'\n" % p.replace("'", "'\\''"))
        name = "aqing-news-%s.mp3" % hashlib.md5((text + str(time.time())).encode()).hexdigest()[:12]
        final = os.path.join(AUDIO_DIR, name)
        os.makedirs(AUDIO_DIR, exist_ok=True)
        r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
                            "-c", "copy", final], capture_output=True, timeout=120)
        if r.returncode != 0 or not os.path.exists(final):
            raise RuntimeError("concat 失败: " + (r.stderr or b"").decode("utf-8", "replace")[:200])
        size = os.path.getsize(final)
        log("合成完成 %s %.0fKB" % (name, size / 1024))
        return name


def broadcast_now(topic=NEWS_QUERY):
    t0 = time.time()
    script = make_script(topic)
    name = synth_long(script)
    url = AUDIO_BASE + "/" + name
    res = play_url(url)
    state = "ACK_OK" if res.get("ack") else "ACK_WARN(设备未即时回执，交宿主层确认完整下载)"
    log("主动播报 PUB 完成 总耗时=%.1fs url=%s %s" % (time.time() - t0, url, state))
    return {"url": url, "name": name, **res}


# ---------------- 定时调度 ----------------
def daemon():
    import datetime
    log("daemon 启动 SCHEDULE=%s" % SCHEDULE)
    slots = sorted(set(s.strip() for s in SCHEDULE.split(",") if s.strip()))
    fired = set()
    # 启动宽限：等网关 listen 就绪，避免容器冷启动时守护先跑 -> Connection refused
    time.sleep(20)
    log("daemon 就绪，开始按点监听（错过的时间点不补播）")
    while True:
        now = datetime.datetime.now()
        key = now.strftime("%Y-%m-%d")
        cur = now.strftime("%H:%M")
        for s in slots:
            tag = key + " " + s
            # 只在「正好到点那一分钟」触发一次；cur>=s 会在每次冷启动补播所有已过点，是错的
            if cur == s and tag not in fired:
                fired.add(tag)
                log("到点播报", tag)
                try:
                    broadcast_now()
                except Exception as e:
                    log("播报失败", repr(e))
        # 只保留今天/昨天的 fired
        fired = {x for x in fired if x.split(" ")[0] >= (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")}
        time.sleep(20)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "once"
    if cmd == "daemon":
        daemon()
    elif cmd == "once":
        res = broadcast_now(NEWS_QUERY)
        # v1.33 机器可读行：宿主 _broadcast_verified.sh 据此盯 nginx 完整下载
        print("BC_FILE %s" % res["name"], flush=True)
    elif cmd == "say":
        play_text(" ".join(sys.argv[2:]))
    elif cmd == "url":
        # 宿主层重推同一 URL 用；回执由宿主盯 nginx 下载确认，此处等 ACK 会拖慢重推，故关掉
        play_url(sys.argv[2], want_ack=False)
    elif cmd == "script":
        print(make_script(NEWS_QUERY))
    else:
        print("用法: once | daemon | say <text> | url <url> | script")


if __name__ == "__main__":
    main()
