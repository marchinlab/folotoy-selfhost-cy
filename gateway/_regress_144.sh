#!/bin/bash
# v1.44 全量回归：以退出码为权威判据（项目铁律，避 grep alternation 被 MSYS 吞）
cd /mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway
echo "=== py_compile 四文件 ==="
python3 -m py_compile llm_gateway.py yue_polish.py tts_pron.py news_broadcaster.py && echo "  py_compile OK" || { echo "  py_compile FAIL"; exit 1; }
echo "=== 全量单测（退出码判据）==="
ok=0; bad=0
for t in _yue44_unit _yue42_unit _yue41_unit _yue39_unit _yue32_unit _yue30_unit \
         _dan_unit _slash_unit _anchor_unit _kb_unit _subject_unit _mandarin_unit \
         _en_auto_unit _fact_unit _eng_space_unit _conv_unit _bc133_unit; do
  PYTHONIOENCODING=utf-8 python3 "$t.py" >/dev/null 2>&1
  rc=$?
  if [ "$rc" -eq 0 ]; then printf "  PASS %-18s rc=0\n" "$t"; ok=$((ok+1));
  else printf "  FAIL %-18s rc=%s\n" "$t" "$rc"; bad=$((bad+1)); fi
done
echo "=== 汇总 OK=$ok FAIL=$bad ==="
[ "$bad" -eq 0 ] && echo "REGRESS_144_ALL_PASS" || echo "REGRESS_144_HAS_FAIL"
exit "$bad"
