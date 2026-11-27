# -*- coding: utf-8 -*-
"""v1.44 综合声学探针：主人报「渐渐」「亲自」发音唔啱，「称帝」同几个含称词都唔啱。

沿用 v1.43 已验证嘅【单字声学指纹为主 + 整词字节碰撞】框架（避开 v1.42 切字坑：
edge-tts 中文 WordBoundary 整词一个、唔逐字，切词内字会飘）。

三组目标 + 粤语背景：
  ===== 渐 jim6（阴去/阳去, 韵 -im, 齿音 z）=====
    普通话 jiàn = 舌面 j + 韵 -ian。简体「渐」若被普通话 G2P 劫持，会念成
    【牙音 g / 舌面 j + 前元音 -in/-ian 尾】(似「见」gin3) 而唔系【齿音 z + -m 尾】。
    ? 简「渐」单字 F1/F2/字节 似正音锚「漸」/「尖」zim1(-m尾) 定似反锚「箭」zin3/「賤」zin6(-n尾)/「見」gin3？
    ? 转繁「漸」能否正音？「渐/漸」一字一音(jim6)，若繁体正音→全局单字安全(同 v1.28)。
  ===== 亲 can1（阴平, 韵 -an, 齿音 c）=====
    普通话 qīn = 舌面送气 q + 韵 -in。简体「亲」若被劫持，会念成【-in 韵】(似「千」cin1)
    或【-ing 韵】(似「青」cing1)，而唔系【-an 韵 + 齿音 c】can1。
    ⚠️「亲」多音：can1(亲人/亲自/亲切) vs can3(亲家)。转繁「親」保留两读先至全局安全(同 v1.28「会」wui6/kui2)。
    ? 简「亲」单字 F1/F2 似正音「親」/「餐」caan1(-an) 定似反锚「千」cin1/「青」cing1/「侵」cam1(-m尾)？
  ===== 称 cing1(称呼/声称/称王/名称/简称/称赞/堪称/称帝) / cing3(对称/相称/称职) =====
    ⚠️ 上版 v1.42 只实锤【声调】(称帝词内掉降调似第三声)，【未实锤单字简繁 F1/F2 音色】——本版补。
    ⚠️ 上版用「趁」做 cing3 反锚系【错】(趁读 can3, 声母韵都唔同)。cing3 正音锚应为「秤」cing3；
       cing1 锚用「清」cing1。逐含称词比对【简X vs X清(cing1锚) vs X秤(cing3锚)】字节/时长
       → 字节同边 = 该词「称」念边个调，同「应读调」对照就知边几个词错。
    ?「称/稱」单字 F1/F2 简繁对比 + 卷舌排查(普通话 chēng 卷舌 ch vs 粤 cing 齿音 c)。
    ?「称帝」应 cing1：简体现今系咪似「清帝」(cing1) 定「秤帝」(cing3)？
    ? 转繁「稱帝」系咪反而更乱(v1.42 已证) → 称【绝唔全局转繁】，只词级换字/暂缓。

判据：A) 整词/单字 mp3 字节碰撞(同音素必同字节,最硬) B)【单字】F0/F1F2/时长(最干净)
      D) 单字声学指纹汇总  E) 含称词「简 vs cing1锚 vs cing3锚」字节判调表
用法(网关容器)：python3 _yue44_probe.py
"""
import subprocess, os, struct, math, re, hashlib

V = "zh-HK-HiuMaanNeural"
R = "+20%"
D = "/audio/pron_yue44"
FS = 16000
os.makedirs(D, exist_ok=True)

