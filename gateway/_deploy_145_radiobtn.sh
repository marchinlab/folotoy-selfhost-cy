#!/bin/bash
# ============================================================
# v1.45：1 号键(【角色:aqing_chat】) 改成电台开关
#   按 1 键讲任何一句 -> 网关拦截、写 /audio/radio_cmd.json、回一句短确认
#   Windows 侧 radio_cmd_bridge.py 轮询执行开/停。
# ★只重建 llm-gateway，绝不碰 folotoy / stt-proxy / emqx / nginx，
#   UDP 语音 token 保住、唔使踢设备；电台播放唔受影响。
# ★回滚：还原 llm_gateway.py.bak-pre-radiobtn + docker-compose.yml.bak-pre-1.45
#        (tag 改返 1.44)，重 build 1.44 再 up；或临时设 RADIO_BTN=0。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [1/5] 基线（只读）====="
for c in folotoy_folotoy_1 folotoy_stt_proxy_1 folotoy_nginx_1 folotoy_emqx_1; do
  docker ps --format '{{.Names}}|{{.Status}}' | grep "^$c|" || echo "  $c 未在跑(!)"
done

echo "===== [2/5] 语法 + 标记 ====="
cd $SRC/gateway
python3 -m py_compile llm_gateway.py && echo "  py_compile: OK"
grep -q 'RADIO_BTN_ENABLED' llm_gateway.py && echo "  v1.45 标记: OK"
grep -q 'image: aqing-gateway:1.45' $SRC/docker-compose.yml && echo "  compose tag 1.45: OK"

echo "===== [3/5] 备份 + 同步到生产 ====="
[ -f $G/llm_gateway.py.bak-pre-1.45 ] || cp $G/llm_gateway.py $G/llm_gateway.py.bak-pre-1.45
[ -f $COMPOSE.bak-pre-1.45 ] || cp $COMPOSE $COMPOSE.bak-pre-1.45
cp $SRC/gateway/llm_gateway.py $G/llm_gateway.py
cp $SRC/docker-compose.yml     $COMPOSE
md5sum $G/llm_gateway.py $SRC/gateway/llm_gateway.py

echo "===== [4/5] 重建镜像 1.45 ====="
cd $G
docker build -t aqing-gateway:1.45 -f Dockerfile . 2>&1 | tail -4
docker image inspect aqing-gateway:1.45 --format '  built {{.Id}}'

echo "===== [5/5] 只 recreate 网关 ====="
cd $D
if ! docker-compose config >/tmp/cfg145.out 2>&1; then echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg145.out; exit 1; fi
echo "  compose config: OK"
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关已移除"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -4
sleep 6
echo "  --- 不动容器 Up time 应延续 ---"
for c in folotoy_folotoy_1 folotoy_stt_proxy_1 folotoy_nginx_1 folotoy_emqx_1; do
  docker ps --format '{{.Names}}|{{.Status}}' | grep "^$c|" || echo "  ⚠️ $c 未在跑!"
done
echo -n "  /health: "; curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "=== DONE_145 ==="
