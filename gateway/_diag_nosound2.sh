#!/bin/bash
# 第二轮只读诊断：坐实「设备下载被截断」根因 + 评估 MP3 兼容性 + 历史对比
exec > /tmp/diag_nosound2.log 2>&1
echo "########## DIAG2 $(date '+%F %T %Z') ##########"
for i in $(seq 1 15); do docker info >/dev/null 2>&1 && break; sleep 1; done
GW=folotoy_llm_gateway_1
NX=folotoy_nginx_1
FT=folotoy_folotoy_1

echo "=== 1) 今晚播报 MP3 编码/时长/码率（设备兼容性）==="
timeout 12 docker exec "$GW" ffprobe -v error \
  -show_entries format=duration,size,bit_rate -show_entries stream=codec_name,sample_rate,channels,channel_layout \
  -of default=noprint_wrappers=1 /audio/aqing-news-DEVICEKEY_REDACTED.mp3 2>&1 || echo "  (ffprobe 不可用)"

echo "=== 2) nginx error.log：18:01 时段有无断连/重置（坐实下载被斩断）==="
timeout 12 docker logs --since 40m "$NX" 2>&1 | grep -iE '10:01|reset|premature|closed|client|upstream' | tail -30 || echo "  (无匹配)"

echo "=== 3) folotoy-server 18:00-18:03 全量日志（找下载/播放/Text to sound/回执）==="
timeout 12 docker logs --since 15m "$FT" 2>&1 | grep -E '18:0[0-3]:' | grep -viE 'Connection refused|ConnectionRefusedError' | head -80 || echo "  (该时段无非refused日志)"

echo "=== 4) nginx 全历史：设备拉过哪些播报成品、每次实收字节（对比历史3个manual）==="
timeout 15 docker logs --since 72h "$NX" 2>&1 | grep -iE 'GET /aqing-news' | tail -60 || echo "  (无历史 GET)"

echo "=== 5) 所有播报成品文件（含历史manual，核对大小）==="
find /opt/folotoy/audio -maxdepth 1 -name 'aqing-news-*.mp3' -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %f\n' 2>/dev/null | sort

echo "=== 6) EMQX v4 订阅关系（火火兔订了哪些 topic）==="
CID=$(curl -s --max-time 6 -u admin:public "http://127.0.0.1:18083/api/v4/clients?limit=200" 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);r=d if isinstance(d,list) else d.get("data",[]);print(next((c.get("clientid","") for c in r if "DEVICEKEY_REDACTED" in str(c.get("clientid",""))),""))' 2>/dev/null)
echo "  cid=$CID"
[ -n "$CID" ] && curl -s --max-time 6 -u admin:public "http://127.0.0.1:18083/api/v4/clients/$CID/subscriptions" 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);r=d if isinstance(d,list) else d.get("data",[]);[print("  SUB %-62s qos=%s"%(x.get("topic"),x.get("qos"))) for x in r];not r and print("  (无订阅)")' 2>/dev/null

echo "=== 7) 设备当前在线 + 连接时长（v4 clients 详情）==="
curl -s --max-time 6 -u admin:public "http://127.0.0.1:18083/api/v4/clients/DEVICEKEY_REDACTED" 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);d=d[0] if isinstance(d,list) and d else d;print("  ",{k:d.get(k) for k in ("clientid","username","ipaddress","state","connected_at","keepalive","proto_name")})' 2>/dev/null

echo "=== 8) 容器启动时序（是不是反复冷重启）==="
timeout 12 docker ps --format '{{.Names}}|{{.Status}}' 2>/dev/null | grep folotoy
echo "  网关 daemon 最近启动行:"
timeout 12 docker logs --since 15m "$GW" 2>&1 | grep -E 'daemon 启动' | tail -8

echo "########## DIAG2_DONE $(date '+%F %T') ##########"
