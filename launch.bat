@echo off
chcp 65001 > nul
title Real-time Translation App

cd /d "%~dp0"

:: .venv の python を使う
set PYTHON="%~dp0.venv\Scripts\pythonw.exe"

if not exist %PYTHON% (
    echo [エラー] .venv が見つかりません。
    echo uv sync を実行してください。
    pause
    exit /b 1
)

echo Real-time Translation App を起動しています...
start "" %PYTHON% "%~dp0launcher.py"
