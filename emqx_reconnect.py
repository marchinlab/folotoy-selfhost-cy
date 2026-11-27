#!/usr/bin/env python3
"""
重建 folotoy 服务端容器后的自愈脚本。

根因：FoloToy 服务端的语音会话 token 是【内存态】的（容器只挂 config/audio，
没有 token 持久化）。一旦 folotoy 容器被重建/重启，内存 token 表全丢；
但玩具的 MQTT 长连接连的是 emqx（没断），它不会重新注册 token，
于是继续拿旧 token 发 UDP 音频 -> 服务端全判 unknown、block the peer -> 玩具哑掉。

本脚本通过 EMQX 管理 API (18083) 踢掉玩具的 MQTT 连接，逼它断线重连 ->
重新注册 -> 拿到新 token。踢完通常再按一次玩具对话键即可恢复；
若玩具不自动重连，则给玩具断电重启。

用法（WSL 内运行）：
    python3 /opt/folotoy/emqx_reconnect.py
"""
import urllib.request, urllib.parse, json, time, subprocess

BASE = "http://127.0.0.1:18083/api/v5"
USER, PASS = "admin", "public"
WAIT = 10
SKIP_IDS = {"folotoy"}  # 服务端自己的 clientid，别踢


def req(method, path, tok=None, data=None):
    h = {"Content-Type": "application/json"}
    if tok:
        h["Authorization"] = "Bearer " + tok
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(BASE + path, data=body, headers=h, method=method)
    raw = urllib.request.urlopen(r, timeout=8).read().decode()
    return json.loads(raw) if raw.strip() else None  # 204 No Content 兼容


def as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return x.get("data", [])
    return []


def token_err_count(since="120s"):
    try:
        out = subprocess.run(
            ["docker", "logs", "--since", since, "folotoy_folotoy_1"],
            capture_output=True, text=True, timeout=15,
        )
        return (out.stdout + out.stderr).count("is unknown")
    except Exception:
        return -1


def main():
    try:
        tok = req("POST", "/login", data={"username": USER, "password": PASS})["token"]
    except Exception as e:
        print("EMQX 登录失败:", repr(e)); return

    clients = as_list(req("GET", "/clients?limit=100", tok))
    print("=== 踢之前在线客户端 ===")
    for c in clients:
        print("  %-16s conn=%-5s since=%s user=%s" %
              (c.get("clientid"), c.get("connected"), c.get("connected_at"), c.get("username")))

    toys = [c for c in clients
            if c.get("clientid") not in SKIP_IDS and c.get("connected")]
    if not toys:
        print("没有玩具连接在线（可能已断电）-> 给火火兔通电开机即可")
        return

    before = token_err_count()
    for c in toys:
        cid = c["clientid"]
        subs = as_list(req("GET", "/clients/" + urllib.parse.quote(cid) + "/subscriptions", tok))
        print("  订阅 topic:", [(s.get("topic"), s.get("qos")) for s in subs][:8])
        req("DELETE", "/clients/" + urllib.parse.quote(cid), tok)  # 204 空 body
        print("  >>> 已踢:", cid)

    print("=== 等 %ds 玩具自动重连 ===" % WAIT)
    time.sleep(WAIT)

    after = as_list(req("GET", "/clients?limit=100", tok))
    print("=== 踢之后在线客户端 ===")
    for c in after:
        print("  %-16s conn=%-5s since=%s" %
              (c.get("clientid"), c.get("connected"), c.get("connected_at")))
    back = [c for c in after if c.get("clientid") in [t["clientid"] for t in toys]]
    print("玩具自动重连:", "YES" if back else "NO（需给玩具断电重启）")
    print("陌生令牌报错数(近2分钟) 前/后: %s / %s" % (before, token_err_count()))
    print("下一步：请按一次玩具对话键说句话，看是否出声。")


if __name__ == "__main__":
    main()
