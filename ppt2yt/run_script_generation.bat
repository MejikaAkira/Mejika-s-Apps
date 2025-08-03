@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo PPTX to YouTube 動画自動生成システム
echo スクリプト生成実行バッチ
echo ========================================

:: 現在のディレクトリを保存
set CURRENT_DIR=%CD%

:: 1. ローカルポートの停止（8080ポート）
echo.
echo [1/6] ローカルポート8080の停止を確認中...
netstat -ano | findstr :8080 >nul
if %errorlevel% equ 0 (
    echo ポート8080が使用中です。停止を試行します...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080') do (
        taskkill /PID %%a /F >nul 2>&1
        echo PID %%a を停止しました。
    )
) else (
    echo ポート8080は使用されていません。
)

:: 2. 仮想環境の確認と作成
echo.
echo [2/6] 仮想環境の確認中...
if not exist "venv" (
    echo 仮想環境が見つかりません。作成します...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo エラー: 仮想環境の作成に失敗しました。
        echo Pythonがインストールされているか確認してください。
        pause
        exit /b 1
    )
    echo 仮想環境を作成しました。
) else (
    echo 仮想環境が見つかりました。
)

:: 3. 仮想環境のアクティベート
echo.
echo [3/6] 仮想環境をアクティベート中...
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo エラー: 仮想環境のアクティベートに失敗しました。
    pause
    exit /b 1
)
echo 仮想環境をアクティベートしました。

:: 4. 依存パッケージのインストール
echo.
echo [4/6] 依存パッケージをインストール中...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo エラー: 依存パッケージのインストールに失敗しました。
    pause
    exit /b 1
)
echo 依存パッケージのインストールが完了しました。

:: 5. 設定ファイルの確認
echo.
echo [5/6] 設定ファイルを確認中...
if not exist ".env" (
    echo 警告: .envファイルが見つかりません。
    echo env.exampleをコピーして.envファイルを作成してください。
    echo その後、APIキーを設定してください。
    echo.
    echo 設定例:
    echo OPENAI_API_KEY=your_openai_api_key_here
    echo YOUTUBE_CLIENT_ID=your_youtube_client_id_here
    echo YOUTUBE_CLIENT_SECRET=your_youtube_client_secret_here
    echo.
    pause
    exit /b 1
)

:: 6. スクリプト生成の実行
echo.
echo [6/6] スクリプト生成を実行中...
echo.

:: 入力ファイルの確認
if not exist "input" (
    echo inputディレクトリを作成します...
    mkdir input
    echo inputディレクトリにPPTXファイルを配置してください。
    pause
    exit /b 1
)

:: PPTXファイルの確認
set PPTX_FOUND=0
for %%f in (input\*.pptx) do (
    set PPTX_FOUND=1
    echo 見つかったPPTXファイル: %%f
)

if %PPTX_FOUND% equ 0 (
    echo エラー: inputディレクトリにPPTXファイルが見つかりません。
    echo inputディレクトリにPPTXファイルを配置してください。
    pause
    exit /b 1
)

:: 最初のPPTXファイルを処理
for %%f in (input\*.pptx) do (
    echo.
    echo 処理開始: %%f
    python main.py "%%f" --validate-only
    if %errorlevel% neq 0 (
        echo エラー: 設定の検証に失敗しました。
        pause
        exit /b 1
    )
    
    echo 設定検証が完了しました。スクリプト生成を開始します...
    python main.py "%%f"
    if %errorlevel% neq 0 (
        echo エラー: スクリプト生成に失敗しました。
        pause
        exit /b 1
    )
    
    echo.
    echo ========================================
    echo スクリプト生成が完了しました！
    echo ========================================
    echo.
    echo 生成されたファイル:
    echo - output/scripts/%%~nf_script.json
    echo.
    echo 次のステップ:
    echo 1. 生成された台本を確認
    echo 2. 必要に応じて台本を編集
    echo 3. 画像処理モジュールを実装
    echo.
    goto :end
)

:end
echo.
echo 処理が完了しました。
echo 仮想環境を終了します...
deactivate
echo.
pause 