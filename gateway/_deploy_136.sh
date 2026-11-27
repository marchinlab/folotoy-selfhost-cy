#!/bin/bash
# ============================================================
# 阿晴网关 v1.36 固化部署（2026-11-11 夜）——治长文「开口前干等 10~27 秒」。
# 生产实测根因：上游硅基流动对 stream=True 系真流式（长文 559 字：首 token 2.06s、
#   首句 3.43s、全文 26.77s、509 帧逐 token 吐），但旧 forward() 用 r.read()
#   把 509 帧全憋到 26.77s 先一次过回填；玩具（小智系，实测一次长文切 7 个 mp3
#   逐句播）要等全文到齐先开始切句 TTS -> 主人干等 26 秒先听到第一句。
# 改动（只 llm_gateway.py 一文件 + compose 加开关，回滚最干净）：
#   ① 新增 forward_stream(payload, sink)：句子级缓冲增量吐帧。逐帧读上游 delta.content
#      -> 凑够一句(句末标点/MIN字数/FLUSH兜底) -> 对该句跑【整段 polish+正音+清符号】
#      -> 即刻 yield 一帧。首句约3s到玩具即刻开播，其余边生成边补，总时长唔变。
#   ② do_POST 加流式分支：stream=True 且粤语角色(非英文/非诗词)走真流式(chunked+
#      每帧flush)；英文老师/诗词/E2E探针(stream=False)保留旧整段路径一字不动。
#   ③ 联网抓取多源并行：gather_knowledge/gather_gz_news/gather_news/gather_subject
#      的百科+Bing/多RSS 由串行改 ThreadPool 并行，结果按顺序收返(语义唔变)，
#      联网题抓取最坏 24s -> ≈8s。
# ★质量铁证：_verify_stream_quality.py 用生产 11 条真实答复稿验
#   【逐句 polish 拼接 == 整段 polish】逐字一致 11/11；_test_forward_stream.py 帧级 9/9。
# ★只重建网关、唔重启大脑/nginx/emqx、保 token。docker rm -f + up --no-deps。
# ★★数据铁律：任何步骤都唔会 truncate/move/重命名 conversations/；部署前后唯一记录数相等。
# ★回滚：compose 设 GW_STREAMING=0 只关流式(保留并行)重启网关即回 v1.35 行为；
#   或还原 .bak-pre-1.36 + compose 改返 1.36 镜像 tag 之下嘅 1.35(仍在册)重建。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [0/9] 部署前数据基线（只读）====="
mkdir -p $G
cp $SRC/gateway/_conv_count_baseline.py $G/_conv_count_baseline.py
BASE_N=$(CONV_DIR=$D/conversations python3 $G/_conv_count_baseline.py 2>/dev/null || echo "?")
echo "  部署前唯一记录数: $BASE_N"

echo "===== [1/9] 校验 v1.36 新代码标记 + 旧链路保护 ====="
grep -q 'def forward_stream(payload, sink)' $SRC/gateway/llm_gateway.py && echo "  v1.36 forward_stream: OK"
grep -q 'STREAM_ENABLED = os.getenv' $SRC/gateway/llm_gateway.py && echo "  v1.36 流式开关: OK"
grep -q 'use_stream = bool(' $SRC/gateway/llm_gateway.py && echo "  v1.36 do_POST 流式分支: OK"
grep -q 'Transfer-Encoding", "chunked' $SRC/gateway/llm_gateway.py && echo "  v1.36 chunked: OK"
grep -c 'ThreadPoolExecutor' $SRC/gateway/llm_gateway.py | xargs echo "  v1.36 并行抓取点数(应>=4):"
grep -q 'image: aqing-gateway:1.36' $SRC/docker-compose.yml && echo "  compose 镜像 1.36: OK"
grep -q 'GW_STREAMING' $SRC/docker-compose.yml && echo "  compose 流式开关: OK"
# 旧链路保护
grep -q 'def is_history_fact(q)' $SRC/gateway/llm_gateway.py && echo "  史实题联网(1.35): OK"
grep -q 'def polish(text, report=False, poem=False)' $SRC/gateway/yue_polish.py && echo "  粤语化 poem 参数: OK"
grep -q '("会", "會")' $SRC/gateway/tts_pron.py && echo "  多音字正音(1.16): OK"
grep -q 'X-No-Record' $SRC/gateway/llm_gateway.py && echo "  X-No-Record 探针语义: OK"
grep -q 'CONV_KEEP_DAYS = max' $SRC/gateway/llm_gateway.py && echo "  30天保留(1.31): OK"
grep -q 'TOPIC_ACK = "/sys/folotoy/+/thing/command/callAck"' $SRC/gateway/news_broadcaster.py && echo "  播报 callAck(1.33): OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py $SRC/gateway/news_broadcaster.py \
  $SRC/gateway/yue_polish.py $SRC/gateway/tts_pron.py && echo "  py_compile 四文件: OK"

echo "===== [2/9] 生产语料等价性 + 帧级单测（流式质量零回归）====="
cp $SRC/gateway/_verify_stream_quality.py $G/_verify_stream_quality.py
cp $SRC/gateway/_run_verify_stream_quality.sh $G/_run_verify_stream_quality.sh
echo "  --- 生产 11 条真实答复稿：逐句 vs 整段逐字一致 ---"
bash $G/_run_verify_stream_quality.sh 2>&1 | grep -E "CANTONESE_CHAIN|FIRST_SENTENCE|全文切"
echo "  --- 帧级单测 9/9 ---"
cd $SRC/gateway && PYTHONIOENCODING=utf-8 python3 _test_forward_stream.py 2>&1 | tail -1

