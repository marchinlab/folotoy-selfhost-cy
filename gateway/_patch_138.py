# -*- coding: utf-8 -*-
# v1.38 出声判据修订 patch：精确替换 + 断言，全部命中先至写回。
import io, sys

P = "/mnt/c/Users/YOURNAME/WorkBuddy/2026-11-10-15-56-24/folotoy-selfhost/gateway/_broadcast_verified.sh"
raw = open(P, "rb").read()
assert b"\r\n" not in raw, "unexpected CRLF"
txt = raw.decode("utf-8")

def sub_once(txt, old, new, tag):
    n = txt.count(old)
    assert n == 1, "PATTERN %s count=%d (expect 1)" % (tag, n)
    print("[patch] %s : replaced 1 occurrence" % tag)
    return txt.replace(old, new, 1)

# ---- 1) 铁律注释第 3 条：判据语义改写 + 追加 v1.38 说明 ----
old1 = (
    "#  3. 判据必须【来源IP==设备 AND 200 AND bytes==size】，单看 200 会把我自己\n"
    "#     curl 自测当成设备下载。\n"
)
new1 = (
    "#  3. 判据【来源IP==设备 AND 200 AND 下载够量】（v1.38 修订，见下）：单看 200\n"
    "#     会把我自己 curl 自测当成设备下载；死盯 bytes==size 会把火火兔误判没播。\n"
    "#\n"
    "# ★★ v1.38 出声判据修订（2026-11-12 主人拍板）★★\n"
    "#   火火兔【边下边播】：缓冲够就主动断 HTTP、本地继续播完，nginx 永远记唔到\n"
    "#   bytes==文件大小。旧判据 $10==sz 会误判「没播」→ 每轮重推，2026-11-12 AM\n"
    "#   同一条重复播咗约 9 遍（主人：「一直重复播报」）。\n"
    "#   新判据：来源IP==设备 AND 200 AND ( $10 >= sz*ratio OR $10 >= min_bytes )\n"
    "#     默认 ratio=0.9、min_bytes=1000000(1MB)：\n"
    "#       40k 1,039,677B 下到 1,035,127(99.5%) -> 真出声\n"
    "#       48k 1,247,277B 下到 1,083,950(>1MB)  -> 真出声（大文件按绝对下限豁免）\n"
    "#       v1.33 冷重启掐断 71.8% / 只 48KB     -> 仍 FAIL，继续重推（真故障唔漏）\n"
    "#       自己 curl(非设备IP) / 206 分段        -> 仍 FAIL\n"
    "#   本地单测：_test_bc_complete_138.sh (8/8)。回滚：.bak-pre-1.38。\n"
)
txt = sub_once(txt, old1, new1, "header-note")

# ---- 2) 用法注释补一行可覆盖变量 ----
old2 = "#                 STATE_DIR / CATCHUP_WINDOW_HOURS / NOW_OVERRIDE(测试用)\n"
new2 = (
    "#                 STATE_DIR / CATCHUP_WINDOW_HOURS / NOW_OVERRIDE(测试用)\n"
    "#                 COMPLETE_RATIO / COMPLETE_MIN_BYTES (v1.38 出声判据阈值)\n"
)
txt = sub_once(txt, old2, new2, "usage-vars")

# ---- 3) 环境变量声明区追加两个阈值（放在 SLOT_TAG 行后）----
old3 = 'SLOT_TAG=${SLOT_TAG:-}                                  # 补播显式时段 AM/PM，空=按当前钟点自动判定\n'
new3 = (
    'SLOT_TAG=${SLOT_TAG:-}                                  # 补播显式时段 AM/PM，空=按当前钟点自动判定\n'
    '# v1.38 出声判据阈值：下载够【文件比例】或【绝对字节下限】任一满足即视为真出声\n'
    'COMPLETE_RATIO=${COMPLETE_RATIO:-0.9}                   # 小文件按 90% 判定\n'
    'COMPLETE_MIN_BYTES=${COMPLETE_MIN_BYTES:-1000000}      # 大文件(>~1.11MB)按 1MB 绝对下限豁免\n'
)
txt = sub_once(txt, old3, new3, "env-vars")

# ---- 4) complete_line() 函数本体 ----
old4 = (
    "complete_line(){\n"
    '  timeout 10 docker logs --since 20m --tail 1500 "$NX" 2>&1 \\\n'
    '    | grep -F "GET /$NAME" \\\n'
    "    | awk -v sz=\"$SIZE\" -v dev=\"$DEV\" '$1==dev && $9==\"200\" && $10==sz {print; exit}'\n"
    "}\n"
)
new4 = (
    "# v1.38：火火兔边下边播，nginx 记唔到 bytes==size；改为「下载够量」判定。\n"
    "#   $10 >= sz*ratio  OR  $10 >= min_bytes  -> 真出声\n"
    "complete_line(){\n"
    '  timeout 10 docker logs --since 20m --tail 1500 "$NX" 2>&1 \\\n'
    '    | grep -F "GET /$NAME" \\\n'
    "    | awk -v sz=\"$SIZE\" -v dev=\"$DEV\" -v ratio=\"$COMPLETE_RATIO\" -v minb=\"$COMPLETE_MIN_BYTES\" "
    "'$1==dev && $9==\"200\" && ($10>=sz*ratio || $10>=minb) {print; exit}'\n"
    "}\n"
)
txt = sub_once(txt, old4, new4, "complete_line")

# ---- 5) 第 206 行注释同步 ----
old5 = "# 2) 盯完整下载：nginx access.log 出现来源设备 GET /NAME 200 bytes==SIZE\n"
new5 = "# 2) 盯够量下载：来源设备 GET /NAME 200 且下载达 v1.38 门槛（唔再死等 bytes==SIZE）\n"
txt = sub_once(txt, old5, new5, "step2-comment")

open(P, "wb").write(txt.encode("utf-8"))
print("[patch] WRITTEN ok, bytes=%d" % len(txt.encode("utf-8")))
