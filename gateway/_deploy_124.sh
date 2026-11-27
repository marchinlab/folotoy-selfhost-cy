#!/bin/bash
# ============================================================
# 阿晴网关 v1.24 固化部署：修 4 号英语老师「双语教学讲成粤语」
#   ①网关检测到 english_teacher 时，把 system prompt 整体换成【纯普通话】版
#     （读镜像内 /app/roles.json 的 4 号，读唔到用内置兜底）——不重启大脑、不动 token
#   ②polish_english 轻量后处理：清 emoji/Markdown/元话语/串味粤字，绝不碰中英文正文
#   ③英语老师默认唔联网（原始需求只讲「中英对话+解释清楚」），显式「上网查」先搜
#   ④网关追加嘅字数/长文/资料尾注对英语老师一律改普通话措辞
# 只重建 llm-gateway，不动大脑/ nginx / emqx / 在播 MP3，保住 token。
# ★重建姿势：docker rm -f + docker-compose up --no-deps（【不加 --force-recreate】，
#   避开本机 docker-compose v1.29.2 同新版 Docker 嘅 ContainerConfig KeyError bug）。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [1/8] 校验 1.24 新代码标记 ====="
grep -q "def polish_english" $SRC/gateway/yue_polish.py && echo "  polish_english: OK"
grep -q "_EN_YUE_BACK" $SRC/gateway/yue_polish.py && echo "  粤->普回退表: OK"
grep -q "def _load_english_system" $SRC/gateway/llm_gateway.py && echo "  _load_english_system: OK"
grep -q "ENGLISH_SYSTEM_FALLBACK" $SRC/gateway/llm_gateway.py && echo "  内置兜底 prompt: OK"
grep -q "ENGLISH_SYS_OVERRIDE applied" $SRC/gateway/llm_gateway.py && echo "  system 整体替换接线: OK"
grep -q "polish_response(body, stream, poem=want_poem, skip=is_english)" $SRC/gateway/llm_gateway.py && echo "  英语轻量清洗接线: OK"
grep -q "COPY roles.json /app/roles.json" $SRC/gateway/Dockerfile && echo "  Dockerfile COPY roles.json: OK"
# 旧链路保护
grep -q "def gather_subject" $SRC/gateway/llm_gateway.py && echo "  学科联网: OK"
grep -q "def gather_weather" $SRC/gateway/llm_gateway.py && echo "  天气链路: OK"
grep -q "def conv_record" $SRC/gateway/llm_gateway.py && echo "  对话落盘: OK"
grep -q "MODEL_OVERRIDE" $SRC/gateway/llm_gateway.py && echo "  换模型: OK"

echo "===== [2/8] 校验 4 号 prompt 已纯普通话（零粤语指令污染）====="
python3 -c "
import json
d=json.load(open('$SRC/config/roles.json',encoding='utf-8'))
p=d['4']['prompt']; s=d['4']['start_text']
yue=('你系','唔系','即系','唔好','你嘅','畀','佢','系咪','明唔明','而家','呢个','嗰个','讲下','试下','有冇')
bad=[w for w in yue if w in p or w in s]
assert 'english_teacher' in p
assert '标准普通话' in p and '北京' in p
assert not bad, '4号 prompt 仍有粤语指令: %s'%bad
print('  4号 prompt 纯普通话 OK，开场白粤语字:', [w for w in yue if w in s] or '无')
"

echo "===== [3/8] 覆盖前 diff 留档 + 校验新 compose 保留生产关键配置 ====="
[ -f $COMPOSE.bak-pre-1.24 ] || cp $COMPOSE $COMPOSE.bak-pre-1.24
echo "  backup: $COMPOSE.bak-pre-1.24"
diff -u $COMPOSE.bak-pre-1.24 $SRC/docker-compose.yml | grep -E "^[+-].*(image:|CONV|MODEL_OVERRIDE|HARD_MAX|LONG_MAX|DUMP_MSG|VIEW_TOKEN)" || true
for k in "MODEL_OVERRIDE: Qwen/Qwen3-30B-A3B-Instruct-2507" \
         "HARD_MAX_CHARS: 1000" "HARD_MAX_TOKENS: 1800" \
         "LONG_MAX_TOKENS: 1600" "DUMP_MSG" "image: aqing-gateway:1.24"; do
  grep -q "$k" $SRC/docker-compose.yml && echo "  保留/新增 OK: $k" || { echo "  缺失! 中止: $k"; exit 1; }
done

echo "===== [4/8] 同步网关代码 + compose + roles.json 到生产 ====="
cp $SRC/gateway/llm_gateway.py       $G/llm_gateway.py
cp $SRC/gateway/news_broadcaster.py  $G/news_broadcaster.py
cp $SRC/gateway/yue_polish.py        $G/yue_polish.py
cp $SRC/gateway/tts_pron.py          $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py  $G/export_chat_html.py
cp $SRC/gateway/Dockerfile           $G/Dockerfile
cp $SRC/gateway/entrypoint.sh        $G/entrypoint.sh
# 构建 context 系 $G，故 roles.json 要入到 $G 先至 COPY 得到
cp $SRC/config/roles.json            $G/roles.json
cp $SRC/docker-compose.yml           $COMPOSE
# 生产 config/roles.json 都同步（将来大脑重启后都系老师版，同镜像内一致）
cp $SRC/config/roles.json            $D/config/roles.json
echo "  同步完成"
md5sum $G/llm_gateway.py $G/yue_polish.py $G/roles.json $D/config/roles.json

echo "===== [5/8] 构建镜像 1.24 ====="
cd $G
docker build -t aqing-gateway:1.24 -f Dockerfile . 2>&1 | tail -12

echo "===== [6/8] compose 校验 + 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg124.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg124.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -10

echo "===== [7/8] 等网关起来 + 验证 ====="
sleep 4
echo "--- 容器状态（大脑应仍 Up 好耐，token 未动）---"
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- 网关启动日志（确认 ENGLISH_SYSTEM 来源）---"
docker logs --tail 12 folotoy_llm_gateway_1 2>&1 | grep -iE "ENGLISH_SYSTEM|start|upstream_key|POLISH" || true
echo "--- 镜像内 roles.json 4号 是否纯普通话 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import json;d=json.load(open('/app/roles.json'));print('  4号含标准普通话锚定:', '标准普通话' in d['4']['prompt'])"

echo "===== [8/8] 完成 ====="
echo "  aqing-gateway:1.24 已部署；大脑/ nginx/ emqx 未动，token 保住。"
echo "  英语老师现已讲标准普通话 + 中英双语，emoji/Markdown/元话语已清。"
