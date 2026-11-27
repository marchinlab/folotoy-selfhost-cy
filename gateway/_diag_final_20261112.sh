#!/usr/bin/env bash
# 收口诊断：① 设备连接是否假在线(recv_cnt 两次对比) ② 订阅主题是否对得上 ③ v1.39 流式真实转发
# 只读/不落盘(X-No-Record)/不推播/不重启
API=http://127.0.0.1:18083/api/v5
TOKEN=$(curl -s -m 6 -X POST $API/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"public"}' 2>/dev/null | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("token",""))
except Exception: print("")' 2>/dev/null)
HDR="Authorization: Bearer $TOKEN"

echo "=== 1. 设备连接详情 (第1次) ==="
curl -s -m 6 -H "$HDR" "$API/clients/DEVICEKEY_REDACTED" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); d=d.get("data",d) if isinstance(d,dict) else d
    if isinstance(d,list): d=d[0] if d else {}
    for k in ("clientid","connected","connected_at","recv_cnt","send_cnt","keepalive","state","ipaddress","port","proto_name","proto_ver","username"):
        print("  ",k,"=",d.get(k))
except Exception as e: print("  PARSE_ERR",e)' 2>&1
sleep 4
echo "=== 2. 设备连接详情 (第2次, 隔4s; recv_cnt 应增长否则假在线) ==="
curl -s -m 6 -H "$HDR" "$API/clients/DEVICEKEY_REDACTED" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); d=d.get("data",d) if isinstance(d,dict) else d
    if isinstance(d,list): d=d[0] if d else {}
    for k in ("connected","connected_at","recv_cnt","send_cnt","state"):
        print("  ",k,"=",d.get(k))
except Exception as e: print("  PARSE_ERR",e)' 2>&1

echo "=== 3. 设备订阅主题 ==="
curl -s -m 6 -H "$HDR" "$API/subscriptions?clientid=DEVICEKEY_REDACTED" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); items=d.get("data",d) if isinstance(d,dict) else d
    for c in (items if isinstance(items,list) else []): print("  topic=",c.get("topic"),"qos=",c.get("qos"))
    if not items: print("  (无订阅)")
except Exception as e: print("  PARSE_ERR",e)' 2>&1

echo "=== 4. 大脑订阅主题 (对照) ==="
curl -s -m 6 -H "$HDR" "$API/subscriptions?clientid=folotoy" 2>/dev/null | python3 -c 'import sys,json
try:
    d=json.load(sys.stdin); items=d.get("data",d) if isinstance(d,dict) else d
    for c in (items if isinstance(items,list) else []): print("  topic=",c.get("topic"),"qos=",c.get("qos"))
    if not items: print("  (无订阅 / clientid 唔系 folotoy)")
except Exception as e: print("  PARSE_ERR",e)' 2>&1

echo "=== 5. v1.39 流式真实转发 (大脑容器 -> llm-gateway:8000, stream=True, X-No-Record) ==="
docker exec folotoy_folotoy_1 python3 -c "
import urllib.request,json,time
body=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':True,
 'messages':[{'role':'system','content':'【角色:aqing_chat】\n你叫阿晴，20岁广州西关女仔，用街坊悠闲倾计嘅慢节奏，纯正广州西关口音。'},
             {'role':'user','content':'阿晴，喺唔喺度？简短答我一句就得。'}]}).encode()
req=urllib.request.Request('http://llm-gateway:8000/v1/chat/completions',data=body,
  headers={'Content-Type':'application/json','X-No-Record':'1'})
t=time.time(); buf=b''; first=None
try:
    r=urllib.request.urlopen(req,timeout=90)
    print('  HTTP',r.status)
    while True:
        c=r.read(256)
        if not c: break
        if first is None: first=round(time.time()-t,2)
        buf+=c
    s=buf.decode('utf-8','ignore')
    print('  first_chunk_s=',first,'total_s=',round(time.time()-t,2),'bytes=',len(buf))
    print('  has_delta_content=', ('content' in s), 'has_DONE=', ('[DONE]' in s))
    print('  RAW_HEAD=',s[:260].replace(chr(10),' | '))
except Exception as e:
    print('  STREAM_ERR',type(e).__name__,str(e)[:160])
    try: print('  BODY',e.read()[:300])
    except Exception: pass
" 2>&1
echo "=== DONE ==="
