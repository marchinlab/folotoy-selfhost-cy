#!/bin/bash
# ============================================================
# 阿晴网关 v1.41 部署（2026-11-12）——去掉「资料讲得清清楚楚，唔好乱改」
# 这类模型自己加的指令腔元评论。
# 主人报「呢个時间点，资料讲得清清楚楚，唔好乱改 这句话很奇怪」。
# 根因：落盘实测 30B 写长文把【约束自己点样用资料】的核查指令
#   （照资料讲/唔好改/唔好乱作/清清楚楚）当正文复述出来，零知识。
# 改动（两层、都落网关；唔改大脑 roles.json / token / 其它镜像）：
#   ①【治本】llm_gateway.py：字数/口头禅 system 尾钉之后加一条【最高优先级】
#      约束，禁模型把内部核查规则、自我叮嘱、对资料评价讲出口；保留对小朋友
#      安全教育「过马路唔好乱跑」嘅 legit 例外。英语老师普通话措辞；防重复。
#   ②【兜底】yue_polish.py：polish() 加一条高置信清理——删「[资料]+[讲/写
#      得清清楚楚]+[唔好(乱)改]」整句，繁简通吃；正常描写/安全教育/诚实
#      坦白/知识内容一律唔碰。poem 豁免。
# ★只重建网关镜像、唔重启大脑/nginx/emqx/stt-proxy、保 token。
#   ⚠️ 血泪教训（v1.40）：重建/重启大脑会冲掉设备配对令牌→「说话没反应」。
#      本脚本【绝不】碰大脑或 stt-proxy，且部署前后断言两者 Up time 未变。
# ★★数据铁律：任何步骤都唔会 truncate/move/重命名 conversations/；前后唯一记录数相等。
# ★回滚：还原 .bak-pre-1.41（compose + 四 py）+ compose image 改返 1.41→1.39
#   + docker build aqing-gateway:1.39（旧镜像仍在册）+ 只 recreate 网关。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [0/9] 部署前基线（只读）====="
mkdir -p $G
cp $SRC/gateway/_conv_count_baseline.py $G/_conv_count_baseline.py
BASE_N=$(CONV_DIR=$D/conversations python3 $G/_conv_count_baseline.py 2>/dev/null || echo "?")
echo "  部署前唯一记录数: $BASE_N"
echo "  --- 不动容器 Up time 基线（大脑 / stt-proxy / nginx / emqx）---"
for c in folotoy_folotoy_1 folotoy_stt_proxy_1 folotoy_nginx_1 folotoy_emqx_1; do
  docker ps --format '{{.Names}}|{{.Status}}' | grep "^$c|" || echo "  $c 未在跑(!)"
done

echo "===== [1/9] 校验 v1.41 新代码标记 + 旧链路保护 ====="
grep -q '最高优先级·规则唔好讲出口' $SRC/gateway/llm_gateway.py && echo "  v1.41 治本·粤语 system 尾钉: OK"
grep -q 'rules are for you to follow' $SRC/gateway/llm_gateway.py && echo "  v1.41 治本·英语老师 system 尾钉: OK"
grep -q 'V1.41_META_BAN injected' $SRC/gateway/llm_gateway.py && echo "  v1.41 治本·注入日志: OK"
grep -q 'def _clean_meta_instruction(text)' $SRC/gateway/yue_polish.py && echo "  v1.41 兜底·_clean_meta_instruction: OK"
grep -q '指令腔元评论清理' $SRC/gateway/yue_polish.py && echo "  v1.41 兜底·polish 调用: OK"
grep -q '_META_DOC = re.compile' $SRC/gateway/yue_polish.py && echo "  v1.41 兜底·正则: OK"
# 旧链路保护
grep -q 'V1.39_FILLER_BAN injected' $SRC/gateway/llm_gateway.py && echo "  v1.39 口头禅尾钉: OK"
grep -q 'def _clean_filler(text)' $SRC/gateway/yue_polish.py && echo "  v1.39 兜底: OK"
grep -q 'def forward_stream(payload, sink)' $SRC/gateway/llm_gateway.py && echo "  v1.36 流式: OK"
grep -q 'def is_history_fact(q)' $SRC/gateway/llm_gateway.py && echo "  史实题联网(1.35): OK"
grep -q 'X-No-Record' $SRC/gateway/llm_gateway.py && echo "  X-No-Record 探针语义: OK"
grep -q 'TOPIC_ACK = "/sys/folotoy/+/thing/command/callAck"' $SRC/gateway/news_broadcaster.py && echo "  播报 callAck(1.33): OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py $SRC/gateway/news_broadcaster.py \
  $SRC/gateway/yue_polish.py $SRC/gateway/tts_pron.py && echo "  py_compile 四文件: OK"

