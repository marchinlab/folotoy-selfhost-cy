#!/bin/bash
# ============================================================
# v1.44 增量部署：只更新 tts_pron.py（v1.44 三条正音）
#   · 说→說【全局单字】：syut3 转繁返粤；唯一多音「游说→游說」字节 7776 全同、唔会带偏 seoi3。
#   · 渐→漸【全局单字】：jim6 转繁；简「渐」被念成「尖」zim1(错)。
#   · 称帝/稱帝→清帝【词级】：换 cing1 同音字，8208→8352；称王/亲/其他含称词一律唔改。
#   重建 aqing-gateway:1.44、只 recreate 网关。
#   ⚠️主人一句「可以改」授权；此后「称帝/称王」新证据由整词字节碰撞定案，唔再切词内字 F0
#     (v1.42 能量谷 / v1.44b SRT42% 两套都自相矛盾，连正确锚清帝都判错，已弃用)。
# ★★绝不碰大脑/stt-proxy/emqx/nginx；部署前后断言 Up time 延续、保 UDP 令牌、唔使踢设备。
# ★回滚：还原 tts_pron.py.bak-pre-1.44 + docker-compose.yml.bak-pre-1.44
#        (compose 改返 1.42)，build 1.42 重建网关即可，唔使重启大脑、唔使踢设备。
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
grep -q 'v1.44' $SRC/gateway/tts_pron.py && echo "  v1.44 docstring 标记: OK"
grep -q '称帝", "清帝' $SRC/gateway/tts_pron.py && echo "  词级 称帝→清帝 标记: OK"
grep -q '说", "說' $SRC/gateway/tts_pron.py && echo "  全局 说→說 标记: OK"
grep -q '渐", "漸' $SRC/gateway/tts_pron.py && echo "  全局 渐→漸 标记: OK"
grep -q '称王 坚决唔改' $SRC/gateway/tts_pron.py && echo "  称王唔改边界标注: OK"
cd $SRC/gateway
python3 -m py_compile llm_gateway.py yue_polish.py tts_pron.py news_broadcaster.py && echo "  py_compile 四文件: OK"
echo "  --- v1.44 专项 ---"
PYTHONIOENCODING=utf-8 python3 _yue44_unit.py 2>&1 | tail -1
echo "  --- 全量回归（17 套，退出码判据）---"
bash $SRC/gateway/_regress_144.sh 2>&1 | tail -2

echo "===== [3/7] 备份（幂等，已存在唔覆盖）====="
[ -f $G/tts_pron.py.bak-pre-1.44 ] || cp $G/tts_pron.py $G/tts_pron.py.bak-pre-1.44 2>/dev/null || true
[ -f $COMPOSE.bak-pre-1.44 ] || cp $COMPOSE $COMPOSE.bak-pre-1.44
echo "  .bak-pre-1.44 就绪（工作区侧已建，此处补生产侧）"

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
grep -q 'image: aqing-gateway:1.44' $COMPOSE && echo "  compose tag 1.44: OK" || { echo "  ABORT tag"; exit 1; }
grep -q 'OPENAI_WHISPER_API_BASE: http://stt-proxy:8000/v1' $COMPOSE && echo "  stt-proxy 切流仍在: OK"

echo "===== [5/7] 重建镜像 1.44 ====="
cd $G
docker build -t aqing-gateway:1.44 -f Dockerfile . 2>&1 | tail -4
docker image inspect aqing-gateway:1.44 --format '  built {{.Id}}' 2>&1

echo "===== [6/7] 只 recreate 网关（禁 force，不碰其它）====="
cd $D
if ! docker-compose config >/tmp/cfg144.out 2>&1; then echo "  COMPOSE_CONFIG_FAIL"; tail -15 /tmp/cfg144.out; exit 1; fi
echo "  compose config: OK"
docker rm -f folotoy_llm_gateway_1 >/dev/null 2>&1 && echo "  旧网关已移除"
docker-compose up -d --no-deps llm-gateway 2>&1 | tail -4
sleep 6
echo "  --- 不动容器 Up time 应延续 ---"
for c in folotoy_folotoy_1 folotoy_stt_proxy_1 folotoy_nginx_1 folotoy_emqx_1; do
  docker ps --format '{{.Names}}|{{.Status}}' | grep "^$c|" || echo "  ⚠️ $c 未在跑!"
done
echo "  --- /health ---"; curl -s --max-time 6 http://127.0.0.1:8010/health; echo
echo "  --- 镜像内 v1.44 三条正音确认 ---"
docker exec folotoy_llm_gateway_1 python3 -c "
import tts_pron as t
print('  fix(说话)  =',t.fix('说话'),'  (期望 說话,音=說話8208)')
print('  fix(渐渐)  =',t.fix('渐渐'),'  (期望 漸漸)')
print('  fix(称帝)  =',t.fix('称帝'),'  (期望 清帝)')
print('  fix(称王)  =',t.fix('称王'),'  (期望 称王 唔改)')
print('  fix(游说)  =',t.fix('游说'),'  (期望 游說,音素7776不变)')
print('  fix(亲)    =',t.fix('亲'),'  (期望 亲 唔改)')
"
AFTER_N=$(curl -s --max-time 10 "http://127.0.0.1:8010/logs?limit=5000" | python3 -c "import sys,json;print(json.loads(sys.stdin.read()).get('count'))")
echo "  记录: $BASE_N -> $AFTER_N $([ "$AFTER_N" -ge "$BASE_N" ] && echo '✅零丢失' || echo '⚠️下降!')"

echo "===== [7/7] 生产 E2E（纯函数链，验四路 fix 生效 + 边界）====="
docker exec folotoy_llm_gateway_1 python3 -c "
import tts_pron as t, yue_polish as y
def bc(s):
    nc,_=y.polish(s,report=True); nc=t.fix(nc); return y.clean_tts_symbols(nc)
s='而家佢说话渐渐大声，朱元璋称帝称王，对称嘅事要相称，游说同亲家唔好搞错，过马路小心。'
out=bc(s)
print('  输入:',s)
print('  输出:',out)
print('  说话已正音(說):', '說' in out, '(期望 True)')
print('  渐渐已正音(漸):', '漸' in out, '(期望 True)')
print('  称帝→清帝:', '清帝' in out, '(期望 True)')
print('  称王保留(唔改):', '称王' in out, '(期望 True)')
print('  对称/相称保留(cing3):', ('对称' in out and '相称' in out), '(期望 True)')
print('  游说→游說(音素不变):', '游說' in out, '(期望 True)')
print('  亲家保留(唔改):', '亲家' in out, '(期望 True)')
print('  过马路保留:', '过马路' in out, '(期望 True)')
"
echo "  ⚠️ 无清落盘动作；绝不碰大脑/stt-proxy/emqx/nginx；UDP 令牌保住、唔使踢设备。"
echo "=== DONE_144 ==="
