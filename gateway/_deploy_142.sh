#!/bin/bash
# ============================================================
# v1.42 增量部署：只更新 tts_pron.py（新增「走过来/走過來」->「行過嚟」词级正音），
#   重建 aqing-gateway:1.42、只 recreate 网关。
# 相对 v1.41b：新增一条【词级】粤语正音，主人 A/B 试听第3段真人耳选定「行過嚟」。
#   ⚠️「称帝」个称本版唔郁（未获锚字拍板，宁可少改不可改错），单独开版。
# ★★绝不碰大脑/stt-proxy/emqx/nginx；部署前后断言 Up time 延续、保 UDP 令牌。
# ★回滚：还原 tts_pron.py.bak-pre-1.42 + docker-compose.yml.bak-pre-1.42
#        (compose 改返 1.41)，build 1.41 重建网关即可，唔使重启大脑、唔使踢设备。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [1/7] 基线（只读）====="
BASE_N=$(CONV_DIR=$D/conversations python3 $G/_conv_count_baseline.py 2>/dev/null || echo "?")
echo "  部署前唯一记录数: $BASE_N"
echo "  不动容器 Up time 基线:"
for c in folotoy_folotoy_1 folotoy_stt_proxy_1 folotoy_nginx_1 folotoy_emqx_1; do
  docker ps --format '{{.Names}}|{{.Status}}' | grep "^$c|" || echo "  $c 未在跑(!)"
done

echo "===== [2/7] 代码标记 + 单测 + 全量回归 ====="
grep -q 'v1.42' $SRC/gateway/tts_pron.py && echo "  v1.42 docstring 标记: OK"
grep -q '走过来", "行過嚟' $SRC/gateway/tts_pron.py && echo "  词级映射标记: OK"
cd $SRC/gateway
python3 -m py_compile llm_gateway.py yue_polish.py tts_pron.py news_broadcaster.py && echo "  py_compile 四文件: OK"
echo "  --- v1.42 专项 ---"
PYTHONIOENCODING=utf-8 python3 _yue42_unit.py 2>&1 | tail -1
echo "  --- 全量回归（16 套，退出码判据）---"
bash $SRC/gateway/_regress_142.sh 2>&1 | tail -2

echo "===== [3/7] 备份（幂等，已存在唔覆盖）====="
[ -f $G/tts_pron.py.bak-pre-1.42 ] || cp $G/tts_pron.py $G/tts_pron.py.bak-pre-1.42 2>/dev/null || true
[ -f $COMPOSE.bak-pre-1.42 ] || cp $COMPOSE $COMPOSE.bak-pre-1.42
echo "  .bak-pre-1.42 就绪（工作区侧已建，此处补生产侧）"

echo "===== [4/7] 同步 py（只 tts_pron.py 有变）+ compose tag ====="
cp $SRC/gateway/llm_gateway.py        $G/llm_gateway.py
cp $SRC/gateway/news_broadcaster.py   $G/news_broadcaster.py
cp $SRC/gateway/yue_polish.py         $G/yue_polish.py
cp $SRC/gateway/tts_pron.py           $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py   $G/export_chat_html.py
cp $SRC/gateway/Dockerfile            $G/Dockerfile
cp $SRC/gateway/entrypoint.sh         $G/entrypoint.sh
cp $SRC/config/roles.json             $G/roles.json
cp $SRC/docker-compose.yml            $COMPOSE
echo "  构建源 md5:"; md5sum $G/tts_pron.py $SRC/gateway/tts_pron.py
grep -q 'image: aqing-gateway:1.42' $COMPOSE && echo "  compose tag 1.42: OK" || { echo "  ABORT tag"; exit 1; }
grep -q 'OPENAI_WHISPER_API_BASE: http://stt-proxy:8000/v1' $COMPOSE && echo "  stt-proxy 切流仍在: OK"

echo "===== [5/7] 重建镜像 1.42 ====="
cd $G
docker build -t aqing-gateway:1.42 -f Dockerfile . 2>&1 | tail -4
docker image inspect aqing-gateway:1.42 --format '  built {{.Id}}' 2>&1

echo "===== [6/7] 只 recreate 网关（禁 force，不碰其它）====="
cd $D
if ! docker-compose config >/tmp/cfg142.out 2>&1; then echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg142.out; exit 1; fi
echo "  compose config: OK"
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关已移除"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -4
sleep 6
echo "  --- 不动容器 Up time 应延续 ---"
for c in folotoy_folotoy_1 folotoy_stt_proxy_1 folotoy_nginx_1 folotoy_emqx_1; do
  docker ps --format '{{.Names}}|{{.Status}}' | grep "^$c|" || echo "  ⚠️ $c 未在跑!"
done
echo "  --- /health ---"; curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "  --- 镜像内 v1.42 词级映射确认 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import tts_pron; print('  镜像内 fix(走过来) =', tts_pron.fix('走过来')); print('  镜像内 fix(走過來) =', tts_pron.fix('走過來'))"
AFTER_N=$(curl -s --max-time 10 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))")
echo "  记录: $BASE_N -> $AFTER_N $([ "$AFTER_N" -ge "$BASE_N" ] && echo '✅零丢失' || echo '⚠️下降!')"

echo "===== [7/7] 生产 E2E（X-No-Record，验四路链路 fix 生效）====="
echo "  --- 粤语角色非流式：验「走过来」在整段被换成「行過嚟」---"
docker exec folotoy_llm_gateway_1 python3 -c "
import json,urllib.request
body=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':False,
  'messages':[{'role':'system','content':'【角色:chitchat】你系阿晴，用纯正广州粤语口语同人倾偈，简短自然。'},
              {'role':'user','content':'我想行过去搵你，你走过来接我啦。'}]}).encode()
req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=body,
  headers={'Content-Type':'application/json','X-No-Record':'1'})
a=json.loads(urllib.request.urlopen(req,timeout=120).read())['choices'][0]['message']['content']
print('  回答前80字:',a[:80])
print('  含残留「走过来/走過來」:', ('走过来' in a or '走過來' in a), '(期望 False)')
print('  含正音「行過嚟」或本身地道:', ('行過嚟' in a), '(模型未必原样复述,False亦正常)')
print('  字数:',len(a))
"
echo "  --- 直验网关 fixer 作用于典型播报句（不走 LLM，纯函数链）---"
docker exec folotoy_llm_gateway_1 python3 -c "
import tts_pron as t, yue_polish as y
nc,_=y.polish('而家走过来啦，过马路唔好乱跑，过程要小心。',report=True)
nc=t.fix(nc); nc=y.clean_tts_symbols(nc)
print('  polish→fix→clean =',nc)
print('  「走过来」已正音:', '行過嚟' in nc)
print('  「过马路/过程」未误伤:', ('过马路' in nc and '过程' in nc))
"
echo "  ⚠️ 无清落盘动作；绝不碰大脑/stt-proxy/emqx/nginx；UDP 令牌保住、唔使踢设备。"
echo "=== DONE_142 ==="
