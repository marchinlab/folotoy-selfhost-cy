import json, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:18083/api/v5"
CID = "DEVICEKEY_REDACTED"

def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=8) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {"err": str(e)}

st, login = req("POST", "/login", body={"username": "admin", "password": "public"})
token = login.get("token", "")
print("LOGIN status=%s token_len=%d" % (st, len(token)))
if not token:
    print("ABORT: no token")
    raise SystemExit(1)

def client():
    return req("GET", "/clients/" + CID, token)

st0, d0 = client()
data0 = d0.get("data", d0) if isinstance(d0, dict) else {}
before = data0.get("connected_at", "?")
print("BEFORE kick: connected_at=%s connected=%s recv=%s send=%s"
      % (before, data0.get("connected"), data0.get("recv_cnt"), data0.get("send_cnt")))

stk, dk = req("DELETE", "/clients/" + CID, token)
print("KICK: status=%s %s" % (stk, "" if stk in (204, 200) else dk))

reconnected = False
new = {}
for i in range(16):
    time.sleep(4)
    st, d = client()
    dd = d.get("data", d) if isinstance(d, dict) else {}
    ca = dd.get("connected_at")
    print("  poll%02d st=%s connected=%s connected_at=%s recv=%s send=%s"
          % (i + 1, st, dd.get("connected"), ca, dd.get("recv_cnt"), dd.get("send_cnt")))
    if ca and ca != before:
        reconnected = True
        new = dd
        break

print("RECONNECTED=%s" % reconnected)
if reconnected:
    print("NEW connected_at=%s" % new.get("connected_at"))
    print("设备已在大脑重启(09:44)之后重新握手 -> 应已拿到新配对令牌")
else:
    print("设备约64秒内未自动重连 -> 请主人断电重启火火兔（拔电源10秒+再上电）")
