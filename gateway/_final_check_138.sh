#!/bin/bash
SH=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/_broadcast_verified.sh
echo "=== FINAL v1.38 check ==="
bash -n "$SH" && echo "  [OK] bash -n syntax"
echo "  [判据行]"; grep -n '10>=sz\*ratio' "$SH"
echo "  [备份]"; ls -la "$SH.bak-pre-1.38"
echo "  [阈值变量]"; grep -n 'COMPLETE_RATIO=\|COMPLETE_MIN_BYTES=' "$SH"
echo "  [probe]"; bash "$SH" probe 2>&1 | tail -3
