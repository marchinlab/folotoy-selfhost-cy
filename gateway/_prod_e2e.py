#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产 8010 真链路回归：直接打部署后网关，验证意图分流/联网/30B/后处理/模型覆盖。"""
import urllib.request, json, time, re, sys

GW = "http://127.0.0.1:8010/v1/chat/completions"
PERSONA = ("你叫阿晴，20岁广州西关女仔，性格温柔沉静。全程只用简体中文地道粤语口语，短句，"
           "唔夹普通话、唔中英夹杂、唔用 Markdown、emoji、列表、括号；唔知就坦率讲唔知，唔好乱作。"
           "读诗引用原文时「是」等书面字逐字照读，唔改做口语。")

def chat(q, history=None, temp=0.8):
    msgs = [{"role": "system", "content": PERSONA}]
    for role, txt in (history or []):
        msgs.append({"role": role, "content": txt})
    msgs.append({"role": "user", "content": q})
    p = {"model": "THUDM/GLM-4-9B-0414", "messages": msgs, "stream": False,
         "temperature": temp, "top_p": 0.95, "max_tokens": 200}  # 故意传 9B+200，验网关覆盖
    req = urllib.request.Request(GW, data=json.dumps(p, ensure_ascii=False).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=150).read())
        return d["choices"][0]["message"]["content"], time.time() - t0, d.get("model", "")
    except Exception as e:
        return "ERR %s %s" % (type(e).__name__, e), time.time() - t0, ""

def cn(t): return len(re.findall(r"[\u4e00-\u9fff]", t))
EN = lambda t: re.findall(r"[A-Za-z]{2,}", t)

# 阈值按【联网抓料 + 30B 长文】现实放宽（纯透传 9B 先至系秒回）；
# 长文(庐山/故宫)30B 出 800 字实测 ~29s，属正常，唔当失败。
cases = [
    ("知识·李白(人名修复)", "李白系边个", None, ["诗仙", "唐"], 14.0),
    # 数字断言兼容阿拉伯/中文两种写法：资料注入后 30B 用「八千八百四十四点四三」照读，
    # 对粤语 TTS 反而更稳，唔好因为只认阿拉伯数字就误判 FAIL。
    ("知识·珠峰(数字照抄)", "珠穆朗玛峰有几高", None, ["8844|八千八百四十四", "8848|八千八百四十八"], 14.0),
    ("介绍·庐山(场景锚定+长文)", "介绍庐山",
     [("user", "介绍下广州塔"), ("assistant", "广州塔喺海珠区，系广州地标。"),
      ("user", "讲下陈家祠"), ("assistant", "陈家祠喺荔湾，木雕出名。")], ["江西"], 45.0),
    ("广州新闻(唔当知识题)", "广州本地有咩新闻", None, [], 16.0),
    ("天气(数值)", "广州今日天气几度", None, [], 26.0),
    ("诗词(是照原文)", "读首静夜思俾我听", None, ["是"], 8.0),
    ("讲笑(唔搜+短)", "讲个笑话", None, [], 8.0),
    ("情绪(唔搜+短)", "我今日唔开心", None, [], 8.0),
]
fails = 0
for name, q, hist, must, tmax in cases:
    out, dt, mdl = chat(q, hist)
    # must 项可含「a|b」多写法，命中任一即算（珠峰中文数字/阿拉伯数字）
    hit = [w for w in must if not any(alt in out for alt in w.split("|"))]
    gz = [w for w in ("广州", "小蛮腰", "珠江", "西关", "老广") if w in out] if "庐山" in name else []
    # 地名保真：李白出生地系四川江油，唔好串成广东（30B 本地人设渗透实测错误）
    place_err = []
    if "李白" in name:
        place_err = [w for w in ("广东江油", "广东绵州", "广州江油") if w in out]
    en = EN(out)
    slow = dt >= tmax   # 耗时只做软警告：30B 生成长文/上游负载波动，属正常，唔当功能失败
    flag = "OK  " if (not hit and not gz and not en and not place_err) else "FAIL"
    if flag == "FAIL": fails += 1
    print("\n[%s%s] %s  t=%.1fs 汉字=%d 上游model=%r" %
          (flag, " (偏慢)" if slow and flag == "OK  " else "", name, dt, cn(out), mdl))
    print("   缺关键:%s 串广州:%s 英文:%s 地名错:%s" %
          (hit or "无", gz or "无", en or "无", place_err or "无"))
    print("   ", repr(out[:180]))
print("\n" + ("PROD_E2E_ALL_PASS" if fails == 0 else "PROD_E2E_FAIL=%d" % fails))
sys.exit(0 if fails == 0 else 1)
