# ============================================================
# 火火兔自建服务端 —— 放行本机防火墙端口（双击自动提权）
# 直接双击本文件即可：会弹出 UAC 窗口，点「是」自动以管理员运行。
#
# 放行端口（WSL mirrored 模式，容器端口绑在 YOUR_SERVER_IP）：
#   1883/tcp  MQTT        —— 玩具连服务端（必需）
#   8082/tcp  音频下载     —— 玩具下载 TTS mp3（必需）
#   8085/udp  语音上传     —— 玩具推实时语音（必需，UDP 最容易漏）
#   18083/tcp EMQX 控制台  —— 可选，调试用
#   8083/tcp  MQTT over WS —— 可选
# 作用域：专用 + 公用（当前 WLAN 是 Public，必须覆盖）
#
# 回滚（管理员 PowerShell）：
#   Get-NetFirewallRule -DisplayName 'FoloToy-*' | Remove-NetFirewallRule
# ============================================================

# ---- 自提权：不是管理员就重启自己并请求 UAC ----
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    try {
        Start-Process -FilePath "powershell.exe" `
            -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$($MyInvocation.MyCommand.Path)`"" `
            -Verb RunAs
        Write-Host "已请求管理员权限，请在弹出的 UAC 窗口点「是」。" -ForegroundColor Yellow
    } catch {
        Write-Host "[ERROR] 自动提权失败，请右键 -> 以管理员身份运行。" -ForegroundColor Red
    }
    exit 0
}

$ErrorActionPreference = 'Stop'
$rules = @(
    @{ Name = 'FoloToy-MQTT-1883';  Port = 1883;  Proto = 'TCP' },
    @{ Name = 'FoloToy-Audio-8082'; Port = 8082;  Proto = 'TCP' },
    @{ Name = 'FoloToy-Voice-8085'; Port = 8085;  Proto = 'UDP' },
    @{ Name = 'FoloToy-EMQX-18083'; Port = 18083; Proto = 'TCP' },
    @{ Name = 'FoloToy-MQTTWS-8083';Port = 8083;  Proto = 'TCP' }
)

foreach ($r in $rules) {
    Remove-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
    New-NetFirewallRule `
        -DisplayName $r.Name `
        -Direction Inbound `
        -Action Allow `
        -Protocol $r.Proto `
        -LocalPort $r.Port `
        -Profile @('Private', 'Public') `
        -Description "FoloToy 火火兔自建服务端 $($r.Proto) $($r.Port)" | Out-Null
    Write-Host ("[OK] 放行 {0}/{1}  ({2})" -f $r.Proto, $r.Port, $r.Name) -ForegroundColor Green
}

Write-Host ""
Write-Host "=== 已生效的 FoloToy 放行规则 ===" -ForegroundColor Cyan
Get-NetFirewallRule -DisplayName 'FoloToy-*' | ForEach-Object {
    $pf = $_ | Get-NetFirewallPortFilter
    "{0,-22} {1,-5} {2,-6} {3}" -f $_.DisplayName, $pf.Protocol, $pf.LocalPort, ($(if($_.Enabled){'启用'}else{'禁用'}))
}

Write-Host ""
Write-Host "===== 现在验证本机端口是否放行成功 =====" -ForegroundColor Cyan
foreach ($p in @(1883, 8082, 18083)) {
    $r = Test-NetConnection -ComputerName YOUR_SERVER_IP -Port $p -InformationLevel Quiet -WarningAction SilentlyContinue 2>$null
    Write-Host ("  YOUR_SERVER_IP:{0} -> {1}" -f $p, $(if($r){'通 ✅'}else{'不通 ❌'})) -ForegroundColor $(if($r){'Green'}else{'Red'})
}
# UDP 无法用 Test-NetConnection 测，用 check_server.py 或实际对话验证

Write-Host ""
Write-Host "完成。TCP 若显示「通」，就把火火兔开机，我来切 broker 并联调。" -ForegroundColor Cyan
Write-Host "（按任意键关闭）" -ForegroundColor DarkGray
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
