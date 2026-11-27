#!/usr/bin/env bash
# 「对着说话没反应」只读诊断：UDP 语音链路 (设备 --UDP8085--> 大脑 --Whisper--> 文字 --> 网关)
# 不推播、不落盘、不重启、不发包触发
echo "=== 1. 大脑日志: 语音/STT/Whisper/错误相关 (本次启动至今全量) ==="
docker logs folotoy_folotoy_1 2>&1 | grep -iE "whisper|stt|asr|transcri|speech|audio|udp|8085|录音|语音|转写|error|traceback|exception|failed" | tail -50
echo "=== 2. 大脑日志: 最近 50 行原始 ==="
docker logs --tail 50 folotoy_folotoy_1 2>&1
echo "=== 3. Whisper 后端(硅基流动, 国内域名)连通性 - 拉模型列表不花钱 ==="
docker exec folotoy_folotoy_1 python3 -c "
import urllib.request
try:
    r=urllib.request.urlopen('https://api.siliconflow.cn/v1/models',timeout=12)
    print('  siliconflow /v1/models ->',r.status)
except Exception as e:
    print('  ERR',type(e).__name__,str(e)[:160])
" 2>&1
echo "=== 4. 大脑 Whisper 配置 (脱敏, 只看模型/base) ==="
docker exec folotoy_folotoy_1 sh -c "env | grep -iE \"WHISPER|SPEECH|STT|ASR|AUDIO\" | grep -viE \"KEY|TOKEN|SECRET\"" 2>&1
echo "=== 5. UDP 8085 socket 完整状态 (0x1F95) ==="
docker exec folotoy_folotoy_1 sh -c "grep -i ':1F95 ' /proc/net/udp 2>/dev/null || echo NOT_BOUND" 2>&1
echo "=== 6. 网关最近 3h 有无真实 REQ (确认 09:08 后仍无) ==="
docker logs --since 3h folotoy_llm_gateway_1 2>&1 | grep -E "REQ q=|RESP [0-9]{3}" | tail -12
echo "=== DONE ==="
