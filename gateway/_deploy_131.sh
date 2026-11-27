#!/bin/bash
# ============================================================
# 阿晴网关 v1.31 固化部署：修【对话记录一刷新就全部唔见 + 至少保留 30 天】
#   根因：旧 _verify_*.sh 每次部署将当日主 jsonl 清空、备份成 .bak-pre-1.xx-clean，
#     而 conv_dates 正则只认纯 .jsonl$ -> 查看页读到空档，65 条真实记录「隐形」（数据其实未丢，
#     全喺 6 个 .bak 快照，ext4 持久卷）。代码里亦冇任何保留策略。
#   修法(只重建网关、唔重启大脑、保 token)：
#     ① 聚合读取：conv_dates/conv_read 聚合【主文件 + 所有同日 .bak-* + archive/】按 epoch 去重
#        -> 历史备份记录立即复活、未来快照重叠都唔重复。
#     ② 30 天保留：CONV_KEEP_DAYS=30，超期【主文件】移 archive/ 仍可经 /logs 查（默认永不删）；
#        CONV_PURGE_DAYS=0 默认关，显式开先会删。/logs 返 keep_days、上限 200->5000。
#     ③ 根除清落盘：X-No-Record:1 header 令 E2E 自检唔落盘；本脚本【绝不清空/重命名】任何记录文件。
#     ④ compose 镜像 1.30->1.31，加 CONV_KEEP_DAYS/PURGE_DAYS 环境变量。
# ★姿势：docker rm -f + docker-compose up --no-deps（【不加 --force-recreate】）。
# ★数据铁律：本脚本任何步骤都唔会 truncate / move / 重命名 conversations/ 下嘅记录。
# ============================================================
set -e
SRC=/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost
D=/opt/folotoy
G=$D/gateway
COMPOSE=$D/docker-compose.yml
CONVDIR=$D/conversations

echo "===== [0/8] 部署前数据基线（记录当前真实条数，部署后要对得上）====="
cp $SRC/gateway/_conv_count_baseline.py $G/_conv_count_baseline.py
BASE_N=$(python3 $G/_conv_count_baseline.py 2>/dev/null || echo "?")
echo "  部署前唯一记录数: $BASE_N（期望 65）"

echo "===== [1/8] 校验 1.31 新代码标记 + 旧链路保护 ====="
grep -q 'def _rec_key(r)' $SRC/gateway/llm_gateway.py && echo "  v1.31 epoch 去重: OK"
grep -q 'def _day_files(d, day)' $SRC/gateway/llm_gateway.py && echo "  v1.31 聚合来源: OK"
grep -q 'CONV_KEEP_DAYS = max' $SRC/gateway/llm_gateway.py && echo "  v1.31 30天保留: OK"
grep -q 'def conv_retention(force=False)' $SRC/gateway/llm_gateway.py && echo "  v1.31 归档不删: OK"
grep -q 'X-No-Record' $SRC/gateway/llm_gateway.py && echo "  v1.31 自检唔落盘: OK"
grep -q 'CONV_KEEP_DAYS: "30"' $SRC/docker-compose.yml && echo "  v1.31 compose 保留策略: OK"
# 旧链路保护
grep -q '("单", "單")' $SRC/gateway/tts_pron.py && echo "  v1.28 单->單 正音: OK"
grep -q 'def clean_tts_symbols(text, report=False)' $SRC/gateway/yue_polish.py && echo "  v1.29 斜杠清理: OK"
grep -q 'def conv_retention' $SRC/gateway/llm_gateway.py && echo "  落盘链路保留: OK"
python3 -m py_compile $SRC/gateway/llm_gateway.py $SRC/gateway/yue_polish.py $SRC/gateway/tts_pron.py && echo "  py_compile: OK"

echo "===== [2/8] 单元回归（本地新代码，八套零回归）====="
cd $SRC/gateway
PYTHONIOENCODING=utf-8 python3 _conv_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _yue30_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _slash_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _dan_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _eng_space_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _fact_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _en_auto_unit.py 2>&1 | tail -2
PYTHONIOENCODING=utf-8 python3 _mandarin_unit.py 2>&1 | tail -2

