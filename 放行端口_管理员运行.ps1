# ============================================================
# 火火兔自建服务端 —— 放行本机防火墙端口（Windows）
# 必须「以管理员身份运行」，否则规则加不上（会报"拒绝访问"）。
# 用法：右键本文件 -> 使用 PowerShell 运行（管理员）；
#      或在管理员 PowerShell 里：powershell -ExecutionPolicy Bypass -File "本文件完整路径"
#
# 放行端口（WSL mirrored 模式下，容器端口直接绑在 YOUR_SERVER_IP）：
#   1883/tcp  MQTT        —— 玩具连服务端（必需）
#   8082/tcp  音频下载     —— 玩具下载 TTS mp3（必需）
#   8085/udp  语音上传     —— 玩具推实时语音（必需，UDP 最容易漏！）
#   18083/tcp EMQX 控制台  —— 可选，调试用
#   8083/tcp  MQTT over WS —— 可选
# 作用域：仅「专用网络」(Private)。若你把 WLAN 设成了"公用网络"，
#         脚本会同时放行公用，或你把 WLAN 改成专用更安全。
# 回滚：把下面 -Action Allow 改成 -Action Block，或删掉同名规则。
# ============================================================

$ErrorActionPreference = 'Stop'
$rules = @(
    @{ Name = 'FoloToy-MQTT-1883';  Port = 1883;  Proto = 'TCP' },
    @{ Name = 'FoloToy-Audio-8082'; Port = 8082;  Proto = 'TCP' },
    @{ Name = 'FoloToy-Voice-8085'; Port = 8085;  Proto = 'UDP' },
    @{ Name = 'FoloToy-EMQX-18083'; Port = 18083; Proto = 'TCP' },
    @{ Name = 'FoloToy-MQTTWS-8083';Port = 8083;  Proto = 'TCP' }
)

# 权限自检
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[ERROR] 不是管理员权限！请右键 -> 以管理员身份运行。" -ForegroundColor Red
    Write-Host "       或在已提权的 PowerShell 里重新执行本脚本。" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

foreach ($r in $rules) {
    # 先删同名旧规则（幂等，重复跑不会堆积）
    Remove-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
    $profiles = @('Private', 'Public')  # 覆盖专用+公用，避免 WLAN 是 Public 时被拦
    New-NetFirewallRule `
        -DisplayName $r.Name `
        -Direction Inbound `
        -Action Allow `
        -Protocol $r.Proto `
        -LocalPort $r.Port `
        -Profile $profiles `
        -Description "FoloToy 火火兔自建服务端 $($r.Proto) $($r.Port)" | Out-Null
    Write-Host ("[OK] 放行 {0}/{1}  ({2})" -f $r.Proto, $r.Port, $r.Name) -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 当前放行规则 ===" -ForegroundColor Cyan
Get-NetFirewallRule -DisplayName 'FoloToy-*' |
    Get-NetFirewallPortFilter |
    Select-Object @{N='规则';E={$_.InstanceID}}, Protocol, LocalPort | Format-Table -AutoSize

Write-Host "完成。现在火火兔应该能连上 YOUR_SERVER_IP 了。" -ForegroundColor Cyan
Write-Host "（若之后改了 IP，重跑本脚本前请先改 .env 的 PUBLIC_HOST 并重启容器）" -ForegroundColor DarkGray
