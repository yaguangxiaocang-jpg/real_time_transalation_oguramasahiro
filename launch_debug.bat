@echo off
chcp 65001 > nul
title Real-time Translation App [Debug]

cd /d "%~dp0"

set PYTHON="%~dp0.venv\Scripts\python.exe"

if not exist %PYTHON% (
    echo [エラー] .venv が見つかりません。
    echo uv sync を実行してください。
    pause
    exit /b 1
)

echo Real-time Translation App を起動しています...
echo ブラウザが開いたら使えます。このウィンドウは閉じないでください。
echo 終了するには Ctrl+C を押してください。
echo.

%PYTHON% "%~dp0launcher.py"
pause
