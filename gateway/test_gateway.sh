#!/bin/bash
# 独立验证网关：透传 + 联网转述。在 WSL 内执行，避开跨层转义。
set -e
K=$(python3 -c 'import re; s=open("/opt/folotoy/.env",encoding="utf-8").read(); m=re.search(r"^LLM_API_KEY=(.+)$",s,re.M); print(m.group(1).strip())')
echo "key_len=${#K}"

docker rm -f gwtest >/dev/null 2>&1 || true
docker run -d --name gwtest --network host \
  -e UPSTREAM_BASE=https://api.siliconflow.cn/v1 \
  -e UPSTREAM_KEY="$K" \
  -e UPSTREAM_MODEL=THUDM/GLM-4-9B-0414 \
  -e NO_PROXY=api.siliconflow.cn,.cn,localhost,127.0.0.1 \
  -e no_proxy=api.siliconflow.cn,.cn,localhost,127.0.0.1 \
  -e PORT=8010 \
  aqing-gateway:1.0 >/dev/null
sleep 3
echo "=== key状态 ==="
docker logs gwtest 2>&1 | grep key_set

echo "=== 测试1: 普通对话(透传,不联网) ==="
curl -s http://127.0.0.1:8010/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"THUDM/GLM-4-9B-0414","messages":[{"role":"system","content":"你系广州西关阿晴，全程粤语短句。"},{"role":"user","content":"你叫咩名啊？"}],"max_tokens":120}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["choices"][0]["message"]["content"][:200])'

echo "=== 测试2: 联网意图(抓真实新闻+粤语转述) ==="
curl -s http://127.0.0.1:8010/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"THUDM/GLM-4-9B-0414","messages":[{"role":"system","content":"你系广州西关阿晴，全程粤语短句，温柔。"},{"role":"user","content":"今日广州有咩新闻啊？"}],"max_tokens":500}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["choices"][0]["message"]["content"][:800])'

echo "=== 测试3: 长文意图(应提到长文/字数多) ==="
curl -s http://127.0.0.1:8010/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"THUDM/GLM-4-9B-0414","messages":[{"role":"system","content":"你系广州西关阿晴，全程粤语，短句。"},{"role":"user","content":"详细啲讲下广州早茶，讲长啲"}],"max_tokens":200}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); c=d["choices"][0]["message"]["content"]; print("字数=",len(c)); print(c[:300])'

echo "=== 网关日志 ==="
docker logs gwtest 2>&1 | tail -20
