#!/usr/bin/env bash
# 权威判据：判断 EMQX broker 是真活着还是 Erlang 节点假死
# 只读：建立一次 MQTT 连接读 $SYS 在线数 + 走 v5 API 拉在线客户端列表，随即断开
echo "=== A. paho MQTT CONNECT/CONNACK + \$SYS connected count (from brain container) ==="
docker exec folotoy_folotoy_1 python3 -c "
import paho.mqtt.client as mqtt, time
got={'rc':None,'sys':[]}
def on_connect(c,u,flags,rc=None,properties=None):
    got['rc']=rc
    print('  ON_CONNECT rc=',rc)
    try: c.subscribe('\$SYS/broker/clients/connected',qos=0)
    except Exception as e: print('  SUB_ERR',e)
def on_message(c,u,msg):
    got['sys'].append((msg.topic,msg.payload.decode('utf-8','ignore')))
    print('  SYS_MSG',msg.topic,'=',msg.payload.decode('utf-8','ignore'))
c=mqtt.Client(client_id='diag_liveness_01',clean_session=True)
c.on_connect=on_connect
c.on_message=on_message
try:
    c.connect('emqx',1883,5)
    c.loop_start()
    t=time.time()
    while got['rc'] is None and time.time()-t<6: time.sleep(0.1)
    if got['rc'] is None:
        print('  NO_CONNACK_IN_6S  <-- broker 可能假死')
    time.sleep(2)
    c.loop_stop()
    try: c.disconnect()
    except Exception: pass
    print('  RESULT rc=',got['rc'],'sys=',got['sys'])
except Exception as e:
    print('  CONNECT_ERR',type(e).__name__,str(e)[:140])
" 2>&1
echo "=== B. EMQX dashboard v5 login + online clients ==="
TOKEN=$(curl -s -m 6 -X POST http://127.0.0.1:18083/api/v5/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"public"}' 2>/dev/null | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("token",""))
except Exception as e: print("")' 2>/dev/null)
if [ -n "$TOKEN" ]; then
  echo "  dashboard login OK, token len=${#TOKEN}"
  echo "=== B2. online clients (v5) ==="
  curl -s -m 6 -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:18083/api/v5/clients?limit=20" 2>&1 | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); items=d.get("data",d) if isinstance(d,dict) else d
    print("  online client count:",len(items) if isinstance(items,list) else "?")
    for c in (items if isinstance(items,list) else [])[:20]:
        print("   -",c.get("clientid"),"ip=",c.get("ipaddress"),"connected=",c.get("connected"))
except Exception as e:
    print("  PARSE_ERR",e); print(sys.stdin.read()[:300])' 2>&1
else
  echo "  dashboard v5 login FAILED (public 密码可能改过) -> 以 A 的 CONNACK 为判据"
fi
echo "=== C. 大脑到 EMQX 的 TCP 连接状态 ==="
docker exec folotoy_folotoy_1 sh -c "(ss -tnp 2>/dev/null || netstat -tnp 2>/dev/null) | grep 1883 || echo NO_SS" 2>&1
echo "=== DONE ==="
