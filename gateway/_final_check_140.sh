#!/bin/bash
echo "=== 1. 容器状态（5 个应全 Up）==="
docker ps --format '{{.Names}} | {{.Status}} | {{.Image}}' | grep -E "folotoy_1|stt_proxy|llm_gateway|nginx|emqx"
echo "=== 2. 大脑 STT base_url 指向代理 ==="
docker exec folotoy_folotoy_1 sh -c 'echo "  OPENAI_WHISPER_API_BASE=$OPENAI_WHISPER_API_BASE"'
echo "=== 3. 代理健康（生产钩子应 false）==="
docker exec folotoy_stt_proxy_1 python3 -c "import urllib.request;print('  '+urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5).read().decode())"
echo "=== 4. 大脑 key/人设未变 ==="
echo -n "  key len: "; docker exec folotoy_folotoy_1 sh -c 'echo -n "$OPENAI_WHISPER_KEY" | wc -c'
echo -n "  roles.json md5: "; docker exec folotoy_folotoy_1 md5sum /config/roles.json | awk '{print "  "$1}'
echo "=== 5. compose 两处 md5 一致 + 备份在 ==="
md5sum /mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/docker-compose.yml /opt/folotoy/docker-compose.yml
ls -la /opt/folotoy/docker-compose.yml.bak-pre-1.40 | awk '{print "  backup:",$5,$9}'
echo "=== 6. 生产 py md5 与真相源一致 ==="
md5sum /opt/folotoy/stt-proxy/stt_proxy.py /mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/stt-proxy/stt_proxy.py
echo "=== 7. 网关 v1.39 无回归 ==="
docker exec folotoy_llm_gateway_1 python3 -c "import urllib.request;print('  '+urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5).read().decode()[:90])"
echo "=== 8. 大脑最新日志无 STT 报错 ==="
docker logs --tail 6 folotoy_folotoy_1 2>&1 | tail -6
echo "=== FINAL 140 DONE ==="
