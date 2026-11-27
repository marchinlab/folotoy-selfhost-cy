#!/usr/bin/env python3
import urllib.parse
# -*- coding: utf-8 -*-
"""动态抓包：逆向 FoloToy 主动播报(iwantplay)的真实 MQTT topic + payload 格式。
在 folotoy 容器内运行（能连 emqx:1883 和 emqx:18083）：
    docker exec -i folotoy_folotoy_1 python3 - < mqtt_sniff.py
流程：① 列所有客户端订阅 ② 订阅 # 抓全流量 ③ 主动发 iwantplay 测试 ④ 打印服务端日志
"""
import json, time, threading, urllib.request, base64

MQTT_HOST = "emqx"
MQTT_PORT = 1883
API = "http://emqx:18083/api/v5"
TOY = "DEVICEKEY_REDACTED"
TOPIC_CMD = "/user/folotoy/%s/thing/command/call" % TOY

import paho.mqtt.client as mqtt


def emqx_api(method, path, tok=None, data=None):
    h = {"Content-Type": "application/json"}
    if tok:
        h["Authorization"] = "Bearer " + tok
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(API + path, data=body, headers=h, method=method)
    raw = urllib.request.urlopen(req, timeout=8).read().decode()
    return json.loads(raw) if raw.strip() else None


def list_subscriptions():
    print("=== ① 所有客户端订阅关系（定 topic 结构）===")
    try:
        tok = emqx_api("POST", "/login", data={"username": "admin", "password": "public"})["token"]
        clients = emqx_api("GET", "/clients?limit=100", tok)
        clients = clients if isinstance(clients, list) else clients.get("data", [])
        for c in clients:
            cid = c.get("clientid")
            subs = emqx_api("GET", "/clients/" + urllib.parse.quote(cid) + "/subscriptions", tok)
            subs = subs if isinstance(subs, list) else subs.get("data", [])
            print("  [%s] user=%s" % (cid, c.get("username")))
            for s in subs:
                print("      SUB %-55s qos=%s" % (s.get("topic"), s.get("qos")))
    except Exception as e:
        print("  列订阅失败:", repr(e))


def main():
    import urllib.parse
    list_subscriptions()

    print("\n=== ② 订阅 # 抓全流量 30s，中途发 3 种 iwantplay 格式 ===")
    captured = []

    def on_connect(c, userdata, flags, *args):
        print("  [sniffer] connected, SUB #")
        c.subscribe("#", qos=0)

    def on_message(c, userdata, msg):
        try:
            payload = msg.payload.decode("utf-8", "replace")
        except Exception:
            payload = repr(msg.payload[:200])
        line = "%-60s | %s" % (msg.topic, payload[:400])
        captured.append(line)
        mark = "  <<<" if ("command" in msg.topic or "play" in msg.topic or "iwant" in payload or "url" in payload.lower()) else ""
        print("  [MQTT] " + line + mark)

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="folotoy-sniffer")
    c.connect(MQTT_HOST, MQTT_PORT, 60)
    c.on_connect = on_connect
    c.on_message = on_message
    c.loop_start()
    time.sleep(2)

    tests = [
        ("A_原猜测_sys", "/sys/folotoy/%s/thing/command/call" % TOY,
         {"msgId": 990001, "identifier": "iwantplay", "inputParams": {"role": 1, "text": "阿晴测试，听到我未？"}}),
        ("B_user前缀", TOPIC_CMD,
         {"msgId": 990002, "identifier": "iwantplay", "inputParams": {"role": 1, "text": "阿晴测试，听到我未？"}}),
        ("C_user带url", TOPIC_CMD,
         {"msgId": 990003, "identifier": "iwantplay", "inputParams": {"role": 1, "text": "阿晴测试，听到我未？", "voice": {"voiceName": "zh-HK-HiuMaanNeural"}}}),
    ]
    for name, topic, payload in tests:
        print("  >>> 发送 %s -> %s" % (name, topic))
        c.publish(topic, json.dumps(payload, ensure_ascii=False), qos=0)
        time.sleep(6)

    time.sleep(20)
    c.loop_stop()
    c.disconnect()

    print("\n=== ③ 服务端日志（找 Text to sound / send / play / 报错）===")
    try:
        import subprocess
        out = subprocess.run(["docker", "logs", "--since", "90s", "folotoy_folotoy_1"],
                             capture_output=True, text=True, timeout=15)
        lines = (out.stdout + out.stderr).splitlines()
        keep = [l for l in lines if any(k in l.lower() for k in
                ("text to sound", "send", "play", "iwant", "error", "warning", "audio", "tts", "transcrib"))]
        for l in keep[-40:]:
            print("  " + l[:300])
    except Exception as e:
        print("  日志读取失败:", repr(e))

    print("\n=== ④ 抓包小结：含 command/play/url 的消息共 %d 条 ===" %
          sum(1 for l in captured if "command" in l or "url" in l.lower() or "play" in l))


if __name__ == "__main__":
    main()
