# ============================================================
# FoloToy self-host server - allow inbound ports (mirrored mode)
# Run as ADMIN. Two firewall layers must be opened in WSL mirrored:
#   1) Windows Defender firewall  (localhost / general)
#   2) Hyper-V firewall for WSL VMCreator  (PHYSICAL LAN ip inbound)
# Without layer 2, LAN devices get TIMEOUT on YOUR_SERVER_IP.
# ============================================================
$ErrorActionPreference = 'Stop'

$rules = @(
    @{ Name = 'FoloToy-MQTT-1883';   Port = 1883;  Proto = 'TCP' },
    @{ Name = 'FoloToy-Audio-8082';  Port = 8082;  Proto = 'TCP' },
    @{ Name = 'FoloToy-Voice-8085';  Port = 8085;  Proto = 'UDP' },
    @{ Name = 'FoloToy-EMQX-18083';  Port = 18083; Proto = 'TCP' },
    @{ Name = 'FoloToy-MQTTWS-8083'; Port = 8083;  Proto = 'TCP' }
)

Write-Host "=== Layer 1/2: Windows Defender firewall ===" -ForegroundColor Cyan
foreach ($r in $rules) {
    Remove-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $r.Name -Direction Inbound -Action Allow `
        -Protocol $r.Proto -LocalPort $r.Port -Profile @('Private', 'Public') `
        -Description "FoloToy self-host server $($r.Proto) $($r.Port)" | Out-Null
    Write-Host ("  [OK] {0}/{1}  ({2})" -f $r.Proto, $r.Port, $r.Name) -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Layer 2/2: Hyper-V firewall (WSL VMCreator) ===" -ForegroundColor Cyan
$vm = (Get-NetFirewallHyperVVMCreator).VMCreatorId
if (-not $vm) {
    Write-Host "  [WARN] No WSL VMCreator found; skip Hyper-V layer." -ForegroundColor Yellow
} else {
    Write-Host ("  WSL VMCreatorId = {0}" -f $vm) -ForegroundColor DarkGray
    foreach ($r in $rules) {
        $hvName = 'FoloToy-HV-' + $r.Port
        Remove-NetFirewallHyperVRule -Name $hvName -ErrorAction SilentlyContinue
        New-NetFirewallHyperVRule -Name $hvName -DisplayName $hvName `
            -Direction Inbound -VMCreatorId $vm -Protocol $r.Proto `
            -LocalPorts ([string]$r.Port) -Action Allow -Enabled True | Out-Null
        Write-Host ("  [OK] {0}/{1}  ({2})" -f $r.Proto, $r.Port, $hvName) -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "=== Active Hyper-V firewall rules ===" -ForegroundColor Cyan
Get-NetFirewallHyperVRule -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'FoloToy-HV-*' } | ForEach-Object {
    "  {0,-20} {1,-6} {2}" -f $_.Name, $_.Protocol, $_.LocalPorts
}

Write-Host ""
Write-Host "=== Verify TCP from this PC to YOUR_SERVER_IP ===" -ForegroundColor Cyan
foreach ($p in @(1883, 8082, 18083)) {
    $c = New-Object Net.Sockets.TcpClient
    try {
        $iar = $c.BeginConnect('YOUR_SERVER_IP', $p, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(2000)) { $c.EndConnect($iar); $ok = $true } else { $ok = $false }
    } catch { $ok = $false } finally { $c.Close() }
    Write-Host ("  YOUR_SERVER_IP:{0} -> {1}" -f $p, $(if ($ok) { 'OPEN (OK)' } else { 'CLOSED/TIMEOUT' })) -ForegroundColor $(if ($ok) { 'Green' } else { 'Red' })
}

Write-Host ""
Write-Host "UDP 8085 is UDP; cannot be tested by TCP connect. Verify by actual toy voice." -ForegroundColor DarkGray
Write-Host "If 1883 and 8082 show OPEN, tell the assistant - it will switch the toy's broker." -ForegroundColor Yellow
Write-Host "(Press any key to close)"
try { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') } catch { Start-Sleep -Seconds 20 }
