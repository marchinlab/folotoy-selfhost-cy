#!/bin/bash
cd /mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway
echo "=== 部署依赖脚本齐全性 ==="
MISS=0
for f in _yue41_unit.py _yue39_unit.py _verify_stream_quality.py _run_verify_stream_quality.sh \
  _test_forward_stream.py _conv_count_baseline.py _anchor_unit.py _kb_unit.py _subject_unit.py \
  _mandarin_unit.py _en_auto_unit.py _fact_unit.py _eng_space_unit.py _dan_unit.py _slash_unit.py \
  _yue30_unit.py _yue32_unit.py _conv_unit.py _bc133_unit.py _broadcast_verified.sh; do
  if [ -f "$f" ]; then echo "  OK       $f"; else echo "  MISSING  $f"; MISS=$((MISS+1)); fi
done
echo "=== 缺失 $MISS 个 ==="
echo "=== 测试目录 scripts/ 是否有同名（部分单测可能喺子目录）==="
for f in _anchor_unit.py _kb_unit.py _conv_unit.py _bc133_unit.py; do
  find . -maxdepth 2 -name "$f" 2>/dev/null | head -2
done
