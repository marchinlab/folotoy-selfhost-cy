#!/bin/bash
# v1.40 切流部署：STT 代理 + 大脑切流（破例重启大脑一次，已获主人拍板）
# 铁律：
#   - 只重建 stt-proxy（新增）+ folotoy（重建一次）；emqx/nginx/llm-gateway 一律不动
#   - 大脑 key/人设/记忆不丢：key 在 .env 注入、roles.json 与 audio 在挂载卷
#   - 安全姿势：先 docker rm -f 大脑，再 up --no-deps（禁 --force-recreate，绕 compose v1 bug）
#   - 全程可回滚：compose .bak-pre-1.40 + 改回一行 base_url 重建大脑
set -e
W=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
BRAIN=folotoy_folotoy_1
PROXY=folotoy_stt_proxy_1

echo "===== [1/8] 备份 compose（真相源 + 生产，两处）====="
for f in "$W/docker-compose.yml" "$D/docker-compose.yml"; do
  if [ ! -f "$f.bak-pre-1.40" ]; then cp -f "$f" "$f.bak-pre-1.40"; fi
done
echo "  backups:"; ls -la "$D/docker-compose.yml.bak-pre-1.40" | awk '{print "   ",$5,$9}'
echo "  记录数基线:"
docker logs --tail 2000 $BRAIN 2>&1 | grep -c "Ask" >/dev/null 2>&1 || true

echo "===== [2/8] 记录大脑重启前关键状态（用于核验不丢）====="
echo -n "  brain image: "; docker inspect $BRAIN --format '{{.Config.Image}}'
echo -n "  key len: "; docker exec $BRAIN sh -c 'echo -n "$OPENAI_WHISPER_KEY" | wc -c'
echo -n "  roles.json md5: "; docker exec $BRAIN sh -c 'md5sum /config/roles.json' 2>/dev/null | awk '{print $1}'
echo -n "  audio 文件数: "; ls /opt/folotoy/audio/ 2>/dev/null | wc -l
echo -n "  conversations 行数: "; cat /opt/folotoy/conversations/*.jsonl 2>/dev/null | wc -l

echo "===== [3/8] 应用 compose 补丁（断言式，幂等）====="
tr -d "\r" < "$W/gateway/_patch_140_compose.py" > /tmp/_patch140.py
python3 /tmp/_patch140.py
echo -n "  两处 md5 一致性: "
md5sum "$W/docker-compose.yml" /opt/folotoy/docker-compose.yml 2>/dev/null | awk '{print $1}' | tr '\n' ' '; echo
M1=$(md5sum "$W/docker-compose.yml" | awk '{print $1}')
M2=$(md5sum "$D/docker-compose.yml" | awk '{print $1}')
[ "$M1" = "$M2" ] || { echo "  ABORT: 两处 compose md5 不一致"; exit 1; }
echo "  OK 一致"

echo "===== [3.5/8] 准备生产 stt-proxy 目录（config 校验前必须有 build context）====="
mkdir -p "$D/stt-proxy"
cp -f "$W/stt-proxy/stt_proxy.py" "$D/stt-proxy/stt_proxy.py"
cp -f "$W/stt-proxy/Dockerfile" "$D/stt-proxy/Dockerfile"
echo -n "  生产 py md5: "; md5sum "$D/stt-proxy/stt_proxy.py" | awk '{print $1}'
echo -n "  真相源 py md5: "; md5sum "$W/stt-proxy/stt_proxy.py" | awk '{print $1}'

echo "===== [4/8] compose 配置语法校验 ====="
cd "$D"
if ! docker-compose config >/tmp/_compose140_rendered.yml 2>/tmp/_compose140_err.txt; then
  echo "  ABORT: docker-compose config 失败"; cat /tmp/_compose140_err.txt; exit 1
fi
echo "  config OK"; grep -nE "stt-proxy:|aqing-stt-proxy|OPENAI_WHISPER_API_BASE" /tmp/_compose140_rendered.yml

echo "===== [5/8] build 代理镜像（复用大脑镜像 python3.11，零出网零pip）====="
cd "$D/stt-proxy"
docker rmi -f aqing-stt-proxy:1.0 >/dev/null 2>&1 || true
cd "$D" && docker-compose build stt-proxy >/tmp/_build140.log 2>&1
BR=$?
tail -15 /tmp/_build140.log
[ $BR -eq 0 ] || { echo "  ABORT: build 失败 rc=$BR"; exit 1; }
docker image inspect aqing-stt-proxy:1.0 --format '  built image {{.Id}} size={{.Size}}' 2>&1 || { echo "  ABORT: 镜像未生成"; exit 1; }

echo "===== [6/8] 起代理容器（新增，独立，不动别的）====="
cd "$D"
docker rm -f $PROXY >/dev/null 2>&1 || true
docker-compose up -d --no-deps stt-proxy 2>&1 | tail -8
sleep 2
echo -n "  proxy /health: "; docker exec $PROXY python3 -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5).read().decode())" 2>&1

echo "===== [7/8] 安全重建大脑（先 rm 再 up --no-deps，禁 force-recreate）====="
echo "  停止并删除大脑容器..."
docker rm -f $BRAIN >/dev/null 2>&1 && echo "   old brain removed" || echo "   no old brain"
echo "  重建大脑（挂载卷 /audio /config 原样复用）..."
cd "$D" && docker-compose up -d --no-deps folotoy 2>&1 | tail -8
echo "  等待就绪..."; sleep 8
docker ps --filter name=folotoy_folotoy --format '   {{.Names}} | {{.Status}} | {{.Image}}'
echo -n "  大脑 STT base_url 已指向代理: "; docker exec $BRAIN sh -c 'echo $OPENAI_WHISPER_API_BASE' 2>&1
echo -n "  key len (应不变): "; docker exec $BRAIN sh -c 'echo -n "$OPENAI_WHISPER_KEY" | wc -c'
echo -n "  roles.json md5 (应不变): "; docker exec $BRAIN sh -c 'md5sum /config/roles.json' 2>/dev/null | awk '{print $1}'

echo "===== [8/8] 核验：数据零丢失 + 其它服务未动 + 网关链路 ====="
echo -n "  conversations 行数 (应≥基线): "; cat /opt/folotoy/conversations/*.jsonl 2>/dev/null | wc -l
echo -n "  audio 文件数 (应≥基线): "; ls /opt/folotoy/audio/ 2>/dev/null | wc -l
echo "  其它容器状态（应全 Up，Start time 未变）:"
docker ps --format '   {{.Names}} | {{.Status}}' | grep -E "emqx|nginx|llm_gateway|stt_proxy|folotoy_1"
echo -n "  网关 /health: "; docker exec folotoy_llm_gateway_1 sh -c 'curl -s -m 5 http://127.0.0.1:8000/health 2>&1 | head -c 120' 2>&1; echo
echo "  大脑最新日志（看有无 STT/启动报错）:"
docker logs --tail 12 $BRAIN 2>&1 | tail -12
echo "===== DEPLOY_140 DONE ====="
