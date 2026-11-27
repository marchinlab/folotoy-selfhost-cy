#!/bin/bash
set -e
cd /opt/folotoy/gateway
docker build -t aqing-gateway:1.1 . >/dev/null 2>&1
echo "镜像重建完成"
docker rm -f gwtest >/dev/null 2>&1 || true
K=$(python3 -c 'import re; s=open("/opt/folotoy/.env",encoding="utf-8").read(); m=re.search(r"^LLM_API_KEY=(.+)$",s,re.M); print(m.group(1).strip())')
docker run -d --name gwtest --network host \
  -e UPSTREAM_BASE=https://api.siliconflow.cn/v1 -e UPSTREAM_KEY="$K" \
  -e UPSTREAM_MODEL=THUDM/GLM-4-9B-0414 \
  -e NO_PROXY=api.siliconflow.cn,.cn,localhost,127.0.0.1 -e no_proxy=api.siliconflow.cn,.cn,localhost,127.0.0.1 \
  -e PORT=8010 aqing-gateway:1.1 >/dev/null
sleep 3
echo "=== 联网转述复测：今日广州新闻 ==="
curl -s http://127.0.0.1:8010/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"THUDM/GLM-4-9B-0414","messages":[{"role":"system","content":"你系广州西关阿晴，全程粤语短句，温柔,有少少俏皮。"},{"role":"user","content":"今日广州有咩新闻啊？"}],"max_tokens":600}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["choices"][0]["message"]["content"][:1000])'
echo; echo "=== 日志 ==="; docker logs gwtest 2>&1 | tail -12
