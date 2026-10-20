@echo off
chcp 65001 > nul
title Real-time Translation App

cd /d "%~dp0"

:: .venv の python を使う
set PYTHON="%~dp0.venv\Scripts\pythonw.exe"

:: 初回（.venv がない）は自動でセットアップする
if not exist %PYTHON% call "%~dp0setup.bat" /nopause

if not exist %PYTHON% (
    echo [エラー] セットアップに失敗しました。
    echo 上のメッセージを確認して、setup.bat をもう一度実行してください。
    pause
    exit /b 1
)

echo Real-time Translation App を起動しています...
start "" %PYTHON% "%~dp0launcher.py"
