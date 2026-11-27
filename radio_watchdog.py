#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""电台看门狗（2026-11-21 建，2026-11-23 升级）：两大假死都救。

【假死 A：进程死了】running=true 但 loop 进程不存在 + 残留锁陈旧
     -> 清锁 + schtasks /run。
【假死 B：假活（11-23 新增）】loop 进程还在，但「长时间冇成功推送」
     典型场景：WSL/Docker 重启后，旧进程握着失效的 \\wsl$ 句柄，
     录制写唔入音频卷 / nginx 校验失败，进程空转几粒钟都唔出声。
     判定：radio_loop.log 最后一条成功 PUSH_RESULT 老过 STALL_THRESHOLD
     -> kill 旧进程 + 清锁 + schtasks /run（新进程重建 SMB 句柄）。

安全：
  - running=false（主人暂停）绝不动作。
  - 正常循环每 ~120s 推一次；阈值 420s 留足 3 倍余量，唔会误伤录制重试。
  - COOLDOWN 防止反复抖动；单实例锁防止重叠运行。
  - 唔碰 folotoy / stt / nginx / emqx 容器。

用法：
  python radio_watchdog.py --dry-run   # 只判定打印，不动作
  python radio_watchdog.py             # 实际执行
  python radio_watchdog.py --force     # 忽略冷却（手工排障用）
  python radio_watchdog.py --wake      # 唤醒触发：先等 WSL 就绪，自愈后复检推送
