# -*- coding: utf-8 -*-
"""v1.37 高频字批量筛查(并行·定案)：从生产真实语料挖出嘅高频高风险字，用
v4 唯一可信口径「嘅X嘅」(srt 真切三条、目标字节独立)逐个测 简体/繁体 F1/F2。
只采信 srt==3 条嘅字；简繁同形跳过。目的：揪出【简繁F2差>300】= 似 v1.32 儿/时
咁「转繁真会改音」嘅漏网字；差<160 = 简繁同音(转繁无效,同亚/华)。
并行 6 workers 避串行超时。用法(网关容器)：python3 _yue37_scan3.py
"""
import subprocess, os, struct, math, re
from concurrent.futures import ThreadPoolExecutor

V, R, D, FS = "zh-HK-HiuMaanNeural", "+20%", "/audio/pron_yue37h", 16000
os.makedirs(D, exist_ok=True)
C = "嘅"

# (简, 繁, 频次, 普通话声母类) —— 语料挖掘 top，简繁不同形、频次>=5
PAIRS = [
    ("系","係",179,"j"),("学","學",31,"x"),("制","制",34,"zh"),("强","強",21,"q"),
    ("权","權",20,"q"),("书","書",18,"sh"),("几","幾",11,"j"),("晋","晉",10,"j"),
    ("据","據",10,"j"),("节","節",10,"j"),("诗","詩",10,"sh"),("稳","穩",9,"w"),
    ("记","記",9,"j"),("传","傳",9,"ch"),("结","結",9,"j"),("鲜","鮮",8,"x"),
    ("紧","緊",8,"j"),("场","場",7,"ch"),("气","氣",7,"q"),("树","樹",7,"sh"),
    ("集","集",7,"j"),("写","寫",7,"x"),("游","遊",6,"y"),("虽","雖",6,"s"),
    ("问","問",6,"w"),("错","錯",6,"c"),("照","照",6,"zh"),("望","望",6,"w"),
    ("创","創",6,"ch"),("镜","鏡",6,"j"),("现","現",5,"x"),("祖","祖",5,"z"),
    ("充","充",5,"ch"),("着","著",5,"zh"),("处","處",5,"ch"),("远","遠",5,"y"),
    ("乐","樂",5,"y"),("运","運",5,"y"),("精","精",5,"j"),
    # 补一批 v1 单字阶段有差、值得用可信口径复核嘅
    ("车","車",0,"ch"),("识","識",0,"sh"),("说","說",0,"sh"),("计","計",0,"j"),
    ("长","長",0,"ch"),("种","種",0,"zh"),("进","進",0,"j"),("声","聲",0,"sh"),
    ("东","東",0,"d"),("为","為",0,"w"),("举","舉",0,"j"),("万","萬",0,"w"),
    ("转","轉",0,"zh"),("经","經",0,"j"),("讲","講",0,"j"),("无","無",0,"w"),
    ("众","眾",0,"zh"),("终","終",0,"zh"),("亚","亞",0,"y"),("华","華",0,"h"),
]


def gen(tag, text):
    mp3 = "%s/%s.mp3" % (D, tag); srt = "%s/%s.srt" % (D, tag)
    r = subprocess.run(["python3","-m","edge_tts","--voice",V,"--rate="+R,
                        "--text",text,"--write-media",mp3,"--write-subtitles",srt],
                       capture_output=True)
    return (mp3, srt) if (not r.returncode and os.path.exists(mp3)) else (None, None)


def srt_ranges(path):
    txt = open(path, encoding="utf-8-sig").read().replace("\r","") if os.path.exists(path) else ""
    out = []
    for b in re.split(r"\n\s*\n", txt.strip()):
        lines = [l for l in b.split("\n") if l.strip()!=""]
        tm = next((l for l in lines if "-->" in l), None)
        if not tm: continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", tm)
        if not m: continue
        g=[int(x) for x in m.groups()]
        out.append((g[0]*3600+g[1]*60+g[2]+g[3]/1000.0,
                    g[4]*3600+g[5]*60+g[6]+g[7]/1000.0))
    return out


def pcm(path):
    raw = subprocess.run(["ffmpeg","-v","quiet","-i",path,"-ac","1","-ar",str(FS),
                          "-f","s16le","-"], capture_output=True).stdout
    n=len(raw)//2
    return list(struct.unpack("<%dh" % n, raw[:n*2]))


def feat(seg):
    if len(seg) < int(0.03*FS): return None
    N=len(seg); win=[0.5-0.5*math.cos(2*math.pi*i/(N-1)) for i in range(N)]
    x=[seg[i]*win[i] for i in range(N)]; freqs=list(range(250,2901,40))
    def gz(freq):
        kk=2.0*math.cos(2*math.pi*freq/FS); s1=s2=0.0
        for v in x:
            s0=v+kk*s1-s2; s2,s1=s1,s0
        return s1*s1+s2*s2-kk*s1*s2
    E={f:gz(f) for f in freqs}
    return (max([f for f in freqs if 250<=f<=1100],key=lambda f:E[f]),
            max([f for f in freqs if 1050<=f<=2900],key=lambda f:E[f]))


def mid(ch, tag):
    mp3, srt = gen(tag, C+ch+C)
    if not mp3: return None, 0
    sl = srt_ranges(srt); s = pcm(mp3)
    if len(sl) >= 3:
        ss, ee = sl[1][1], sl[1][2]; n = 3
    else:
        tot=len(s)/float(FS); ss,ee=tot/3.0,2*tot/3.0; n=len(sl)
    a=max(0,int(ss*FS)+int(0.006*FS)); b=min(len(s),int(ee*FS)-int(0.006*FS))
    return feat(s[a:b]), n


def one(i_pair):
    i,(j,f,n,cls)=i_pair
    fj,nj=mid(j,"j%d"%i)
    ff,nf=mid(f,"f%d"%i)
    if not fj or not ff: return None
    return (j,f,n,cls,fj[0],fj[1],ff[0],ff[1],min(nj,nf),abs(fj[1]-ff[1]))


def main():
    jobs=[(i,p) for i,p in enumerate(PAIRS) if p[0]!=p[1]]
    skip=[p for p in PAIRS if p[0]==p[1]]
    rows=[]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(one, jobs):
            if r: rows.append(r)
    ok=[r for r in rows if r[8]==3]       # srt 真三条,口径可信
    weak=[r for r in rows if r[8]!=3]     # 口径弱
    print("="*80)
    print("简繁同形跳过 %d 字 | 合成成功 %d | srt真三条(可信) %d | srt口径弱 %d" %
          (len(skip), len(rows), len(ok), len(weak)))
    print()
    print("【可信口径】按 |简繁F2差| 降序 (差>300=转繁真改音,疑漏网; <160=简繁同音,转繁无效)")
    print("%-3s %-3s %-4s %-3s | 简F1/F2 | 繁F1/F2 | dF2 | 判读" % ("简","繁","频","类"))
    print("-"*80)
    for j,f,n,cls,j1,j2,f1,f2,nn,ad2 in sorted(ok,key=lambda x:-x[9]):
        note = "★转繁改音(疑漏网,需深挖)" if ad2>300 else \
               ("小差" if ad2>=160 else "简繁同音(转繁无效)")
        print("%-3s %-3s %-4d %-3s | %4d/%4d | %4d/%4d | %+4d | %s" %
              (j,f,n,cls,j1,j2,f1,f2,j2-f2,note))
    print()
    print("【srt口径弱,仅参考(不足3条)】%d字: %s" % (len(weak), " ".join(r[0]+"/"+r[1] for r in weak)))
    print("=== DONE ===")


if __name__=="__main__":
    main()
