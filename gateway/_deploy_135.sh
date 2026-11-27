#!/bin/bash
# ============================================================
# 阿晴网关 v1.35 固化部署（2026-11-11 晚）——修「讲唐朝开国嘅故事」唔联网、
#   30B 凭记忆将《礼记·礼运》「天下为公」张冠李戴塞畀李渊。
#   llm_gateway.py 四处改（只此一文件，回滚最干净）：
#     ① 新增 HISTORY_ANCHORS + is_history_fact + _history_search_subject
#        （朝代/帝王/事件/史书/思想归属词 + 「讲<专名>嘅故事/生平」泛化）
#     ② is_knowledge_intent / is_fact_check_needed / is_subject_question
#        三处 BLOCK 判定加「and not is_history_fact(q)」+ 史实命中强制联网
#     ③ _kb_search_query / gather_knowledge：史实题用干净锚点词查
#        （「讲唐朝开拓嘅故事」->「唐朝 开拓 对外交流 历史」）
#     ④ do_POST want_kb 抓唔到资料时，史实题注入【正向】兜底硬钉
#        （唔点具体错名词，反粉红大象；只讲有把握嘅、冇把握就坦白）
# ★只重建网关、唔重启大脑/nginx/emqx、保 token。姿势：docker rm -f + up --no-deps
#   （【不加 --force-recreate】，避开 v1.29.2 ContainerConfig bug）。
# ★★数据铁律：任何步骤都唔会 truncate/move/重命名 conversations/；
#   部署前后唯一记录数必须相等（网络新增另计，绝唔清落盘）。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [0/8] 部署前数据基线（只读）====="
mkdir -p $G
cp $SRC/gateway/_conv_count_baseline.py $G/_conv_count_baseline.py
BASE_N=$(CONV_DIR=$D/conversations python3 $G/_conv_count_baseline.py 2>/dev/null || echo "?")
echo "  部署前唯一记录数: $BASE_N"

echo "===== [1/8] 校验 v1.35 新代码标记 + v1.33/v1.32 旧链路保护 ====="
grep -q 'def is_history_fact(q)' $SRC/gateway/llm_gateway.py && echo "  v1.35 is_history_fact: OK"
grep -q 'HISTORY_ANCHORS = (' $SRC/gateway/llm_gateway.py && echo "  v1.35 史实锚点表: OK"
grep -q 'def _history_search_subject(q)' $SRC/gateway/llm_gateway.py && echo "  v1.35 搜索词提纯: OK"
grep -q 'KNOWLEDGE_BLOCK) and not is_history_fact(q)' $SRC/gateway/llm_gateway.py && echo "  v1.35 BLOCK 软判(3处): OK"
grep -q 'HISTORY_NO_REF -> 注入正向史实兜底' $SRC/gateway/llm_gateway.py && echo "  v1.35 兜底硬钉: OK"
grep -q 'image: aqing-gateway:1.35' $SRC/docker-compose.yml && echo "  compose 镜像 1.35: OK"
# 旧链路保护
grep -q 'def is_gz_news_intent' $SRC/gateway/llm_gateway.py && echo "  广州本地新闻(1.15): OK"
grep -q 'def gather_weather' $SRC/gateway/llm_gateway.py && echo "  天气数值(1.14): OK"
grep -q 'def is_poem_intent' $SRC/gateway/llm_gateway.py && echo "  诗词豁免(1.17): OK"
grep -q 'def is_fact_check_needed' $SRC/gateway/llm_gateway.py && echo "  事实核查(1.26): OK"
grep -q 'CONV_KEEP_DAYS = max' $SRC/gateway/llm_gateway.py && echo "  30天保留(1.31): OK"
grep -q '("会", "會")' $SRC/gateway/tts_pron.py && echo "  多音字正音(1.16): OK"
grep -q 'def polish(text, report=False, poem=False)' $SRC/gateway/yue_polish.py && echo "  粤语化 poem 参数: OK"
grep -q 'TOPIC_ACK = "/sys/folotoy/+/thing/command/callAck"' $SRC/gateway/news_broadcaster.py && echo "  播报 callAck(1.33): OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py $SRC/gateway/news_broadcaster.py \
  $SRC/gateway/yue_polish.py $SRC/gateway/tts_pron.py && echo "  py_compile 四文件: OK"

echo "===== [2/8] 单元回归（v1.35 史实题 + 旧链路零回归）====="
cd $SRC/gateway
echo "  --- v1.35 史实题意图（期望 0/16 不符）---"
PYTHONIOENCODING=utf-8 python3 _diag_story.py 2>&1 | grep -E "NET 判定|!!!"
for t in _conv_unit.py _fact_unit.py _en_auto_unit.py _mandarin_unit.py _yue32_unit.py; do
  printf "  %-22s" "$t"
  PYTHONIOENCODING=utf-8 python3 $t 2>&1 | tail -1
done

