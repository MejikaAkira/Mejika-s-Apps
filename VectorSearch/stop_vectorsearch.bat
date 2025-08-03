@echo off
echo ========================================
echo VectorSearch System - Stop Script
echo 百人一首ベクトル検索システム - 停止スクリプト
echo ========================================

REM 既存のVectorSearchServerウィンドウのpython.exeを停止
for /f "tokens=2 delims==;" %%i in ('tasklist /v /fi "imagename eq python.exe" /fi "windowtitle eq VectorSearchServer*" /fo list ^| find "PID"') do (
    echo Stopping process PID: %%i
    taskkill /F /PID %%i >nul 2>&1
)

echo ========================================
echo ✅ VectorSearch server stopped successfully.
echo 🎌 百人一首ベクトル検索システムを停止しました。
echo ========================================
pause 