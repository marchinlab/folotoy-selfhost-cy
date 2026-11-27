#!/bin/sh
# 静态侦察：主动播报可行性 + 长文 TTS 拼接工具 + MQTT 下发协议
echo "=== 1. 音频拼接工具（分段并行合成后要 concat）==="
which ffmpeg ffprobe 2>/dev/null || echo "  NO ffmpeg"
python3 -c "import pydub; print('  pydub', pydub.__version__)" 2>&1 | head -2

echo "=== 2. MQTT 客户端库（动态抓包用）==="
which mosquitto_sub 2>/dev/null || echo "  NO mosquitto_sub"
python3 -c "import paho.mqtt.client as m; print('  paho-mqtt OK')" 2>&1 | head -2

echo "=== 3. 服务端编译 .so 文件清单 ==="
find /src/folotoy -name "*.so" 2>/dev/null | head -25

echo "=== 4. 从 .so 挖 MQTT topic / 播放 / 音频相关字符串 ==="
for f in $(find /src/folotoy -name "*.so" 2>/dev/null); do
  hits=$(strings -n 6 "$f" 2>/dev/null | grep -Ei "thing/|/user/|command/call|postAck|play|audio|mqtt|tts|voice|url" | head -20)
  if [ -n "$hits" ]; then echo "--- $f"; echo "$hits"; fi
done

echo "=== 5. 挂载配置目录里的所有文件 ==="
find /config -maxdepth 2 -type f 2>/dev/null

echo "=== 6. 服务端 TTS/AUDIO/HTTPX 相关环境变量 ==="
env | grep -iE "TTS|MAX|AUDIO|VOICE|HTTPX|EXECUTOR|SPEECH" | sort

echo "=== 7. edge-tts 版本与可用参数 ==="
/usr/local/bin/edge-tts.real --version 2>&1
/usr/local/bin/edge-tts.real --help 2>&1 | grep -iE "rate|volume|pitch|text|voice|write-media|words" | head -20
