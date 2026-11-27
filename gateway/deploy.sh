#!/bin/bash
# 正式集成部署（在 WSL /opt/folotoy 内执行）
set -e
cd /opt/folotoy

echo "=== 0. 停测试容器 ==="
docker rm -f gwtest >/dev/null 2>&1 || true

echo "=== 1. 清掉所有 folotoy_folotoy 残留容器（compose v1 ContainerConfig bug 预防）==="
for c in $(docker ps -a --filter name=folotoy_folotoy --format '{{.Names}}'); do
  echo "  rm $c"; docker rm -f "$c" >/dev/null 2>&1 || true
done

echo "=== 2. 一次起全部服务（emqx/nginx 复用，重建 folotoy + 新 llm-gateway）==="
docker-compose up -d --no-deps emqx nginx 2>&1 | tail -3
# folotoy 与网关分开起，确保网关先就绪
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -4
sleep 3
echo "  --- 网关健康 ---"
curl -s http://127.0.0.1:8010/health || echo "网关未就绪"

echo "  --- 起 folotoy（指向网关）---"
docker-compose up -d --no-deps folotoy 2>&1 | tail -4
sleep 8

echo "=== 3. 容器状态 ==="
docker ps --filter name=folotoy_ --format "{{.Names}} | {{.Status}} | {{.Image}}"

echo "=== 4. folotoy 确认走网关 ==="
docker exec folotoy_folotoy_1 sh -c 'echo "LLM_BASE=$OPENAI_OPENAI_API_BASE"; echo "HTTPX_TIMEOUT=$HTTPX_TIMEOUT"' 2>&1

echo "=== 5. 网关日志 ==="
docker logs --tail 6 folotoy_llm_gateway_1 2>&1

echo "=== 6. 令牌自愈（重建 folotoy 后玩具会哑，踢连接逼重连）==="
python3 /opt/folotoy/emqx_reconnect.py 2>&1 | tail -20
