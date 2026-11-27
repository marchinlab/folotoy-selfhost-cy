#!/bin/bash
# 18:00 播报后只读核验：多出的对话记录来源 + MP3 可下载 + MQTT 推送日志
CG=folotoy_llm_gateway_1
AUDIO=/opt/folotoy/audio
echo "===1) /logs 最新3条(查多出那条来源)==="
curl -s --max-time 5 "http://127.0.0.1:8010/logs?limit=3" 2>/dev/null | python3 -c '
import sys,json
d=json.load(sys.stdin)
print("count=",d.get("count"),"dates=",d.get("dates"))
for it in d.get("items",[]):
    print(it.get("ts"),"btn=",it.get("btn"),"role=",it.get("role"),"| q=",str(it.get("q"))[:40])
'
echo "===2) 新成品 8082 可下载==="
F=$(ls -t "$AUDIO"/aqing-news-*.mp3 2>/dev/null | head -1)
echo "file=$(basename "$F" 2>/dev/null) size=$(stat -c%s "$F" 2>/dev/null)"
curl -s -o /dev/null -w "8082 http=%{http_code} size=%{size_download} time=%{time_total}s\n" --max-time 10 "http://127.0.0.1:8082/$(basename "$F")"
echo "===3) daemon 播报日志(自证链路 + 有无误落盘)==="
docker logs "$CG" --since 6m 2>&1 | grep -E '到点播报|生成播报稿|稿成|长文切片|合成完成|\[bc\].*PUB |主动播报完成|播报失败|SEG_FAIL|Traceback' | tail -25
echo "===4) 落盘文件当晚时间线==="
find "$AUDIO" -maxdepth 1 -name 'aqing-news-*.mp3' -newermt "2026-11-11 17:55" -printf "%TH:%TM:%TS %s %f\n" 2>/dev/null | sort
