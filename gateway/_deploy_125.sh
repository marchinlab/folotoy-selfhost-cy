#!/bin/bash
# ============================================================
# 阿晴网关 v1.25 固化部署：修「英文例句冇发音」
#   根因：主人习惯 1 号闲聊键通吃，用英文问会被 yue_polish 英文碎片清理
#        删到净系得返零星字母，TTS 冇英文可念。4 号英语老师键本身系好嘅，
#        但主人唔系按 4 号键。
#   修法：闲聊键（role 空/aqing_chat）检测到明确英文意图 -> 当英语老师处理，
#        复用 v1.24 全链路（普通话 system / 豁免清英文 / 唔乱联网 / 字数尾注）。
#        只影响 1 号键 + 未识别角色，6 个学科键零回归；AUTO_EN=0 可关。
#        落盘 role 显示加「〔英文自动〕」后缀 + auto_en 字段，查看页零改动。
#   只重建 llm-gateway，不动大脑/ nginx / emqx / 在播 MP3，保住 token。
# ★姿势：docker rm -f + docker-compose up --no-deps（【不加 --force-recreate】，
#   避开本机 docker-compose v1.29.2 同新版 Docker 嘅 ContainerConfig KeyError bug）。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml

echo "===== [1/7] 校验 1.25 新代码标记 ====="
grep -q "def is_english_auto" $SRC/gateway/llm_gateway.py && echo "  is_english_auto: OK"
grep -q "AUTO_EN = os.getenv" $SRC/gateway/llm_gateway.py && echo "  AUTO_EN 开关: OK"
grep -q "EN_INTENT_WORDS" $SRC/gateway/llm_gateway.py && echo "  英文意图词表: OK"
grep -q "_EN_SMALLTALK" $SRC/gateway/llm_gateway.py && echo "  寒暄排除表: OK"
grep -q "auto_en = is_english_auto(q, role_key)" $SRC/gateway/llm_gateway.py && echo "  do_POST 接入: OK"
grep -q "auto_en=auto_en" $SRC/gateway/llm_gateway.py && echo "  落盘 auto_en 字段: OK"
grep -q "〔英文自动〕" $SRC/gateway/llm_gateway.py && echo "  落盘显示标记: OK"
# 旧链路保护（v1.24 英语老师本尊 + 各学科/天气/落盘）
grep -q "def polish_english" $SRC/gateway/yue_polish.py && echo "  v1.24 polish_english: OK"
grep -q "ENGLISH_SYS_OVERRIDE applied" $SRC/gateway/llm_gateway.py && echo "  v1.24 system 替换: OK"
grep -q "def gather_subject" $SRC/gateway/llm_gateway.py && echo "  学科联网: OK"
grep -q "def gather_weather" $SRC/gateway/llm_gateway.py && echo "  天气链路: OK"
grep -q "def conv_record" $SRC/gateway/llm_gateway.py && echo "  对话落盘: OK"
grep -q "MODEL_OVERRIDE" $SRC/gateway/llm_gateway.py && echo "  换模型: OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py && echo "  py_compile: OK"

echo "===== [2/7] 单元回归（本地新代码）====="
cd $SRC/gateway
PYTHONIOENCODING=utf-8 python3 _en_auto_unit.py 2>&1 | tail -3

echo "===== [3/7] 覆盖前 diff 留档 + 校验 compose 关键配置 ====="
[ -f $COMPOSE.bak-pre-1.25 ] || cp $COMPOSE $COMPOSE.bak-pre-1.25
echo "  backup: $COMPOSE.bak-pre-1.25"
for k in "image: aqing-gateway:1.25" \
         "AUTO_EN: \${AUTO_EN:-1}" \
         "MODEL_OVERRIDE: Qwen/Qwen3-30B-A3B-Instruct-2507" \
         "HARD_MAX_CHARS: 1000" "HARD_MAX_TOKENS: 1800" \
         "LONG_MAX_TOKENS: 1600" "CONVERSATIONS_DIR: /data/conversations"; do
  grep -q "$k" $SRC/docker-compose.yml && echo "  保留/新增 OK: $k" || { echo "  缺失! 中止: $k"; exit 1; }
done

echo "===== [4/7] 同步网关代码 + compose 到生产 ====="
[ -f $G/llm_gateway.py.bak-pre-1.25 ] || cp $G/llm_gateway.py $G/llm_gateway.py.bak-pre-1.25
cp $SRC/gateway/llm_gateway.py       $G/llm_gateway.py
cp $SRC/gateway/news_broadcaster.py  $G/news_broadcaster.py
cp $SRC/gateway/yue_polish.py        $G/yue_polish.py
cp $SRC/gateway/tts_pron.py          $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py  $G/export_chat_html.py
cp $SRC/gateway/Dockerfile           $G/Dockerfile
cp $SRC/gateway/entrypoint.sh        $G/entrypoint.sh
cp $SRC/config/roles.json            $G/roles.json
cp $SRC/docker-compose.yml           $COMPOSE
cp $SRC/config/roles.json            $D/config/roles.json
echo "  同步完成"
md5sum $G/llm_gateway.py $G/yue_polish.py $G/roles.json $D/config/roles.json $COMPOSE

echo "===== [5/7] 构建镜像 1.25 ====="
cd $G
docker build -t aqing-gateway:1.25 -f Dockerfile . 2>&1 | tail -8

echo "===== [6/7] compose 校验 + 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg125.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg125.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8

echo "===== [7/7] 等网关起来 + 验证 ====="
sleep 4
echo "--- 容器状态（大脑应仍 Up 好耐，token 未动）---"
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- 网关启动日志（确认 AUTO_EN 生效）---"
docker logs --tail 20 folotoy_llm_gateway_1 2>&1 | grep -iE "ENGLISH_SYSTEM|start|AUTO_EN|POLISH" || true
echo "--- 镜像内新函数存在 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import llm_gateway as g;print('  镜像内 is_english_auto 命中测试:', g.is_english_auto('用英文介绍上海','aqing_chat'))"
echo ""
echo "  aqing-gateway:1.25 已部署；大脑/ nginx/ emqx 未动，token 保住。"
echo "  而家 1 号键用英文问会自动走英语老师链路，英文例句保得住、TTS 念得出。"