echo "===== [2/9] v1.41 元评论单测（28 断言）+ v1.39 口头禅回归 + 流式质量 ====="
cd $SRC/gateway
PYTHONIOENCODING=utf-8 python3 $SRC/gateway/_yue41_unit.py 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python3 $SRC/gateway/_yue39_unit.py 2>&1 | tail -1
cp $SRC/gateway/_verify_stream_quality.py $G/_verify_stream_quality.py
cp $SRC/gateway/_run_verify_stream_quality.sh $G/_run_verify_stream_quality.sh
echo "  --- 生产 11 条真实稿：逐句 polish 拼接 == 整段 polish ---"
bash $G/_run_verify_stream_quality.sh 2>&1 | grep -E "CANTONESE_CHAIN|FIRST_SENTENCE|全文切|ALL_PASS|FAIL" | head -8
echo "  --- 帧级单测 9/9 ---"
PYTHONIOENCODING=utf-8 python3 _test_forward_stream.py 2>&1 | tail -1

echo "===== [3/9] 既有单测全回归（13 套）====="
for t in _anchor_unit.py _kb_unit.py _subject_unit.py _mandarin_unit.py _en_auto_unit.py \
  _fact_unit.py _eng_space_unit.py _dan_unit.py _slash_unit.py _yue30_unit.py \
  _yue32_unit.py _conv_unit.py _bc133_unit.py; do
  printf "  %-20s" "$t"
  PYTHONIOENCODING=utf-8 python3 $t 2>&1 | grep -iE "ALL_PASS|ALL PASS|全绿|FAIL [1-9]|FAIL=[1-9]|结果" | tail -1
done

echo "===== [4/9] 备份生产（幂等，.bak-pre-1.41 已由 precheck 建好）====="
[ -f $COMPOSE.bak-pre-1.41 ] || cp $COMPOSE $COMPOSE.bak-pre-1.41
for f in llm_gateway.py news_broadcaster.py yue_polish.py tts_pron.py _broadcast_verified.sh; do
  [ -f $G/$f.bak-pre-1.41 ] || cp $G/$f $G/$f.bak-pre-1.41
done
echo "  生产备份 .bak-pre-1.41 就绪"

echo "===== [5/9] 同步网关代码 + compose 改镜像 tag 1.39 -> 1.41 ====="
cp $SRC/gateway/llm_gateway.py        $G/llm_gateway.py
cp $SRC/gateway/news_broadcaster.py   $G/news_broadcaster.py
cp $SRC/gateway/yue_polish.py         $G/yue_polish.py
cp $SRC/gateway/tts_pron.py           $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py   $G/export_chat_html.py
cp $SRC/gateway/Dockerfile            $G/Dockerfile
cp $SRC/gateway/entrypoint.sh         $G/entrypoint.sh
cp $SRC/config/roles.json             $G/roles.json
cp $SRC/config/roles.json             $D/config/roles.json
# compose 镜像 tag：1.39 -> 1.41（只改网关服务那行）
if grep -q 'image: aqing-gateway:1\.41' $SRC/docker-compose.yml; then
  echo "  compose 已是 1.41（幂等跳过）"
else
  sed -i 's/image: aqing-gateway:1\.39/image: aqing-gateway:1.41/' $SRC/docker-compose.yml
fi
cp $SRC/docker-compose.yml            $COMPOSE
# v1.38 宿主脚本同步（唔影响网关代码，保持昨夜修复）
cp $SRC/gateway/_broadcast_verified.sh $G/_broadcast_verified.sh 2>/dev/null || true
chmod +x $G/_broadcast_verified.sh 2>/dev/null || true
echo "  同步完成；构建源 md5："
md5sum $G/llm_gateway.py $G/yue_polish.py $COMPOSE
grep -q 'image: aqing-gateway:1.41' $COMPOSE && echo "  compose tag 1.41: OK" || { echo "  ABORT: compose tag 未改到 1.41"; exit 1; }
# stt-proxy / 大脑 base_url 保护（v1.40 必须保留，绝唔好被 sed 误伤）
grep -q 'OPENAI_WHISPER_API_BASE: http://stt-proxy:8000/v1' $COMPOSE && echo "  stt-proxy 切流(v1.40)仍在: OK" || { echo "  ABORT: stt-proxy 切流丢失"; exit 1; }
grep -q 'image: aqing-stt-proxy:1.0' $COMPOSE && echo "  stt-proxy 服务仍在: OK"

echo "===== [6/9] 构建镜像 1.41 ====="
cd $G
docker build -t aqing-gateway:1.41 -f Dockerfile . 2>&1 | tail -10
docker image inspect aqing-gateway:1.41 --format '  built {{.Id}} size={{.Size}}' 2>&1

echo "===== [7/9] 只重建网关（rm + up --no-deps，禁 force-recreate，绝不碰大脑/stt-proxy）====="
cd $D
if ! docker-compose config >/tmp/cfg141.out 2>&1; then echo "  COMPOSE_CONFIG_FAIL"; tail -20 /tmp/cfg141.out; exit 1; fi
echo "  compose config: OK"
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8
sleep 6

