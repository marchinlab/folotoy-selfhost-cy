#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
火火兔「按需单次推送电台」  (2026-11-14)

主人要求：取消自动连续播放，等指令才推一次。
本脚本录一段(默认 120 秒) -> 转 MP3 落盘 -> 只发一条 iwantplay -> 立即退出。
没有常驻进程、不启用任何计划任务、播完自然停，**不会自动续段**。

用法
----
  python radio_once.py                              # 香港电台第一台 / 120 秒
  python radio_once.py --station rthk2 --clip 300   # 换台 / 改片段时长
  python radio_once.py --dry-run                    # 只校验台源，不录不推
  radio-once.bat                                   # 双击

注意
----
* 火火兔只支持「下载完整 MP3 后播放」，所以是实时录的片段，不是直播流。
* 单次锁 .radio_once.lock 防止重复触发造成「一段播两遍」。
* 一条内容 = 一条 iwantplay；沿用 v1.45 铁律：callAck=YES 绝不重推。
"""
import os
import io
import sys
import time
import argparse
import traceback
from datetime import datetime

import clawbot_to_folotoy as b

HERE      = b.HERE
LOG_PATH  = os.path.join(HERE, "radio_once.log")
LOCK_PATH = os.path.join(HERE, ".radio_once.lock")
LOCK_STALE = 900          # 比最长片段还长，录制期间无需刷新


def rlog(msg):
    line = "[once] %s %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with io.open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def acquire():
    """单实例锁：防止连按两次导致同时录两段、推两条。"""
    try:
        if os.path.exists(LOCK_PATH):
            if time.time() - os.path.getmtime(LOCK_PATH) < LOCK_STALE:
                return False
            os.remove(LOCK_PATH)          # 崩溃残留
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--station", default=os.getenv("CB2FT_STATION", "rthk1"))
    ap.add_argument("--clip", type=int,
                    default=int(os.getenv("CB2FT_CLIP", "120")))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    stations = b.load_stations()
    st = stations.get(a.station)
    if not st:
        rlog("ERROR 未知电台 id=%s（可用 %d 个台，如 rthk1/rthk2/rthk5）" %
             (a.station, len(stations)))
        return 1

    rlog("单次推送 station=%s clip=%ds dry=%s" % (a.station, a.clip, a.dry_run))
    rlog("台源 %s" % str(st.get("url", ""))[:110])
    if a.dry_run:
        rlog("DRY-RUN：台源有效，未录制、未推送")
        return 0

    if not acquire():
        rlog("SKIP 已有一次推送在进行（或刚结束），本次不重复推")
        return 0

    try:
        b.CFG["radio_clip"] = a.clip
        item = {"id": int(time.time()), "text": "按需单次推送电台",
                "play": {"type": "radio", "id": a.station}}
        try:
            url = b.record_radio(item)
        except Exception as e:
            rlog("ERROR 录制异常: %s\n%s" % (e, traceback.format_exc()[-400:]))
            return 1
        if not url:
            rlog("ERROR 录制/落盘失败，未推送")
            return 1

        rlog("片段就绪: %s" % url)
        res = b.push_url(url)      # 唯一一条 iwantplay
        rlog("PUSH_RESULT=%s" % res)
        rlog("完成：这段播完即停，不会自动续播；要再听请再下指令")
        return 0 if res and res.get("puback") else 1
    finally:
        release()


if __name__ == "__main__":
    sys.exit(main())
