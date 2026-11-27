#!/bin/bash
# ============================================================
# 阿晴网关 v1.39 部署（2026-11-12）——取消模型自加嘅填充口头禅。
# 主人报「经常有奇怪口头禅「唔好意思讲」「你知唔知」，取消」。
# 根因：落盘实测「你知唔知」一日 18 次左右，全系模型喺人设「口语化/
#   娓娓道来」同老师 prompt「讲完轻轻追问一句，睇下学生明唔明」引导下
#   自己加嘅无信息量填充，唔系网关替换表造、唔系内容错。
# 改动（两层、都落网关，唔改大脑 roles.json / token / 其它镜像）：
#   ①【治本】llm_gateway.py：喺字数上限 system 尾钉之后加一条【最高优先级】
#      约束，令模型根本唔好生成句首「你知唔知，」、开场「好我同你讲」、句尾
#      「你明唔明？」呢类填充/客套追问；英语老师用普通话措辞；防重复注入。
#   ②【兜底】yue_polish.py：polish() 加高置信清理——删句首转场「(而家)?你知唔知，」
#      (保留无逗号带宾语嘅真问句)、删整句客套「你明唔明？」；poem 朗读豁免。
# ★只重建网关镜像、唔重启大脑/nginx/emqx、保 token。docker build + rm + up --no-deps。
# ★★数据铁律：任何步骤都唔会 truncate/move/重命名 conversations/；部署前后唯一记录数相等。
# ★回滚：还原 .bak-pre-1.39 (llm_gateway.py/yue_polish.py/compose) + build aqing-gateway:1.36
#   + compose 改返 image 1.36 + 只 recreate 网关；或改 GW 相关开关（本版无环境开关，纯代码）。
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

echo "===== [1/8] 校验 v1.39 新代码标记 + 旧链路保护 ====="
grep -q '最高优先级·讲话唔好加填充口头禅' $SRC/gateway/llm_gateway.py && echo "  v1.39 治本·粤语 system 尾钉: OK"
grep -q '最高优先级·不要加填充口头禅' $SRC/gateway/llm_gateway.py && echo "  v1.39 治本·英语老师 system 尾钉: OK"
grep -q 'V1.39_FILLER_BAN injected' $SRC/gateway/llm_gateway.py && echo "  v1.39 治本·注入日志: OK"
grep -q 'def _clean_filler(text)' $SRC/gateway/yue_polish.py && echo "  v1.39 兜底·_clean_filler: OK"
grep -q '填充口头禅清理' $SRC/gateway/yue_polish.py && echo "  v1.39 兜底·polish 调用: OK"
grep -q '_FILLER_LEAD = re.compile' $SRC/gateway/yue_polish.py && echo "  v1.39 兜底·句首转场正则: OK"
grep -q '_FILLER_TAIL_Q = re.compile' $SRC/gateway/yue_polish.py && echo "  v1.39 兜底·客套追问正则: OK"
grep -q 'image: aqing-gateway:1.39' $SRC/docker-compose.yml && echo "  compose 镜像 1.39: OK" || echo "  ⚠️ compose 未改 1.39（部署脚本 [5/8] 会改）"
# 旧链路保护
grep -q 'def forward_stream(payload, sink)' $SRC/gateway/llm_gateway.py && echo "  v1.36 流式: OK"
grep -q 'STREAM_ENABLED = os.getenv' $SRC/gateway/llm_gateway.py && echo "  v1.36 流式开关: OK"
grep -q 'def is_history_fact(q)' $SRC/gateway/llm_gateway.py && echo "  史实题联网(1.35): OK"
grep -q 'def polish(text, report=False, poem=False)' $SRC/gateway/yue_polish.py && echo "  粤语化 poem 参数: OK"
grep -q 'X-No-Record' $SRC/gateway/llm_gateway.py && echo "  X-No-Record 探针语义: OK"
grep -q 'TOPIC_ACK = "/sys/folotoy/+/thing/command/callAck"' $SRC/gateway/news_broadcaster.py && echo "  播报 callAck(1.33): OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py $SRC/gateway/news_broadcaster.py \
  $SRC/gateway/yue_polish.py $SRC/gateway/tts_pron.py && echo "  py_compile 四文件: OK"

echo "===== [2/8] v1.39 口头禅单测（23 断言）+ 流式质量零回归 ====="
cd $SRC/gateway
PYTHONIOENCODING=utf-8 python3 $SRC/gateway/_yue39_unit.py 2>&1 | tail -1
cp $SRC/gateway/_verify_stream_quality.py $G/_verify_stream_quality.py
cp $SRC/gateway/_run_verify_stream_quality.sh $G/_run_verify_stream_quality.sh
echo "  --- 生产 11 条真实稿：逐句 polish 拼接 == 整段 polish ---"
bash $G/_run_verify_stream_quality.sh 2>&1 | grep -E "CANTONESE_CHAIN|FIRST_SENTENCE|全文切|ALL_PASS|FAIL" | head -8
echo "  --- 帧级单测 9/9 ---"
PYTHONIOENCODING=utf-8 python3 _test_forward_stream.py 2>&1 | tail -1

echo "===== [3/8] 既有单测全回归（13 套）====="
for t in _anchor_unit.py _kb_unit.py _subject_unit.py _mandarin_unit.py _en_auto_unit.py \
  _fact_unit.py _eng_space_unit.py _dan_unit.py _slash_unit.py _yue30_unit.py \
  _yue32_unit.py _conv_unit.py _bc133_unit.py; do
  printf "  %-20s" "$t"
  PYTHONIOENCODING=utf-8 python3 $t 2>&1 | grep -iE "ALL_PASS|ALL PASS|全绿|FAIL [1-9]|FAIL=[1-9]|结果" | tail -1
