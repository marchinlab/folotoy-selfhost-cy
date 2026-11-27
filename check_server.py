#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""部署完自建服务端后、切换火火兔之前，先跑这个检查端口是否真的通。
用法: python check_server.py 1.2.3.4
"""
import sys
import socket
import struct
import argparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def tcp_mqtt(host, port=1883, timeout=4):
    """真做一次 MQTT CONNECT 握手，比单纯测端口更可靠。"""
    cid = b"folotoy-probe"
    variable = b"\x00\x04MQTT\x04\x02\x00\x3c" + struct.pack("!H", len(cid)) + cid
    packet = b"\x10" + bytes([len(variable)]) + variable
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(packet)
        data = s.recv(4)
        s.close()
        if len(data) >= 4 and data[0] == 0x20:
            code = data[3]
            return (code == 0), "CONNACK 返回码=%d %s" % (code, "接受连接" if code == 0 else "被拒绝")
        return False, "没收到 CONNACK，收到: %r" % data
    except Exception as e:
        return False, str(e)


def tcp_http(host, port=8082, timeout=4):
    """nginx 音频目录：只要回 HTTP 响应就算通（403 也算，说明服务在跑）。"""
    req = ("GET / HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n" % host).encode()
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(req)
        data = s.recv(256)
        s.close()
        if data.startswith(b"HTTP/"):
            return True, data.split(b"\r\n", 1)[0].decode(errors="replace")
        return False, "非 HTTP 响应: %r" % data[:60]
    except Exception as e:
        return False, str(e)


def udp_voice(host, port=8085, timeout=2):
    """UDP 无连接，服务端不会回探测包，这里只能排除『明确不可达』。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.sendto(b"\x00", (host, port))
        try:
            data, _ = s.recvfrom(256)
            s.close()
            return True, "收到回包 %d 字节" % len(data)
        except socket.timeout:
            s.close()
            return True, "无回包（正常，服务端不响应探测包）；仍需以实际对话验证"
        except (ConnectionRefusedError, ConnectionResetError):
            # Windows 上 UDP 收到 ICMP port unreachable 常表现为 WSAECONNRESET(10054)
            s.close()
            return False, "ICMP port unreachable，UDP 端口未监听或未放行"
    except Exception as e:
        return False, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("host", help="云电脑公网 IP 或域名")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--http-port", type=int, default=8082)
    ap.add_argument("--udp-port", type=int, default=8085)
    a = ap.parse_args()

    try:
        ip = socket.gethostbyname(a.host)
    except Exception as e:
        print("[FAIL] 域名解析失败: %s" % e)
        return 1
    print("目标: %s -> %s\n" % (a.host, ip))

    checks = [
        ("1883/tcp MQTT 握手", lambda: tcp_mqtt(a.host, a.mqtt_port)),
        ("8082/tcp 音频下载", lambda: tcp_http(a.host, a.http_port)),
        ("8085/udp 语音上传", lambda: udp_voice(a.host, a.udp_port)),
    ]
    ok = True
    for name, fn in checks:
        good, detail = fn()
        print("[%s] %-22s %s" % ("PASS" if good else "FAIL", name, detail))
        ok = ok and good

    print()
    if not ok:
        print("有端口不通。检查顺序：")
        print("  1) 云电脑: docker compose ps  确认 emqx / nginx / folotoy 都是 Up")
        print("  2) 云电脑: ss -lntup | grep -E '1883|8082|8085'  看端口有没有监听")
        print("  3) 云厂商安全组 + 系统防火墙（firewalld/ufw/iptables）都要放行")
        print("  4) 8085 必须是 UDP，只开 TCP 无效；HTTP 隧道不转发 UDP")
        return 1
    print("基本连通。可以继续跑 switch_broker.py 切换火火兔。")
    print("注意 UDP 是尽力探测，最终以玩具实际能对话为准。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
