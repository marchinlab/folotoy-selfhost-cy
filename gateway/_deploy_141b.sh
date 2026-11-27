#!/bin/bash
# ============================================================
# v1.41b 增量部署：只更新增强后的 yue_polish.py（整句删除版），
#   重建 aqing-gateway:1.41 同 tag、只 recreate 网关。
# 相对 v1.41：兜底从「三要素子串删」升级为「资料+清楚 同句整句删」，
#   覆盖 E2E 漏网变体「资料清清楚楚写明嘅」，防误伤铁律不变。
# ★★绝不碰大脑/stt-proxy/emqx/nginx；部署前后断言 Up time 延续。
# ★compose 已是 1.41，本脚本唔再改 tag；.bak-pre-1.41 已在、唔覆盖。
# ★回滚：还原 .bak-pre-1.41（compose + 四 py），build 1.39 重建网关。
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

echo "===== [2/7] 增强代码标记 + 单测 + 流式一致性 ====="
grep -q '句首边界（唔跨句）' $SRC/gateway/yue_polish.py && echo "  v1.41b 整句删除版标记: OK"
grep -q '资料清清楚楚写明嘅' $SRC/gateway/yue_polish.py && echo "  v1.41b E2E 变体注释: OK"
cd $SRC/gateway
python3 -m py_compile llm_gateway.py yue_polish.py tts_pron.py news_broadcaster.py && echo "  py_compile 四文件: OK"
PYTHONIOENCODING=utf-8 python3 _yue41_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 _yue39_unit.py 2>&1 | tail -1
echo "  --- 流式 11 真实稿逐句vs整段（应仍 2 条历史空白差异，无新 META 差异）---"
PYTHONIOENCODING=utf-8 python3 _verify_stream_quality.py 2>&1 | grep -E "CANTONESE_CHAIN"
echo "  --- 既有 13 套单测全回归 ---"
for t in _anchor_unit.py _kb_unit.py _subject_unit.py _mandarin_unit.py _en_auto_unit.py \
  _fact_unit.py _eng_space_unit.py _dan_unit.py _slash_unit.py _yue30_unit.py \
  _yue32_unit.py _conv_unit.py _bc133_unit.py; do
  R=$(PYTHONIOENCODING=utf-8 python3 $t 2>&1 | grep -iE "ALL_PASS|ALL PASS|全绿|FAIL [1-9]|FAIL=[1-9]" | tail -1)
  printf "  %-20s %s\n" "$t" "$R"
done

echo "===== [3/7] 备份（幂等，已存在唔覆盖）====="
[ -f $COMPOSE.bak-pre-1.41 ] || cp $COMPOSE $COMPOSE.bak-pre-1.41
[ -f $G/yue_polish.py.bak-pre-1.41 ] || cp $G/yue_polish.py $G/yue_polish.py.bak-pre-1.41 2>/dev/null || true
echo "  .bak-pre-1.41 就绪"

echo "===== [4/7] 同步增强 py（只 yue_polish.py 有变）====="
cp $SRC/gateway/llm_gateway.py        $G/llm_gateway.py
cp $SRC/gateway/news_broadcaster.py   $G/news_broadcaster.py
cp $SRC/gateway/yue_polish.py         $G/yue_polish.py
cp $SRC/gateway/tts_pron.py           $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py   $G/export_chat_html.py
cp $SRC/gateway/Dockerfile            $G/Dockerfile
cp $SRC/gateway/entrypoint.sh         $G/entrypoint.sh
cp $SRC/config/roles.json             $G/roles.json
echo "  构建源 md5:"; md5sum $G/llm_gateway.py $G/yue_polish.py
grep -q 'image: aqing-gateway:1.41' $COMPOSE && echo "  compose tag 1.41: OK" || { echo "  ABORT tag"; exit 1; }
grep -q 'OPENAI_WHISPER_API_BASE: http://stt-proxy:8000/v1' $COMPOSE && echo "  stt-proxy 切流仍在: OK"

echo "===== [5/7] 重建镜像 1.41（同 tag 覆盖）====="
cd $G
docker build -t aqing-gateway:1.41 -f Dockerfile . 2>&1 | tail -4
docker image inspect aqing-gateway:1.41 --format '  built {{.Id}}' 2>&1

echo "===== [6/7] 只 recreate 网关（禁 force，不碰其它）====="
cd $D
if ! docker-compose config >/tmp/cfg141b.out 2>&1; then echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg141b.out; exit 1; fi
echo "  compose config: OK"
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关已移除"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -4
sleep 6
echo "  --- 不动容器 Up time 应延续 ---"
for c in folotoy_folotoy_1 folotoy_stt_proxy_1 folotoy_nginx_1 folotoy_emqx_1; do
  docker ps --format '{{.Names}}|{{.Status}}' | grep "^$c|" || echo "  ⚠️ $c 未在跑!"
done
echo "  --- /health ---"; curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "  --- 镜像内 v1.41b 代码确认 ---"
docker exec folotoy_llm_gateway_1 sh -c "grep -c '句首边界（唔跨句）' /app/yue_polish.py | xargs echo '  整句版标记:'; grep -c 'V1.41_META_BAN' /app/llm_gateway.py | xargs echo '  治本注入:'"
AFTER_N=$(curl -s --max-time 10 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))")
echo "  记录: $BASE_N -> $AFTER_N $([ "$AFTER_N" -ge "$BASE_N" ] && echo '✅零丢失' || echo '⚠️下降!')"

echo "===== [7/7] 生产 E2E（X-No-Record）====="
echo "  --- A) 历史老师唐朝：验无元评论、知识完整、治本注入日志 ---"
docker exec folotoy_llm_gateway_1 python3 -c "
import json,urllib.request
body=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':False,
  'messages':[{'role':'system','content':'【角色:history_teacher】\n你系一位耐心嘅初中历史老师，用纯正广州粤语口语讲课。讲完可以轻轻追问一句，睇下学生明唔明。'},
              {'role':'user','content':'同我讲下唐朝开国嘅历史，讲详细啲。'}]}).encode()
req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=body,
  headers={'Content-Type':'application/json','X-No-Record':'1'})
a=json.loads(urllib.request.urlopen(req,timeout=120).read())['choices'][0]['message']['content']
print('  前50字:',a[:50])
import re
meta=[s for s in re.split(r'(?<=[。！？])',a) if re.search(r'资料.{0,12}(清清楚楚|写得清楚|讲得清楚)',s)]
print('  资料评价元评论句:', meta if meta else '无', '(期望 无)')
print('  实质内容(李渊/称帝):', ('李渊' in a or '称帝' in a), '(期望 True)')
print('  字数:',len(a))
"
echo "  --- 治本注入日志 ---"
docker logs --tail 60 folotoy_llm_gateway_1 2>&1 | grep -E "V1.41_META_BAN" | tail -3
echo "  ⚠️ 无清落盘动作；绝不碰大脑/stt-proxy/emqx/nginx；token 保住。"
echo "=== DONE_141b ==="
