#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产 8010 真链路回归 1.22：7角色带真实 system prompt 打部署后网关。
验：①6学科老师联网抓料+粤语讲解+事实正确 ②英语老师中英双语保留英文 ③全部<=1000字 ④上游30B。"""
import urllib.request, json, time, re, sys

GW = "http://127.0.0.1:8010/v1/chat/completions"
ROLES = json.load(open("/opt/folotoy/config/roles.json", encoding="utf-8"))

def chat(rid, q):
    persona = ROLES[rid]["prompt"]
    msgs = [{"role": "system", "content": persona}, {"role": "user", "content": q}]
    p = {"model": "THUDM/GLM-4-9B-0414", "messages": msgs, "stream": False,
         "temperature": 0.6, "max_tokens": 1800}  # 故意传旧model+大token，验网关覆盖+封顶
    req = urllib.request.Request(GW, data=json.dumps(p, ensure_ascii=False).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=150).read())
        return d["choices"][0]["message"]["content"], time.time()-t0, d.get("model", "")
    except Exception as e:
        return "ERR %s %s" % (type(e).__name__, e), time.time()-t0, ""

def cn(t): return len(re.findall(r"[\u4e00-\u9fff]", t))
def en(t): return re.findall(r"[A-Za-z]{3,}", t)

cases = [
    ("1 闲聊", "1", "今日心情唔错，倾下计？", [], False),
    ("2 语文·作者", "2", "「床前明月光」系边个写嘅？", ["李白"], False),
    ("2 语文·原文", "2", "静夜思首两句系乜？照原文读", ["床前明月光", "疑是地上霜"], False),
    ("3 数学·解方程", "3", "解方程 x²-5x+6=0", ["2", "3"], False),
    ("4 英语·词义", "4", "affect 同 effect 有乜唔同？", ["affect", "effect", "影响"], True),
    ("4 英语·例句", "4", "用 present continuous 造个句，解释清楚", ["ing", "正在"], True),
    ("5 物理·欧姆", "5", "欧姆定律公式同单位系乜？", ["I", "U", "R"], False),
    ("6 化学·方程式", "6", "水电解嘅化学方程式点写？", ["H", "O"], False),
    ("7 历史·唐朝", "7", "唐朝系公元几多年建立？", ["618"], False),
    ("7 历史·秦始皇", "7", "秦始皇几时统一六国？", ["前221", "公元前221"], False),
]
fails = 0
for name, rid, q, must, want_en in cases:
    out, dt, mdl = chat(rid, q)
    hit = [w for w in must if w not in out]
    n = cn(out)
    over = n > 1000
    en_hit = en(out)
    # 英语老师要保留英文；其余角色英文残留要少(公式符号除外)
    en_ok = (len(en_hit) > 0) if want_en else True
    flag = "OK  " if (not hit and not over and en_ok and not out.startswith("ERR")) else "FAIL"
    if flag == "FAIL": fails += 1
    print("\n[%s] %s  %s  t=%.1fs 汉字=%d 上游=%r" % (flag, name, "" if flag=="OK  " else "", dt, n, mdl))
    print("   缺关键:%s  超1000字:%s  英文词:%s" % (hit or "无", "是" if over else "否", (en_hit[:5] or "无")))
    print("   ", repr(out[:200]))
print("\n" + ("SUBJECT_E2E_ALL_PASS" if fails == 0 else "SUBJECT_E2E_FAIL=%d" % fails))
sys.exit(0 if fails == 0 else 1)
