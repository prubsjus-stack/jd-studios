# JD Studios - Chat en linea (visitable desde otros dispositivos)
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

# 1) Levantar el servidor local si no esta corriendo
$serverUp = Test-Port $port
if (-not $serverUp) {
  Start-Process powershell -ArgumentList "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$root\chat_serve.ps1`"" -WindowStyle Hidden
  Start-Sleep -Seconds 2
  "SERVIDOR: iniciado $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File "$root\chat.log" -Append -Encoding utf8
} else {
  "SERVIDOR: ya estaba activo $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File "$root\chat.log" -Append -Encoding utf8
}

# 2) Levantar tunel de cloudflared PROPIO (apuntando a este puerto)
$tunnelPidFile = "$root\tunnel.pid"
$pidVivo = $false
if (Test-Path $tunnelPidFile) {
  $tunPid = [int](Get-Content $tunnelPidFile -ErrorAction SilentlyContinue)
  if ($tunPid -and (Get-Process -Id $tunPid -ErrorAction SilentlyContinue)) { $pidVivo = $true }
}
if (-not $pidVivo) {
  Start-Process -FilePath "$root\cloudflared.exe" -ArgumentList "tunnel --url http://localhost:$port --no-autoupdate" -WorkingDirectory $root -RedirectStandardError "$root\tunnel_err.txt" -RedirectStandardOutput "$root\tunnel_out.txt" -WindowStyle Hidden
  Start-Sleep -Seconds 2
  $proc = Get-Process -Name cloudflared -ErrorAction SilentlyContinue | Where-Object { $_.StartTime -gt (Get-Date).AddMinutes(-1) } | Select-Object -Last 1
  if ($proc) { $proc.Id | Set-Content "$root\tunnel.pid" -Encoding utf8 }
  "TUNEL: iniciado $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File "$root\chat.log" -Append -Encoding utf8
} else {
  "TUNEL: ya estaba activo $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File "$root\chat.log" -Append -Encoding utf8
}

# 3) Esperar hasta que cloudflared entregue la URL publica (~30s max)
$publica = $null
for ($i = 0; $i -lt 30; $i++) {
  if (Test-Path "$root\tunnel_err.txt") {
    $linea = Select-String -Path "$root\tunnel_err.txt" -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -Last 1
    if ($linea) {
      $m = [regex]::Match($linea.Line, 'https://[a-z0-9-]+\.trycloudflare\.com')
      $publica = $m.Value
      break
    }
  }
  Start-Sleep -Seconds 1
}

if ($publica) {
  $publica | Set-Content "$root\tunnel_url.txt" -NoNewline -Encoding utf8
}

""
"============================================================"
"  JD Studios - ONLINE"
"  1) Sitio publico:"
if ($publica) {
  "     $publica"
} else {
  "     (espere ~10s y vuelva a abrir este script, o revise tunnel_err.txt)"
}
"  2) Panel admin publico:"
if ($publica) {
  "     $publica/?admin=jdstudios2024"
}
"  3) Local:   http://localhost:$port"
"  4) Local admin:  http://localhost:$port/?admin=jdstudios2024"
"============================================================"
""
"  Envia el enlace publico a quien quieras. Tu abres el"
"  panel admin (punto 2) para recibir los mensajes en vivo."
"  IMPORTANTE: deja este servidor Y el panel abiertos."
"  El enlace trycloudflare cambia en cada reinicio de conexion."
"==========================================================="

# Abrir el panel admin en el navegador
if ($publica) {
  Start-Process "$publica/?admin=jdstudios2024"
}