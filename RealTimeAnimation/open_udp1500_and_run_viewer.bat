@echo off
setlocal enabledelayedexpansion

rem Change to script directory
pushd "%~dp0"

echo [INFO] Checking admin rights...
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] 管理者権限で実行してください（右クリック→管理者として実行）
  pause
  popd
  exit /b 1
)

echo [INFO] Opening inbound firewall for UDP ports 1500 and 1501 (if needed)...
powershell -NoProfile -Command "foreach($p in 1500,1501){ $name=\"UDP$($p)\"; if(Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue){ Write-Output \"[INFO] Firewall rule $name already exists.\" } else { New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol UDP -LocalPort $p -Action Allow | Out-Null; Write-Output \"[INFO] Firewall rule $name created.\" } }"

echo [INFO] Checking and freeing UDP ports 1500/1501 before launch...
powershell -NoProfile -Command "foreach($p in 1500,1501){ $eps = Get-NetUDPEndpoint -LocalPort $p -ErrorAction SilentlyContinue; if($eps){ $pids = $eps | Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique; foreach($pid in $pids){ try{ $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue; $name = if($proc){ $proc.ProcessName } else { 'unknown' }; Write-Output \"[INFO] UDP $p in use by PID $pid ($name). Killing...\"; Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 150 } catch {} } } else { Write-Output \"[INFO] UDP $p is free.\" } }"

echo [INFO] Checking existing viewer_pyqtgraph_fixed.py processes...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'viewer_pyqtgraph_fixed.py' } | ForEach-Object { Write-Output \"[INFO] Existing viewer found (PID $($_.ProcessId)). Killing...\"; Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 150 }"

echo [INFO] Starting viewer_pyqtgraph_fixed.py...
if exist "venv\Scripts\python.exe" (
  call "venv\Scripts\activate.bat"
  python viewer_pyqtgraph_fixed.py
) else (
  python viewer_pyqtgraph_fixed.py
)

popd
pause


