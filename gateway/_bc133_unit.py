# -*- coding: utf-8 -*-
"""v1.33 网关层单元测试：出声确认闭环 + X-No-Record + 语速 1.0 + 无回归。
本地跑（无需 emqx/paho）：静态源码断言 + 纯逻辑模拟。生产真链路由部署后 _verify_133.sh + 宿主确认脚本覆盖。
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_broadcaster.py"),
           encoding="utf-8").read()
P = F = 0


def ck(name, cond, extra=""):
    global P, F
    if cond:
        P += 1; print("  PASS", name, extra)
    else:
        F += 1; print("  FAIL", name, extra)


print("== A. MQTT 确认闭环（v1.33 核心）==")
ck("TOPIC_ACK 订阅 topic 定义", 'TOPIC_ACK = "/sys/folotoy/+/thing/command/callAck"' in SRC)
ck("ACK_WAIT 可调（默认8s）", 'ACK_WAIT = float(os.getenv("ACK_WAIT", "8"))' in SRC)
ck("mqtt_publish qos=1", "qos=1)" in SRC and "info = c.publish" in SRC)
ck("订阅 callAck", "c.subscribe(TOPIC_ACK" in SRC)
ck("on_message 收回执", "def on_message" in SRC and "got.append" in SRC)
ck("wait_for_publish 等 PUBACK", "wait_for_publish" in SRC)
ck("回执只记 WARN 唔阻断（deadline 循环）", "deadline" in SRC and "and not got" in SRC)
ck("返回 puback/ack 字典", '"puback": puback' in SRC and '"ack": bool(ack)' in SRC)
ck("broadcast_now 用 ACK_OK/ACK_WARN 区分", "ACK_OK" in SRC and "ACK_WARN" in SRC)

print("== B. 播报稿落盘污染修复 ==")
ck("make_script 加 X-No-Record:1", '"X-No-Record": "1"' in SRC)
ck("header 落喺 /chat/completions 请求", "headers={" in SRC and "X-No-Record" in SRC)

print("== C. 语速 1.0 + 开关 ==")
ck("NEWS_RATE 默认 +0%", 'NEWS_RATE = os.getenv("NEWS_RATE", "+0%")' in SRC)
ck("合成命令用 NEWS_RATE", '"--rate=" + NEWS_RATE' in SRC)
ck("无写死 +20%/-20% 合成值", '"--rate=+20%"' not in SRC and '"--rate=-20%"' not in SRC)

print("== D. 宿主层对接（BC_FILE 机器行 + url 轻推）==")
ck("once 输出 BC_FILE 文件名", 'print("BC_FILE %s"' in SRC)
ck("BC_FILE 用合成名 res[name]", 'res["name"]' in SRC)
ck("url 子命令 want_ack=False 轻推", "play_url(sys.argv[2], want_ack=False)" in SRC)

print("== E. 旧链路无回归 ==")
for tok, desc in [
    ("def make_script", "抓稿"), ("def synth_long", "长文合成"),
    ("def split_sentences", "分句"), ("def daemon", "定时守护"),
    ("yue_polish.polish", "粤语化兜底"), ("tts_pron.fix", "正音"),
    ("cmd == \"daemon\"", "daemon 子命令"), ("cmd == \"once\"", "once 子命令"),
    ("cmd == \"say\"", "say 子命令"), ("cmd == \"url\"", "url 子命令"),
    ("cmd == \"script\"", "script 子命令"),
    ("--voice\", VOICE", "粤语女声"), ("ffmpeg", "拼接"),
]:
    ck("保留 " + desc, tok in SRC)

print("== F. 语法可编译 ==")
import py_compile
try:
    py_compile.compile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_broadcaster.py"),
                       doraise=True)
    ck("py_compile news_broadcaster.py", True)
except Exception as e:
    ck("py_compile news_broadcaster.py", False, repr(e))

print("\n== 结果 ==")
print("%d PASS / %d FAIL -> %s" % (P, F, "ALL_PASS" if F == 0 else "HAS_FAIL"))
sys.exit(1 if F else 0)
