# JD Studios - Chat en tiempo real
$root = 'C:\JDStudios'
$port = 8000

function Test-Port($port) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', $port)
    $c.Close()
    return $true
  } catch { return $false }
}

$serverUp = Test-Port $port
if (-not $serverUp) {
  Start-Process powershell -ArgumentList "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$root\chat_serve.ps1`"" -WindowStyle Hidden
  Start-Sleep -Seconds 2
  "SERVIDOR CHAT: iniciado $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File "$root\chat.log" -Append -Encoding utf8
} else {
  "SERVIDOR CHAT: ya estaba activo $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File "$root\chat.log" -Append -Encoding utf8
}

# Abrir el sitio (y desbloquear puertos si hace falta)
Start-Process "http://localhost:$port"
$conf = Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "*JDStudios*" }
if (-not $conf) {
  try {
    New-NetFirewallRule -DisplayName "JDStudios-ChitChat" -Direction Inbound -LocalPort $port -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null
  } catch {}
}

""
"================================================"
"  JD Studios - Chat activo"
"  Sitio : http://localhost:$port"
"  Admin : http://localhost:$port/?admin=jdstudios2024"
"  (Mantene esta pestaña/administrador abierta"
"   para recibir los mensajes de los clientes)"
"================================================"