# (tag, 文本, 说明)
CASES = [
    # ===== 渐 jim6 单字 + 反锚 =====
    ("j_j",   "渐",  "简体 渐 单字(主人报)"),
    ("j_f",   "漸",  "繁体 漸 单字(候选正音 jim6)"),
    ("j_b1",  "箭",  "反锚 箭(zin3 齿音+ -n尾, 调近)"),
    ("j_b2",  "賤",  "反锚 賤(zin6 齿音+ -n尾, 只差韵尾 -n/-m)"),
    ("j_b3",  "尖",  "反锚 尖(zim1 -m尾但阴平, 只差调)"),
    ("j_b4",  "見",  "反锚 見(gin3 牙音+ -n尾)"),
    # 渐词
    ("jj_j",  "渐渐", "简体 渐渐(主人报)"),
    ("jj_f",  "漸漸", "繁体 漸漸"),
    ("jj_b1", "箭箭", "反锚 箭箭(zin3 zin3)"),
    ("zj_j",  "逐渐", "简体 逐渐"),
    ("zj_f",  "逐漸", "繁体 逐漸"),
    # ===== 亲 can1 单字 + 反锚 =====
    ("q_j",   "亲",  "简体 亲 单字(主人报)"),
    ("q_f",   "親",  "繁体 親 单字(候选正音 can1)"),
    ("q_b1",  "千",  "反锚 千(cin1 -in韵, 测普通话qīn劫持)"),
    ("q_b2",  "青",  "反锚 青(cing1 -ing韵)"),
    ("q_b3",  "侵",  "反锚 侵(cam1 -m尾)"),
    ("q_b4",  "餐",  "锚 餐(caan1 -aan长a韵)"),
    ("qjia_j","亲家","⚠️多音 can3 亲家(全局须护)"),
    ("qjia_f","親家","親家 转繁"),
    # 亲词
    ("qz_j",  "亲自", "简体 亲自(主人报)"),
    ("qz_f",  "親自", "繁体 親自"),
    ("qz_b1", "千自", "反锚 千自(cin1)"),
    ("qr_j",  "亲人", "简体 亲人"),
    ("qq_j",  "亲切", "简体 亲切"),
    ("fq_j",  "父亲", "简体 父亲"),
    ("fq_f",  "父親", "繁体 父親"),
    # ===== 称 单字（补 v1.42 未测嘅 F1/F2 音色 + 卷舌）=====
    ("c_j",   "称",  "简体 称 单字(补 F1/F2)"),
    ("c_f",   "稱",  "繁体 稱 单字"),
    ("c_a1",  "清",  "cing1 正音锚(齿音c+ing)"),
    ("c_a2",  "秤",  "cing3 正音锚(修正:上版误用趁can3)"),
    ("c_a3",  "卿",  "cing1 锚2"),
    # ===== 含称词：简 vs cing1锚(清) vs cing3锚(秤) 判调 =====
    # 应 cing1
    ("cd_j",  "称帝", "应cing1 称帝"), ("cd_a", "清帝", "锚 清帝(cing1)"), ("cd_b", "秤帝", "锚 秤帝(cing3)"),
    ("ch_j",  "称呼", "应cing1 称呼"), ("ch_a", "清呼", "锚 清呼(cing1)"),
    ("cs_j",  "声称", "应cing1 声称"), ("cs_a", "声清", "锚 声清(cing1)"),
    ("mc_j",  "名称", "应cing1 名称"), ("mc_a", "名清", "锚 名清(cing1)"),
    ("jc_j",  "简称", "应cing1 简称"), ("jc_a", "简清", "锚 简清(cing1)"),
    ("cz_j",  "称赞", "应cing1 称赞"), ("cz_a", "清赞", "锚 清赞(cing1)"),
    ("kc_j",  "堪称", "应cing1 堪称"), ("kc_a", "堪清", "锚 堪清(cing1)"),
    ("cw_j",  "称王", "应cing1 称王"), ("cw_a", "清王", "锚 清王(cing1)"),
    # 应 cing3
    ("dc_j",  "对称", "应cing3 对称"), ("dc_a", "对清", "交叉锚 对清(cing1)"), ("dc_b", "对秤", "锚 对秤(cing3)"),
    ("xc_j",  "相称", "应cing3 相称"), ("xc_b", "相秤", "锚 相秤(cing3)"),
    ("ct_j",  "称职", "应cing3 称职"), ("ct_b", "秤职", "锚 秤职(cing3)"),
]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    if r.returncode or not os.path.exists(mp3):
        print("  GEN_ERR %-7s %s" % (tag, r.stderr.decode("utf-8", "ignore")[:120]))
        return None, None
    return mp3, srt


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", p], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def parse_srt(path):
    if not path or not os.path.exists(path):
        return []
    txt = open(path, encoding="utf-8-sig").read().replace("\r", "")
    blocks = re.split(r"\n\s*\n", txt.strip())
    out = []
    for b in blocks:
        lines = [l for l in b.split("\n") if l.strip() != ""]
        tm = next((l for l in lines if "-->" in l), None)
        if not tm:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", tm)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
        e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
        word = "".join(l for l in lines if "-->" not in l and not l.strip().isdigit()).strip()
        if word:
            out.append((word, s, e))
    return out


