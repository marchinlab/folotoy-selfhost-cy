#!/usr/bin/env bash
# ============================================================
# 火火兔自建服务端 —— 一键联调自检（在 WSL 里以 root 跑）
# 用法: wsl.exe -d Ubuntu-22.04 -u root -- bash /opt/folotoy/联调自检.sh
# 检查: 容器状态 / edge-tts 版本 / 7 音色 / MQTT 握手 / 服务日志报错
# ============================================================
set -u
C=folotoy_folotoy_1
D=/opt/folotoy
G='\033[0;32m'; R='\033[0;31m'; Y='\033[0;33m'; N='\033[0m'
ok(){ echo -e "${G}[PASS]${N} $*"; }
bad(){ echo -e "${R}[FAIL]${N} $*"; }
warn(){ echo -e "${Y}[WARN]${N} $*"; }

echo "===== 1. 容器状态 ====="
docker ps -a --filter name=folotoy_ --format '{{.Names}} | {{.Status}} | {{.Image}}'

echo; echo "===== 2. 三容器是否 Up ====="
for x in emqx nginx folotoy; do
  st=$(docker ps --filter "name=folotoy_${x}_1" --format '{{.Status}}')
  [ -n "$st" ] && ok "$x: $st" || bad "$x 没在跑 -> cd $D && docker-compose up -d"
done

echo; echo "===== 3. edge-tts 版本（须 >= 7.x，6.x 会 403） ====="
v=$(docker exec $C python3 -c 'import edge_tts;print(edge_tts.__version__)' 2>/dev/null)
echo "  edge-tts = $v"
case "$v" in 6.*) bad "旧版会 403 -> 重建: cd $D/build-tts && docker-compose -f $D/docker-compose.yml up -d --force-recreate folotoy";; *) ok "版本 OK";; esac

echo; echo "===== 4. 7 个角色音色逐个合成 ====="
docker exec $C python3 -c '
import json,edge_tts,asyncio,os,re
raw=open("/config/roles.json").read()
vs=[]
for v in re.findall(r"\"voice_name\"\s*:\s*\"([^\"]+)\"",raw):
    v=v.strip()
    if v and v not in vs: vs.append(v)
async def m():
    for v in vs:
        try:
            f="/tmp/_"+v+".mp3"; await edge_tts.Communicate("测试",v).save(f)
            print("  OK   %-30s %d B"%(v,os.path.getsize(f)))
        except Exception as e:
            print("  FAIL %-30s %s"%(v,str(e)[:70]))
asyncio.run(m())
'

echo; echo "===== 5. MQTT 1883 握手（容器内 -> emqx） ====="
docker exec $C python3 -c '
import socket,struct
try:
    s=socket.create_connection(("emqx",1883),3); cid=b"probe"
    v=b"\x00\x04MQTT\x04\x02\x00\x3c"+struct.pack("!H",len(cid))+cid
    s.sendall(b"\x10"+bytes([len(v)])+v); d=s.recv(4); s.close()
    print("  CONNACK code=",d[3],"->", "OK" if len(d)>=4 and d[0]==0x20 and d[3]==0 else "FAIL")
except Exception as e: print("  FAIL",e)
'

echo; echo "===== 6. 服务日志最近报错 ====="
err=$(docker logs --since 10m $C 2>&1 | grep -Ei 'Text to sound failed|403|ERROR' | tail -10)
if [ -z "$err" ]; then ok "近 10 分钟无 TTS/ERROR"; else echo -e "${R}$err${N}"; fi

echo; echo "===== 7. 玩具当前 broker（在 Windows 侧单独跑） ====="
echo "  python switch_broker.py --port COM6 --host YOUR_SERVER_IP --dry-run"
echo "  应显示 mqtt.broker=YOUR_SERVER_IP 且 udpSpeechServer.address=YOUR_SERVER_IP"

echo; echo "===== 完成 ====="
echo "真·端到端：按玩具对话键说一句，然后看: wsl -u root -- docker logs -f folotoy_folotoy_1"
echo "应见音频落盘、无 'Text to sound failed'。回滚设备: python switch_broker.py --rollback"
