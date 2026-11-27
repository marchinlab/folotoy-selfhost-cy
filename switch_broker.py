#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把火火兔从官方服务器 f.folotoy.cn 切到自己的 FoloToy 服务端，或一键回滚。
依赖: pip install pyserial   （本机 esptool 已带，通常不用再装）

用法:
  python switch_broker.py --host 1.2.3.4            # 切到自建服务器
  python switch_broker.py --rollback                 # 切回官方服务器
  python switch_broker.py --host 1.2.3.4 --dry-run  # 只看计划，不写设备
  python switch_broker.py --port COM6 --host folo.example.com --mqtt-port 1883

重要: 实测 AT 指令只能用 \\n 结尾，用 \\r\\n 会返回 "Invalid keyName in the command"；
      AT 只开放 mqtt.broker / mqtt.port，改不了 udpSpeechServer.address，
      该地址由服务端连上后下发，所以切换后必须重启并再读一次配置确认。
"""
import sys
import os
import re
import json
import time
import socket
import argparse
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import serial
except ImportError:
    sys.exit("缺少 pyserial，请先执行: pip install pyserial")

OFFICIAL_BROKER = "f.folotoy.cn"
HERE = os.path.dirname(os.path.abspath(__file__))


def open_serial(port, retries=3, interval=1.5):
    """玩具休眠、USB 重新枚举、或被别的串口工具占用时，打开会失败，重试几次。"""
    last = None
    for _ in range(retries):
        try:
            s = serial.Serial(port, 115200, timeout=0.2)
            # 不要把 DTR/RTS 拉成下载模式，否则玩具会复位进 bootloader
            s.setDTR(False)
            s.setRTS(False)
            time.sleep(0.4)
            s.reset_input_buffer()
            return s
        except serial.SerialException as e:
            last = e
            time.sleep(interval)
    raise RuntimeError(
        "打不开串口 %s：%s\n"
        "常见原因：\n"
        "  1) 玩具关机或休眠了 —— 只插 USB 不够，要把玩具开机（设备管理器里端口状态应为 OK）\n"
        "  2) tool.folotoy.com 的串口日志、串口监视器或其他程序占着这个 COM 口\n"
        "  3) USB 正在重新枚举 —— 拔插一次数据线再试\n"
        % (port, last)
    )


def at(s, cmd, wait=2.0):
    """发一条 AT 指令并返回设备回显。指令必须小写、只用 \\n 结尾。"""
    s.write((cmd + "\n").encode("ascii"))
    buf = bytearray()
    t = time.time()
    while time.time() - t < wait:
        n = s.in_waiting
        if n:
            buf += s.read(n)
        else:
            time.sleep(0.05)
    return bytes(buf).decode("utf-8", "replace")


def read_config(s):
    txt = at(s, "at+config=?", wait=3.0)
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise RuntimeError("读不到配置文件，设备回显: %r" % txt[:300])
    return json.loads(m.group(0))


def expect_ok(reply, cmd):
    if "Invalid" in reply or "OK" not in reply:
        raise RuntimeError("指令失败: %s\n设备回显: %s" % (cmd, reply.strip()))
    return True


def check_tcp(host, port):
    try:
        s = socket.create_connection((host, port), timeout=3)
        s.close()
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM6", help="玩具串口，默认 COM6")
    ap.add_argument("--host", help="云电脑公网 IP / 域名")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--http-port", type=int, default=8082)
    ap.add_argument("--rollback", action="store_true", help="切回官方服务器 f.folotoy.cn")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不改设备")
    ap.add_argument("--no-check", action="store_true", help="跳过切换前的端口连通性检查")
    a = ap.parse_args()

    target = OFFICIAL_BROKER if a.rollback else a.host
    if not target:
        ap.error("需要 --host <公网IP/域名>，或 --rollback")
    target = target.strip().replace("http://", "").replace("https://", "").rstrip("/")

    print("串口: %s" % a.port)
    print("目标 MQTT broker: %s:%d" % (target, a.mqtt_port))
    print("模式: %s\n" % ("回滚到官方服务器" if a.rollback else ("试运行(不写入)" if a.dry_run else "切换到自建服务器")))

    if not a.rollback and not a.no_check and not a.dry_run:
        print("切换前连通性检查...")
        try:
            socket.gethostbyname(target)
        except Exception as e:
            print("[FAIL] 域名解析失败: %s" % e)
            return 1
        mqtt_ok = check_tcp(target, a.mqtt_port)
        http_ok = check_tcp(target, a.http_port)
        print("  1883/tcp MQTT : %s" % ("PASS" if mqtt_ok else "FAIL"))
        print("  8082/tcp HTTP : %s" % ("PASS" if http_ok else "FAIL"))
        print("  8085/udp      : 无法可靠探测，请确认安全组已放行 UDP")
        if not (mqtt_ok and http_ok):
            print("\nTCP 端口不通，已中止切换（避免玩具改完就失联）。")
            print("先跑 python check_server.py %s 排查。" % target)
            return 1
        print("")

    try:
        s = open_serial(a.port)
    except RuntimeError as e:
        print("[FAIL] %s" % e)
        print("\n脚本本身已就绪；等玩具开机/重新插线后再跑一次即可。")
        return 1
    try:
        cfg = read_config(s)
        old_broker = cfg["mqtt"]["broker"]
        old_udp = cfg["udpSpeechServer"]["address"]
        print("当前配置:")
        print("  mqtt.broker            = %s" % old_broker)
        print("  mqtt.port              = %s" % cfg["mqtt"]["port"])
        print("  udpSpeechServer.address= %s" % old_udp)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = os.path.join(HERE, "device_config_%s.json" % stamp)
        with open(backup, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print("  已备份 -> %s" % backup)

        if a.dry_run:
            print("\n试运行结束，未写入任何配置。")
            print("真正切换时会执行:")
            print("  at+config=mqtt,broker,%s" % target)
            print("  at+config=mqtt,port,%d" % a.mqtt_port)
            print("  at+reboot")
            return 0

        if old_broker == target and cfg["mqtt"]["port"] == a.mqtt_port:
            print("\nbroker 已经是目标值，无需重复写入。")
        else:
            expect_ok(at(s, "at+config=mqtt,broker,%s" % target), "at+config=mqtt,broker")
            expect_ok(at(s, "at+config=mqtt,port,%d" % a.mqtt_port), "at+config=mqtt,port")
            time.sleep(0.5)
            cfg2 = read_config(s)
            print("\n写入后校验: mqtt.broker = %s, port = %s" % (cfg2["mqtt"]["broker"], cfg2["mqtt"]["port"]))
            if cfg2["mqtt"]["broker"] != target:
                raise RuntimeError("broker 没写进去，请检查设备回显")

        print("\n重启设备（让新 broker 生效，并接收服务端下发的 UDP 地址）...")
        at(s, "at+reboot", wait=1.5)
    finally:
        s.close()

    print("等待 10 秒重连...")
    time.sleep(10)
    try:
        s2 = open_serial(a.port)
        try:
            cfg3 = read_config(s2)
        finally:
            s2.close()
        print("\n重启后配置:")
        print("  mqtt.broker            = %s" % cfg3["mqtt"]["broker"])
        print("  udpSpeechServer.address= %s" % cfg3["udpSpeechServer"]["address"])
        if a.rollback:
            print("\n已回到官方服务器，开机试一下对话。")
        else:
            if cfg3["udpSpeechServer"]["address"] == OFFICIAL_BROKER:
                print("\n[注意] UDP 地址仍是官方域名，服务端没下发新地址。")
                print("  检查 docker-compose 的 SPEECH_UDP_SERVER_HOST 是否填了公网地址，")
                print("  改完执行 docker compose up -d 后再把玩具关机重开一次。")
            else:
                print("\nUDP 地址已更新，开机按对话键实测一次。")
    except Exception as e:
        print("重启后没读到配置（玩具可能在休眠或未开机）: %s" % e)
        print("手动开机后运行: python switch_broker.py --host %s --no-check 复查" % target)

    print("\n回滚命令: python switch_broker.py --rollback")
    return 0


if __name__ == "__main__":
    sys.exit(main())