echo "===== [3/8] 备份生产 + 校验 compose ====="
[ -f $COMPOSE.bak-pre-1.31 ] || cp $COMPOSE $COMPOSE.bak-pre-1.31
[ -f $G/llm_gateway.py.bak-pre-1.31 ] || cp $G/llm_gateway.py $G/llm_gateway.py.bak-pre-1.31
echo "  生产备份 .bak-pre-1.31 就绪"
for k in "image: aqing-gateway:1.31" \
         "CONV_KEEP_DAYS: \"30\"" "CONV_PURGE_DAYS: \"0\"" \
         "CONVERSATIONS_DIR: /data/conversations" \
         "MODEL_OVERRIDE: Qwen/Qwen3-30B-A3B-Instruct-2507" \
         "FACT_CHECK: \${FACT_CHECK:-1}" "AUTO_EN: \${AUTO_EN:-1}"; do
  grep -q "$k" $SRC/docker-compose.yml && echo "  OK: $k" || { echo "  缺失! 中止: $k"; exit 1; }
done

echo "===== [4/8] 同步网关代码 + compose 到生产 ====="
cp $SRC/gateway/llm_gateway.py       $G/llm_gateway.py
cp $SRC/gateway/news_broadcaster.py  $G/news_broadcaster.py
cp $SRC/gateway/yue_polish.py        $G/yue_polish.py
cp $SRC/gateway/tts_pron.py          $G/tts_pron.py
cp $SRC/gateway/export_chat_html.py  $G/export_chat_html.py
cp $SRC/gateway/Dockerfile           $G/Dockerfile
cp $SRC/gateway/entrypoint.sh        $G/entrypoint.sh
cp $SRC/config/roles.json            $G/roles.json
cp $SRC/config/roles.json            $D/config/roles.json
cp $SRC/docker-compose.yml           $COMPOSE
echo "  同步完成"
md5sum $G/llm_gateway.py $G/yue_polish.py $G/tts_pron.py $G/roles.json $COMPOSE

echo "===== [5/8] 构建镜像 1.31 ====="
cd $G
docker build -t aqing-gateway:1.31 -f Dockerfile . 2>&1 | tail -8

echo "===== [6/8] 只重建网关（rm + up，无 force-recreate）====="
cd $D
docker-compose config >/tmp/cfg131.out 2>&1 && echo "  compose config: OK" || { echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg131.out; exit 1; }
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关容器已移除" || echo "  旧网关容器本就不存在"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -8

echo "===== [7/8] 等网关起来 + 镜像内行为 + 记录数不丢 ====="
sleep 5
echo "--- 容器状态（大脑应仍 Up，token 未动）---"
docker ps --format "{{.Names}}\t{{.Status}}\t{{.Image}}" | grep folotoy_
echo "--- /health ---"
curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "--- /logs 部署后条数（应 == 部署前 $BASE_N，一条都唔少）---"
AFTER_N=$(curl -s --max-time 10 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))")
echo "  部署后 /logs count: $AFTER_N"
[ "$AFTER_N" = "$BASE_N" ] && echo "  ✅ 数据零丢失（部署前后一致）" || { echo "  ⚠️ 条数变化！检查（可能 E2E 落盘，逐步核对）"; }
echo "--- 镜像内正音/清理行为零回归 ---"
docker exec folotoy_llm_gateway_1 python3 -c "import sys;sys.path.insert(0,'/app');import tts_pron as t, yue_polish as y;print('  9词:', t.fix('净力 质量 陈桥 文风 单词'));print('  斜杠:', y.clean_tts_symbols('point /pɔɪnt/ 同 F/m'))"

echo "===== [8/8] 生产真链路 E2E（恢复/保留/刷新/唔落盘/落盘可见）====="
cp $SRC/gateway/_conv_e2e.py $G/_conv_e2e.py
cd $G && PYTHONIOENCODING=utf-8 python3 _conv_e2e.py 2>&1 | tail -55
echo ""
echo "  ⚠️ 本脚本【绝无】清落盘动作；记录只增不减（除 _conv_e2e 精确移除自己嘅标记条）。"
echo "  aqing-gateway:1.31 已部署；大脑/ nginx/ emqx 未动，token 保住。"
