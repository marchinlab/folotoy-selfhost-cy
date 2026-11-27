#!/usr/bin/env bash
# 对照实验：同一 STT 接口分别喂 ①设备刚录的 wav ②已知有效的 TTS 成品 mp3
# 目的：区分「上游全站 500」vs「这条录音特有的问题」
# 只读探活：max_retries=0，不推播/不落对话/不发MQTT/不出声，key 不回显
echo "=== A/B 对照探活 (max_retries=0) ==="
docker exec folotoy_folotoy_1 python3 -c "
import os, glob, openai
client = openai.OpenAI(
    api_key=os.getenv('OPENAI_WHISPER_KEY'),
    base_url=os.getenv('OPENAI_WHISPER_API_BASE'),
    max_retries=0, timeout=40,
)
model = os.getenv('OPENAI_WHISPER_MODEL')
def probe(label, path):
    try:
        with open(path, 'rb') as f:
            t = client.audio.transcriptions.create(model=model, file=f, language='zh')
        print('  %s -> 200 OK  text=%s' % (label, getattr(t, 'text', '')[:50]))
    except Exception as e:
        print('  %s -> FAIL status=%s type=%s' % (label, getattr(e,'status_code',None), type(e).__name__))
        print('       detail=%s' % str(e)[:180])
wavs = sorted(glob.glob('/audio/recording-*.wav'), key=os.path.getmtime, reverse=True)
mp3s = sorted(glob.glob('/audio/voice-*.mp3'), key=os.path.getmtime, reverse=True)
if wavs: probe('A 设备刚录 wav ('+os.path.basename(wavs[0])+')', wavs[0])
if mp3s: probe('B TTS成品 mp3 ('+os.path.basename(mp3s[0])+')', mp3s[0])
" 2>&1
echo "=== 备用 STT 配置 (脱敏) ==="
grep -iE "^(STT_TYPE|STT_API_BASE|STT_MODEL|STT_API_KEY)=" /opt/folotoy/.env 2>/dev/null | sed -E 's/^(STT_API_KEY=).*/\1<SET>/' 2>&1
echo "=== 大脑最近 3 分钟 STT 日志 ==="
docker logs --since 3m folotoy_folotoy_1 2>&1 | grep -iE "transcriptions|Transcribed|500|200 OK|Retrying" | tail -12
echo "=== DONE ==="
