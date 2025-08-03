@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo PPTX to YouTube 動画自動生成システム
echo 環境設定バッチ
echo ========================================

:: 1. 必要なディレクトリの作成
echo.
echo [1/4] 必要なディレクトリを作成中...
if not exist "input" (
    mkdir input
    echo inputディレクトリを作成しました。
) else (
    echo inputディレクトリは既に存在します。
)

if not exist "output" (
    mkdir output
    echo outputディレクトリを作成しました。
) else (
    echo outputディレクトリは既に存在します。
)

if not exist "logs" (
    mkdir logs
    echo logsディレクトリを作成しました。
) else (
    echo logsディレクトリは既に存在します。
)

:: 2. .envファイルの確認と作成
echo.
echo [2/4] .envファイルを確認中...
if not exist ".env" (
    if exist "env.example" (
        echo .envファイルが見つかりません。env.exampleからコピーします...
        copy env.example .env >nul
        echo .envファイルを作成しました。
        echo.
        echo ========================================
        echo 重要: .envファイルを編集してください
        echo ========================================
        echo.
        echo 以下のAPIキーを設定してください:
        echo.
        echo 1. OpenAI APIキー
        echo    - https://platform.openai.com/ にアクセス
        echo    - APIキーを生成
        echo    - .envファイルの OPENAI_API_KEY= を編集
        echo.
        echo 2. YouTube API設定
        echo    - https://console.cloud.google.com/ にアクセス
        echo    - プロジェクトを作成
        echo    - YouTube Data API v3を有効化
        echo    - OAuth 2.0クライアントIDを作成
        echo    - .envファイルの YOUTUBE_CLIENT_ID= と YOUTUBE_CLIENT_SECRET= を編集
        echo.
        echo 設定完了後、run_script_generation.bat を実行してください。
        echo.
        pause
        exit /b 0
    ) else (
        echo エラー: env.exampleファイルが見つかりません。
        pause
        exit /b 1
    )
) else (
    echo .envファイルは既に存在します。
)

:: 3. Python環境の確認
echo.
echo [3/4] Python環境を確認中...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo エラー: Pythonがインストールされていません。
    echo https://www.python.org/downloads/ からPythonをダウンロードしてください。
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Python %PYTHON_VERSION% がインストールされています。

:: 4. FFmpegの確認
echo.
echo [4/4] FFmpegを確認中...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo 警告: FFmpegがインストールされていません。
    echo 動画処理機能を使用するにはFFmpegが必要です。
    echo.
    echo インストール方法:
    echo Windows: https://ffmpeg.org/download.html
    echo または: choco install ffmpeg
    echo.
    echo 現在はスクリプト生成のみ実行可能です。
) else (
    echo FFmpegがインストールされています。
)

echo.
echo ========================================
echo 環境設定が完了しました！
echo ========================================
echo.
echo 次のステップ:
echo 1. .envファイルにAPIキーを設定
echo 2. inputディレクトリにPPTXファイルを配置
echo 3. run_script_generation.bat を実行
echo.
pause 