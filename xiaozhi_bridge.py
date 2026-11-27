#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可选进阶：把火火兔的对话事件接进本机 ClawBot（它已连 wss://api.xiaozhi.me/mcp/ 的小智 MCP）。

这是「接入小智AI」的第三条路：不改 FoloToy 固件、不换模型，
让火火兔说的话能进入 ClawBot / 小智 MCP 生态，并能把工具结果念回玩具。

前置条件:
  1) 服务端 .env 里 INTEGRATION_MQTT=true，然后 docker compose up -d
  2) 本机 pip install paho-mqtt
  3) 环境变量:
       MQTT_HOST=<云电脑公网IP>        必填
       MQTT_PORT=1883                  可选
       CLAWBOT_BASE=http://127.0.0.1:3000   可选
       CLAWBOT_ADMIN_KEY=<管理密钥>     --forward / --tool 时必填（不要写进代码）
       BRIDGE_TRIGGER=小智              可选，触发词

用法:
  python xiaozhi_bridge.py --listen
      只订阅并打印事件，完全不干预 FoloToy 自己的对话。先用这个看清事件格式。
  python xiaozhi_bridge.py --forward
      把用户说的话 POST 到 ClawBot /api/inbox-push（进入收件箱/小智生态）。
  python xiaozhi_bridge.py --tool <MCP工具名>
      用户说的话以触发词开头时，调用 ClawBot /api/mcp-run 执行小智 MCP 工具，
      再把返回文本通过 MQTT iwantplay 让火火兔念出来。
      （工具名可在 ClawBot 日志的 tools/list 里看到，共 7 个）

注意: FoloToy 服务端自己也会用 LLM 回答每一句话。--tool 模式请用触发词区分，
      否则会出现「服务端回答 + 工具回答」两份语音。
"""
import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("缺少 paho-mqtt，请先执行: pip install paho-mqtt")

EVENT_TOPIC = "/sys/folotoy/+/thing/event/post"
COMMAND_TOPIC = "/sys/folotoy/%s/thing/command/call"
TEXT_KEYS = ("text", "voiceText", "transcript", "content", "asr", "query", "question")


def http_post(url, payload, admin_key):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "X-Admin-Key": admin_key or ""},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "HTTP %s: %s" % (e.code, e.read().decode(errors="replace")[:200])}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def pick_text(params):
    """不同固件版本字段名不完全一致，做一次宽松提取。"""
    if not isinstance(params, dict):
        return ""
    for k in TEXT_KEYS:
        v = params.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for v in params.values():
        if isinstance(v, str) and v.strip() and not v.startswith("http"):
            return v.strip()
    return ""


def make_client(host, port):
    try:  # paho-mqtt 2.x
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="folotoy-bridge")
    except AttributeError:  # paho-mqtt 1.x
        c = mqtt.Client(client_id="folotoy-bridge")
    c.connect(host, port, 60)
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", action="store_true", help="只打印事件，不干预对话")
    ap.add_argument("--forward", action="store_true", help="把用户说的话推进 ClawBot 收件箱")
    ap.add_argument("--tool", default="", help="触发词命中时调用的小智 MCP 工具名")
    ap.add_argument("--trigger", default=os.getenv("BRIDGE_TRIGGER", "小智"), help="触发词前缀")
    ap.add_argument("--mqtt-host", default=os.getenv("MQTT_HOST", ""))
    ap.add_argument("--mqtt-port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    ap.add_argument("--clawbot", default=os.getenv("CLAWBOT_BASE", "http://127.0.0.1:3000"))
    ap.add_argument("--admin-key", default=os.getenv("CLAWBOT_ADMIN_KEY", ""))
    a = ap.parse_args()

    if not a.mqtt_host:
        ap.error("需要 --mqtt-host 或环境变量 MQTT_HOST（云电脑公网 IP）")
    if (a.forward or a.tool) and not a.admin_key:
        ap.error("--forward / --tool 需要 --admin-key 或环境变量 CLAWBOT_ADMIN_KEY")

    mode = "listen" if a.listen else ("tool:" + a.tool if a.tool else ("forward" if a.forward else "listen"))
    print("MQTT: %s:%d | ClawBot: %s | 模式: %s" % (a.mqtt_host, a.mqtt_port, a.clawbot, mode))
    print("订阅: %s\n" % EVENT_TOPIC)

    client = make_client(a.mqtt_host, a.mqtt_port)
    msg_id = [int(time.time()) % 100000]

    def speak(sn, text):
        msg_id[0] += 1
        topic = COMMAND_TOPIC % sn
        payload = {"msgId": msg_id[0], "identifier": "iwantplay",
                   "inputParams": {"role": 1, "text": text}}
        client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=0)
        print("  -> 播报: %s" % text[:80])

    def on_connect(c, userdata, flags, *args):
        print("已连上 EMQX，等待玩具事件...\n")
        c.subscribe(EVENT_TOPIC, qos=0)

    def on_message(c, userdata, msg):
        try:
            body = json.loads(msg.payload.decode("utf-8", "replace"))
        except Exception:
            return
        ident = body.get("identifier", "?")
        params = body.get("inputParams", {})
        text = pick_text(params)
        parts = msg.topic.split("/")
        sn = parts[3] if len(parts) > 3 else ""
        print("[%s] %s | sn=%s | %s" % (time.strftime("%H:%M:%S"), ident, sn, text[:100]))

        if a.listen:
            return

        # 用户说的话（不同版本 identifier 可能是 recording_transcribed 或类似）
        user_said = "transcrib" in ident.lower() or "asr" in ident.lower() or "record" in ident.lower()
        if not user_said or not text:
            return

        if a.tool:
            if not text.startswith(a.trigger):
                return  # 非触发词，交给 FoloToy 自己的 LLM，避免抢答
            query = text[len(a.trigger):].strip(" ，,:：") or text
            url = a.clawbot.rstrip("/") + "/api/mcp-run?key=" + a.admin_key
            r = http_post(url, {"name": a.tool, "args": {"text": query}}, a.admin_key)
            print("  MCP 返回:", str(r)[:300])
            out = r.get("text") if isinstance(r, dict) else ""
            if out and sn:
                speak(sn, str(out)[:500])
        elif a.forward:
            url = a.clawbot.rstrip("/") + "/api/inbox-push?key=" + a.admin_key
            r = http_post(url, {"key": a.admin_key, "text": text}, a.admin_key)
            print("  转发结果:", str(r)[:200])

    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n已退出")
        client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
