#!/bin/bash
# ============================================================
# v1.47：修「按 1 键通知播电台没反应」
#   1) 唔再纯靠【角色:aqing_chat】标记：句入面有「电台」一律开播
#   2) 1 号键停机时按一下就开播，播住先换台
#   3) 播报稿/早晚报 daemon 文本放行（v1.46 曾把 18:00 稿拦成 5 个字）
#   4) Windows 侧 radio_loop.py 首段复用窗口 1800s -> 6h，开机秒出声
# ★只重建 llm-gateway，绝不碰 folotoy / stt-proxy / emqx / nginx，
#   UDP 语音 token 保住、唔使踢设备；电台播放唔受影响。
# ★回滚：还原 llm_gateway.py.bak-pre-1.47 + radio_loop.py.bak-pre-1.47
#        + docker-compose.yml.bak-pre-1.47，重建 1.46 再 up；
#        或临时设 RADIO_BTN=0 停用两个键。
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

echo "===== [2/5] 语法 + v1.47 标记 ====="
cd $SRC/gateway
python3 -m py_compile llm_gateway.py && echo "  py_compile: OK"
grep -q 'RADIO_FORCE_PLAY_WORDS' llm_gateway.py && echo "  电台词强制开播: OK"
grep -q 'RADIO_SCRIPT_WORDS' llm_gateway.py && echo "  播报稿放行: OK"
grep -q 'def radio_action' llm_gateway.py && echo "  统一动作函数: OK"
grep -q 'REUSE_MAX_AGE = 6 \* 3600' $SRC/radio_loop.py && echo "  首段复用 6h: OK"
grep -q 'image: aqing-gateway:1.47' $SRC/docker-compose.yml && echo "  compose tag 1.47: OK"

echo "===== [3/5] 备份 + 同步到生产 ====="
[ -f $G/llm_gateway.py.bak-pre-1.47 ] || cp $G/llm_gateway.py $G/llm_gateway.py.bak-pre-1.47
[ -f $COMPOSE.bak-pre-1.47 ] || cp $COMPOSE $COMPOSE.bak-pre-1.47
cp $SRC/gateway/llm_gateway.py $G/llm_gateway.py
cp $SRC/docker-compose.yml     $COMPOSE
md5sum $G/llm_gateway.py $SRC/gateway/llm_gateway.py

echo "===== [4/5] 重建镜像 1.47 ====="
cd $G
docker build -t aqing-gateway:1.47 -f Dockerfile . 2>&1 | tail -4
docker image inspect aqing-gateway:1.47 --format '  built {{.Id}}'

echo "===== [5/5] 只 recreate 网关 ====="
cd $D
if ! docker-compose config >/tmp/cfg147.out 2>&1; then echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg147.out; exit 1; fi
echo "  compose config: OK"
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关已移除"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -4
sleep 6
echo "  --- 不动容器 Up time 应延续 ---"
for c in folotoy_folotoy_1 folotoy_stt_proxy_1 folotoy_nginx_1 folotoy_emqx_1; do
  docker ps --format '{{.Names}}|{{.Status}}' | grep "^$c|" || echo "  ⚠️ $c 未在跑!"
done
echo -n "  /health: "; curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "=== DONE_147 ==="