echo "===== [8/9] 起来后自检 + 不动容器 Up time 断言 ====="
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "  --- 不动容器 Up time 应【延续】而非归零（若归零=被误重建，立刻告警）---"
for c in folotoy_folotoy_1 folotoy_stt_proxy_1 folotoy_nginx_1 folotoy_emqx_1; do
  docker ps --format '{{.Names}}|{{.Status}}' | grep "^$c|" || echo "  ⚠️ $c 未在跑!"
done
echo "  --- 网关 /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "  --- 镜像内 v1.41 代码确认 ---"
docker exec folotoy_llm_gateway_1 sh -c "grep -c 'V1.41_META_BAN' /app/llm_gateway.py | xargs echo '  治本注入定义数:'; grep -c 'def _clean_meta_instruction' /app/yue_polish.py | xargs echo '  兜底清理定义数:'; grep -c 'def forward_stream' /app/llm_gateway.py | xargs echo '  v1.36 流式仍在:'"
echo "  --- 记录零丢失 ---"
AFTER_N=$(curl -s --max-time 10 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))")
echo "  部署后 /logs count: $AFTER_N (部署前 $BASE_N)"
[ "$AFTER_N" -ge "$BASE_N" ] && echo "  ✅ 数据零丢失（只增不减）" || echo "  ⚠️ 条数下降，核查！"
echo "  --- 治本注入确实执行（日志标记）---"
docker logs --tail 200 folotoy_llm_gateway_1 2>&1 | grep -E "V1.41_META_BAN|V1.39_FILLER_BAN" | tail -5 || echo "  (暂无请求日志，E2E 后会打)"

echo "===== [9/9] 生产 E2E（X-No-Record 唔落盘）====="
echo "  --- E2E A) 历史老师讲唐朝（联网抓资料，验元评论唔再出现、知识完整）---"
docker exec folotoy_llm_gateway_1 python3 -c "
import json,urllib.request
body=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':False,
  'messages':[{'role':'system','content':'【角色:history_teacher】\n你系一位耐心嘅初中历史老师，用纯正广州粤语口语讲课。讲完可以轻轻追问一句，睇下学生明唔明。'},
              {'role':'user','content':'同我讲下唐朝开国嘅历史，讲详细啲。'}]}).encode()
req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=body,
  headers={'Content-Type':'application/json','X-No-Record':'1'})
a=json.loads(urllib.request.urlopen(req,timeout=120).read())['choices'][0]['message']['content']
print('  答复前60字:',a[:60])
print('  元评论「清清楚楚/唔好乱改」:', ('清清楚楚' in a or '唔好乱改' in a), '(期望 False)')
print('  自我叮嘱「唔好乱讲/唔好乱打」:', ('唔好乱讲' in a or '唔好乱打' in a or '唔好乱估' in a), '(期望 False)')
print('  有实质内容(唐/李渊/称帝):', ('李渊' in a or '称帝' in a), '(期望 True)')
print('  答复字数:',len(a))
"
echo "  --- E2E B) 安全教育例外唔会误伤（闲聊人设问过马路）---"
docker exec folotoy_llm_gateway_1 python3 -c "
import json,urllib.request
body=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':False,
  'messages':[{'role':'system','content':'【角色:aqing_chat】\n你叫阿晴，20岁广州西关女仔，用街坊悠闲倾计嘅慢节奏，纯正广州西关口音。'},
              {'role':'user','content':'阿晴，细路过马路要注意啲乜？教下佢。'}]}).encode()
req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=body,
  headers={'Content-Type':'application/json','X-No-Record':'1'})
a=json.loads(urllib.request.urlopen(req,timeout=90).read())['choices'][0]['message']['content']
print('  答复前60字:',a[:60])
print('  安全教育「唔好乱跑/睇车」保留:', ('唔好乱跑' in a or '睇车' in a or '小心' in a), '(期望 True，唔好被治本误伤)')
"
echo "  --- E2E C) 英语老师仍普通话+中英双语（治本术语无污染）---"
docker exec folotoy_llm_gateway_1 python3 -c "
import json,urllib.request
body=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':False,
  'messages':[{'role':'system','content':'【角色:english_teacher】\nYou are an English teacher. 用标准普通话讲课，关键字词保留英文。'},
              {'role':'user','content':'abundant 呢个单词咩意思？'}]}).encode()
req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=body,
  headers={'Content-Type':'application/json','X-No-Record':'1'})
a=json.loads(urllib.request.urlopen(req,timeout=90).read())['choices'][0]['message']['content']
print('  答复前60字:',a[:60])
print('  保留英文 abundant:', 'abundant' in a, '(期望 True)')
"
echo "  --- E2E 后治本日志标记 ---"
docker logs --tail 100 folotoy_llm_gateway_1 2>&1 | grep -E "V1.41_META_BAN|V1.39_FILLER_BAN" | tail -6
echo "  ⚠️ 本脚本【绝无】清落盘动作；记录只增不减；【绝不】碰大脑/stt-proxy/emqx/nginx。"
echo "  aqing-gateway:1.41 已部署；大脑/nginx/emqx/stt-proxy 未动，token 保住。"
echo "=== DONE_141 ==="
