#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
隐藏 ffmpeg 弹出的黑色终端窗口  (2026-11-14)

背景
----
电台连续播放由 pythonw.exe 常驻运行（本身无控制台）。它每录一段(默认 120 秒)
就会启动 imageio_ffmpeg 的 ffmpeg.exe —— 这是控制台程序，Windows 会为它新建
一个 Windows Terminal 窗口，于是桌面每隔两分钟闪出一个黑框。

根治
----
clawbot_to_folotoy.py::_run_ffmpeg 已加 CREATE_NO_WINDOW，**下次循环重启后**
ffmpeg 不再弹窗。本脚本负责覆盖「当前这版仍在运行的旧循环」：把已弹/会弹的
窗口立刻 ShowWindow(SW_HIDE)。只隐藏窗口，**不结束任何进程**，电台录制与播放
完全不受影响。

用法
----
  pythonw hide_ffmpeg_windows.py --loop    # 常驻（计划任务 \\AqingHideConsole）
  python  hide_ffmpeg_windows.py --once    # 扫描隐藏一次
  python  hide_ffmpeg_windows.py --show    # 恢复显示（调试/不想隐藏时用）
  python  hide_ffmpeg_windows.py --status  # 看守护是否活着、当前有几个可见窗口

停用：schtasks /change /disable /tn AqingHideConsole
"""
import os
import io
import sys
import time
import ctypes
import argparse
from ctypes import wintypes
from datetime import datetime

HERE       = os.path.dirname(os.path.abspath(__file__))
LOCK_PATH  = os.path.join(HERE, ".hide_ffmpeg.lock")
LOG_PATH   = os.path.join(HERE, "hide_ffmpeg.log")
MATCH      = ("imageio_ffmpeg", "ffmpeg-win")
POLL_SEC   = 0.1          # 100ms：过渡期把「先创建再隐藏」的一帧压到看不见
LOCK_STALE = 300          # 锁陈旧阈值(秒)；循环每秒刷新

SW_HIDE = 0
SW_SHOW = 5


def wlog(msg):
    line = "[hide] %s %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with io.open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def enum_targets(include_hidden=False):
    """列出标题命中 ffmpeg 的顶层窗口（默认只看可见的）。"""
    u = ctypes.windll.user32
    Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    out = []

    def cb(hwnd, _lp):
        if not include_hidden and not u.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(1024)
        u.GetWindowTextW(hwnd, buf, 1024)
        title = buf.value or ""
        if any(m in title for m in MATCH):
            out.append((hwnd, title))
        return True

    u.EnumWindows(Proc(cb), 0)
    return out


def hide_all():
    u = ctypes.windll.user32
    n = 0
    for hwnd, _title in enum_targets():
        if u.IsWindowVisible(hwnd):
            u.ShowWindow(hwnd, SW_HIDE)
            n += 1
    return n


def show_all():
    u = ctypes.windll.user32
    items = enum_targets(include_hidden=True)
    for hwnd, _title in items:
        u.ShowWindow(hwnd, SW_SHOW)
    return len(items)


def acquire():
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


def touch():
    try:
        os.utime(LOCK_PATH, None)
    except Exception:
        pass


def release():
    try:
        os.remove(LOCK_PATH)
    except Exception:
        pass


def status():
    alive = os.path.exists(LOCK_PATH) and \
            time.time() - os.path.getmtime(LOCK_PATH) < LOCK_STALE
    print("守护运行中       : %s" % ("YES" if alive else "NO"))
    print("当前可见黑窗口数 : %d" % len(enum_targets()))
    print("日志             : %s" % LOG_PATH)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    if a.status:
        return status()
    if a.show:
        n = show_all()
        print("已恢复显示 %d 个 ffmpeg 窗口" % n)
        return 0
    if a.once:
        n = hide_all()
        print("已隐藏 %d 个 ffmpeg 窗口" % n)
        return 0
    if not acquire():
        wlog("已有守护实例在运行，本实例退出")
        return 0

    wlog("==== 守护启动 poll=%.1fs ====" % POLL_SEC)
    try:
        while True:
            try:
                touch()
                n = hide_all()
                if n:
                    wlog("隐藏 %d 个 ffmpeg 终端窗口" % n)
            except Exception as e:
                wlog("ERROR %s" % e)
            time.sleep(POLL_SEC)
    finally:
        wlog("==== 守护结束 ====")
        release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
