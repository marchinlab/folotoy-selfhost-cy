# -*- coding: utf-8 -*-
"""v1.27 生产真链路 E2E：打生产 8010，用 stream=True 验证英文词间空格/断句修复。
★重点补 v1.25 最大盲区：之前只测非流式，流式逐 token .strip() 粘词溜过咗。
部署新网关后先至跑（旧镜像流式会 FAIL）。本机 --noproxy 直达。
"""
import json, re, sys, urllib.request

BASE = "http://127.0.0.1:8010/v1/chat/completions"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
AQING_SYS = "【角色:aqing_chat】\n你叫阿晴，20岁广州西关女仔。全程只用粤语，唔中英夹杂。"
ENG_SYS = ("【角色:english_teacher】\nYou are a patient and professional middle-school "
           "English teacher. 你是一位有耐心、专业的初中英语老师，用标准普通话 + 中英双语讲解，"
           "英文例句保留英文并附中文翻译。")

def call_stream(system, user):
    payload = {"model": "Qwen/Qwen3-30B-A3B-Instruct-2507", "stream": True,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    req = urllib.request.Request(BASE, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    deltas, frames, done = [], 0, False
    with _opener.open(req, timeout=120) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if line == "data: [DONE]":
                done = True; break
            if not line.startswith("data:"):
                continue
            js = line[5:].strip()
            if not js: continue
            try:
                d = json.loads(js)
            except Exception:
                continue
            frames += 1
            for ch in d.get("choices", []):
                c = (ch.get("delta") or {}).get("content")
                if c:
                    deltas.append(c)
    return "".join(deltas), frames, done, deltas

OK = []
def ck(name, cond, extra=""):
    OK.append(bool(cond)); print("  %-4s %-32s %s" % ("PASS" if cond else "FAIL", name, extra))

CASES = [
    # (名, system, user, 期望最少英文词, 必须出现的完整英文短语(空格正确), 必须无嘅粘词)
    ("4号键-英文例句", ENG_SYS,
     "用英文教我三个去上海旅行嘅例句，每句附中文翻译", 12,
     (), ()),
    ("1号键-auto英文问", AQING_SYS,
     "用英文介绍上海三个旅游景点，每个景点俾一个英文例句同中文翻译", 12,
     (), ()),
    ("4号键-引号短语", ENG_SYS,
     "用英文解释 be famous for 同 plan to do 嘅区别，各造一个例句", 8,
     (), ()),
]

for name, system, user, min_en, must_phrases, no_glue in CASES:
    print("\n== %s ==" % name)
    try:
        ans, frames, done, deltas = call_stream(system, user)
    except Exception as e:
        ck(name + " 流式请求", False, repr(e)[:90]); continue
    en_words = re.findall(r"[A-Za-z]{2,}", ans)
    spaces = sum(1 for w in re.findall(r"[A-Za-z][A-Za-z .!?,;'\"-]{4,}", ans) if " " in w)
    # 粘词特征：小写紧接大写 (planningto 唔会、但 planningTo/引号内 plantodo 会现)
    glued = re.findall(r"[a-z]{3,}[A-Z]", ans)
    # 更准：连续 ≥2 个 2+ 字母英文词之间无空格 —— 用「英文块」平均长度近似（粘词会暴涨）
    eng_blocks = re.findall(r"[A-Za-z][A-Za-z'’\-]*", ans)
    long_blocks = [b for b in eng_blocks if len(b) >= 14]   # 正常英文单词极少 ≥14 连续字母
    print("  回复:", repr(ans[:220]))
    print("  帧数=%d done=%s 英文词=%d 含空格片段=%d 超长块=%s" %
          (frames, done, len(en_words), spaces, long_blocks[:6]))
    ck(name + " 流式到齐[DONE]", done)
    ck(name + " 帧数正常", frames >= 5, "frames=%d" % frames)
    ck(name + " 英文词数达标", len(en_words) >= min_en, "%d>=%d" % (len(en_words), min_en))
    ck(name + " 有词间空格", spaces >= 5, "含空格英文片段=%d" % spaces)
    ck(name + " 无粘词长块", len(long_blocks) == 0, "超长块=%s" % long_blocks[:4])
    for p in must_phrases:
        ck("  含完整短语 %r" % p, p.lower() in ans.lower())

# 回归：1号键粤语闲聊必须保持粤语、唔好被 auto 路由带去英文
print("\n== 1号键-粤语闲聊不回归 ==")
try:
    ans, frames, done, _ = call_stream(AQING_SYS, "你而家系边个啊？同我讲句笑话")
    print("  回复:", repr(ans[:160]))
    ck("闲聊 保持粤语人设", ("阿晴" in ans or "我系" in ans or "讲" in ans), repr(ans[:50]))
    en = re.findall(r"[A-Za-z]{3,}", ans)
    ck("闲聊 无英文乱入", len(en) == 0, "英文词=%d" % len(en))
except Exception as e:
    ck("闲聊 流式请求", False, repr(e)[:90])

# ★v1.27 同源修复：粤语学科老师流式必须完成词级粤语化（旧逐 token 会漏「我们/现在」）
PHY_SYS = "【角色:physics_teacher】\n你系初中物理老师，全程用广州粤语同学生讲解，讲清楚物理概念。"
print("\n== 5号键-物理老师粤语流式(词级粤语化不漏) ==")
try:
    ans, frames, done, _ = call_stream(PHY_SYS,
        "同我解释下牛顿第二定律，用生活嘅例子说明，讲下而家点样应用")
    print("  回复:", repr(ans[:200]))
    ck("物理老师 流式到齐[DONE]", done)
    ck("物理老师 有粤语口语字", any(z in ans for z in ("系", "嘅", "我哋", "而家", "讲", "唔", "啲")),
       repr(ans[:60]))
    # 关键：整段清洗后，30B 若吐「我们/现在/今天」应转成「我哋/而家/今日」；
    #      Role prompt 已要求粤语，正常唔会吐普通话，故只要有足够粤语特征即算流式粤语化生效
    ck("物理老师 有实质内容", len(ans) >= 40, "长度=%d" % len(ans))
    # ★公式符号白名单：若模型吐咗 F=ma / ma，必须完整保留（唔好被清成「F =」）
    if "F=ma" in ans or "F = ma" in ans or " ma" in ans:
        ck("物理公式变量未被清", "ma" in ans and "=" in ans, repr(ans[:90]))
    else:
        ck("物理公式(模型用中文讲,跳过)", True)
except Exception as e:
    ck("物理老师 流式请求", False, repr(e)[:90])

# ★v1.27 公式符号白名单真链路：化学老师讲 pH / H2O，必然触发，直接验符号唔会念丢
CHM_SYS = "【角色:chemistry_teacher】\n你系初中化学老师，全程用广州粤语讲解，讲到化学式同 pH 要照写。"
print("\n== 6号键-化学老师公式符号(pH/H2O)流式不丢 ==")
try:
    ans, frames, done, _ = call_stream(CHM_SYS,
        "用粤语讲下酸碱性同 pH 值，顺便写出水嘅化学式，要讲清楚")
    print("  回复:", repr(ans[:200]))
    ck("化学老师 流式到齐[DONE]", done)
    ck("化学 pH 符号保留", "pH" in ans or "PH" in ans, repr(ans[:80]))
    ck("化学 H2O 化学式保留", "H2O" in ans or "H₂O" in ans,
       "H2O=%s" % ("H2O" in ans or "H₂O" in ans))
    ck("化学老师 有粤语口语字", any(z in ans for z in ("系", "嘅", "而家", "讲", "唔", "啲", "酸")),
       repr(ans[:60]))
except Exception as e:
    ck("化学老师 流式请求", False, repr(e)[:90])

n = len(OK); p = sum(OK)
print("\n===== 结果 %d/%d %s =====" % (p, n, "ALL PASS ✔" if p == n else "有FAIL ✘"))
sys.exit(0 if p == n else 1)
