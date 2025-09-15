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

echo [INFO] Removing inbound firewall for UDP ports 1500 and 1501 (if exists)...
powershell -NoProfile -Command "foreach($p in 1500,1501){ $name=\"UDP$($p)\"; $rule=Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue; if($rule){ Remove-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Out-Null; Write-Output \"[INFO] Firewall rule $name removed.\" } else { Write-Output \"[INFO] Firewall rule $name not found.\" } }"

echo [INFO] Done.
popd
pause



