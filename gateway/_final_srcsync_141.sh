#!/bin/bash
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
echo "=== 真相源(Windows) vs 生产(/opt/folotoy) md5 一致性 ==="
for f in llm_gateway.py yue_polish.py news_broadcaster.py tts_pron.py export_chat_html.py; do
  m1=$(md5sum "$SRC/gateway/$f" | awk '{print $1}')
  m2=$(md5sum "$D/gateway/$f" | awk '{print $1}')
  echo "  $f  SRC=$m1  PROD=$m2  $([ "$m1" = "$m2" ] && echo SAME || echo 'DIFF!')"
done
echo "=== 文档 v1.41 提及 ==="
grep -c "v1.41" "$SRC/火火兔7键学科老师说明.md" | xargs echo "  文档:"
echo "=== compose 真相源 vs 生产 ==="
m1=$(md5sum "$SRC/docker-compose.yml" | awk '{print $1}')
m2=$(md5sum "$D/docker-compose.yml" | awk '{print $1}')
echo "  compose SRC=$m1 PROD=$m2 $([ "$m1" = "$m2" ] && echo SAME || echo 'DIFF!')"
echo "=== DONE ==="