def pcm(path):
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-ac", "1", "-ar", str(FS),
                          "-f", "s16le", "-"], capture_output=True).stdout
    n = len(raw) // 2
    return list(struct.unpack("<%dh" % n, raw[: n * 2]))


def goertzel(sig, freq):
    k = 2.0 * math.cos(2.0 * math.pi * freq / FS)
    s1 = s2 = 0.0
    for x in sig:
        s0 = x + k * s1 - s2
        s2, s1 = s1, s0
    return s1 * s1 + s2 * s2 - k * s1 * s2


def f0_of(seg):
    f0s = []
    for st in range(0, max(1, len(seg) - 384), 128):
        fr = seg[st:st + 384]
        if len(fr) < 384:
            break
        mean = sum(fr) / 384
        x = [fr[i] - mean for i in range(384)]
        e0 = sum(v * v for v in x)
        if e0 < 4e5:
            continue
        lo, hi = int(FS / 320.0), int(FS / 70.0)
        best, bestlag = 0.0, 0
        for lag in range(lo, hi + 1):
            sc = sum(x[i] * x[i + lag] for i in range(384 - lag)) / (e0 + 1e-9)
            if sc > best:
                best, bestlag = sc, lag
        if best >= 0.36:
            v = FS / float(bestlag)
            if 70 <= v <= 320:
                f0s.append(v)
    if not f0s:
        return None, None
    sv = sorted(f0s)
    med = sv[len(sv) // 2]
    m = len(f0s)
    k = max(1, m // 3)
    pre = sum(f0s[:k]) / k
    post = sum(f0s[-k:]) / k
    return med, post - pre


def analyze_syl(s, ss, ee):
    a = max(0, int(ss * FS) + int(0.015 * FS))
    b = min(len(s), int(ee * FS) - int(0.015 * FS))
    if b - a < int(0.05 * FS):
        a, b = int(ss * FS), min(len(s), int(ee * FS))
    seg = s[a:b]
    if len(seg) < int(0.04 * FS):
        return None
    N = len(seg)
    win = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (N - 1)) for i in range(N)]
    sig = [seg[i] * win[i] for i in range(N)]
    freqs = list(range(250, 2901, 40))
    E = {f: goertzel(sig, f) for f in freqs}
    f1 = max([f for f in freqs if 250 <= f <= 1100], key=lambda f: E[f])
    f2 = max([f for f in freqs if 1050 <= f <= 2900], key=lambda f: E[f])
    med, slope = f0_of(seg)
    return (f1, f2, med, slope)


