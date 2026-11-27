#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把网关 v1.46 嘅按键命令落到 Windows 侧执行  (2026-11-14)

链路
----
  火火兔按 1 号键讲一句
    -> llm_gateway.py 拦截(role_key=aqing_chat)，写 /audio/radio_cmd.json
       {seq, action:"set_station", station:"rthk2"}，回「轉咗香港電台第二台」
    -> 本脚本写 radio_station.json；radio_loop.py 每轮重读台号，
       当前段继续播完、下一段自动录新台 -> 播住换台、唔停播

  火火兔按对话键讲一句
    -> 网关拦截(role_key="")，写 {seq, action:"toggle", want:true/false}
    -> 本脚本调 radio_voice_ctl.act()：
       开始 = 清 STOP 标志 + 启用/运行 AqingRadioLoop
       暂停 = 禁用自愈 + radio_loop.py --stop（写标志 + 1 秒静音抢占）
    -> 写回 /audio/radio_state.json 实际状态（running + station）

设计
----
* 与 nginx / 网关共用 `/opt/folotoy/audio`（已 chmod 777），唔使调 wsl.exe。
* 按 seq 幂等：同一条命令绝唔会执行两次（防重复播报）。
* 首跑把当前 seq 当水位，唔回溯历史（部署测试留低嘅命令唔会打到正在播嘅电台）。
* 每轮只处理最新一条：连续快按两次等价于最终目标状态，唔会中途乱切。
* 独立锁 + 计划任务每分钟触发 = 崩溃自愈，唔会起第二个实例。
"""
import os
import io
import sys
import json
import time
import argparse
import traceback
from datetime import datetime

import radio_voice_ctl as ctl

HERE       = os.path.dirname(os.path.abspath(__file__))
AUDIO_UNC  = r"\\wsl$\$DISTRO\opt\folotoy\audio"
CMD_PATH   = os.path.join(AUDIO_UNC, "radio_cmd.json")
STATE_PATH = os.path.join(AUDIO_UNC, "radio_state.json")
STATION_PATH = os.path.join(HERE, "radio_station.json")  # 循环每轮重读，实现播住换台
LOCAL_ST   = os.path.join(HERE, ".radio_bridge_state.json")
LOG_PATH   = os.path.join(HERE, "radio_cmd_bridge.log")
LOCK_PATH  = os.path.join(HERE, ".radio_cmd_bridge.lock")
LOOP_LOCK  = os.path.join(HERE, ".radio_loop.lock")
LOCK_STALE = 45
POLL_SEC   = 1


def rlog(msg):
    line = "[bridge] %s %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with io.open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_local():
    try:
        with io.open(LOCAL_ST, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_seq": None}


def save_local(st):
    tmp = LOCAL_ST + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LOCAL_ST)


def write_state(running=None, station=None):
    """写共享状态；未指定嘅字段沿用旧值（防止 --set-state 抹走台号）。

    文件可能由容器内 root 建立(644)，Windows 侧直接覆盖会 PermissionError：
    用 tmp + os.replace（rename 只需目录写权限）；再兜底删后重建（目录已 777）。
    """
    old = {}
    try:
        with io.open(STATE_PATH, encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        pass
    obj = {
        "running": bool(old.get("running")) if running is None else bool(running),
        "station": str(old.get("station") or "rthk1") if station is None else str(station),
        "ts": time.time(),
    }
    payload = json.dumps(obj, ensure_ascii=False)
    tmp = STATE_PATH + ".tmp"
    try:
        with io.open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, STATE_PATH)
    except PermissionError:
        try:
            os.remove(STATE_PATH)          # 目录 777，删得走 root 属主文件
        except Exception:
            pass
        with io.open(STATE_PATH, "w", encoding="utf-8") as f:
            f.write(payload)


def set_station(sid):
    """只改台号文件；循环下一轮录制自动用新台，当前段继续播 -> 播住换、唔停播。"""
    tmp = STATION_PATH + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump({"station": sid, "ts": time.time()}, f, ensure_ascii=False)
    os.replace(tmp, STATION_PATH)


def loop_alive():
    return (os.path.exists(LOOP_LOCK) and
            time.time() - os.path.getmtime(LOOP_LOCK) < 900)


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


def read_cmd():
    try:
        with io.open(CMD_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def scan(st, dry=False):
    cmd = read_cmd()
    if not cmd:
        return
    seq = int(cmd.get("seq") or 0)
    if st["last_seq"] is None:
        st["last_seq"] = seq
        if not dry:
            save_local(st)
            # 启动时用真实循环状态校准一次，避免测试残留污染（台号保留）
            write_state(loop_alive())
        rlog("首跑水位 seq=%s（唔回溯历史）；实际状态 running=%s" %
             (seq, loop_alive()))
        return
    if seq <= st["last_seq"]:
        return
    action = str(cmd.get("action") or "toggle")
    rlog("新命令 seq=%s action=%s %s" % (seq, action, cmd))
    if dry:
        rlog("DRY-RUN 会执行 %s（未真执行）" % action)
    else:
        try:
            if action == "set_station":
                sid = str(cmd.get("station") or "").strip()
                if not sid:
                    rlog("ERROR set_station 缺 station，忽略")
                else:
                    set_station(sid)
                    write_state(None, sid)
                    rlog("换台 -> %s（循环下一段生效，当前段继续播）" % sid)
            else:
                want = bool(cmd.get("want"))
                kind = "play" if want else "stop"
                rlog("执行 %s" % kind)
                ctl.act(kind)
                write_state(want, None)
                rlog("执行完成，状态写回 running=%s" % want)
        except Exception as e:
            rlog("ERROR 执行失败: %s\n%s" % (e, traceback.format_exc()[-300:]))
    st["last_seq"] = seq
    if not dry:
        save_local(st)


def status():
    st = load_local()
    alive = os.path.exists(LOCK_PATH) and \
            time.time() - os.path.getmtime(LOCK_PATH) < LOCK_STALE
    print("命令桥接运行中 : %s" % ("YES" if alive else "NO"))
    print("已处理 seq     : %s" % st["last_seq"])
    print("当前命令       : %s" % read_cmd())
    try:
        with io.open(STATE_PATH, encoding="utf-8") as f:
            print("共享状态       : %s" % f.read().strip())
    except Exception as e:
        print("共享状态       : 读取失败 %s" % e)
    try:
        with io.open(STATION_PATH, encoding="utf-8") as f:
            print("当前台号       : %s" % f.read().strip())
    except Exception:
        print("当前台号       : (未设置，默认 rthk1)")
    print("电台循环       : %s" % ("运行中" if loop_alive() else "未运行"))
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
    ap.add_argument("--set-state", choices=["true", "false"],
                    help="手动同步共享状态（供 radio-play/stop.bat 调用）")
    a = ap.parse_args()

    if a.set_state:
        write_state(a.set_state == "true")   # station=None -> 保留当前台号
        rlog("手动同步状态 running=%s" % (a.set_state == "true"))
        print("state set to running=%s" % a.set_state)
        return 0
    if a.status:
        status()
        return 0
    if a.dry_run:
        scan(load_local(), dry=True)
        return 0
    if not a.loop:
        if not acquire():
            rlog("已有实例，跳过")
            return 0
        try:
            scan(load_local())
        finally:
            release()
        return 0

    if not acquire():
        rlog("已有桥接实例在运行，本实例退出")
        return 0
    rlog("==== 命令桥接启动 poll=%ds ====" % POLL_SEC)
    try:
        while True:
            touch_lock()
            try:
                scan(load_local())
            except Exception as e:
                rlog("ERROR 扫描异常: %s\n%s" % (e, traceback.format_exc()[-300:]))
            time.sleep(POLL_SEC)
    finally:
        rlog("==== 命令桥接结束 ====")
        release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
