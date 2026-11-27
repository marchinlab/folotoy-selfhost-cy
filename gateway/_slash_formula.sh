#!/bin/bash
# v1.29 公式斜杠修法实测：m/s² / F/m / 10N / 2kg 该删、转中文、还是保留？
# 同 voice/rate，比较时长+字节；时长越短越干净（乱码爆发会显著拉长）。
set -e
V=zh-HK-HiuMaanNeural
R="+20%"
D=/audio/pron_slash
mkdir -p "$D"
probe() {
  python3 -m edge_tts --voice "$V" --rate="$R" --text "$2" --write-media "$D/$1.mp3" >/dev/null 2>&1 \
    || { printf "%-16s ERR  %s\n" "$1" "$2"; return; }
  local dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$D/$1.mp3" 2>/dev/null)
  local sz=$(stat -c%s "$D/$1.mp3")
  printf "%-16s %5ss %6sB  %s\n" "$1" "$dur" "$sz" "$2"
}
echo "=== m/s² 单位斜杠 ==="
probe u1_slash   "米每二次方秒（m/s²）"
probe u2_del     "米每二次方秒（ms²）"
probe u3_mei     "米每二次方秒（m每s²）"
probe u4_plain   "米每二次方秒"
echo "=== F/m 除号 ==="
probe d1_slash   "a 等于 F/m"
probe d2_del     "a 等于 Fm"
probe d3_chu     "a 等于 F 除以 m"
probe d4_space   "a 等于 F m"
echo "=== 10N / 2kg ==="
probe n1_slash   "10N / 2kg"
probe n2_del     "10N 2kg"
probe n3_chu     "10N 除以 2kg"
echo "=== 整条公式行（现网 vs 各修法）==="
probe f1_raw     "a = F/m = 10N / 2kg = 5 m/s²"
probe f2_del     "a = Fm = 10N 2kg = 5 ms²"
probe f3_chu     "a 等于 F 除以 m 等于 10N 除以 2kg 等于 5 m 每 s 平方"
echo "=== ASR 可用性 ==="
docker exec folotoy_folotoy_1 bash -lc "python3 -c 'import whisper; print(\"WHISPER_OK\")' 2>&1 | head -1; python3 -c 'import funasr; print(\"FUNASR_OK\")' 2>&1 | head -1" 2>&1 | head -3 || true
echo "=== DONE ==="