def main():
    print("=" * 96)
    print("A) 整词/单字字节碰撞（sz/md5/dur）—— 同音素必同字节")
    print("%-8s %-9s %8s %12s %8s  %s" % ("tag", "文本", "sz", "md5", "dur", "说明"))
    print("-" * 96)
    info = {}
    for tag, text, note in CASES:
        mp3, srt = gen(tag, text)
        if not mp3:
            continue
        sz = os.path.getsize(mp3)
        md = hashlib.md5(open(mp3, "rb").read()).hexdigest()[:10]
        dt = dur(mp3)
        info[tag] = (text, sz, note, srt, mp3, dt)
        print("%-8s %-9s %8d %12s %8.3f  %s" % (tag, text, sz, md, dt, note))

    print()
    print("=" * 96)
    print("B) 逐音节 F0/F1F2 —— 【单字行可信】, 词内行仅参考(切字会飘)")
    print("%-11s %-5s %6s %6s %8s %9s" % ("tag#idx", "字", "F1", "F2", "F0med", "F0slope"))
    print("-" * 96)
    for tag, (text, sz, note, srt, mp3, dt) in info.items():
        s = pcm(mp3)
        sl = parse_srt(srt)
        for j, (ch, ss, ee) in enumerate(sl):
            r = analyze_syl(s, ss, ee)
            if not r:
                print("%-11s %-5s SKIP" % (tag + "#" + str(j), ch))
                continue
            print("%-11s %-5s %6d %6d %8s %9s" %
                  (tag + "#" + str(j), ch, r[0], r[1],
                   ("%d" % r[2]) if r[2] else "n/a",
                   ("%+.0f" % r[3]) if r[3] is not None else "n/a"))

    print()
    print("=" * 96)
    print("C) 判读辅助：目标 vs 锚/反锚 字节差")
    def sz(t): return info[t][1] if t in info else None
    def dt(t): return info[t][5] if t in info else None
    groups = [
        ("渐 单字 j_j", "j_j", ["j_f", "j_b1", "j_b2", "j_b3", "j_b4"]),
        ("渐渐 jj_j", "jj_j", ["jj_f", "jj_b1"]),
        ("逐渐 zj_j", "zj_j", ["zj_f"]),
        ("亲 单字 q_j", "q_j", ["q_f", "q_b1", "q_b2", "q_b3", "q_b4"]),
        ("亲家 qjia_j", "qjia_j", ["qjia_f"]),
        ("亲自 qz_j", "qz_j", ["qz_f", "qz_b1"]),
        ("称 单字 c_j", "c_j", ["c_f", "c_a1", "c_a2", "c_a3"]),
    ]
    for label, tgt, anchors in groups:
        t = sz(tgt)
        if t is None:
            continue
        parts = []
        for a in anchors:
            v = sz(a)
            if v is not None:
                parts.append("%s=%d(%+d)" % (a, v, v - t))
        print("  %-14s sz=%-6d dur=%.2fs | %s" % (label, t, dt(tgt) or 0, " ".join(parts)))

    print()
    print("=" * 96)
    print("D) 单字声学指纹汇总（判据主力）")
    print("%-8s %-5s %6s %6s %8s %9s %8s  %s" %
          ("tag", "字", "F1", "F2", "F0med", "F0slope", "dur", "说明"))
    print("-" * 96)
    for tag in ["j_j", "j_f", "j_b1", "j_b2", "j_b3", "j_b4",
                "q_j", "q_f", "q_b1", "q_b2", "q_b3", "q_b4",
                "c_j", "c_f", "c_a1", "c_a2", "c_a3"]:
        if tag not in info:
            continue
        text, sz_, note, srt, mp3, dt_ = info[tag]
        s = pcm(mp3)
        sl = parse_srt(srt)
        r = analyze_syl(s, sl[0][1], sl[0][2]) if sl else analyze_syl(s, 0, dt_)
        if not r:
            print("%-8s %-5s SKIP" % (tag, text)); continue
        print("%-8s %-5s %6d %6d %8s %9s %8.3f  %s" %
              (tag, text, r[0], r[1],
               ("%d" % r[2]) if r[2] else "n/a",
               ("%+.0f" % r[3]) if r[3] is not None else "n/a", dt_, note))

    print()
    print("=" * 96)
    print("E) 含称词判调：简X vs X清(cing1锚) vs X秤(cing3锚) —— 字节贴边 = 念嗰个调")
    pairs = [
        ("称帝(应1)", "cd_j", "cd_a", "cd_b"),
        ("称呼(应1)", "ch_j", "ch_a", None),
        ("声称(应1)", "cs_j", "cs_a", None),
        ("名称(应1)", "mc_j", "mc_a", None),
        ("简称(应1)", "jc_j", "jc_a", None),
        ("称赞(应1)", "cz_j", "cz_a", None),
        ("堪称(应1)", "kc_j", "kc_a", None),
        ("称王(应1)", "cw_j", "cw_a", None),
        ("对称(应3)", "dc_j", "dc_a", "dc_b"),
        ("相称(应3)", "xc_j", None, "xc_b"),
        ("称职(应3)", "ct_j", None, "ct_b"),
    ]
    print("%-12s %-22s %-22s %s" % ("词", "简体 X", "cing1锚(清)", "cing3锚(秤)"))
    print("-" * 96)
    for label, j, a1, a3 in pairs:
        sj, s1, s3 = sz(j), sz(a1), sz(a3)
        line = "%-12s %-22s " % (label, ("%s=%d" % (info[j][0], sj)) if sj else "n/a")
        line += "%-22s " % (("%s=%d(%+d)" % (info[a1][0], s1, s1 - sj)) if (s1 and sj) else "—")
        line += ("%s=%d(%+d)" % (info[a3][0], s3, s3 - sj)) if (s3 and sj) else "—"
        print(line)
    print("\n=== DONE_44 ===")


if __name__ == "__main__":
    main()
