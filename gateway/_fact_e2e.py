# -*- coding: utf-8 -*-
"""v1.26 端到端真链路回归：打生产 8010，验证「每个角色讲的资料都联网核查 + 专名保真」。
核心证据 = 落盘 net 标记：修复前英语老师/英文auto问东方明珠塔 net=False（凭记忆），
修复后必须 net=True（真联网核查），且专名逐字「东方明珠塔」、唔会出现「上海塔」。
同时回归：阿晴粤语闲聊/纯语言操练唔好误联网（net=False，唔拖慢语音）。
部署新网关后先至跑。本机 --noproxy 直达。测完要清落盘。"""
import json, re, sys, time, urllib.request

BASE = "http://127.0.0.1:8010"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
AQING_SYS = "【角色:aqing_chat】\n你叫阿晴，20岁广州西关女仔。全程只用粤语，唔中英夹杂。"
ENG_SYS = "【角色:english_teacher】\nYou are a patient and professional middle-school English teacher. 你是一位有耐心、专业的初中英语老师。"

# (名字, system, 问题, 期望net, 必须出现的专名, 必须唔出现嘅错名)
CASES = [
    ("4号键-英语老师-东方明珠塔多高", ENG_SYS,
     "用英文同我讲东方明珠塔有几高，边年起好嘅",
     True, ("东方明珠", "Oriental Pearl", "468"), ("上海塔", "Shanghai Tower")),
    ("1号键-auto英文-上海地标", AQING_SYS,
     "用英文介绍上海嘅标志性景点，特别要讲到东方明珠塔，每句附中文翻译",
     True, ("东方明珠", "Oriental Pearl"), ("上海塔", "Shanghai Tower")),
    ("1号键-阿晴粤语-介绍庐山", AQING_SYS,
     "介绍下庐山，同我讲清楚佢系点样嘅",
     True, ("庐山",), ("广州", "西关")),
    ("4号键-纯语法-唔好误搜", ENG_SYS,
     "用英文解释下 present continuous 点用，比三个例句我",
     False, ("present continuous",), ()),
    ("1号键-粤语闲聊-唔好误搜", AQING_SYS,
     "你而家系边个啊？同我讲句笑话",
     False, ("阿晴",), ()),
]

def call(system, user):
    p = {"model": "Qwen/Qwen3-30B-A3B-Instruct-2507", "stream": False,
         "messages": [{"role": "system", "content": system},
                      {"role": "user", "content": user}]}
    r = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=json.dumps(p, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with _opener.open(r, timeout=180) as f:
        return json.load(f)

def last_log():
    with _opener.open(BASE + "/logs?limit=1", timeout=15) as f:
        d = json.load(f)
    return d.get("items", [{}])[0] if d.get("items") else {}

OK = []
def ck(name, cond):
    OK.append(bool(cond))
    print("  %s %s" % ("OK  " if cond else "FAIL", name))

for name, system, user, want_net, must, must_not in CASES:
    print("\n=== %s ===" % name)
    try:
        t = time.time()
        call(system, user)
        log = last_log()
        got_net = bool(log.get("net"))
        ans = log.get("a", "")
        print("  落盘: btn=%s role=%s net=%s auto_en=%s (%.1fs)" %
              (log.get("btn"), log.get("role"), got_net, log.get("auto_en"), time.time() - t))
        print("  正文前120: %s" % ans[:120].replace("\n", " / "))
        ck("  net=%s（期望 %s）" % (got_net, want_net), got_net == want_net)
        for w in must:
            ck("  含专名/关键 %r" % w, w.lower() in ans.lower())
        for w in must_not:
            ck("  无错名 %r" % w, w.lower() not in ans.lower())
    except Exception as e:
        ck("  %s 执行异常 %r" % (name, e), False)

n = len(OK); p = sum(OK)
print("\n结果: %d/%d %s" % (p, n, "全绿" if p == n else "有FAIL"))
raise SystemExit(0 if p == n else 1)
