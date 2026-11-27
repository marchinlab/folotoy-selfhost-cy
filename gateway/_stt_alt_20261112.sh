#!/usr/bin/env bash
# 只读对照：同一条真实录音分别喂两个硅基流动免费 ASR 模型，比较成功率与粤语质量
# 只调 STT、max_retries=0、不改配置/不重建/不推播/不出声
docker exec folotoy_folotoy_1 python3 -c "
import os, glob, openai, time
c=openai.OpenAI(api_key=os.getenv('OPENAI_WHISPER_KEY'),base_url=os.getenv('OPENAI_WHISPER_API_BASE'),max_retries=0,timeout=45)
w=sorted(glob.glob('/audio/recording-*.wav'),key=os.path.getmtime,reverse=True)[0]
tts=sorted(glob.glob('/audio/voice-*.mp3'),key=os.path.getmtime,reverse=True)[0]
models=['FunAudioLLM/SenseVoiceSmall','TeleAI/TeleSpeechASR']
for m in models:
    for label,path in [('设备录音',w),('TTS已知',tts)]:
        ok=0
        for i in range(3):
            try:
                t=c.audio.transcriptions.create(model=m,file=open(path,'rb'),language='zh')
                if i==0: print('  [%s] %s -> 200  %s'%(m,label,getattr(t,'text','')[:44]))
                ok+=1
            except Exception as e:
                print('  [%s] %s -> probe%d FAIL %s'%(m,label,i+1,getattr(e,'status_code',None)))
            time.sleep(1)
        print('      成功率 %d/3'%ok)
" 2>&1
echo "=== DONE ==="
