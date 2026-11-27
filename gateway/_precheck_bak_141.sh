#!/bin/bash
# v1.41 部署前：只读勘察 + 幂等备份（.bak-pre-1.41）
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [A] 当前容器状态（大脑/stt-proxy Up time 作基线）====="
docker ps --format '{{.Names}} | {{.Status}} | {{.Image}}' | grep -E 'folotoy_' | sort

echo "===== [B] compose 当前网关镜像 tag ====="
grep -n 'image: aqing-gateway' $COMPOSE
echo "--- stt-proxy 服务在不在（v1.40 必须保留）---"
grep -nE 'stt-proxy|OPENAI_WHISPER_API_BASE' $COMPOSE

echo "===== [C] 对话记录基线（唯一记录数）====="
cp $SRC/gateway/_conv_count_baseline.py $G/_conv_count_baseline.py 2>/dev/null || true
CONV_DIR=$D/conversations python3 $G/_conv_count_baseline.py 2>/dev/null || echo 'baseline script err'

echo "===== [D] 源码 vs 生产 md5（应一致才改）====="
for f in llm_gateway.py yue_polish.py; do
  m1=$(md5sum $SRC/gateway/$f | awk '{print $1}')
  m2=$(md5sum $G/$f | awk '{print $1}')
  echo "  $f  SRC=$m1  PROD=$m2  $([ "$m1" = "$m2" ] && echo SAME || echo DIFF!)"
done

echo "===== [E] 幂等备份 .bak-pre-1.41（已存在绝不覆盖）====="
[ -f $COMPOSE.bak-pre-1.41 ] && echo "  compose bak 已在" || { cp $COMPOSE $COMPOSE.bak-pre-1.41; echo "  compose bak 新建"; }
for f in llm_gateway.py news_broadcaster.py yue_polish.py tts_pron.py _broadcast_verified.sh; do
  if [ -f $G/$f ]; then
    [ -f $G/$f.bak-pre-1.41 ] && echo "  $f.bak 已在" || { cp $G/$f $G/$f.bak-pre-1.41; echo "  $f.bak 新建"; }
  fi
done
echo "  --- 备份 md5 校验（compose + 四 py 应与原件一致）---"
md5sum $COMPOSE.bak-pre-1.41 $G/llm_gateway.py.bak-pre-1.41 $G/yue_polish.py.bak-pre-1.41
echo "=== PRECHECK_DONE ==="
