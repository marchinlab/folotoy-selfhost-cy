#!/bin/bash
# 只读诊断：18:00 播报服务端 PUB 了，但主人听不到声音。定位卡在哪一环。
# 证据链：本机IP -> EMQX设备在线 -> command/call 发出 -> callAck 回执 -> nginx 设备GET MP3 -> folotoy 出声
exec > /tmp/diag_nosound.log 2>&1
echo "########## DIAG_NOSOUND $(date '+%F %T %Z') ##########"
# 冷启动兜底：等 docker daemon 就绪（最多 15s）
for i in $(seq 1 15); do docker info >/dev/null 2>&1 && break; sleep 1; done

echo "=== A) 本机当前 IPv4（核对 AUDIO_BASE_URL 里写死的 YOUR_SERVER_IP 还对不对）==="
ip -4 -o addr show 2>/dev/null | awk '{print "  "$2" "$4}' | grep -vE ' lo | 127\.'
echo -n "  .env PUBLIC_HOST = "; grep -a '^PUBLIC_HOST' /opt/folotoy/.env 2>/dev/null | head -1
echo -n "  .env SCHEDULE     = "; grep -a '^SCHEDULE' /opt/folotoy/.env 2>/dev/null | head -1
echo -n "  .env ENABLE_SCHED = "; grep -a '^ENABLE_SCHEDULER' /opt/folotoy/.env 2>/dev/null | head -1

echo "=== B) EMQX 在线客户端（火火兔 DEVICEKEY_REDACTED 在不在/从哪连/连多久）==="
TOK=$(curl -s --max-time 6 -X POST -u admin:public http://127.0.0.1:18083/api/v5/login \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"public"}' 2>/dev/null \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
if [ -n "$TOK" ]; then
  curl -s --max-time 6 -H "Authorization: Bearer $TOK" "http://127.0.0.1:18083/api/v5/clients?limit=200" 2>/dev/null \
  | python3 -c '
import sys,json
try: d=json.load(sys.stdin)
except Exception as e: print("  parse_err",e); raise SystemExit
rows = d if isinstance(d,list) else d.get("data",d.get("clients",[]))
if not rows: print("  (无在线客户端)")
for c in rows:
    cid=str(c.get("clientid","")); ip=c.get("ipaddress",""); cn=c.get("connected","")
    st=c.get("state",""); un=c.get("username",""); ka=c.get("keepalive","")
    mark="  <<< 火火兔" if "DEVICEKEY_REDACTED" in cid else ""
    print("  cid=%s user=%s ip=%s state=%s connected=%s keepalive=%s%s"%(cid,un,ip,st,cn,ka,mark))
' 2>/dev/null
else
  echo "  (EMQX API login 失败，试 v4 basic)"
  curl -s --max-time 6 -u admin:public "http://127.0.0.1:18083/api/v4/clients?limit=200" 2>/dev/null \
  | python3 -c 'import sys,json;d=json.load(sys.stdin);rows=d if isinstance(d,list) else d.get("data",[]);[print("  cid=%s ip=%s state=%s connected=%s"%(c.get("clientid"),c.get("ipaddress"),c.get("state"),c.get("connected"))) for c in rows] or (not rows and print("  (无在线客户端)"))' 2>/dev/null
fi

echo "=== B2) 火火兔订阅关系（它到底订没订 command/call topic）==="
if [ -n "$TOK" ]; then
  curl -s --max-time 6 -H "Authorization: Bearer $TOK" "http://127.0.0.1:18083/api/v5/clients?limit=200" 2>/dev/null \
  | python3 -c '
import sys,json,urllib.request,urllib.parse
try: d=json.load(sys.stdin)
except: raise SystemExit
rows=d if isinstance(d,list) else d.get("data",[])
for c in rows:
    cid=str(c.get("clientid",""))
    if "DEVICEKEY_REDACTED" not in cid: continue
    req=urllib.request.Request("http://127.0.0.1:18083/api/v5/clients/"+urllib.parse.quote(cid)+"/subscriptions",headers={"Authorization":"Bearer "+__import__("os").environ.get("TOK","")})
    try:
        s=json.load(urllib.request.urlopen(req,timeout=6)); ss=s if isinstance(s,list) else s.get("data",[])
        print("  [%s] 订阅 %d 条:"%(cid,len(ss)))
        for x in ss: print("     SUB %-60s qos=%s"%(x.get("topic"),x.get("qos")))
    except Exception as e: print("  订阅查询失败:",repr(e))
' 2>/dev/null
fi

echo "=== C) nginx access.log：设备有没有真的 GET 播报 MP3（最关键·出声前置）==="
timeout 12 docker logs --since 40m folotoy_nginx_1 2>&1 | grep -iE 'aqing-news|\.mp3' | tail -30 || echo "  (docker logs 无匹配或权限问题)"

echo "=== C2) nginx 容器内 access.log 直读兜底 ==="
timeout 12 docker exec folotoy_nginx_1 sh -c 'grep -iE "aqing-news|\.mp3" /var/log/nginx/access.log 2>/dev/null | tail -30' 2>&1 | head -35

echo "=== D) folotoy-server：收没收到 iwantplay / 有没下载或播放报错 ==="
timeout 12 docker logs --since 40m folotoy_folotoy_1 2>&1 | grep -iE 'iwantplay|iwant|command/call|download|\.mp3|text to sound|play|error|warn' | tail -50 || echo "  (无匹配)"

echo "=== E) EMQX 日志：command/call 发没发、callAck 回没回 ==="
timeout 12 docker logs --since 40m folotoy_emqx_1 2>&1 | grep -iE 'DEVICEKEY_REDACTED|iwantplay|command/call|callAck|publish|disconnect' | tail -40 || echo "  (无匹配)"

echo "=== F) 网关 daemon 今晚播报日志 ==="
timeout 12 docker logs --since 40m folotoy_llm_gateway_1 2>&1 | grep -E '\[bc\]|到点播报|稿成|PUB|主动播报完成|播报失败' | tail -30 || echo "  (无匹配)"

echo "=== G) 最新播报成品 + 8082 自测可达 ==="
F=$(ls -t /opt/folotoy/audio/aqing-news-*.mp3 2>/dev/null | head -1)
echo "  latest=$(basename "$F") size=$(stat -c%s "$F" 2>/dev/null)"
curl -s -o /dev/null -w "  8082 自测 http=%{http_code} size=%{size_download}\n" --max-time 8 "http://127.0.0.1:8082/$(basename "$F")"
echo "  用写死IP自测:"
curl -s -o /dev/null -w "  YOUR_SERVER_IP:8082 http=%{http_code} size=%{size_download}\n" --max-time 8 "http://YOUR_SERVER_IP:8082/$(basename "$F")"

echo "########## DIAG_DONE $(date '+%F %T') ##########"
