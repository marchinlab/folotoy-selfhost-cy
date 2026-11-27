#!/bin/bash
# 只读勘察大脑容器：镜像/挂载/token 位置/STT 代码/构建方式。不动任何服务。
set +e
C=folotoy_folotoy_1
echo "=== [1] 大脑相关镜像 tags ==="
docker images --format '{{.Repository}}:{{.Tag}}|{{.ID}}|{{.CreatedSince}}|{{.Size}}' | grep -iE 'folotoy|aqing'
echo "=== [2] 大脑容器 镜像ID/状态/启动/重启次数 ==="
docker inspect $C --format 'Image={{.Image}} Status={{.State.Status}} StartedAt={{.State.StartedAt}} RestartCount={{.RestartCount}}'
echo "=== [3] 挂载卷 (token/数据是否在卷里 = 重建能否保住) ==="
docker inspect $C --format '{{range .Mounts}}{{.Type}} {{.Source}} -> {{.Destination}} rw={{.RW}}{{println}}{{end}}'
echo "=== [4] Entrypoint / Cmd / WorkingDir ==="
docker inspect $C --format 'Entrypoint={{.Config.Entrypoint}} Cmd={{.Config.Cmd}} WorkDir={{.Config.WorkingDir}}'
echo "=== [5] STT 相关环境变量 (密钥行整行过滤, 只看非敏感值) ==="
docker exec $C sh -c 'env | grep -iE "WHISPER|STT|ASR|SPEECH|AUDIO|OPENAI" | grep -viE "KEY|TOKEN|SECRET|PASSWORD"'
echo "=== [6] transcriptions / retry 代码文件定位 ==="
docker exec $C sh -c 'echo "-- trans--"; grep -rln "transcriptions" /app 2>/dev/null; echo "-- retry/err --"; grep -rln "Retrying\|max_retries\|InternalServerError\|audio.transcriptions" /app 2>/dev/null | head -20'
echo "=== [7] /app 顶层 + core 目录 ==="
docker exec $C sh -c 'ls -la /app; echo "--- core ---"; ls -la /app/core 2>/dev/null'
echo "=== [8] 疑似 token/授权/数据文件 (在容器可写层还是卷) ==="
docker exec $C sh -c 'find /app /data /config -maxdepth 3 -type f \( -iname "*token*" -o -iname "*auth*" -o -iname "*license*" -o -iname "*.db" -o -iname "*secret*" -o -iname "*.json" \) 2>/dev/null | head -40'
echo "=== DONE ==="
