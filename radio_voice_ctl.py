#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
火火兔「按键 / 语音指令」控制电台开播停播  (2026-11-14)

零侵入旁路：只读 gateway /logs（本机 8010），不改容器、不改 compose、
不重启任何服务、不需要 INTEGRATION_MQTT。

信号来源
--------
  /logs 每条对话记录：
    epoch  时间戳（水位，保证每条只处理一次）
    q      用户说话的 STT 识别文本 -> 语音指令
    btn    按键编号（1闲聊 2语文 3数学 4英语 5物理 6化学 7历史）
           注意：btn 是由 role_key 映射出来的「角色键」，纯按键不说话
           不会产生记录；需按键后说一句。默认不启用按键触发。

局限（重要）
------------
  conv_record() 是在 LLM 回答写完之后才落盘，所以指令有 10~30 秒延迟，
  且玩具会先照常把 LLM 的回答念出来，之后才执行开播/停播。
  想要零延迟且不让玩具回话，需要改 llm_gateway.py（本脚本不做）。
"""
import os
import io
import sys
import json
import time
import argparse
import subprocess
import traceback
import urllib.request
from datetime import datetime

HERE       = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, ".radio_ctl_state.json")
LOG_PATH   = os.path.join(HERE, "radio_ctl.log")
LOCK_PATH  = os.path.join(HERE, ".radio_ctl.lock")
STOP_FLAG  = os.path.join(HERE, "radio.stop")
LOCK_STALE = 45

LOGS_URL   = os.getenv("RADIO_CTL_LOGS", "http://127.0.0.1:8010/logs?limit=8")
POLL_SEC   = int(os.getenv("RADIO_CTL_POLL", "2"))
COOLDOWN   = int(os.getenv("RADIO_CTL_COOLDOWN", "90"))
PY         = os.path.join(os.path.dirname(sys.executable), "python.exe")  # 常驻用 pythonw，动作要 python.exe
RADIO_LOOP = os.path.join(HERE, "radio_loop.py")
RADIO_ONCE = os.path.join(HERE, "radio_once.py")      # 按需单次推送（不再常驻循环）

# 按键触发默认关闭：填 "6"/"7" 之类才启用（会占用该学科键）
BTN_PLAY   = os.getenv("RADIO_BTN_PLAY", "").strip()
BTN_STOP   = os.getenv("RADIO_BTN_STOP", "").strip()

PLAY_WORDS = [
    "播放电台", "播电台", "听电台", "打开电台", "开电台", "电台开",
    "开播", "开始播", "开始播放", "我要听", "香港电台", "播下电台",
    "听下电台", "播新闻", "听新闻",
]
STOP_WORDS = [
    "停播", "停止播放", "停止电台", "电台停", "关闭电台", "关掉电台",
    "关电台", "不要播", "别播", "唔好播", "唔播", "停咗", "停低",
    "收声", "静音", "停止播报", "别放了", "关掉",
]


def rlog(msg):
    line = "[ctl] %s %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with io.open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state():
    try:
        with io.open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_epoch": None, "last_action": {"kind": "", "ts": 0}}


def save_state(st):
    tmp = STATE_PATH + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def touch_lock():
    try:
        with open(LOCK_PATH, "a"):
            pass
        os.utime(LOCK_PATH, None)
    except Exception:
        pass


def acquire():
    try:
        if os.path.exists(LOCK_PATH):
            if time.time() - os.path.getmtime(LOCK_PATH) < LOCK_STALE:
                return False
            os.remove(LOCK_PATH)
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except Exception:
        return False


def release():
    try:
        os.remove(LOCK_PATH)
    except Exception:
        pass


def fetch_logs():
    with urllib.request.urlopen(LOGS_URL, timeout=6) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return d.get("items", []) or []


def classify(rec):
    """返回 ('play'|'stop', 原因) 或 (None, '')。"""
    q = str(rec.get("q") or "").strip()
    btn = str(rec.get("btn") or "").strip()
    if BTN_STOP and btn == BTN_STOP:
        return "stop", "按键 btn=%s" % btn
    if BTN_PLAY and btn == BTN_PLAY:
        return "play", "按键 btn=%s" % btn
    for w in STOP_WORDS:
        if w in q:
            return "stop", "语音「%s」" % q[:30]
    for w in PLAY_WORDS:
        if w in q:
            return "play", "语音「%s」" % q[:30]
    return None, ""


def run_cmd(args, timeout=20):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout)
        out = (p.stdout or b"").decode("utf-8", "replace").strip()
        err = (p.stderr or b"").decode("utf-8", "replace").strip()
        return p.returncode, (out + " " + err).strip()[:160]
    except Exception as e:
        return -1, str(e)[:160]


def act(kind, dry=False):
    """执行开播/停播。dry=True 只打印，绝不动作。"""
    if dry:
        rlog("DRY-RUN 会执行 %s（未真执行）" % kind)
        return
    if kind == "play":
        # 主人 2026-11-14 18:24 指令：恢复「连续播放」。
        # 开播 = 启用 \AqingRadioLoop 并立即拉起常驻循环，播到主人下停播指令为止。
        # 用 schtasks 触发（秒回、不阻塞桥接锁刷新 LOCK_STALE=45s），
        # 循环由 pythonw 独立常驻，单实例锁保证不会双触发。
        try:
            os.remove(STOP_FLAG)
            rlog("已清除 STOP 标志")
        except Exception:
            pass
        for args in (["schtasks", "/change", "/enable", "/tn", "AqingRadioLoop"],
                     ["schtasks", "/run", "/tn", "AqingRadioLoop"]):
            rc, out = run_cmd(args)
            rlog("开播 %s rc=%s %s" % (args[1], rc, out))
    else:
        rc, out = run_cmd(["schtasks", "/change", "/disable", "/tn", "AqingRadioLoop"])
        rlog("停播 禁用自愈 rc=%s %s" % (rc, out))
        rc, out = run_cmd([PY, RADIO_LOOP, "--stop"], timeout=40)
        rlog("停播 STOP+静音 rc=%s %s" % (rc, out))


def scan(st, dry=False):
    try:
        items = fetch_logs()
    except Exception as e:
        rlog("WARN /logs 读取失败: %s" % e)
        return
    epochs = [float(i.get("epoch") or 0) for i in items]
    newest = max(epochs) if epochs else 0.0
    if st["last_epoch"] is None:
        st["last_epoch"] = newest
        if not dry:
            save_state(st)
        rlog("首次运行：水位 epoch=%s，不回溯历史" % newest)
        return
    fresh = sorted([i for i in items
                    if float(i.get("epoch") or 0) > st["last_epoch"]],
                   key=lambda x: float(x.get("epoch") or 0))
    for rec in fresh:
        kind, why = classify(rec)
        if kind:
            last = st["last_action"]
            if kind == last.get("kind") and time.time() - float(last.get("ts") or 0) < COOLDOWN:
                rlog("忽略（冷却中）%s | %s" % (kind, why))
            else:
                rlog("命中 %s | %s | btn=%s" % (kind, why, rec.get("btn")))
                act(kind, dry=dry)
                if not dry:
                    st["last_action"] = {"kind": kind, "ts": time.time()}
        else:
            rlog("新对话(非指令) btn=%s q=%s" %
                 (rec.get("btn"), str(rec.get("q") or "")[:30]))
    if fresh:
        st["last_epoch"] = max(st["last_epoch"], newest)
        if not dry:
            save_state(st)


def status():
    st = load_state()
    alive = os.path.exists(LOCK_PATH) and \
            time.time() - os.path.getmtime(LOCK_PATH) < LOCK_STALE
    print("监听运行中 : %s" % ("YES" if alive else "NO"))
    print("水位 epoch : %s" % st["last_epoch"])
    print("上次动作   : %s" % st["last_action"])
    print("按键映射   : play=%s stop=%s（空=未启用）" % (BTN_PLAY or "-", BTN_STOP or "-"))
    print("日志       : %s" % LOG_PATH)
    if os.path.exists(LOG_PATH):
        with io.open(LOG_PATH, encoding="utf-8") as f:
            lines = f.readlines()[-8:]
        print("--- 最近 ---")
        for l in lines:
            print(l.rstrip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    if a.status:
        status()
        return 0
    if a.dry_run:                     # dry-run 不拿锁、不写状态
        scan(load_state(), dry=True)
        return 0
    if not a.loop:                    # --once：扫一次（供手动/测试）
        if not acquire():
            rlog("已有监听实例，跳过")
            return 0
        try:
            scan(load_state())
        finally:
            release()
        return 0

    if not acquire():
        rlog("已有监听实例在运行，本实例退出")
        return 0
    rlog("==== 指令监听启动 poll=%ds cooldown=%ds ====" % (POLL_SEC, COOLDOWN))
    try:
        while True:
            touch_lock()
            try:
                scan(load_state())
            except Exception as e:
                rlog("ERROR 扫描异常: %s\n%s" % (e, traceback.format_exc()[-300:]))
            time.sleep(POLL_SEC)
    finally:
        rlog("==== 指令监听结束 ====")
        release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
