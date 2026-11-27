#!/bin/bash
# 一次性：今日 AM 新闻 MP3 48k -> 40k（成品层，原文件保留），
# 规避火火兔 ~1.1MB 下载上限，再走确认型 replay 重推。
# 单会话跑完：转码 -> 重推 -> 盯 nginx 完整下载 -> 落 done -> 保活起播。
set -u
GW=folotoy_llm_gateway_1
AUDIO=/opt/folotoy/audio
SRC=aqing-news-DEVICEKEY_REDACTED.mp3
OUT=aqing-news-DEVICEKEY_REDACTED-40k.mp3
SH=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/_broadcast_verified.sh
LIMIT=1094493   # 昨晚 PM 真出声成功的文件大小

echo "[lowbr] === START $(date '+%F %T') ==="
echo "[lowbr] check mp3 encoder in $GW"
docker exec "$GW" sh -c "ffmpeg -hide_banner -encoders 2>/dev/null | grep -qi libmp3lame" && ENC=OK || ENC=NO
echo "[lowbr] encoder=$ENC"
if [ "$ENC" != "OK" ]; then
  echo "[lowbr] FATAL no mp3 encoder, nothing changed, no push"
  exit 3
fi

docker exec "$GW" ffmpeg -y -loglevel error -i "/audio/$SRC" -codec:a libmp3lame -b:a 40k "/audio/$OUT"
RC=$?
echo "[lowbr] ffmpeg 40k rc=$RC"
[ "$RC" -ne 0 ] && { echo "[lowbr] FATAL transcode failed, no push"; exit 3; }

SZ=$(stat -c%s "$AUDIO/$OUT")
echo "[lowbr] $OUT size=$SZ limit=$LIMIT"
if [ "$SZ" -ge "$LIMIT" ]; then
  echo "[lowbr] 40k still >= limit, fallback 34k"
  docker exec "$GW" ffmpeg -y -loglevel error -i "/audio/$SRC" -codec:a libmp3lame -b:a 34k "/audio/$OUT" || { echo "[lowbr] FATAL 34k failed"; exit 3; }
  SZ=$(stat -c%s "$AUDIO/$OUT")
  echo "[lowbr] 34k size=$SZ"
fi
docker exec "$GW" ffprobe -v error -show_entries format=bit_rate,duration,size -of default=nw=1 "/audio/$OUT" 2>&1
echo "[lowbr] original kept: $AUDIO/$SRC ($(stat -c%s "$AUDIO/$SRC")B)"
echo "[lowbr] exec confirmed replay (single session)"
exec bash "$SH" replay "$OUT"
