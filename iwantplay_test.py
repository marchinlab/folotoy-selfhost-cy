#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证主动播报 iwantplay 协议：发播放指令 + 订阅 callAck 回执。
在 folotoy 容器内运行：docker exec -i folotoy_folotoy_1 python3 - < iwantplay_test.py
"""
import json, time, sys
import paho.mqtt.client as mqtt

SN = "DEVICEKEY_REDACTED"
TOPIC_CMD = "/sys/folotoy/%s/thing/command/call" % SN      # 发给服务端（文档权威格式）
TOPIC_CMD_USER = "/user/folotoy/%s/thing/command/call" % SN  # 玩具实际订阅
TOPIC_ACK = "/sys/folotoy/+/thing/command/callAck"
TOPIC_ACK_USER = "/user/folotoy/+/thing/command/callAck"

acks = []
events = []


def on_connect(c, userdata, flags, *args):
    print("  [conn] rc=%s, 订阅 ACK + event" % (args[0] if args else flags))
    c.subscribe(TOPIC_ACK, qos=0)
    c.subscribe(TOPIC_ACK_USER, qos=0)
    c.subscribe("/sys/folotoy/+/thing/event/post", qos=0)
    c.subscribe("/user/folotoy/+/thing/event/postAck", qos=0)


def on_message(c, userdata, msg):
    try:
        p = msg.payload.decode("utf-8", "replace")
    except Exception:
        p = repr(msg.payload[:200])
    print("  [RECV] %-58s | %s" % (msg.topic, p[:300]))
    if "callAck" in msg.topic:
        acks.append((msg.topic, p))
    else:
        events.append((msg.topic, p))


def mkc():
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="iwantplay-test")
    except AttributeError:
        c = mqtt.Client(client_id="iwantplay-test")
    c.on_connect = on_connect
    c.on_message = on_message
    return c


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "text"
    c = mkc()
    c.connect("emqx", 1883, 60)
    c.loop_start()
    time.sleep(2)

    if mode == "text":
        payload = {"msgId": 88001, "identifier": "iwantplay",
                   "inputParams": {"role": 1, "text": "阿晴测试，我系广州西关嘅阿晴，听到我讲话吗？"}}
    elif mode == "url":
        payload = {"msgId": 88002, "identifier": "iwantplay",
                   "inputParams": {"url": "http://YOUR_SERVER_IP:8082/voice-test.mp3"}}
    else:
        payload = {"msgId": 88003, "identifier": "iwantplay",
                   "inputParams": {"role": 1, "text": "阿晴测试，听到我讲话吗？"}}

    print(">>> 发到 %s : %s" % (TOPIC_CMD, json.dumps(payload, ensure_ascii=False)))
    c.publish(TOPIC_CMD, json.dumps(payload, ensure_ascii=False), qos=0)
    time.sleep(1)
    print(">>> 同时发到 %s（对比）" % TOPIC_CMD_USER)
    c.publish(TOPIC_CMD_USER, json.dumps(payload, ensure_ascii=False), qos=0)

    print(">>> 等 12s 收 ACK / 事件 ...")
    time.sleep(12)
    c.loop_stop()
    c.disconnect()

    print("\n=== 结果 ===")
    print("ACK 数:", len(acks), "| 其他事件数:", len(events))
    if acks:
        print("主动播报指令被服务端/玩具应答 -> 协议可用 ✅")
    else:
        print("无 ACK：可能 INTEGRATION_MQTT=false 拦了 /sys/ topic，或玩具未唤醒")


if __name__ == "__main__":
    main()