echo "===== [3/8] 备份生产 + 校验 compose ====="
[ -f $COMPOSE.bak-pre-1.35 ] || cp $COMPOSE $COMPOSE.bak-pre-1.35
for f in llm_gateway.py news_broadcaster.py yue_polish.py tts_pron.py; do
  [ -f $G/$f.bak-pre-1.35 ] || cp $G/$f $G/$f.bak-pre-1.35
done
[ -f $D/.env.bak-pre-1.35 ] || cp $D/.env $D/.env.bak-pre-1.35
echo "  生产备份 .bak-pre-1.35 就绪（compose + 四 py + .env）"

echo "===== [4/8] 同步网关代码 + compose 到生产 ====="
cp $SRC/gateway/llm_gateway.py        $G/llm_gateway.py
cp $SRC/gateway/news_broadcaster.py   $G/news_broadcaster.py
cp $SRC/gateway/yue_polish.py         $G/yue_polish.py
cp $SRC/gateway/tts_pron.py           $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py   $G/export_chat_html.py
cp $SRC/gateway/Dockerfile            $G/Dockerfile
cp $SRC/gateway/entrypoint.sh         $G/entrypoint.sh
cp $SRC/config/roles.json             $G/roles.json
cp $SRC/config/roles.json             $D/config/roles.json
cp $SRC/docker-compose.yml            $COMPOSE
cp $SRC/gateway/_broadcast_verified.sh $G/_broadcast_verified.sh 2>/dev/null || true
chmod +x $G/_broadcast_verified.sh 2>/dev/null || true
echo "  同步完成"
md5sum $G/llm_gateway.py $G/news_broadcaster.py $COMPOSE

echo "===== [5/8] 构建镜像 1.35 ====="
cd $G
docker build -t aqing-gateway:1.35 -f Dockerfile . 2>&1 | tail -8

echo "===== [6/8] 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg135.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -20 /tmp/cfg135.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8

echo "===== [7/8] 等网关起来 + 镜像内 v1.35 行为 + 记录数不丢 ====="
sleep 6
echo "--- 容器状态（大脑/nginx/emqx 应仍 Up，token 未动）---"
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- /logs 部署后条数（应 >= 部署前 $BASE_N，只增不减）---"
AFTER_N=$(curl -s --max-time 10 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))")
echo "  部署后 /logs count: $AFTER_N"
[ "$AFTER_N" -ge "$BASE_N" ] && echo "  ✅ 数据零丢失（只增不减）" || echo "  ⚠️ 条数下降 $BASE_N -> $AFTER_N，核查！"
echo "--- 镜像内 v1.35 代码确认 ---"
docker exec folotoy_llm_gateway_1 sh -c "grep -c 'def is_history_fact' /app/llm_gateway.py | xargs echo '  is_history_fact 定义数:'; grep -c 'HISTORY_NO_REF' /app/llm_gateway.py | xargs echo '  兜底硬钉标记数:'"
echo "--- 镜像内史实题意图自检 ---"
docker exec folotoy_llm_gateway_1 python3 -c "
import sys;sys.path.insert(0,'/app')
import llm_gateway as g
print('  唐朝开拓故事 fact=%s kb=%s hist=%s' % (g.is_fact_check_needed('讲唐朝开拓嘅故事。'),(g.is_knowledge_intent('讲唐朝开拓嘅故事。')),g.is_history_fact('讲唐朝开拓嘅故事。')))
print('  童话故事 fact=%s kb=%s hist=%s' % (g.is_fact_check_needed('讲个童话故事'),g.is_knowledge_intent('讲个童话故事'),g.is_history_fact('讲个童话故事')))
print('  搜索词:',g._kb_search_query('讲唐朝开拓嘅故事。'))
print('  史实锚点(开会):',g._history_search_subject('帮我讲下唐朝开国嘅故事。'))
"

echo "===== [8/8] 生产真链路 E2E（带 X-No-Record，唔落盘）====="
echo "  打 /chat/completions 问「讲唐朝开拓嘅故事」，验证 net=True + 唔再蹦「天下为公」"
docker exec folotoy_llm_gateway_1 python3 -c "
import sys,os,json,urllib.request;sys.path.insert(0,'/app')
req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',
  data=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':False,
    'messages':[{'role':'system','content':'你系阿晴，广州西关女仔，用粤语答，100字内。'},
                {'role':'user','content':'讲唐朝开拓嘅故事。'}]}).encode(),
  headers={'Content-Type':'application/json','X-No-Record':'1'})
r=urllib.request.urlopen(req,timeout=90)
d=json.loads(r.read())
a=d['choices'][0]['message']['content']
print('  === 答复 ==='); print('  '+a.replace(chr(10),chr(10)+'  '))
print('  === 核查 ===')
print('  含「天下为公」:', '天下为公' in a, '(应 False)')
print('  含「礼记/禮記」:', ('礼记' in a or '禮記' in a), '(应 False)')
"
echo "  ⚠️ 本脚本【绝无】清落盘动作；记录只增不减。"
echo "  aqing-gateway:1.35 已部署；大脑/nginx/emqx 未动，token 保住。"
echo "=== DONE_135 ==="
