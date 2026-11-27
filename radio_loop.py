#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
火火兔「电台一直播」循环 + 开播/暂停/播住换台控制  (2026-11-14 v1.46)

原理
----
火火兔只支持「下载完整 MP3 后播放」，不接受直播流。所以连续播放的做法是：
  推一段(clip 秒) -> 设备播放这段的同时，本机实时录下一段(clip 秒)
  -> 录完立刻推下一段 -> 无缝接上，如此循环。
录制耗时与播放耗时天然对齐，不需要多线程，也不会重复推送（每段只发 1 条 iwantplay）。

控制
----
  开始：radio-play.bat   （= 清停止标志 + 运行计划任务 AqingRadioLoop）
  暂停：radio-stop.bat   （= 写停止标志 + 推 1 秒静音抢占当前播放）
  换台：1 号键 -> 网关写命令 -> radio_cmd_bridge.py 写 radio_station.json
        本循环每轮重读台号，当前段播完、下一段自动录新台（唔停播、唔重播）
  状态：python radio_loop.py --status

停止语义
--------
写 radio.stop 后，循环在「当前这段录完/推完」时退出，不再续推；
同时 --stop 会额外发一条 1 秒静音 iwantplay 尝试立即抢占播放。
设备若在播放中忽略新指令，则以当前片段播完为准（最多 clip 秒）。
"""
import os
import io
import sys
import glob
import json
import time
import argparse
import traceback
from datetime import datetime

import clawbot_to_folotoy as b

HERE       = b.HERE
STOP_FLAG  = os.path.join(HERE, "radio.stop")
LOCK_PATH   = os.path.join(HERE, ".radio_loop.lock")
RESUME_FLAG = os.path.join(HERE, ".radio_loop.resume")   # 热重启一次性标志
STATION_PATH = os.path.join(HERE, "radio_station.json")  # 由桥接写入，每轮重读
FALLBACK_STATION = "rthk1"
LOG_PATH    = os.path.join(HERE, "radio_loop.log")
LOCK_STALE = 900          # 锁陈旧阈值(秒)；循环每轮都会刷新，正常不会触发


def rlog(msg):
    line = "[radio] %s %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    try:
        print(line, flush=True)          # pythonw 下 stdout 可能为 None
    except Exception:
        pass
    try:
        with io.open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def touch_lock():
    try:
        with open(LOCK_PATH, "a"):
            pass
        os.utime(LOCK_PATH, None)
    except Exception:
        pass


def acquire():
    """单实例锁：防止计划任务每分钟触发时启动第二个循环造成双推。"""
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


def stopping():
    return os.path.exists(STOP_FLAG)


def clear_stop():
    try:
        os.remove(STOP_FLAG)
    except Exception:
        pass


def current_station(default):
    """读桥接写入嘅台号；校验喺电台源表内，唔合法就退回默认台。"""
    try:
        with io.open(STATION_PATH, encoding="utf-8") as f:
            sid = str(json.load(f).get("station") or "").strip()
        if sid and sid in b.load_stations():
            return sid
        if sid:
            rlog("WARN 台号 %s 唔喺电台源表，改用 %s" % (sid, FALLBACK_STATION))
    except Exception:
        pass
    return default


def force_station(sid):
    """录制连续失败时兜底返第一台，并同步网关/桥接嘅共享状态。"""
    tmp = STATION_PATH + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump({"station": sid, "ts": time.time()}, f, ensure_ascii=False)
    os.replace(tmp, STATION_PATH)
    try:
        import radio_cmd_bridge as bridge
        bridge.write_state(None, sid)
    except Exception as e:
        rlog("WARN 同步共享状态失败: %s" % e)


# v1.47：旧值 1800s。2026-11-15 停机 51 分钟后开播，缓存过期 -> 干等 120s
# 先录第一段，主人报「按 1 键没反应」。放宽到 6 小时，开机即刻有声。
REUSE_MAX_AGE = 6 * 3600


def find_reusable(station):
    """复用最近录好的片段，让开播立刻出声（唔使先等 clip 秒录制）。

    先搵同台；同台太旧就退到任意台片段（最多播 120 秒旧内容，循环随即
    接上新录嗰段）。片段只系录播缓存，唔会长期停留喺旧内容。
    """
    now = time.time()

    def _pick(pattern):
        for p in sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True):
            if now - os.path.getmtime(p) < REUSE_MAX_AGE and os.path.getsize(p) > 10000:
                return os.path.basename(p)
        return None

    name = _pick(os.path.join(b.CFG["audio_unc"], "bridge-radio-%s-*.mp3" % station))
    if name:
        return name
    return _pick(os.path.join(b.CFG["audio_unc"], "bridge-radio-*.mp3"))


def do_stop():
    """暂停：写标志 + 推 1 秒静音抢占。只发一条指令，不是重复播报。"""
    with io.open(STOP_FLAG, "w", encoding="utf-8") as f:
        f.write(datetime.now().isoformat())
    rlog("STOP 标志已写入；循环将在本段结束后退出")
    tmp = os.path.join(HERE, "_radio_silence.mp3")
    try:
        ok = b._run_ffmpeg(
            ["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", "1", "-ac", "1", "-ar", "24000",
             "-c:a", "libmp3lame", "-b:a", "64k", tmp], 30)
        if ok:
            url = b.publish_file(tmp, "bridge-silence.mp3")
            if url:
                rlog("推一条 1 秒静音尝试立即抢占: %s" % url)
                rlog("PUSH_RESULT=%s" % b.push_url(url))
            else:
                rlog("WARN 静音落盘失败，仅靠停止标志（本段播完即停）")
        else:
            rlog("WARN 静音生成失败，仅靠停止标志（本段播完即停）")
    except Exception as e:
        rlog("WARN 静音抢占异常: %s" % e)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    return 0


def do_status():
    alive = os.path.exists(LOCK_PATH) and \
            time.time() - os.path.getmtime(LOCK_PATH) < LOCK_STALE
    print("循环运行中 : %s" % ("YES" if alive else "NO"))
    print("停止标志   : %s" % ("已设置" if stopping() else "无"))
    print("当前台号   : %s（默认 %s）" % (current_station("rthk1"), "rthk1"))
    print("片段长度   : 120s (默认)")
    print("日志       : %s" % LOG_PATH)
    if os.path.exists(LOG_PATH):
        with io.open(LOG_PATH, encoding="utf-8") as f:
            lines = f.readlines()[-8:]
        print("--- 最近日志 ---")
        for l in lines:
            print(l.rstrip())
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--station", default="rthk1")
    ap.add_argument("--clip", type=int, default=120)
    ap.add_argument("--no-reuse", action="store_true")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    if a.status:
        return do_status()
    if a.stop:                      # 停止模式不拿锁（循环进程正持有）
        return do_stop()
    if not acquire():
        rlog("已有循环实例在运行，本实例退出")
        return 0

    # 热重启：外部写 .radio_loop.resume 标志。此时设备正在播刚推的一段，
    # 跳过「复用首段立刻推送」，直接开始录下一段 -> 零重播、零静音。
    resume = os.path.exists(RESUME_FLAG)
    if resume:
        try:
            os.remove(RESUME_FLAG)
        except Exception:
            pass

    station = current_station(a.station)
    b.CFG["radio_clip"] = a.clip
    rlog("==== 连续播放启动 station=%s clip=%ds%s ====" %
         (station, a.clip, " [热重启]" if resume else ""))
    try:
        if stopping():
            clear_stop()            # 开播时清掉上次的停止标志

        if resume:
            rlog("热重启：跳过首段复用推送，直接续录（当前已有段在播）")

        # ① 立刻复用最近一段，避免开播先干等 clip 秒
        if not a.no_reuse and not resume:
            name = find_reusable(station)
            if name:
                local = b.CFG["verify_base"].rstrip("/") + "/" + name
                if b.http_ok(local):
                    url = b.CFG["audio_base"].rstrip("/") + "/" + name
                    rlog("立即播首段(复用 %s)" % name)
                    rlog("PUSH_RESULT=%s" % b.push_url(url))
                else:
                    rlog("WARN 复用段 nginx 不可达，跳过")
            else:
                rlog("无可复用片段，直接进入录制循环")

        # ② 录制下一段(clip 秒) === 设备播放上一段的时间，天然无缝
        fail = 0
        while True:
            if stopping():
                rlog("收到 STOP：不再续推，退出（当前段播完自然停）")
                clear_stop()
                break
            touch_lock()
            station = current_station(a.station)   # 每轮重读台号 -> 播住换台
            seg = int(time.time())
            rlog("录制下一段 %s %ds ..." % (station, a.clip))
            try:
                url = b.record_radio({
                    "id": seg, "text": "电台连续播放",
                    "play": {"type": "radio", "id": station}})
            except Exception as e:
                rlog("ERROR 录制异常: %s\n%s" % (e, traceback.format_exc()[-400:]))
                url = None
            touch_lock()
            if not url:
                fail += 1
                if fail >= 3:
                    rlog("连续 %d 次录制失败，兜底返 %s" % (fail, FALLBACK_STATION))
                    force_station(FALLBACK_STATION)
                    fail = 0
                rlog("录制失败，10 秒后重试（期间可被 STOP 打断）")
                for _ in range(10):
                    if stopping():
                        break
                    time.sleep(1)
                continue
            fail = 0
            if stopping():
                rlog("录完但收到 STOP：丢弃该段不推送，退出")
                clear_stop()
                break
            rlog("推送下一段 %s" % url)
            rlog("PUSH_RESULT=%s" % b.push_url(url))
            try:
                b.cleanup_mp3()      # 只删最旧的 bridge-*.mp3，保留 keep_mp3 个
            except Exception:
                pass
    finally:
        rlog("==== 连续播放结束 ====")
        release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
