#!/bin/bash
cd /opt/folotoy/gateway || exit 1
for f in llm_gateway.py yue_polish.py; do
  b="${f}.bak-pre-1.39"
  if [ ! -f "$b" ]; then cp -f "$f" "$b"; echo "backed up $f -> $b"; else echo "backup exists: $b"; fi
done
echo "=== md5 ==="
md5sum llm_gateway.py llm_gateway.py.bak-pre-1.39 yue_polish.py yue_polish.py.bak-pre-1.39
