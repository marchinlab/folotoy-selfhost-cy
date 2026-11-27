#!/bin/bash
# v1.38 出声判据本地单测：喂模拟/真实 nginx 行，验证 complete_line 判定。
# 全程唔碰生产、唔推、唔出声。判定逻辑必须与 _broadcast_verified.sh 一致。
set -u
COMPLETE_RATIO=${COMPLETE_RATIO:-0.9}
COMPLETE_MIN_BYTES=${COMPLETE_MIN_BYTES:-1000000}
DEV=${DEV_IP:-YOUR_DEVICE_IP}

# judge(size) <- stdin = nginx access 行组；输出 SUCCESS / FAIL
judge(){
  awk -v sz="$1" -v dev="$DEV" -v ratio="$COMPLETE_RATIO" -v minb="$COMPLETE_MIN_BYTES" \
    'BEGIN{thr=(sz*ratio<minb?sz*ratio:minb)}
     $1==dev && $9=="200" && $10>=thr {print "SUCCESS"; found=1; exit}
     END{if(!found) print "FAIL"}'
}

PASS=0; FAIL=0
case_run(){ # label size want ; stdin via heredoc
  local label="$1" sz="$2" want="$3" got
  got=$(judge "$sz")
  if [ "$got" = "$want" ]; then echo "  [OK]   $label -> $got (want=$want)"; PASS=$((PASS+1));
  else echo "  [FAIL] $label -> $got (want=$want)"; FAIL=$((FAIL+1)); fi
}

echo "=== v1.38 complete_line judgement unit test (ratio=$COMPLETE_RATIO min=$COMPLETE_MIN_BYTES dev=$DEV) ==="

case_run "昨晚PM真出声 100%" 1094493 SUCCESS <<EOF
$DEV - - [11/Nov/2026:10:52:00 +0000] "GET /aqing-news-replay.mp3 HTTP/1.1" 200 1094493 "-" "-" "-"
EOF

case_run "今日AM 40k 99.5%断连" 1039677 SUCCESS <<EOF
$DEV - - [12/Nov/2026:00:50:52 +0000] "GET /aqing-news-replay-084840.mp3 HTTP/1.1" 200 1035127 "-" "-" "-"
EOF

case_run "今日AM 48k 86.9%断连(大文件按1MB门槛)" 1247277 SUCCESS <<EOF
$DEV - - [12/Nov/2026:00:43:41 +0000] "GET /aqing-news-DEVICEKEY_REDACTED.mp3 HTTP/1.1" 200 1083950 "-" "-" "-"
EOF

case_run "v1.33冷重启掐断 71.8% (要挡住)" 1064493 FAIL <<EOF
$DEV - - [11/Nov/2026:10:00:00 +0000] "GET /aqing-news-cut.mp3 HTTP/1.1" 200 764306 "-" "-" "-"
EOF

case_run "只下一小截 48KB (要挡住)" 1039677 FAIL <<EOF
$DEV - - [12/Nov/2026:00:00:00 +0000] "GET /aqing-news-tiny.mp3 HTTP/1.1" 200 49152 "-" "-" "-"
EOF

case_run "自己curl自测 非设备IP (要挡住)" 1039677 FAIL <<EOF
DOCKER_GATEWAY_IP - - [12/Nov/2026:00:00:00 +0000] "GET /aqing-news-self.mp3 HTTP/1.1" 200 1035127 "curl/7.81" "-" "-"
EOF

case_run "非200状态码 206 (要挡住)" 1039677 FAIL <<EOF
$DEV - - [12/Nov/2026:00:00:00 +0000] "GET /aqing-news-range.mp3 HTTP/1.1" 206 1035127 "-" "-" "-"
EOF

case_run "多行取最佳 有一行达标即成功" 1039677 SUCCESS <<EOF
$DEV - - [12/Nov/2026:00:49:00 +0000] "GET /aqing-news-multi.mp3 HTTP/1.1" 200 50000 "-" "-" "-"
$DEV - - [12/Nov/2026:00:50:52 +0000] "GET /aqing-news-multi.mp3 HTTP/1.1" 200 1033691 "-" "-" "-"
EOF

echo "=== RESULT pass=$PASS fail=$FAIL ==="
[ "$FAIL" -eq 0 ] || exit 1
