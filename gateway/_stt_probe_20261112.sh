#!/usr/bin/env bash
# 主动探活：拿设备刚录的 wav 直接调一次硅基流动转写接口
# 只调 STT、max_retries=0、不推播/不落对话/不发 MQTT/不出声；key 不回显
echo "=== 用大脑容器现成 openai SDK 探一次 STT ==="
docker exec folotoy_folotoy_1 python3 -c "
import os, glob, openai
wavs = sorted(glob.glob('/audio/recording-*.wav'), key=lambda p: os.path.getmtime(p), reverse=True)
if not wavs:
    print('NO_WAV'); raise SystemExit
wav = wavs[0]
print('  probe_file =', os.path.basename(wav), os.path.getsize(wav), 'bytes')
try:
    client = openai.OpenAI(
        api_key=os.getenv('OPENAI_WHISPER_KEY'),
        base_url=os.getenv('OPENAI_WHISPER_API_BASE'),
        max_retries=0,
        timeout=40,
    )
    with open(wav, 'rb') as f:
        t = client.audio.transcriptions.create(
            model=os.getenv('OPENAI_WHISPER_MODEL'),
            file=f,
            language='zh',
        )
    print('  STT_PROBE = 200 OK')
    print('  text =', getattr(t, 'text', ''))
except Exception as e:
    code = getattr(e, 'status_code', None)
    print('  STT_PROBE = FAIL  status_code =', code, ' type =', type(e).__name__)
    print('  detail =', str(e)[:260])
" 2>&1
echo "=== 探活后大脑最近 2 分钟 STT 日志 ==="
docker logs --since 2m folotoy_folotoy_1 2>&1 | grep -iE "transcriptions|Transcribed|500|200 OK|Retrying" | tail -15
echo "=== DONE ==="
