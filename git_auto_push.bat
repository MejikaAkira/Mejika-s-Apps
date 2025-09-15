@echo off
REM === GitHub push automation script ===

REM 依存: PowerShell が必要（YAMLを読むため）
REM 引数なしで実行する

echo [INFO] Loading config from GitHub_push_config.yaml...

REM PowerShell を使って YAML を読み込む
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command ^
    "try {
        $y = Get-Content -Raw 'GitHub_push_config.yaml' | ConvertFrom-Yaml;
        Write-Output ($y.repo_path + '|' + $y.remote_url + '|' + $y.branch + '|' + $y.commit_msg)
     } catch {
        Write-Error 'Failed to parse GitHub_push_config.yaml';
        exit 1
     }"`) do set CONFIG=%%i

for /f "tokens=1,2,3,4 delims=|" %%a in ("%CONFIG%") do (
    set REPO_PATH=%%a
    set REMOTE_URL=%%b
    set BRANCH=%%c
    set COMMIT_MSG=%%d
)

echo [INFO] Repo path   = %REPO_PATH%
echo [INFO] Remote URL  = %REMOTE_URL%
echo [INFO] Branch      = %BRANCH%
echo [INFO] Commit msg  = %COMMIT_MSG%

REM リポジトリへ移動
cd /d %REPO_PATH% || (
    echo [ERROR] repo_path not found: %REPO_PATH%
    exit /b 1
)

REM Git 初期化とリモート設定（存在しなければ）
if not exist ".git" (
    echo [INFO] Initializing git repo...
    git init
    git branch -M %BRANCH%
    git remote add origin %REMOTE_URL%
)

REM 差分確認
echo [INFO] Checking changes...
git status

REM ステージング
echo [INFO] Adding files...
git add .

REM コミット
echo [INFO] Commiting...
git commit -m "%COMMIT_MSG%" || echo [INFO] Nothing to commit.

REM 最新取り込み（競合防止）
echo [INFO] Pulling latest changes...
git pull --rebase origin %BRANCH%

REM Push 実行
echo [INFO] Pushing to %REMOTE_URL% (%BRANCH%)...
git push -u origin %BRANCH%

echo [INFO] Done!
pause
