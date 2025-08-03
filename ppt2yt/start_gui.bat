@echo off
echo PPTX to YouTube 動画自動生成システム - GUI起動
echo.

REM 仮想環境をアクティベート
call venv\Scripts\Activate.bat

REM GUIアプリケーションを起動
python gui_app.py

pause 