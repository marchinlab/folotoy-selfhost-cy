#!/bin/bash
# v1.33 收尾只读终检：五文件三处 md5 / 备份链 / 记录数 / 容器镜像 / 完整下载判据自测
# 全程只读，唔重建、唔推玩具、唔清落盘、自检唔落盘。
set -u
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
CG=folotoy_llm_gateway_1
P=0; F=0
ok(){ echo "  ✅ $*"; P=$((P+1)); }
no(){ echo "  ❌ $*"; F=$((F+1)); }
info(){ echo "  ℹ️  $*"; }

echo "===== 1) 五文件三处 md5（宿主源码 / 生产 / 镜像内）====="
check3(){
  f=$1; img=$2
  H=$(md5sum $SRC/$f 2>/dev/null | awk '{print $1}')       # $f = gateway/xxx.py
  B=$(md5sum $G/$img 2>/dev/null | awk '{print $1}')        # 生产 /opt/folotoy/gateway/xxx.py
  I=$(timeout 10 docker exec $CG md5sum /app/$img 2>/dev/null | awk '{print $1}')
  if [ -n "$H" ] && [ "$H" = "$B" ] && [ "$B" = "$I" ]; then
    ok "$f 三处一致 ($H)"
  else
    no "$f  源码=$H 生产=$B 镜像=$I"
  fi
}
check3 gateway/llm_gateway.py llm_gateway.py
check3 gateway/yue_polish.py yue_polish.py
check3 gateway/tts_pron.py tts_pron.py
check3 gateway/news_broadcaster.py news_broadcaster.py
# roles.json 源码在 config/
H=$(md5sum $SRC/config/roles.json 2>/dev/null | awk '{print $1}')
B=$(md5sum $G/roles.json 2>/dev/null | awk '{print $1}')
I=$(timeout 10 docker exec $CG md5sum /app/roles.json 2>/dev/null | awk '{print $1}')
[ -n "$H" ] && [ "$H" = "$B" ] && [ "$B" = "$I" ] && ok "roles.json 三处一致 ($H)" || no "roles.json 源码=$H 生产=$B 镜像=$I"
# compose 两处
H=$(md5sum $SRC/docker-compose.yml 2>/dev/null | awk '{print $1}')
B=$(md5sum $D/docker-compose.yml 2>/dev/null | awk '{print $1}')
[ "$H" = "$B" ] && ok "docker-compose.yml 两处一致 ($H)" || no "compose 源码=$H 生产=$B"

echo "===== 2) 备份链 .bak-pre-1.33 完整 ====="
for f in docker-compose.yml gateway/news_broadcaster.py gateway/llm_gateway.py gateway/yue_polish.py gateway/tts_pron.py; do
  [ -f "$D/$f.bak-pre-1.33" ] && ok "$f.bak-pre-1.33 存在" || no "$f.bak-pre-1.33 缺失"
done
[ -f "$D/.env.bak-pre-1.33" ] && ok ".env.bak-pre-1.33 存在" || no ".env.bak-pre-1.33 缺失"

echo "===== 3) 网关健康 + 记录数 + 语速开关 ====="
curl -s --max-time 6 http://127.0.0.1:8010/health | grep -q '"ok": true' && ok "/health OK" || no "/health 失败"
CNT=$(curl -s --max-time 8 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))" 2>/dev/null)
[ "$CNT" = "67" ] && ok "/logs count=67（部署前后零丢失）" || info "/logs count=$CNT（若 >67 为真实对话新增，非本次写脏）"
UNIQ=$(CONV_DIR=$D/conversations python3 $G/_conv_count_baseline.py 2>/dev/null)
[ "$UNIQ" = "67" ] && ok "落盘唯一数=67" || info "落盘唯一数=$UNIQ"
RATE=$(timeout 8 docker exec $CG sh -c 'echo $NEWS_RATE' 2>/dev/null | tr -d '\r')
[ "$RATE" = "+0%" ] && ok "容器 NEWS_RATE=+0%（语速 1.0）" || no "容器 NEWS_RATE=[$RATE] 唔系 +0%"

echo "===== 4) 容器镜像（大脑/nginx/emqx 未升级，只网关 1.33）====="
docker ps --format "{{.Names}}|{{.Image}}" | grep folotoy_ | sort | while read -r ln; do echo "  · $ln"; done
docker ps --format "{{.Names}}|{{.Image}}" | grep -q 'folotoy_llm_gateway_1|aqing-gateway:1.33' && ok "网关 = aqing-gateway:1.33" || no "网关镜像唔系 1.33"
docker ps --format "{{.Names}}|{{.Image}}" | grep -q 'folotoy_folotoy_1|folotoy-server:aqing-cantonese' && ok "大脑镜像未动" || no "大脑镜像异常"

echo "===== 5) 完整下载判据自测（明早确认脚本命门）====="
# 与 _broadcast_verified.sh 完全同一条 awk 判据：来源IP==设备 AND 200 AND bytes==size
JUDGE='$1==dev && $9=="200" && $10==sz {print; exit}'
GOOD='YOUR_DEVICE_IP - - [11/Nov/2026:10:17:46 +0000] "GET /aqing-news-test.mp3 HTTP/1.1" 200 1094493 "-" "Mozilla"'
CUT='YOUR_DEVICE_IP - - [11/Nov/2026:10:01:24 +0000] "GET /aqing-news-test.mp3 HTTP/1.1" 200 785262 "-" "Mozilla"'
OTHER='127.0.0.1 - - [11/Nov/2026:10:01:24 +0000] "GET /aqing-news-test.mp3 HTTP/1.1" 200 1094493 "-" "curl"'
G=$(echo "$GOOD" | awk -v sz=1094493 -v dev=YOUR_DEVICE_IP "$JUDGE")
C=$(echo "$CUT"  | awk -v sz=1094493 -v dev=YOUR_DEVICE_IP "$JUDGE")
O=$(echo "$OTHER"| awk -v sz=1094493 -v dev=YOUR_DEVICE_IP "$JUDGE")
[ -n "$G" ] && ok "全字节+设备IP → 命中（会报成功）" || no "全字节用例未命中"
[ -z "$C" ] && ok "71.8% 截断 → 唔命中（会重推）" || no "截断用例误命中!"
[ -z "$O" ] && ok "本机 curl 自测 → 唔命中（唔会误当设备）" || no "curl 用例误命中!"

echo ""
echo "===== 汇总: $P PASS / $F FAIL ====="
[ "$F" = "0" ] && echo "V133_VERIFY_ALL_PASS" || echo "V133_VERIFY_HAS_FAIL"
