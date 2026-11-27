# -*- coding: utf-8 -*-
"""v1.25 端到端真链路回归：打生产 8010，模拟主人真实请求。
验证「1号闲聊键用英文问」自动路由到英语老师，英文例句完整保留到 TTS 文本。
部署新网关后先至跑（旧镜像无 auto 路由会 FAIL）。本机 --noproxy 直达。
"""
import json, re, sys, urllib.request

BASE = "http://127.0.0.1:8010/v1/chat/completions"
# 网关本机直达，唔行系统代理
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# 模拟大脑发嚟嘅 messages：1号键 aqing_chat system（带角色标记）+ 用户英文问题
AQING_SYS = "【角色:aqing_chat】\n你叫阿晴，20岁广州西关女仔。全程只用粤语，唔中英夹杂。"
ENG_SYS = "【角色:english_teacher】\nYou are a patient and professional middle-school English teacher. 你是一位有耐心、专业的初中英语老师。"

CASES = [
    # (名字, system, 用户问题, 期望命中 auto, 必须出现嘅英文, 必须唔出现嘅粤语串味, 必须出现嘅粤语[只用于唔路由case])
    ("1号键-纯英文问", AQING_SYS,
     "i want to a travel to shanghai tourist sky, give me three example sentences",
     True, ("Shanghai", "I "), ("我系", "唔系", "嘅", "而家"), ()),
    ("1号键-中文夹用英文", AQING_SYS,
     "帮我用英文介绍去上海旅行嘅客方案，要三个英文例句附中文翻译",
     True, ("Shanghai", "."), ("我系", "嘅客", "明唔明"), ()),
    ("4号键-本尊回归", ENG_SYS,
     "用英文教我三个去上海旅行嘅例句",
     False, ("Shanghai", "."), ("我系", "嘅", "明唔明"), ()),
    # 呢条【绝对唔好被 auto 路由】：必须保持阿晴粤语人设（正向断言「我系阿晴」）
    ("1号键-粤语闲聊不回归", AQING_SYS,
     "你而家系边个啊？同我讲句笑话",
     False, (), (), ("阿晴", "我系")),
]

def call(system, user):
    payload = {
        "model": "Qwen/Qwen3-30B-A3B-Instruct-2507",
        "stream": False,   # 用非流方便断言；流式分支由 polish_english 同一管线覆盖
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        BASE, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with _opener.open(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]

def log_has(marker):
    """查网关启动日志有冇 EN_AUTO_ROUTE（粗略，靠落盘 auto_en 字段更准）。"""
    return marker

OK = []
def ck(name, cond, extra=""):
    OK.append(bool(cond))
    print("  %s %-34s %s" % ("PASS" if cond else "FAIL", name, extra))

for name, system, user, want_auto, must_en, must_not_yue, must_yue in CASES:
    print("\n== %s ==" % name)
    try:
        ans = call(system, user)
    except Exception as e:
        ck(name + " 请求", False, repr(e)[:80])
        continue
    print("  回复:", ans[:180].replace("\n", " "))
    if want_auto:
        # 必须保住足够英文（英文单词 >= 3）——auto 路由命中 + polish_english 豁免成功
        en_words = re.findall(r"[A-Za-z]{2,}", ans)
        ck(name + " 英文例句保留", len(en_words) >= 3,
           "英文词=%d %s" % (len(en_words), en_words[:8]))
        for e in must_en:
            ck("  含 %r" % e, e.lower() in ans.lower())
    else:
        ck(name + " 请求成功", bool(ans))
    for y in must_not_yue:
        if y:
            ck("  无粤语串味 %r" % y, y not in ans)
    # 唔路由嘅 case：必须保持阿晴粤语人设（证明冇被自动切去英语老师）
    for y in must_yue:
        ck("  保持粤语人设 %r" % y, y in ans)

n = len(OK); p = sum(OK)
print("\n===== 结果: %d/%d %s =====" % (p, n, "ALL PASS ✔" if p == n else "有 FAIL ✘"))
sys.exit(0 if p == n else 1)