done

echo "===== [4/8] 备份生产（防重复，保留 v1.38 宿主脚本备份）====="
[ -f $COMPOSE.bak-pre-1.39 ] || cp $COMPOSE $COMPOSE.bak-pre-1.39
for f in llm_gateway.py news_broadcaster.py yue_polish.py tts_pron.py; do
  [ -f $G/$f.bak-pre-1.39 ] || cp $G/$f $G/$f.bak-pre-1.39
done
echo "  生产备份 .bak-pre-1.39 就绪（compose + 四 py）"

echo "===== [5/8] 同步网关代码 + compose 改镜像 tag 1.39 ====="
cp $SRC/gateway/llm_gateway.py        $G/llm_gateway.py
cp $SRC/gateway/news_broadcaster.py   $G/news_broadcaster.py
cp $SRC/gateway/yue_polish.py         $G/yue_polish.py
cp $SRC/gateway/tts_pron.py           $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py   $G/export_chat_html.py
cp $SRC/gateway/Dockerfile            $G/Dockerfile
cp $SRC/gateway/entrypoint.sh         $G/entrypoint.sh
cp $SRC/config/roles.json             $G/roles.json
cp $SRC/config/roles.json             $D/config/roles.json
# compose 镜像 tag：1.36 -> 1.39（只改网关服务那行）
sed -i 's/image: aqing-gateway:1\.36/image: aqing-gateway:1.39/' $SRC/docker-compose.yml
cp $SRC/docker-compose.yml            $COMPOSE
# v1.38 宿主脚本同步（唔影响网关代码，保持昨夜修复）
cp $SRC/gateway/_broadcast_verified.sh $G/_broadcast_verified.sh 2>/dev/null || true
chmod +x $G/_broadcast_verified.sh 2>/dev/null || true
echo "  同步完成；镜像内将含 v1.39 两文件，构建源 md5："
md5sum $G/llm_gateway.py $G/yue_polish.py $COMPOSE
grep -q 'image: aqing-gateway:1.39' $COMPOSE && echo "  compose tag 1.39: OK"

echo "===== [6/8] 构建镜像 1.39 ====="
cd $G
docker build -t aqing-gateway:1.39 -f Dockerfile . 2>&1 | tail -10

echo "===== [7/8] 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg139.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -20 /tmp/cfg139.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8
sleep 6

echo "===== [8/8] 起来后自检 + 生产 E2E（X-No-Record 唔落盘）====="
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"; curl -s --max-time 6 http://127.0.0.1:8010/health; echo
AFTER_N=$(curl -s --max-time 10 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))")
echo "  部署后 /logs count: $AFTER_N (部署前 $BASE_N)"
[ "$AFTER_N" -ge "$BASE_N" ] && echo "  ✅ 数据零丢失（只增不减）" || echo "  ⚠️ 条数下降，核查！"
echo "--- 镜像内 v1.39 代码确认 ---"
docker exec folotoy_llm_gateway_1 sh -c "grep -c 'V1.39_FILLER_BAN' /app/llm_gateway.py | xargs echo '  治本注入定义数:'; grep -c 'def _clean_filler' /app/yue_polish.py | xargs echo '  兜底清理定义数:'; grep -c 'def forward_stream' /app/llm_gateway.py | xargs echo '  v1.36 流式仍在:'"
echo "  --- E2E A) 粤语老师题：问唐朝开国，验答话无「你知唔知，」填充、无「你明唔明？」收尾 ---"
docker exec folotoy_llm_gateway_1 python3 -c "
import sys,os,json,urllib.request;sys.path.insert(0,'/app')
body=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':False,
  'messages':[{'role':'system','content':'【角色:history_teacher】\n你系一位耐心嘅初中历史老师，用纯正广州粤语口语讲课。讲完可以轻轻追问一句，睇下学生明唔明。'},
              {'role':'user','content':'同我讲下唐朝开国嘅故事，讲详细啲。'}]}).encode()
req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=body,
  headers={'Content-Type':'application/json','X-No-Record':'1'})
d=json.loads(urllib.request.urlopen(req,timeout=90).read())
a=d['choices'][0]['message']['content']
print('  答复前60字:',a[:60])
print('  「你知唔知，」句首填充:', '你知唔知，' in a, '(期望 False)')
print('  「你明唔明？」客套收尾:', '你明唔明' in a, '(期望 False)')
print('  有实质内容(唐/李渊):', ('唐' in a or '李渊' in a), '(期望 True)')
"
echo "  --- E2E B) 英语老师仍普通话+中英双语（治本术语无污染）---"
docker exec folotoy_llm_gateway_1 python3 -c "
import json,urllib.request
body=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':False,
  'messages':[{'role':'system','content':'【角色:english_teacher】\nYou are an English teacher. 用标准普通话讲课，关键字词保留英文。'},
              {'role':'user','content':'abundant 呢个单词咩意思？'}]}).encode()
req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=body,
  headers={'Content-Type':'application/json','X-No-Record':'1'})
d=json.loads(urllib.request.urlopen(req,timeout=90).read())
a=d['choices'][0]['message']['content']
print('  答复前60字:',a[:60])
print('  保留英文 abundant:', 'abundant' in a, '(期望 True)')
"
echo "  ⚠️ 本脚本【绝无】清落盘动作；记录只增不减。"
echo "  aqing-gateway:1.39 已部署；大脑/nginx/emqx 未动，token 保住。"
echo "=== DONE_139 ==="
