#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ClawBot(手表电台) -> 火火兔(FoloToy) 单向桥接  v1.1  (2026-11-14)

目的
----
让火火兔也能收到推给手表的两类内容：
  A) 新闻 / 早安 / 传话等一次性音频（inbox item 带 audio=.ogg）
  B) 电台直播流点播（inbox item 带 play.type=radio）—— 录 3~5 分钟片段转 MP3 再推

设计原则（重要）
--------------
* **零侵入 ClawBot**：不修改 D:/AI/xiaozhi/clawbot 下任何文件，只读 data/inbox.json
  和 data/notify/*.ogg。所有状态写在脚本自己目录的 .bridge_state.json。
* **零侵入火火兔主链路**：不改 news_broadcaster.py / _broadcast_verified.sh / compose。
  只往 EMQX 发一条标准 iwantplay，音频落到音频卷根目录，文件名统一 bridge- 前缀。
* **URL 必须是根目录（v1.1 修复，勿改回子目录）**：实测设备对
  http://YOUR_SERVER_IP:8082/bridge/xxx.mp3 会回 callAck=YES 但从不下载；
  同一文件放根目录 /xxx.mp3 则立刻 GET 200 并播放。设备端不接受带子路径的 URL。
  既有播报 _broadcast_verified.sh 也一直用根目录 URL。
* **运行时不调用 wsl.exe**：音频经 \\\\wsl$\\... UNC 直接写入（已一次性授权根目录），
  避免本环境「频繁 wsl.exe 调用会冷停机、重拉整组容器」的已知坑。
* **严格幂等**：按 inbox item.id 记水位 + pending 队列 + 每轮最多推 1 条 + 推送间隔，
  杜绝重演「一条新闻播两遍」。首跑不回溯历史。
* **对齐 v1.45 防重复铁律**：发完订阅 callAck；设备已回执 = 送达，绝不再发；
  只有「完全没回执」（设备多半在休眠）才允许重推 1 次，每条最多 2 次推送。
  设备长期关机时这条会丢弃（与既有播报一致，靠 catchup 补，不在此桥接范围）。

链路
----
  inbox.json -> 分类 -> ffmpeg(ogg->mp3 / 电台直录mp3) -> UNC audio/ (根目录)
            -> nginx 8082/bridge-xxx.mp3 -> MQTT iwantplay(url) -> 火火兔

用法（Windows Git Bash / CMD）
----
  python clawbot_to_folotoy.py --self-test        # 只读自检，不出声
  python clawbot_to_folotoy.py --dry-run          # 扫描并打印「会推什么」，不出声不改状态
  python clawbot_to_folotoy.py --once             # 扫一次（供计划任务调用）
  python clawbot_to_folotoy.py --loop             # 常驻，每 POLL_SEC 秒轮询
  python clawbot_to_folotoy.py --test-play        # 发一条 5 秒探针音频，人工验收是否真出声
  python clawbot_to_folotoy.py --backfill 2       # 首跑额外回溯最近 2 条（默认 0）
  python clawbot_to_folotoy.py --reset            # 清空水位/队列（不删已生成音频）

环境变量（全部可覆盖，见下方 CFG）
  CB2FT_AUDIO_BASE / CB2FT_SN / CB2FT_MQTT_HOST / CB2FT_RADIO_CLIP 等

依赖
----
  paho-mqtt（已装：python -m pip install paho-mqtt）
  ffmpeg    （自动从 imageio_ffmpeg 定位；可用 CB2FT_FFMPEG 覆盖）
  其余全为标准库。
"""
import os
import sys
import re
import io
import json
import time
import glob
import shutil
import hashlib
import argparse
import traceback
import urllib.request
import urllib.parse
import subprocess
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- 配置
def _ffmpeg_default():
    """优先用 imageio_ffmpeg 自带的 ffmpeg.exe（ClawBot 自己也是这么找的）。"""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return (r"C:\Users\YOURNAME\AppData\Roaming\Python\Python313"
                r"\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe")

CFG = {
    # --- ClawBot 侧（只读） ---
    "claw_dir":    os.getenv("CB2FT_CLAW_DIR", r"D:\AI\xiaozhi\clawbot"),
    # --- 火火兔侧 ---
    # v1.1: 必须落音频卷根目录、URL 不带子路径，否则设备回 callAck 但从不下载
    "audio_unc":   os.getenv("CB2FT_AUDIO_UNC",
                             r"\\wsl$\$DISTRO\opt\folotoy\audio"),
    "audio_base":  os.getenv("CB2FT_AUDIO_BASE",
                             "http://YOUR_SERVER_IP:8082"),   # 下发给设备的 URL
    "verify_base": os.getenv("CB2FT_VERIFY_BASE",
                             "http://127.0.0.1:8082"),        # 本机自检用
    "mqtt_host":   os.getenv("CB2FT_MQTT_HOST", "127.0.0.1"),
    "mqtt_port":   int(os.getenv("CB2FT_MQTT_PORT", "1883")),
    "sn":          os.getenv("CB2FT_SN", "DEVICEKEY_REDACTED"),
    # --- 行为 ---
    "ffmpeg":      os.getenv("CB2FT_FFMPEG", _ffmpeg_default()),
    "poll_sec":    int(os.getenv("CB2FT_POLL_SEC", "20")),
    "min_gap":     int(os.getenv("CB2FT_MIN_GAP", "240")),      # 两条推送最小间隔(秒)
    "radio_clip":  int(os.getenv("CB2FT_RADIO_CLIP", "180")),   # 电台片段时长(秒)
    "radio_cool":  int(os.getenv("CB2FT_RADIO_COOL", "1800")),  # 同一台冷却(秒)
    "news_on":     os.getenv("CB2FT_NEWS_ON", "1") == "1",
    "radio_on":    os.getenv("CB2FT_RADIO_ON", "1") == "1",
    "keep_mp3":    int(os.getenv("CB2FT_KEEP_MP3", "120")),     # 保留最近 N 个成品
    "max_pending": int(os.getenv("CB2FT_MAX_PENDING", "20")),
    # 每条内容最多 2 次推送（对齐 v1.45：只有「没收到 callAck」才可重推 1 次）
    "max_retry":   int(os.getenv("CB2FT_MAX_RETRY", "2")),
    "ack_wait":    int(os.getenv("CB2FT_ACK_WAIT", "8")),
    # 默认跳过米家「进入/离开指定区域」这类高频位置提醒，避免火火兔被刷屏
    "skip_re":     os.getenv("CB2FT_SKIP_RE", r"米家.*(进入指定区域|离开指定区域)"),
    # 电台只认「正在播放 X」这类真点播/起播，跳过开机续播 / 播完回台 / 停止
    "radio_text":  os.getenv("CB2FT_RADIO_TEXT", r"^正在播放"),
    "radio_fallback": os.getenv("CB2FT_RADIO_FALLBACK", "1") == "1",
}

STATE_PATH = os.path.join(HERE, ".bridge_state.json")
LOCK_PATH  = os.path.join(HERE, ".bridge.lock")
LOG_PATH   = os.path.join(HERE, "bridge.log")
TOPIC_CMD  = "/sys/folotoy/%s/thing/command/call" % CFG["sn"]
LOCK_STALE = 300          # 锁超过 5 分钟视为崩溃残留，可清理


# ---------------------------------------------------------------- 工具
def log(msg, also_file=True):
    line = "[cb2ft] %s %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    try:
        print(line, flush=True)          # pythonw 下 stdout 为 None，静默跳过
    except Exception:
        pass
    if also_file:
        try:
            with io.open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def load_state():
    st = {"last_id": None, "pending": [], "last_push_ts": 0,
          "radio_last": {}, "stats": {"news": 0, "radio": 0, "skipped": 0, "failed": 0}}
    if os.path.exists(STATE_PATH):
        try:
            with io.open(STATE_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            st.update({k: saved[k] for k in st if k in saved})
        except Exception as e:
            log("WARN 状态文件损坏，重置: %s" % e)
    return st


def save_state(st):
    tmp = STATE_PATH + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def acquire_lock():
    """单实例锁：防止计划任务与手动 --loop 同时跑导致同一条被推两遍。"""
    try:
        if os.path.exists(LOCK_PATH):
            if time.time() - os.path.getmtime(LOCK_PATH) < LOCK_STALE:
                return False
            os.remove(LOCK_PATH)               # 崩溃残留
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except Exception:
        return False


def release_lock():
    try:
        os.remove(LOCK_PATH)
    except Exception:
        pass


def guarded(fn, *args, **kw):
    if not acquire_lock():
        log("另一实例正在运行，本轮跳过（防双触发）", also_file=False)
        return 0
    try:
        return fn(*args, **kw)
    finally:
        release_lock()


def read_inbox():
    path = os.path.join(CFG["claw_dir"], "data", "inbox.json")
    last_err = None
    for _ in range(3):                       # ClawBot 可能正在写，容错重试
        try:
            with io.open(path, encoding="utf-8") as f:
                d = json.load(f)
            items = d.get("items", [])
            return [i for i in items if isinstance(i, dict) and isinstance(i.get("id"), int)]
        except Exception as e:
            last_err = e
            time.sleep(0.3)
    raise RuntimeError("读 inbox.json 失败: %s" % last_err)


def http_ok(url, expect_size=None):
    """确认成品经 nginx 能被设备下载。"""
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = r.read()
            if r.status != 200:
                return False
            if expect_size is not None and len(data) != expect_size:
                return False
            return True
    except Exception:
        return False


def http_reachable(url):
    """端口是否通：拿到任何 HTTP 响应（含 403/404）都算通。"""
    import urllib.error
    try:
        urllib.request.urlopen(url, timeout=6).close()
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def unc_writable():
    """实测音频卷可写（os.access 对 9p/UNC 不可靠），写完即删。"""
    p = os.path.join(CFG["audio_unc"], ".cb2ft_write_test")
    try:
        with open(p, "wb") as f:
            f.write(b"ok")
        os.remove(p)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- MQTT
TOPIC_ACK = "/sys/folotoy/+/thing/command/callAck"


def mqtt_publish(payload, qos=1, want_ack=True):
    """发一条 iwantplay：qos=1 等 PUBACK，并订阅 callAck 确认设备真收到。

    返回 {"puback": bool, "ack": bool}。
    ack 只是信号、不阻断（对齐 news_broadcaster v1.33）：设备休眠可能不即时回执；
    但「已 ack」绝不再发第二条（对齐 v1.45 防重复播报铁律）。
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        log("ERROR 缺少 paho-mqtt，请执行: python -m pip install paho-mqtt")
        return {"puback": False, "ack": False}
    try:                                   # paho 2.x
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                        client_id="cb2ft-%d" % (time.time() % 1e6))
    except AttributeError:                 # paho 1.x
        c = mqtt.Client(client_id="cb2ft-%d" % (time.time() % 1e6))
    got = []

    def on_message(_c, _u, m):
        got.append(m.topic)

    def on_connect(_c, _u, _flags, *_args):
        # 在 CONNACK 之后才订阅，避免订阅早于连接生效而漏掉 callAck
        if want_ack:
            _c.subscribe(TOPIC_ACK, qos=0)

    c.on_message = on_message
    c.on_connect = on_connect
    try:
        c.connect(CFG["mqtt_host"], CFG["mqtt_port"], 30)
        c.loop_start()
        time.sleep(0.4)
        info = c.publish(TOPIC_CMD, json.dumps(payload, ensure_ascii=False), qos=qos)
        try:
            info.wait_for_publish(timeout=8)
        except Exception:
            pass
        deadline = time.time() + (CFG["ack_wait"] if want_ack else 0)
        while want_ack and time.time() < deadline and not got:
            time.sleep(0.2)
        ok = info.rc == mqtt.MQTT_ERR_SUCCESS and info.is_published()
        c.loop_stop()
        c.disconnect()
        return {"puback": ok, "ack": bool(got)}
    except Exception as e:
        log("ERROR MQTT 发布异常: %s" % e)
        try:
            c.loop_stop(); c.disconnect()
        except Exception:
            pass
        return {"puback": False, "ack": False}


def push_url(url):
    """唯一对外播报入口：一条内容 = 一条 iwantplay。"""
    payload = {"msgId": int(time.time()) % 1000000,
               "identifier": "iwantplay", "inputParams": {"url": url}}
    res = mqtt_publish(payload)
    log("PUSH puback=%s callAck=%s %s" %
        ("OK" if res["puback"] else "FAIL", "YES" if res["ack"] else "NONE", url))
    return res


# ---------------------------------------------------------------- 转码
def _run_ffmpeg(args, timeout):
    cmd = [CFG["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y"] + args
    # Windows：本脚本由 pythonw.exe 常驻运行（无控制台），控制台子进程 ffmpeg.exe
    # 默认会被系统分配一个新控制台 -> 桌面每录一段就弹一个黑色终端窗口。
    # CREATE_NO_WINDOW 让它在无窗口模式运行，capture_output 的管道不受影响。
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, **kw)
        if r.returncode != 0:
            log("WARN ffmpeg rc=%d %s" % (r.returncode,
                (r.stderr or b"").decode("utf-8", "replace")[-300:]))
            return False
        return True
    except subprocess.TimeoutExpired:
        log("WARN ffmpeg 超时 (%ds)" % timeout)
        return False
    except Exception as e:
        log("WARN ffmpeg 异常: %s" % e)
        return False


def publish_file(tmp_mp3, name):
    """把转好的 MP3 放进 nginx 音频卷，校验可见后返回设备 URL。"""
    if not os.path.exists(tmp_mp3) or os.path.getsize(tmp_mp3) < 1000:
        return None
    size = os.path.getsize(tmp_mp3)
    dst = os.path.join(CFG["audio_unc"], name)
    try:
        shutil.copyfile(tmp_mp3, dst)
    except Exception as e:
        log("ERROR 写音频卷失败: %s" % e)
        return None
    url_local = CFG["verify_base"].rstrip("/") + "/" + name
    if not http_ok(url_local, expect_size=size):
        log("ERROR nginx 校验失败: %s" % url_local)
        return None
    return CFG["audio_base"].rstrip("/") + "/" + name


def ogg_to_mp3(item):
    """A) 新闻/语音：ClawBot 的 .ogg -> 火火兔的 .mp3"""
    audio = item.get("audio")
    if not audio:
        return None
    if not re.match(r"^[\w.\-]+\.(ogg|mp3)$", str(audio)):
        log("WARN 跳过可疑文件名: %s" % audio)
        return None
    src = os.path.join(CFG["claw_dir"], "data", "notify", str(audio))
    if not os.path.exists(src):
        src = os.path.join(CFG["claw_dir"], "data", "music", str(audio))
    if not os.path.exists(src):
        log("WARN 音频已不存在(可能已被 ClawBot 清理): %s" % audio)
        return None
    name = "bridge-news-%d.mp3" % item["id"]
    tmp = os.path.join(HERE, "_cb2ft_tmp_%d.mp3" % item["id"])
    ok = _run_ffmpeg(["-i", src, "-vn", "-ac", "1", "-ar", "24000",
                      "-c:a", "libmp3lame", "-b:a", "64k", tmp], timeout=180)
    if not ok:
        try: os.remove(tmp)
        except Exception: pass
        return None
    url = publish_file(tmp, name)
    try: os.remove(tmp)
    except Exception: pass
    return url


# ---------------------------------------------------------------- 电台源
_STATION_CACHE = {}

def load_stations():
    """从 server.js 解析 RADIO_STATIONS 的 url/gain（只读，零副作用）。"""
    if _STATION_CACHE:
        return _STATION_CACHE
    path = os.path.join(CFG["claw_dir"], "server.js")
    try:
        with io.open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        log("WARN 读 server.js 失败: %s" % e)
        return {}
    m0 = re.search(r"const\s+RADIO_STATIONS\s*=\s*\{", text)
    if not m0:
        return {}
    section = text[m0.end():]
    m1 = re.search(r"\n\};", section)
    if m1:
        section = section[:m1.start()]
    for block in re.split(r"\n(?=\s*[A-Za-z0-9_]+:\s*\{)", section):
        mid = re.match(r"\s*([A-Za-z0-9_]+):\s*\{", block)
        murl = re.search(r"url:\s*'([^']*)'", block)
        if not (mid and murl):
            continue
        mgain = re.search(r"gain:\s*([0-9.]+)", block)
        _STATION_CACHE[mid.group(1)] = {
            "url": murl.group(1),
            "gain": float(mgain.group(1)) if mgain else 1.0,
        }
    log("解析电台源 %d 个" % len(_STATION_CACHE))
    return _STATION_CACHE


def record_radio(item):
    """B) 电台直播流：录 CLIP 秒片段转 MP3。

    默认直接拉原台源（对 ClawBot 零副作用）；失败时可选回退打 ClawBot 的
    /api/radio/stream（用 LAN host，避免把 radioLastGoodBase 污染成 127.0.0.1）。
    """
    play = item.get("play") or {}
    sid = str(play.get("id") or "")
    st = load_stations().get(sid)
    if not st:
        log("WARN 未知电台 id=%s，跳过" % sid)
        return None
    name = "bridge-radio-%s-%d.mp3" % (re.sub(r"\W", "_", sid), item["id"])
    tmp = os.path.join(HERE, "_cb2ft_tmp_%d.mp3" % item["id"])
    clip = CFG["radio_clip"]

    def build(src_url, with_gain):
        a = ["-user_agent", "VLC/3.0.20 LibVLC/3.0.20",
             "-rw_timeout", "30000000", "-i", src_url,
             "-t", str(clip), "-vn"]
        if with_gain and st["gain"] != 1.0:
            a += ["-af", "volume=%s,alimiter=limit=0.95:level=false" % st["gain"]]
        a += ["-ac", "1", "-ar", "24000", "-c:a", "libmp3lame", "-b:a", "64k", tmp]
        return a

    ok = _run_ffmpeg(build(st["url"], True), timeout=clip + 120)
    if not ok and CFG["radio_fallback"]:
        # 回退：借 ClawBot 已验证能拉通的转码通道。副作用仅为内存态「正在听」记录，
        # 用 LAN host 保证不改写 radioLastGoodBase。
        fb = ("http://YOUR_SERVER_IP:3000/api/radio/stream?id=%s&device=watch"
              % urllib.parse.quote(sid))
        log("WARN 原台源录制失败，回退 ClawBot 转码通道: %s" % fb)
        ok = _run_ffmpeg(build(fb, False), timeout=clip + 120)
    if not ok:
        try: os.remove(tmp)
        except Exception: pass
        return None
    url = publish_file(tmp, name)
    try: os.remove(tmp)
    except Exception: pass
    return url


# ---------------------------------------------------------------- 分发
def classify(item):
    """返回 (kind, 说明)；kind 为 '' 表示不推。"""
    text = str(item.get("text") or "")
    if CFG["skip_re"] and re.search(CFG["skip_re"], text):
        return "", "命中跳过规则"
    play = item.get("play") or {}
    if item.get("audio") and CFG["news_on"]:
        return "news", "音频 %s" % item.get("audio")
    if (CFG["radio_on"] and play.get("type") == "radio" and not play.get("stop")
            and re.search(CFG["radio_text"], text)):
        return "radio", "电台 %s" % (play.get("id") or "?")
    return "", "非目标条目"


def handle(st, item, dry):
    kind, why = classify(item)
    if not kind:
        return "skip", why
    if dry:
        return "dry", "%s | %s" % (kind, why)
    if kind == "radio":
        sid = str((item.get("play") or {}).get("id") or "?")
        last = st["radio_last"].get(sid, 0)
        if time.time() - last < CFG["radio_cool"]:
            return "skip", "电台 %s 冷却中(%d分钟)" % (sid, CFG["radio_cool"] // 60)
    url = ogg_to_mp3(item) if kind == "news" else record_radio(item)
    if not url:
        return "fail", "转码/落盘失败"
    res = push_url(url)
    if not res["puback"]:
        return "fail", "MQTT 发布失败"
    if not res["ack"]:
        # 对齐 v1.45：只有「没收到回执」才允许重推；已回执绝不重推，避免重复播报。
        return "noack", "设备未回 callAck（可能休眠），保留队列待重推 1 次"
    st["last_push_ts"] = time.time()
    if kind == "radio":
        st["radio_last"][str((item.get("play") or {}).get("id") or "?")] = time.time()
    st["stats"][kind] = st["stats"].get(kind, 0) + 1
    return "ok", url


def cleanup_mp3():
    """只清理本脚本生成的 bridge-*.mp3，绝不碰 aqing-news-* 等主链路文件。"""
    try:
        files = sorted(glob.glob(os.path.join(CFG["audio_unc"], "bridge-*.mp3")),
                       key=os.path.getmtime, reverse=True)
        for p in files[CFG["keep_mp3"]:]:
            try: os.remove(p)
            except Exception: pass
    except Exception as e:
        log("WARN 清理跳过: %s" % e)


def enqueue(st, items):
    """按同一套分类规则把目标条目入队。"""
    for i in sorted(items, key=lambda x: x["id"]):
        kind, why = classify(i)
        if kind:
            st["pending"].append({"item": i, "retry": 0})
            log("入队 #%d %s | %s" % (i["id"], kind, why))
        else:
            st["stats"]["skipped"] += 1
            log("忽略 #%d %s" % (i["id"], why))


def run_once(dry=False, backfill=0):
    st = load_state()
    items = read_inbox()
    max_id = max([i["id"] for i in items], default=0)

    if st["last_id"] is None:
        log("首次运行：水位设为 #%d，不回溯历史%s" %
            (max_id, "（backfill=%d）" % backfill if backfill else ""))
        if dry:
            return
        st["last_id"] = max_id
        if backfill:
            enqueue(st, sorted(items, key=lambda x: x["id"])[-backfill:])
            log("backfill 入队完成，本轮继续处理")
        else:
            save_state(st)
            return                       # 无回溯：首跑只建立水位，绝不推历史

    fresh = [i for i in items if i["id"] > st["last_id"]]
    if fresh:
        enqueue(st, fresh)
        st["last_id"] = max(st["last_id"], max(i["id"] for i in fresh))

    # 队列溢出保护：丢最旧的，避免长期积压后一次性连播
    if len(st["pending"]) > CFG["max_pending"]:
        drop = st["pending"][:-CFG["max_pending"]]
        st["pending"] = st["pending"][-CFG["max_pending"]:]
        log("WARN 队列溢出，丢弃 %d 条最旧待推" % len(drop))

    if not dry:
        save_state(st)

    if not st["pending"]:
        # 每分钟轮询的空转不写日志文件，避免日志暴涨（仍打印，便于手动观察）
        log("无待推条目 (水位 #%d)" % st["last_id"], also_file=False)
        return

    gap = time.time() - st.get("last_push_ts", 0)
    if gap < CFG["min_gap"]:
        log("推送冷却中，还需 %d 秒；队列 %d 条保留" %
            (int(CFG["min_gap"] - gap), len(st["pending"])))
        return

    # 每轮最多推 1 条：新闻与电台不抢播、不叠播
    head = st["pending"][0]
    item = head["item"]
    status, detail = handle(st, item, dry)
    log("处理 #%d -> %s | %s" % (item["id"], status, detail))
    if dry:
        return
    if status in ("ok", "skip"):
        st["pending"].pop(0)
    elif status in ("fail", "noack"):
        # noack 不更新 last_push_ts，下一轮即可重推；每条最多 max_retry 次推送。
        head["retry"] += 1
        if status == "fail":
            st["stats"]["failed"] += 1
        if head["retry"] >= CFG["max_retry"]:
            log("WARN #%d 推送 %d 次仍%s，丢弃（不再重推，防重复播报）" %
                (item["id"], head["retry"],
                 "未收到 callAck" if status == "noack" else "失败"))
            st["pending"].pop(0)
    save_state(st)
    cleanup_mp3()


# ---------------------------------------------------------------- 自检
def self_test():
    log("===== 自检（只读，不出声）=====")
    ok = True

    def chk(label, cond, extra=""):
        nonlocal ok
        log("  [%s] %s %s" % ("PASS" if cond else "FAIL", label, extra))
        if not cond:
            ok = False

    chk("inbox.json 可读", bool(read_inbox()))
    chk("notify/ 目录存在",
        os.path.isdir(os.path.join(CFG["claw_dir"], "data", "notify")))
    chk("ffmpeg 可执行", os.path.exists(CFG["ffmpeg"]), CFG["ffmpeg"])
    chk("音频卷可写(UNC 实测)", unc_writable())
    chk("nginx 8082 可达", http_reachable(CFG["verify_base"].rstrip("/") + "/"))
    stations = load_stations()
    chk("电台源解析", len(stations) > 0, "%d 台" % len(stations))
    try:
        import paho.mqtt.client
        chk("paho-mqtt 已安装", True)
    except ImportError:
        chk("paho-mqtt 已安装", False, "执行 python -m pip install paho-mqtt")
    # MQTT 连通性：发到不存在的 SN，不会触发任何设备
    try:
        probe = {"msgId": 1, "identifier": "bridgeSelfTest",
                 "inputParams": {}}
        topic = "/sys/folotoy/cb2ft-selftest/thing/command/call"
        import paho.mqtt.client as mqtt
        try:
            c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                            client_id="cb2ft-selftest")
        except AttributeError:
            c = mqtt.Client(client_id="cb2ft-selftest")
        c.connect(CFG["mqtt_host"], CFG["mqtt_port"], 10)
        c.loop_start()
        info = c.publish(topic, json.dumps(probe), qos=1)
        info.wait_for_publish(timeout=5)
        good = info.is_published()
        c.loop_stop(); c.disconnect()
        chk("EMQX 1883 连通 + QoS1 PUBACK", good)
    except Exception as e:
        chk("EMQX 1883 连通 + QoS1 PUBACK", False, str(e))
    log("===== 自检 %s =====" % ("全部通过" if ok else "存在失败项"))
    return 0 if ok else 1


def test_play():
    """人工验收：自制 3 秒提示音推给火火兔，只发一条 iwantplay。"""
    probe = os.path.join(HERE, "_cb2ft_probe.mp3")
    if not os.path.exists(probe):
        ok = _run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=660:duration=3",
                          "-ac", "1", "-ar", "24000", "-c:a", "libmp3lame",
                          "-b:a", "64k", probe], timeout=40)
        if not ok:
            log("ERROR 生成探针音频失败")
            return 1
    url = publish_file(probe, "bridge-selftest.mp3")
    if not url:
        log("ERROR 探针音频落盘/校验失败")
        return 1
    log("将向火火兔播一条 3 秒提示音（只发一次）...")
    res = push_url(url)
    log("验收推送 %s；callAck=%s；请听火火兔是否出声" %
        ("已发出" if res["puback"] else "失败", "YES" if res["ack"] else "NONE(设备可能休眠)"))
    return 0 if res["puback"] else 1


def main():
    ap = argparse.ArgumentParser(description="ClawBot -> 火火兔 单向桥接")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--self-test", action="store_true", help="只读自检")
    g.add_argument("--dry-run", action="store_true", help="扫描打印计划，不出声不改状态")
    g.add_argument("--once", action="store_true", help="扫描一次（默认）")
    g.add_argument("--loop", action="store_true", help="常驻轮询")
    g.add_argument("--test-play", action="store_true", help="发一条 5 秒探针真播验收")
    g.add_argument("--reset", action="store_true", help="清空水位与队列")
    ap.add_argument("--backfill", type=int, default=0, help="首跑回溯最近 N 条")
    a = ap.parse_args()

    if a.reset:
        if os.path.exists(STATE_PATH):
            os.remove(STATE_PATH)
        log("已清空状态文件（音频未删）")
        return 0
    if a.self_test:
        return self_test()
    if a.test_play:
        return guarded(test_play)
    if a.dry_run:                            # 只读，不写状态、不发声，无需加锁
        run_once(dry=True, backfill=a.backfill)
        return 0
    if a.loop:
        log("常驻启动 poll=%ds min_gap=%ds clip=%ds" %
            (CFG["poll_sec"], CFG["min_gap"], CFG["radio_clip"]))
        while True:
            try:
                guarded(run_once, backfill=a.backfill)
                a.backfill = 0
            except Exception as e:
                log("ERROR 轮询异常: %s\n%s" % (e, traceback.format_exc()[-500:]))
            time.sleep(CFG["poll_sec"])
    guarded(run_once, backfill=a.backfill)
    return 0


if __name__ == "__main__":
    sys.exit(main())
