# -*- coding: utf-8 -*-
"""重推同一条播放 URL，订阅玩具回执，确认它确实收到 iwantplay 指令。"""
import sys, json, time
sys.path.insert(0, "/app")
import yue_polish  # noqa
import paho.mqtt.client as mqtt

MQTT_HOST = "emqx"
SN = "DEVICEKEY_REDACTED"
URL = "http://YOUR_SERVER_IP:8082/aqing-news-DEVICEKEY_REDACTED.mp3"
CMD = "/sys/folotoy/%s/thing/command/call" % SN
ACK = "/sys/folotoy/+/thing/command/callAck"

got = []

def on_msg(c, u, m):
    payload = m.payload.decode("utf-8", "replace")
    got.append((m.topic, payload))
    print("RECV", m.topic, payload[:400], flush=True)

try:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ackprobe-%d" % (time.time() % 1e6))
except AttributeError:
    c = mqtt.Client(client_id="ackprobe-%d" % (time.time() % 1e6))
c.on_message = on_msg
c.connect(MQTT_HOST, 1883, 30)
c.subscribe(ACK, qos=0)
c.subscribe("/sys/folotoy/#", qos=0)
c.loop_start()
time.sleep(0.6)
msgid = int(time.time()) % 1000000
payload = {"msgId": msgid, "identifier": "iwantplay", "inputParams": {"url": URL}}
c.publish(CMD, json.dumps(payload, ensure_ascii=False), qos=0)
print("REPUB msgId=%d topic=%s" % (msgid, CMD), flush=True)
time.sleep(8)
c.loop_stop()
c.disconnect()
acks = [x for x in got if "callAck" in x[0]]
print("TOTAL_RECV", len(got), "ACKS", len(acks), flush=True)
print("TOY_REACHABLE", "YES" if acks else "UNKNOWN", flush=True)