echo "===== [3/9] 既有单测全回归（13 套）====="
cd $SRC/gateway
for t in _anchor_unit.py _kb_unit.py _subject_unit.py _mandarin_unit.py _en_auto_unit.py \
  _fact_unit.py _eng_space_unit.py _dan_unit.py _slash_unit.py _yue30_unit.py \
  _yue32_unit.py _conv_unit.py _bc133_unit.py; do
  printf "  %-20s" "$t"
  PYTHONIOENCODING=utf-8 python3 $t 2>&1 | grep -iE "ALL_PASS|ALL PASS|全绿|FAIL [1-9]|FAIL=[1-9]|结果" | tail -1
done

echo "===== [4/9] 备份生产 + 校验 compose ====="
[ -f $COMPOSE.bak-pre-1.36 ] || cp $COMPOSE $COMPOSE.bak-pre-1.36
for f in llm_gateway.py news_broadcaster.py yue_polish.py tts_pron.py; do
  [ -f $G/$f.bak-pre-1.36 ] || cp $G/$f $G/$f.bak-pre-1.36
done
[ -f $D/.env.bak-pre-1.36 ] || cp $D/.env $D/.env.bak-pre-1.36
echo "  生产备份 .bak-pre-1.36 就绪（compose + 四 py + .env）"

echo "===== [5/9] 同步网关代码 + compose 到生产 ====="
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
md5sum $G/llm_gateway.py $G/news_broadcaster.py $G/yue_polish.py $G/tts_pron.py $COMPOSE

echo "===== [6/9] 构建镜像 1.36 ====="
cd $G
docker build -t aqing-gateway:1.36 -f Dockerfile . 2>&1 | tail -8

echo "===== [7/9] 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg136.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -20 /tmp/cfg136.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8
sleep 6

echo "===== [8/9] 起来后：容器状态 + 记录零丢失 + 镜像内代码 ====="
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"; curl -s --max-time 6 http://127.0.0.1:8010/health; echo
AFTER_N=$(curl -s --max-time 10 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))")
echo "  部署后 /logs count: $AFTER_N (部署前 $BASE_N)"
[ "$AFTER_N" -ge "$BASE_N" ] && echo "  ✅ 数据零丢失（只增不减）" || echo "  ⚠️ 条数下降，核查！"
echo "--- 镜像内 v1.36 代码确认 ---"
docker exec folotoy_llm_gateway_1 sh -c "grep -c 'def forward_stream' /app/llm_gateway.py | xargs echo '  forward_stream 定义数:'; grep -c 'Transfer-Encoding' /app/llm_gateway.py | xargs echo '  chunked 标记数:'"

echo "===== [9/9] 生产真链路 E2E（带 X-No-Record，唔落盘）====="
echo "  --- A) 流式首帧收益：stream=True 量首帧 vs 全文 ---"
docker exec folotoy_llm_gateway_1 python3 -c "
import sys,os,json,time,urllib.request;sys.path.insert(0,'/app')
body=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':True,
  'messages':[{'role':'system','content':'你系阿晴，广州西关女仔，用粤语答，讲详细啲大约300字。'},
              {'role':'user','content':'详细同我讲下唐朝开国嘅故事。'}]}).encode()
req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=body,
  headers={'Content-Type':'application/json','X-No-Record':'1'})
t0=time.time(); first=None; n=0; text=''
r=urllib.request.urlopen(req,timeout=90)
for raw in r:
  line=raw.decode('utf-8','replace').strip()
  if not line.startswith('data:'):continue
  d=line[5:].strip()
  if d=='[DONE]':break
  try:j=json.loads(d)
  except:continue
  for ch in j.get('choices',[]):
    c=(ch.get('delta') or {}).get('content')
    if c:
      if first is None:first=time.time()-t0
      text+=c;n+=1
full=time.time()-t0
print('  首帧到玩具 %.2fs / 全文 %.2fs / %d 帧 / %d 字' % (first or -1,full,n,len(text)))
print('  ✅ 首句早吐生效' if (first and full and first < full*0.5) else '  ⚠️ 首帧未明显提前，核查 chunked/flush')
print('  答复前40字:',text[:40])
"
echo "  --- B) 非流式 E2E 契约：stream=False 仍返完整 JSON ---"
docker exec folotoy_llm_gateway_1 python3 -c "
import json,urllib.request
body=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':False,
  'messages':[{'role':'user','content':'用一句粤语答，唐朝系边个建立？'}]}).encode()
req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=body,
  headers={'Content-Type':'application/json','X-No-Record':'1'})
d=json.loads(urllib.request.urlopen(req,timeout=90).read())
print('  stream=False 答复:',d['choices'][0]['message']['content'][:50])
print('  ✅ 非流式契约完好')
"
echo "  --- C) 并行抓取 E2E：问广州新闻，量 dur ---"
docker exec folotoy_llm_gateway_1 python3 -c "
import json,urllib.request,time
body=json.dumps({'model':'Qwen/Qwen3-30B-A3B-Instruct-2507','stream':False,
  'messages':[{'role':'user','content':'讲下今日广州嘅新闻。'}]}).encode()
req=urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions',data=body,
  headers={'Content-Type':'application/json','X-No-Record':'1'})
t0=time.time();d=json.loads(urllib.request.urlopen(req,timeout=90).read())
print('  广州新闻 dur %.2fs（并行抓取后应明显 < 旧 46.98s）' % (time.time()-t0))
print('  答复前40字:',d['choices'][0]['message']['content'][:40])
"
echo "  ⚠️ 本脚本【绝无】清落盘动作；记录只增不减。"
echo "  aqing-gateway:1.36 已部署；大脑/nginx/emqx 未动，token 保住。"
echo "=== DONE_136 ==="
