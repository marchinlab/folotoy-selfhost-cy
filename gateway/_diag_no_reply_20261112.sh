#!/usr/bin/env bash
# v1.39 之后「对话没反应」只读诊断：查 EMQX broker 活性 + 设备在线 + 端口连通
# 不重启、不推播、不改任何配置
echo "=== 1. EMQX INSPECT ==="
docker inspect folotoy_emqx_1 --format 'Status={{.State.Status}} Restart={{.RestartCount}} StartedAt={{.State.StartedAt}} ExitCode={{.State.ExitCode}}' 2>&1
echo "=== 2. CONTAINER STATS (cpu/mem) ==="
docker stats --no-stream --format '{{.Name}} CPU={{.CPUPerc}} MEM={{.MemUsage}}' folotoy_emqx_1 folotoy_folotoy_1 folotoy_llm_gateway_1 2>&1
echo "=== 3. EMQX PORT MAP ==="
docker port folotoy_emqx_1 2>&1
echo "=== 4. EMQX LOG last 3h (connect/disconnect/client/error) ==="
docker logs --since 3h folotoy_emqx_1 2>&1 | grep -iE 'a0a3|connect|disconnect|client|error|panic|stopping|started|node' | tail -40
echo "=== 5. EMQX HTTP API health ==="
curl -s -m 5 http://127.0.0.1:18083/api/v4/health_check 2>&1 | head -c 400
echo ""
echo "=== 6. EMQX HTTP API online clients (admin/public) ==="
curl -s -m 5 -u admin:public http://127.0.0.1:18083/api/v4/clients 2>&1 | head -c 1000
echo ""
echo "=== 7. MQTT CONNACK from brain container (proves broker alive) ==="
docker exec folotoy_folotoy_1 python3 -c "
import socket,struct
try:
    s=socket.create_connection(('emqx',1883),timeout=5)
    payload=struct.pack('!H',4)+b'MQTT'+bytes([4,2,0,10])+struct.pack('!H',5)+b'diag01'
    s.sendall(bytes([0x10,len(payload)])+payload)
    r=s.recv(4)
    print('CONNACK=',r.hex(),'(expect 20020000 = accepted)')
    s.close()
except Exception as e:
    print('MQTT_CONNECT_ERR',type(e).__name__,str(e)[:100])
" 2>&1
echo "=== 8. BRAIN-UDP 8085 listening ==="
docker exec folotoy_folotoy_1 sh -c "(netstat -lunp 2>/dev/null || ss -lunp 2>/dev/null) | grep 8085 || echo NO_UDP_LISTEN_INFO" 2>&1
echo "=== 9. BRAIN last 5m FULL ==="
docker logs --since 5m folotoy_folotoy_1 2>&1 | tail -25
echo "=== 10. GW last 5m FULL ==="
docker logs --since 5m folotoy_llm_gateway_1 2>&1 | tail -18
echo "=== DONE ==="
