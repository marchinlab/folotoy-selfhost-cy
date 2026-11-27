#!/bin/bash
# v1.40 验证编排（不切流、不重启大脑、不改任何生产配置）
# 起临时测试代理（共享大脑网络 namespace + 带 key + 测试钩子开），
# 把客户端 copy 进大脑容器跑真实录音验证，收日志，清理。
set +e
W=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
BRAIN=folotoy_folotoy_1
TP=aqing_stt_proxy_test

cleanup() {
  echo "=== CLEANUP ==="
  docker exec $BRAIN rm -f /tmp/_verify_140_client.py /app/stt_proxy.py >/dev/null 2>&1
  docker rm -f $TP >/dev/null 2>&1
  echo "  test proxy removed; brain untouched"
}
trap cleanup EXIT

echo "=== [1] 确认大脑网络 namespace & key 存在 ==="
docker inspect $BRAIN --format 'NetMode=container:{{.Id}}' >/dev/null 2>&1 || { echo "brain not found"; exit 1; }
docker exec $BRAIN sh -c 'test -n "$OPENAI_WHISPER_KEY" && echo "  key: present" || echo "  key: MISSING"'
docker exec $BRAIN sh -c 'test -f /audio/recording-d1aa71849e414399b7d0f3a0807413d4.wav && echo "  wav: present" || echo "  wav: MISSING"'

echo "=== [2] 起临时测试代理（共享大脑网络，测试钩子开，key 透传由客户端带）==="
docker rm -f $TP >/dev/null 2>&1
docker run -d --name $TP \
  --network container:$BRAIN \
  -e STT_ALLOW_TEST=1 \
  -e UPSTREAM_URL=https://api.siliconflow.cn/v1/audio/transcriptions \
  -e PRIMARY_MODEL=TeleAI/TeleSpeechASR \
  -e FALLBACK_MODEL=FunAudioLLM/SenseVoiceSmall \
  -e UPSTREAM_TIMEOUT=30 \
  -v "$W/stt-proxy/stt_proxy.py:/app/stt_proxy.py:ro" \
  --entrypoint python3 folotoy-server:aqing-cantonese -u /app/stt_proxy.py
sleep 2
echo "  proxy health (from brain netns):"
docker exec $BRAIN python3 -c "import urllib.request;print('   ',urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5).read().decode())" 2>&1

echo "=== [3] copy 客户端进大脑容器并跑验证 ==="
docker cp "$W/gateway/_verify_140_client.py" $BRAIN:/tmp/_verify_140_client.py >/dev/null 2>&1
# 客户端 import stt_proxy 需要 /app/stt_proxy.py 在大脑容器可见（测试代理是另一容器，namespace 共享但文件系统不共享）
docker cp "$W/stt-proxy/stt_proxy.py" $BRAIN:/app/stt_proxy.py >/dev/null 2>&1
docker exec $BRAIN python3 /tmp/_verify_140_client.py
RC=$?

echo "=== [4] 测试代理请求日志 ==="
docker logs $TP 2>&1 | grep "\[stt-proxy\]" | tail -30

echo "=== VERIFY_RC=$RC ==="
exit $RC
