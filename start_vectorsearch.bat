@echo off
REM ================= サーバー停止処理 =================
echo ========================================
echo VectorSearch System - Startup Script
echo 百人一首ベクトル検索システム（NFT対応版）
echo ========================================
REM 既存のVectorSearchServerウィンドウのpython.exeを停止
for /f "tokens=2 delims==;" %%i in ('tasklist /v /fi "imagename eq python.exe" /fi "windowtitle eq VectorSearchServer*" /fo list ^| find "PID"') do taskkill /F /PID %%i >nul 2>&1
echo 既存のサーバープロセスを停止しました。
echo ========================================

REM Check if app.py exists
if exist "app.py" goto :check_venv
echo ERROR: app.py not found.
echo Please run this batch file in the VectorSearch project root directory.
pause
exit /b 1

:check_venv
REM Check if virtual environment exists
if exist "venv\Scripts\activate.bat" goto :activate_venv
echo ERROR: Virtual environment (venv) not found.
echo Please run 'python -m venv venv' first.
pause
exit /b 1

:activate_venv
REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check required packages
echo Checking required packages...
python -c "import flask, openai, numpy, sklearn, psycopg2" 2>nul
if %errorlevel% equ 0 goto :check_data
echo ERROR: Required packages not installed.
echo Please run 'pip install -r requirements.txt' first.
echo.
echo Installing packages now...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install packages.
    pause
    exit /b 1
)

:check_data
REM Check if database and embedding files exist
echo Checking data files...
if exist "hyakunin_isshu.db" goto :check_embeddings
echo WARNING: Database file not found.
echo Running database initialization...
python init_db.py
if %errorlevel% neq 0 (
    echo ERROR: Database initialization failed.
    echo Please check your OpenAI API key in .env file.
    pause
    exit /b 1
)

:check_embeddings
if exist "embeddings.npy" goto :start_app
echo WARNING: Embedding files not found.
echo Running embedding generation...
python init_db.py
if %errorlevel% neq 0 (
    echo ERROR: Embedding generation failed.
    echo Please check your OpenAI API key in .env file.
    pause
    exit /b 1
)

:start_app
REM Start Flask app
echo Starting Flask application...
echo.
echo ========================================
echo 🎌 百人一首ベクトル検索システム
echo ========================================
echo 🌸 意味検索: 自然言語で歌を検索
echo 🗃️  DB検索: 番号・歌人・歌冒頭で検索
echo 🎨 NFT画像: 各歌に対応する美しいNFT画像
echo 🌊 OpenSea: クリックでNFT詳細ページへ
echo 💰 無料枠対応: 安全な使用量制限
echo ========================================
echo.
start "VectorSearchServer" python app.py

REM Wait for server startup
echo Waiting for server startup...
timeout /t 3 >nul

REM Open browser
echo Opening browser...
start http://localhost:5000

echo ========================================
echo 🎉 Startup Complete!
echo 🌐 Browser opened at http://localhost:5000
echo 🛑 To stop server, close the VectorSearchServer window.
echo ========================================
echo.
echo 💡 Tips:
echo   - 意味検索: 「春の桜」「恋の歌」「秋の月」など
echo   - NFT画像: 検索結果の画像にマウスオーバー
echo   - OpenSea: 画像をクリックでNFT詳細ページへ
echo ======================================== 