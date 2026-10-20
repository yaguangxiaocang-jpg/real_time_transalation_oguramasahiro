@echo off
chcp 65001 > nul
title Real-time Translation App [Debug]

cd /d "%~dp0"

set PYTHON="%~dp0.venv\Scripts\python.exe"

:: 初回（.venv がない）は自動でセットアップする
if not exist %PYTHON% call "%~dp0setup.bat" /nopause

if not exist %PYTHON% (
    echo [エラー] セットアップに失敗しました。
    echo 上のメッセージを確認して、setup.bat をもう一度実行してください。
    pause
    exit /b 1
)

echo Real-time Translation App を起動しています...
echo ブラウザが開いたら使えます。このウィンドウは閉じないでください。
echo 終了するには Ctrl+C を押してください。
echo.

%PYTHON% "%~dp0launcher.py"
pause