"""
import os
import io
import re
import sys
import time
import json
import argparse
import subprocess
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = r"\\wsl$\$DISTRO\opt\folotoy\audio"
STATE = os.path.join(AUDIO, "radio_state.json")
LOCK = os.path.join(HERE, ".radio_loop.lock")
SELF_LOCK = os.path.join(HERE, ".radio_watchdog.lock")
LAST_HEAL = os.path.join(HERE, ".radio_watchdog_lastheal")
LOG = os.path.join(HERE, "radio_watchdog.log")
RADIO_LOG = os.path.join(HERE, "radio_loop.log")
TASK = "AqingRadioLoop"

STALE_LOCK = 240        # 锁老过呢个秒数先当崩溃残留（正常每轮 touch <120s）
STALL_THRESHOLD = 420   # 假活阈值：正常每 ~120s 推一次，7 分钟无成功推送即空转
COOLDOWN = 300          # 两次自愈最小间隔
WAKE_READY_WAIT = 120   # 唤醒模式：最多等音频卷就绪 120s（WSL/Docker 起身）
WAKE_VERIFY_DELAY = 45  # 唤醒自愈后等 45s 复检有无新推送，冇就再修一次
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PS = ("Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | "
      "Where-Object { $_.CommandLine -like '*radio_loop.py*' } | "
      "Select-Object -ExpandProperty ProcessId")


def wlog(msg):
    line = "[wd] %s %s\n" % (datetime.now().strftime("%H:%M:%S"), msg)
    try:
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    print(line.rstrip(), flush=True)


def run(args, timeout=30):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout,
                           creationflags=NOWIN)
        return p.returncode, (p.stdout or b"").decode("utf-8", "replace").strip()
    except Exception as e:
        return -1, str(e)


def loop_pids():
    rc, out = run(["powershell.exe", "-NoProfile", "-Command", PS])
    return [int(x) for x in out.split() if x.strip().isdigit()]


def read_state():
    try:
        with io.open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def last_push_age():
    """距最后一次「成功推送」嘅秒数（读 radio_loop.log 最后一条 PUSH_RESULT ack=True）。
    读唔到就退化用日志文件 mtime。返 None 表示完全攞唔到。
    """
    try:
        with io.open(RADIO_LOG, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        now = datetime.now()
        for ln in reversed(lines):
            if "PUSH_RESULT=" not in ln or "True" not in ln:
                continue
            m = re.search(r"\[radio\]\s+(\d{2}):(\d{2}):(\d{2})", ln)
            if not m:
                continue
            hh, mm, ss = (int(x) for x in m.groups())
            t = now.replace(hour=hh, minute=mm, second=ss, microsecond=0)
            if t > now:                     # 跨日：日志时间属琴日
                t -= timedelta(days=1)
            return max(0.0, (now - t).total_seconds())
        return time.time() - os.path.getmtime(RADIO_LOG)
    except Exception:
        return None


def wait_audio_ready(max_wait=WAKE_READY_WAIT):
    """唤醒后 WSL/Docker/网络未必即刻起身，轮询等音频卷 + state 可读。
    UNC \\wsl$ 句柄失效/未挂载时 os.path.isdir 会 False，读到就返回 True。
    """
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            if os.path.isdir(AUDIO) and os.path.exists(STATE):
                with io.open(STATE, encoding="utf-8") as f:
                    json.load(f)
                return True
        except Exception:
            pass
        time.sleep(5)
    return False


def verify_wake_heal(dry_run=False):
    """唤醒自愈后复检：等 WAKE_VERIFY_DELAY 秒，看有无新推送。
    如果依然超过假活阈值，再自愈一次（force 绕过冷却），避免白救一场。
    """
    if dry_run:
        return
    time.sleep(WAKE_VERIFY_DELAY)
    age = last_push_age()
    if age is not None and age < STALL_THRESHOLD:
        wlog("WAKE VERIFY OK 最近推送 %.0fs 前" % age)
        return
    wlog("WAKE VERIFY FAIL 仍无新推送(age=%s)，再自愈一次" % age)
    heal("唤醒复检仍无推送", loop_pids(), False, True)


def last_heal_age():
    try:
        return time.time() - os.path.getmtime(LAST_HEAL)
    except Exception:
        return float("inf")


def self_lock():
    """防止看门狗自己重叠运行（每 2 分钟触发，正常 1 秒内完成）。"""
    try:
        if os.path.exists(SELF_LOCK) and time.time() - os.path.getmtime(SELF_LOCK) < 120:
            return False
        with io.open(SELF_LOCK, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return False


def heal(reason, pids, dry_run, force):
    """统一自愈动作：kill 旧进程（如有）-> 清锁 -> 重启循环。"""
    age = last_heal_age()
    if not force and age < COOLDOWN:
        wlog("SKIP 冷却中(上次自愈 %.0fs 前 < %ds)" % (age, COOLDOWN))
        return 0
    if dry_run:
        wlog("DRY-RUN 会自愈：%s -> kill%s + 清锁 + /run %s" %
             (reason, pids, TASK))
        return 0
    if not self_lock():
        wlog("SKIP 另一个看门狗实例运行紧")
        return 0
    for pid in pids:
        rc, out = run(["taskkill", "/PID", str(pid), "/F"])
        wlog("kill 旧循环 PID=%s rc=%s" % (pid, rc))
    try:
        if os.path.exists(LOCK):
            os.remove(LOCK)
            wlog("删除残留锁")
    except Exception as e:
        wlog("WARN 删锁失败 %r" % e)
    rc, out = run(["schtasks", "/run", "/tn", TASK])
    wlog("HEAL %s -> schtasks /run rc=%s %s" % (reason, rc, out[:80]))
    try:
        with io.open(LAST_HEAL, "w", encoding="utf-8") as f:
            f.write(datetime.now().isoformat())
    except Exception:
        pass
    time.sleep(3)
    wlog("自愈后进程 PIDs=%s" % loop_pids())
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--wake", action="store_true",
                    help="唤醒触发：先等 WSL 音频卷就绪，自愈后复检推送")
    a = ap.parse_args()

    if a.wake and not a.dry_run:
        wlog("WAKE 唤醒触发：等音频卷就绪(最多 %ds)" % WAKE_READY_WAIT)
        if not wait_audio_ready():
            wlog("WAKE FAIL 音频卷 %ds 内未就绪，交给 2 分钟任务重试" % WAKE_READY_WAIT)
            return 2
        wlog("WAKE READY 音频卷可访问")

    st = read_state()
    running = bool(st.get("running"))
    pids = loop_pids()
    lock_age = (time.time() - os.path.getmtime(LOCK)) if os.path.exists(LOCK) else None
    push_age = last_push_age()

    wlog("CHECK running=%s loop_pids=%s lock_age=%s push_age=%s" %
         (running, pids,
          ("%.0fs" % lock_age) if lock_age is not None else "none",
          ("%.0fs" % push_age) if push_age is not None else "none"))

    if not running:
        wlog("SKIP 主人已暂停(running=false)，唔动作")
        return 0

    # --- 假死 B：进程活着但长期冇成功推送（假活 / 空转）---
    if pids and push_age is not None and push_age > STALL_THRESHOLD:
        n = heal("假活：%.0fs 无成功推送(阈值%ds)" %
                 (push_age, STALL_THRESHOLD), pids, a.dry_run, a.force)
        if a.wake and n:
            verify_wake_heal(a.dry_run)
        return n

    # --- 进程正常 ---
    if pids:
        wlog("OK 循环进程存活 PIDs=%s，最近推送 %.0fs 前，无需动作" %
             (pids, push_age if push_age is not None else -1))
        return 0

    # --- 假死 A：无进程 + 锁残留 ---
    if lock_age is not None and lock_age < STALE_LOCK:
        wlog("SKIP 锁未过期(%.0fs < %ds)，可能系热重启瞬间，观察下一次" %
             (lock_age, STALE_LOCK))
        return 0
    reason = "锁残留%.0fs" % lock_age if lock_age is not None else "无锁无进程"
    n = heal(reason, [], a.dry_run, a.force)
    if a.wake and n:
        verify_wake_heal(a.dry_run)
    return n


if __name__ == "__main__":
    sys.exit(main())
