# -*- coding: utf-8 -*-
"""v1.37 探针 v6（真实语境定案）：用主人真机原句(带逗号, srt 天然切分)测
「东亚/華夷」喺真实语流里 简体/繁体/换字 三版发音，取代人造载体嘅协同偏差。
真机原句：
  …唔止影响中国，仲影响咗【整个东亚】？
  人同人，【唔分华夷】，只要行得正…
每版合成整句 -> srt 按标点切条 -> 拎含目标词嗰条 -> 切 F1/F2/F0/sz + 整句 md5。
用法(网关容器)：python3 _yue37_probe6.py
"""
import subprocess, os, struct, math, re, hashlib

V, R, D, FS = "zh-HK-HiuMaanNeural", "+20%", "/audio/pron_yue37g", 16000
os.makedirs(D, exist_ok=True)

# (tag, 整句, 要拎嗰条 srt 嘅关键字, 目标词标注)
CASES = [
    # 亚：简体 / 转繁 / 换字(阿) / 换字(啊)
    ("dy_j", "唔止影响中国，仲影响咗整个东亚？", "東亚", "东亚 简"),
    ("dy_f", "唔止影响中国，仲影响咗整个東亞？", "東亞", "東亞 繁"),
    ("dy_a", "唔止影响中国，仲影响咗整个东阿？", "东阿", "东阿 换字"),
    ("dy_a2","唔止影响中国，仲影响咗整个东啊？", "东啊", "东啊 换字"),
    # 亚洲 词首位置
    ("yz_j", "呢个影响，延伸至亚洲各国。", "亚洲", "亚洲 简"),
    ("yz_f", "呢个影响，延伸至亞洲各国。", "亞洲", "亞洲 繁"),
    ("yz_a", "呢个影响，延伸至阿洲各国。", "阿洲", "阿洲 换字"),
    # 华：简体 / 转繁 / 换字对照(嘩/話/化)
    ("hy_j", "人同人，唔分华夷，只要行得正。", "华夷", "华夷 简"),
    ("hy_f", "人同人，唔分華夷，只要行得正。", "華夷", "華夷 繁"),
    ("hy_a", "人同人，唔分嘩夷，只要行得正。", "嘩夷", "嘩夷 换字waa1"),
    ("hy_b", "人同人，唔分化夷，只要行得正。", "化夷", "化夷 反faa3"),
    # 中华
    ("zg_j", "佢话自古皆贵中华，贱夷狄。", "中华", "中华 简"),
    ("zg_f", "佢话自古皆贵中華，贱夷狄。", "中華", "中華 繁"),
    ("zg_a", "佢话自古皆贵中話，贱夷狄。", "中話", "中話 换waa6"),
]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag)
    srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3", "-m", "edge_tts", "--voice", V, "--rate=" + R,
                        "--text", text, "--write-media", mp3, "--write-subtitles", srt],
                       capture_output=True)
    return (mp3, srt) if (not r.returncode and os.path.exists(mp3)) else (None, None)


def parse_srt(path):
    txt = open(path, encoding="utf-8-sig").read().replace("\r", "") if os.path.exists(path) else ""
    out = []
    for b in re.split(r"\n\s*\n", txt.strip()):
        lines = [l for l in b.split("\n") if l.strip() != ""]
        tm = next((l for l in lines if "-->" in l), None)
        if not tm:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", tm)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        s = g[0]*3600+g[1]*60+g[2]+g[3]/1000.0
        e = g[4]*3600+g[5]*60+g[6]+g[7]/1000.0
        word = "".join(l for l in lines if "-->" not in l and not l.strip().isdigit()).strip()
        out.append((word, s, e))
    return out


def pcm(path):
    raw = subprocess.run(["ffmpeg", "-v","quiet","-i",path,"-ac","1","-ar",str(FS),
                          "-f","s16le","-"], capture_output=True).stdout
    n = len(raw)//2
    return list(struct.unpack("<%dh" % n, raw[:n*2]))


def feat(seg):
    if len(seg) < int(0.03*FS):
        return None
    N = len(seg)
    win = [0.5-0.5*math.cos(2*math.pi*i/(N-1)) for i in range(N)]
    x = [seg[i]*win[i] for i in range(N)]
    freqs = list(range(250,2901,40))
    def gz(freq):
        kk = 2.0*math.cos(2*math.pi*freq/FS); s1=s2=0.0
        for v in x:
            s0=v+kk*s1-s2; s2,s1=s1,s0
        return s1*s1+s2*s2-kk*s1*s2
    E = {f:gz(f) for f in freqs}
    f1 = max([f for f in freqs if 250<=f<=1100], key=lambda f:E[f])
    f2 = max([f for f in freqs if 1050<=f<=2900], key=lambda f:E[f])
    f0s=[]
    for st in range(0,max(1,len(seg)-320),96):
        fr=seg[st:st+320]
        if len(fr)<320: break
        mean=sum(fr)/320; y=[fr[i]-mean for i in range(320)]
        e0=sum(v*v for v in y)
        if e0<2e5: continue
        lo,hi=int(FS/320),int(FS/75); bs,bl=0.0,0
        for lag in range(lo,hi+1):
            sc=sum(y[i]*y[i+lag] for i in range(320-lag))/(e0+1e-9)
            if sc>bs: bs,bl=sc,lag
        if bs>=0.32:
            v=FS/float(bl)
            if 75<=v<=320: f0s.append(v)
    f0=int(sorted(f0s)[len(f0s)//2]) if f0s else None
    return (f1,f2,f0,int(len(seg)/float(FS)*1000))


def main():
    print("="*86)
    print("真实语境(srt按逗号切条) 目标词 F1 F2 F0 dur + 整句md8")
    print("%-7s %-13s %-16s %-8s %s" % ("tag","标注","目标词 F1F2F0dur","整句md8","srt切条"))
    print("-"*86)
    for tag, sent, key, note in CASES:
        mp3, srt = gen(tag, sent)
        if not mp3:
            print("%-7s GEN_ERR" % tag); continue
        sl = parse_srt(srt)
        s = pcm(mp3)
        md8 = hashlib.md5(open(mp3,"rb").read()).hexdigest()[:8]
        # 拎含关键字嗰条
        hit = next((x for x in sl if key in x[0]), None)
        if hit:
            ss, ee = hit[1], hit[2]
        else:
            # 退化：打印所有条目，用整词近似
            ss, ee = 0.0, len(s)/float(FS)
        a=max(0,int(ss*FS)+int(0.008*FS)); b=min(len(s),int(ee*FS)-int(0.008*FS))
        r=feat(s[a:b])
        srttxt=" | ".join("%s[%.1f-%.1f]" % (w,s2,e2) for w,s2,e2 in sl)
        print("%-7s %-13s %-16s %-8s %s" %
              (tag, note, ("%4d/%4d/%3s/%3dms"%(r[0],r[1],r[2] if r[2] else "--",r[3])) if r else " -- ",
               md8, srttxt[:54]))
    print("=== DONE ===")


if __name__ == "__main__":
    main()
