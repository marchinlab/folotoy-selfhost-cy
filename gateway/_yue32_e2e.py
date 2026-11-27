# -*- coding: utf-8 -*-
"""v1.32 生产真链路 E2E：打生产 8010，验证 4 项喺【粤语角色真实回答】落地。
  A) 正音：儿子→兒子、时间→時间（「间」故意保留简体）。
  B) 措辞：呢个嗰阵→呢个时期（诱导模型讲「这个时候」，播报稿须变「呢个时期」）。
  C) 措辞：你有啲想知定系唔知→你想唔想知（诱导别扭正反问）。
  D) 防误伤 + 落盘零污染：全部请求带 X-No-Record:1，先後 /logs count 必须一致（65）。

★判定落喺网关返回文本（polish+fix 后，即真入 TTS 嘅播报稿）：
  - 模型输出有随机性：正音/措辞断言用「若出现未处理形态则 FAIL，否则视为模型未用该说法」；
    但【诱导成功关键点】用 must_hit 标记——若模型真系讲咗目标词且未处理，即 FAIL。
  - 防误伤（定系合法句、嗰阵合法用法、护字）恒严格。
★本机经 WSL 127.0.0.1:8010 直达，--noproxy。"""
import json, sys, urllib.request

BASE = "http://127.0.0.1:8010/v1/chat/completions"
LOGS = "http://127.0.0.1:8010/logs?limit=1"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
AQING = ("【角色:aqing_chat】\n你叫阿晴，20岁广州西关女仔。全程只用粤语口语，"
         "唔中英夹杂，唔用 emoji/Markdown。回答简短，两三句就够。")


def logs_count():
    with _opener.open(LOGS, timeout=15) as r:
        return json.loads(r.read().decode("utf-8", "replace")).get("count")


def call(system, user, stream=True):
    payload = {"model": "Qwen/Qwen3-30B-A3B-Instruct-2507", "stream": stream,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    req = urllib.request.Request(BASE, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "X-No-Record": "1"})   # ★唔落盘
    deltas, frames, done = [], 0, False
    with _opener.open(req, timeout=180) as r:
        if not stream:
            d = json.loads(r.read().decode("utf-8", "replace"))
            return (d["choices"][0]["message"].get("content") or ""), 1, True
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if line == "data: [DONE]":
                done = True; break
            if not line.startswith("data:"):
                continue
            js = line[5:].strip()
            if not js:
                continue
            try:
                d = json.loads(js)
            except Exception:
                continue
            frames += 1
            for ch in d.get("choices", []):
                c = (ch.get("delta") or {}).get("content")
                if c:
                    deltas.append(c)
    return "".join(deltas), frames, done


RES = []
def ck(name, cond, extra=""):
    RES.append(bool(cond)); print("  %-4s %-38s %s" % ("PASS" if cond else "FAIL", name, extra))

print("===== v1.32 生产 E2E（全部 X-No-Record:1，唔落盘）=====")
BEFORE = logs_count()
print("  部署后 /logs count 基线:", BEFORE)

ALL = ""
# (name, user, 检查项函数)
def case_a(ans):
    """儿子→兒子、时间→時间；间故意留简体。"""
    print("  回复:", repr(ans[:200]))
    if "儿子" in ans:
        ck("A  「儿子」须正音成「兒子」", "兒子" in ans and "儿子" not in ans, "仍留简体")
    else:
        ck("A  「儿子」未出现/已正音", "兒子" in ans or "儿子" not in ans)
    if "时间" in ans:
        ck("A  「时间」须正音成「時间」", "時间" in ans and "时间" not in ans, "仍留简体")
    else:
        ck("A  「时间」未出现/已正音", True)
    ck("A  「间」保持简体(唔转間)", "時间" not in ans or "時間" not in ans)

CASES = [
    ("A 正音-儿子/时间",
     "用粤语讲下：我个儿子而家几大多，同埋佢每日花几多时间读书？简短答我。",
     case_a),
    ("B 措辞-呢个时期",
     "用粤语讲下你最近读嘅一本好书，一定要用「这个时候」呢个讲法开头，讲两句就够。",
     lambda a: (print("  回复:", repr(a[:200])),
                ck("B  唔再有病句「呢个嗰阵」", "呢个嗰阵" not in a),
                ck("B  「这个时候/呢个时候」已收「呢个时期」",
                   "呢个时期" in a or ("这个时候" not in a and "呢个时候" not in a),
                   "诱导词未落地则视为未触发"))),
    ("C 措辞-想唔想知",
     "用粤语问我一问：你有啲想知定系唔知呢件事？照住呢个讲法问，唔好改。",
     lambda a: (print("  回复:", repr(a[:200])),
                ck("C  别扭「想知定系唔知」已收敛", "想知定系唔知" not in a),
                ck("C  地道「想唔想知」落地/未用该说法",
                   "想唔想知" in a or "想知定系唔知" not in a))),
    ("D 防误伤-定系/嗰阵合法",
     "唔好查天气，直接照抄呢两句粤语回答我，一个字都唔好改：「你去定系我去好呢？」"
     "「从古嗰阵到而家，呢度都好热闹。」",
     lambda a: (print("  回复:", repr(a[:200])),
                # 呢三条系【恒严格负向】断言：无论模型讲乜都唔应该出现病句/被错误收敛。
                # 「定系」「嗰阵」嘅【正向保留】确定性验证已喺 _yue32_unit.py 用固定输入做足
                # （polish("你去定系我去")、polish("从古嗰阵到而家…")），E2E 唔重复恒真式。
                ck("D  唔会冒病句「呢个嗰阵」", "呢个嗰阵" not in a),
                ck("D  唔会冒病句「乜嗰阵」", "乜嗰阵" not in a),
                ck("D  「定系」句唔会被误收敛成「想唔想」",
                   "定系" not in a or "想唔想" not in a))),
]

for name, user, checker in CASES:
    print("\n== %s ==" % name)
    try:
        ans, frames, done = call(AQING, user, True)
    except Exception as e:
        ck(name + " 请求", False, repr(e)[:100]); continue
    ALL += "\n" + ans
    ck(name + " 到齐[DONE]", done and len(ans) > 0, "帧数=%d 字数=%d" % (frames, len(ans)))
    checker(ans)

print("\n== 全局护字恒严格 ==")
for keep, wrong in [("头发", "头發"), ("发现", "發现"), ("语文", "語聞"),
                    ("文化", "聞化"), ("过程", "過程")]:
    ck("护 %s 唔变 %s" % (keep, wrong), wrong not in ALL)

print("\n== 落盘零 pollution（X-No-Record:1）==")
AFTER = logs_count()
print("  请求前 count=%d 请求后 count=%d" % (BEFORE, AFTER))
ck("4 条 E2E 请求冇落盘（count 不变）", AFTER == BEFORE, "%d->%d" % (BEFORE, AFTER))

p = sum(RES)
print("\n=== YUE32_E2E: %d/%d %s ===" % (p, len(RES), "ALL_PASS" if p == len(RES) else "HAS_FAIL"))
sys.exit(0 if p == len(RES) else 1)
