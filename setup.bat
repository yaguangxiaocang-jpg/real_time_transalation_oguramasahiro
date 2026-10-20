@echo off
chcp 65001 > nul
title Real-time Translation App [Setup]

cd /d "%~dp0"

:: 初回セットアップ。Python を事前に入れていなくても動くように、
:: uv（Python 3.13 も自動で取得する）と ffmpeg を必要に応じてインストールする。
:: launch.bat から "call setup.bat /nopause" で呼ばれた場合は最後に pause しない。

echo ============================================
echo  Real-time Translation App 初回セットアップ
echo ============================================
echo.

:: ---- 1. uv ----
echo [1/3] uv を確認しています...
where uv > nul 2> nul
if %errorlevel%==0 goto :uv_ok
if exist "%USERPROFILE%\.local\bin\uv.exe" goto :uv_add_path

echo uv が見つからないため、インストールします...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if not exist "%USERPROFILE%\.local\bin\uv.exe" goto :uv_fail

:uv_add_path
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

:uv_ok
echo uv OK
echo.

:: ---- 2. Python + ライブラリ（.venv） ----
echo [2/3] Python とライブラリを準備しています（初回は数分かかります）...
uv sync --extra microphone
if errorlevel 1 goto :sync_fail
echo ライブラリ OK
echo.

:: ---- 3. ffmpeg ----
echo [3/3] ffmpeg を確認しています...
where ffmpeg > nul 2> nul
if %errorlevel%==0 goto :ffmpeg_ok

where winget > nul 2> nul
if errorlevel 1 goto :ffmpeg_manual

echo ffmpeg が見つからないため、インストールします...
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto :ffmpeg_manual

:: winget はユーザーの PATH に追加するだけなので、このウィンドウにも反映させる
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%PATH%;%%P"
where ffmpeg > nul 2> nul
if errorlevel 1 goto :ffmpeg_manual

:ffmpeg_ok
echo ffmpeg OK
echo.
echo セットアップが完了しました。launch.bat をダブルクリックして起動してください。
goto :end

:uv_fail
echo.
echo [エラー] uv のインストールに失敗しました。
echo インターネット接続を確認して、もう一度 setup.bat を実行してください。
echo 手動で入れる場合: https://docs.astral.sh/uv/getting-started/installation/
goto :end_error

:sync_fail
echo.
echo [エラー] ライブラリの準備（uv sync）に失敗しました。
echo インターネット接続を確認して、もう一度 setup.bat を実行してください。
goto :end_error

:ffmpeg_manual
echo.
echo [注意] ffmpeg を自動でインストールできませんでした。
echo 動画の字幕・音声ファイルの翻訳には ffmpeg が必要です。README.md の
echo 「ffmpeg を手動でインストールする」の手順で入れてください。
echo （マイクのリアルタイム翻訳は ffmpeg なしでも使えます）
goto :end

:end_error
if /i not "%~1"=="/nopause" pause
exit /b 1

:end
if /i not "%~1"=="/nopause" pause
exit /b 0
