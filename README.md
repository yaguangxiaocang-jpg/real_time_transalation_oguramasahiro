# real_time_transalation_oguramasahiro
[launcher_stderr.log](https://github.com/user-attachments/files/26679484/launcher_stderr.log)

"""
Real-time Translation App Launcher
[launcher_error.log](https://github.com/user-attachments/files/26679489/launcher_error.log)
[launcher.py](https://github.com/user-attachments/files/26679488/launcher.py)
[launcher_stdout.log](https://github.com/user-attachments/files/26679485/launcher_stdout.log)

-----------------------------------
- Gradio サーバーをバックグラウンドで起動
- ポートが開いたことを確認してからブラウザを開く
- システムトレイアイコンから終了できる
"""

from __future__ import annotations

import sys
import socket
import threading
import time
import webbrowser
from pathlib import Path

# src パスを追加
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

# pythonw.exe では stdout/stderr が None になる。
# uvicorn のログ設定が sys.stdout.isatty() を呼ぶため、
# None のままだと ValueError で起動できない。ログファイルへリダイレクトする。
if sys.stdout is None:
    sys.stdout = open(ROOT / "launcher_stdout.log", "w", encoding="utf-8", buffering=1)
if sys.stderr is None:
    sys.stderr = open(ROOT / "launcher_stderr.log", "w", encoding="utf-8", buffering=1)

HOST = "127.0.0.1"
PORT = 7860
URL = f"http://{HOST}:{PORT}"


def _is_port_open(host: str, port: int) -> bool:
    """ポートがすでにLISTENされているか確認する。"""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    """サーバーがポートをLISTENするまで待機する。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_port_open(host, port):
            return True
        time.sleep(0.5)
    return False


def _make_icon():
    """アプリアイコン画像を生成する（Pillowで動的生成）。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64), color=(30, 120, 200))
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 20, 56, 44], fill=(255, 255, 255))
    draw.polygon([(20, 10), (44, 10), (32, 22)], fill=(255, 255, 255))
    draw.polygon([(20, 54), (44, 54), (32, 42)], fill=(255, 255, 255))
    return img


def _browser_opener():
    """サーバー起動確認後にブラウザを開くスレッド。"""
    if _wait_for_port(HOST, PORT, timeout=30):
        webbrowser.open(URL)
    else:
        # フォールバック: トレイの通知だけ（タスクトレイ右クリックで開ける）
        pass


def _start_tray(stop_event: threading.Event) -> None:
    """システムトレイアイコンを表示する。失敗しても続行する。"""
    try:
        import pystray

        icon_image = _make_icon()

        def on_open(_icon, _item):
            webbrowser.open(URL)

        def on_quit(_icon, _item):
            stop_event.set()
            _icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem("ブラウザで開く", on_open),
            pystray.MenuItem("終了", on_quit),
        )
        icon = pystray.Icon(
            "RealTimeTranslation",
            icon_image,
            "Real-time Translation",
            menu,
        )
        icon.run()  # メインスレッドをブロックする
    except Exception:
        # トレイが使えない場合はイベント待機にフォールバック
        stop_event.wait()


def main():
    stop_event = threading.Event()

    # すでにサーバーが起動中ならそのままブラウザを開く
    if _is_port_open(HOST, PORT):
        webbrowser.open(URL)
        _start_tray(stop_event)
        sys.exit(0)

    # ブラウザ起動スレッド（サーバー起動を確認してから開く）
    browser_thread = threading.Thread(target=_browser_opener, daemon=True)
    browser_thread.start()

    # Gradio サーバーをバックグラウンドスレッドで起動
    def run_server():
        import traceback
        try:
            from real_time_translation.gradio_demo import build_demo
            demo = build_demo()
            demo.queue()
            demo.launch(
                server_name=HOST,
                server_port=PORT,
                inbrowser=False,
                share=False,
                prevent_thread_lock=True,
            )
            # サーバーが起動したらstop_eventを待つ
            stop_event.wait()
        except Exception as e:
            # フルトレースバックをファイルに書き出す（pythonw.exeはコンソールがないため）
            log_path = ROOT / "launcher_error.log"
            log_path.write_text(
                f"Server error: {e}\n\n{traceback.format_exc()}",
                encoding="utf-8",
            )
            stop_event.set()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # システムトレイ（メインスレッドで実行）
    _start_tray(stop_event)

    sys.exit(0)


if __name__ == "__main__":
    main()

Server error: Unable to configure formatter 'default'

Traceback (most recent call last):
  File "C:\Users\yagua\AppData\Roaming\uv\python\cpython-3.13-windows-x86_64-none\Lib\logging\config.py", line 583, in configure
    formatters[name] = self.configure_formatter(
                       ~~~~~~~~~~~~~~~~~~~~~~~~^
                                        formatters[name])
                                        ^^^^^^^^^^^^^^^^^
  File "C:\Users\yagua\AppData\Roaming\uv\python\cpython-3.13-windows-x86_64-none\Lib\logging\config.py", line 693, in configure_formatter
    result = self.configure_custom(config)
  File "C:\Users\yagua\AppData\Roaming\uv\python\cpython-3.13-windows-x86_64-none\Lib\logging\config.py", line 487, in configure_custom
    result = c(**kwargs)
  File "C:\Users\yagua\Downloads\real_time_translation_oguramasairo0305\real_time_translation-feat-windows-support-and-testing\.venv\Lib\site-packages\uvicorn\logging.py", line 42, in __init__
    self.use_colors = sys.stdout.isatty()
                      ^^^^^^^^^^^^^^^^^
AttributeError: 'NoneType' object has no attribute 'isatty'

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "C:\Users\yagua\Downloads\real_time_translation_oguramasairo0305\real_time_translation-feat-windows-support-and-testing\launcher.py", line 117, in run_server
    demo.launch(
    ~~~~~~~~~~~^
        server_name=HOST,
        ^^^^^^^^^^^^^^^^^
    ...<3 lines>...
        prevent_thread_lock=True,
        ^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "C:\Users\yagua\Downloads\real_time_translation_oguramasairo0305\real_time_translation-feat-windows-support-and-testing\.venv\Lib\site-packages\gradio\blocks.py", line 2738, in launch
    ) = http_server.start_server(
        ~~~~~~~~~~~~~~~~~~~~~~~~^
        app=self.app,
        ^^^^^^^^^^^^^
    ...<4 lines>...
        ssl_keyfile_password=ssl_keyfile_password,
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "C:\Users\yagua\Downloads\real_time_translation_oguramasairo0305\real_time_translation-feat-windows-support-and-testing\.venv\Lib\site-packages\gradio\http_server.py", line 143, in start_server
    config = uvicorn.Config(
        app=app,
    ...<5 lines>...
        ssl_keyfile_password=ssl_keyfile_password,
    )
  File "C:\Users\yagua\Downloads\real_time_translation_oguramasairo0305\real_time_translation-feat-windows-support-and-testing\.venv\Lib\site-packages\uvicorn\config.py", line 280, in __init__
    self.configure_logging()
    ~~~~~~~~~~~~~~~~~~~~~~^^
  File "C:\Users\yagua\Downloads\real_time_translation_oguramasairo0305\real_time_translation-feat-windows-support-and-testing\.venv\Lib\site-packages\uvicorn\config.py", line 372, in configure_logging
    logging.config.dictConfig(self.log_config)
    ~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^
  File "C:\Users\yagua\AppData\Roaming\uv\python\cpython-3.13-windows-x86_64-none\Lib\logging\config.py", line 935, in dictConfig
    dictConfigClass(config).configure()
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^
  File "C:\Users\yagua\AppData\Roaming\uv\python\cpython-3.13-windows-x86_64-none\Lib\logging\config.py", line 586, in configure
    raise ValueError('Unable to configure '
                     'formatter %r' % name) from e
ValueError: Unable to configure formatter 'default'

# Real-time Translation Environment Variables

# Zoom RTMS Credentials (required)
ZOOM_CLIENT_ID=your_zoom_client_id
ZOOM_CLIENT_SECRET=your_zoom_client_secret
ZOOM_WEBHOOK_PORT=8080
ZOOM_WEBHOOK_PATH=/webhook

# Deepgram API Key (required)
DEEPGRAM_API_KEY=4fcd85cc18c6843ad7d9aeaf235eaa2e76121529
DEEPGRAM_MODEL=nova-2-general
DEEPGRAM_ENDPOINTING=250
DEEPGRAM_UTTERANCE_END_MS=1000
DEEPGRAM_INTERIM_RESULTS=true
DEEPGRAM_SMART_FORMAT=true
# DEEPGRAM_VAD_EVENTS=false

# LLM Provider: "gemini" or "openai"
LLM_PROVIDER=gemini

# Google AI API Key (required if LLM_PROVIDER=gemini)
GOOGLE_API_KEY=AIzaSyDIovkzMmmkPRyRF0UY-l6KfA5wmI9w_DA

# OpenAI API Key (required if LLM_PROVIDER=openai)
# OPENAI_API_KEY=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

# Model settings (optional)
GEMINI_MODEL=gemini-2.5-flash
OPENAI_MODEL=gpt-4o-mini

# Translation settings
SOURCE_LANGUAGE=en
TARGET_LANGUAGE=ja
CONTEXT_WINDOW_SIZE=5
TRANSLATION_QUEUE_SIZE=50

# Dictionary (optional) - CSV file with domain-specific terminology
# Format: source_term,target_term,notes
DICTIONARY_PATH=dictionary.csv

# RTMP / ffmpeg settings (microservices)
RTMP_URL=rtmp://nms:1935/live/zoom
FFMPEG_CHUNK_MS=20
FFMPEG_SAMPLE_RATE=16000
FFMPEG_CHANNELS=1

# WebSocket + translation service settings (microservices)
WS_PUBLISH_URL=http://ws:8000/publish
TRANSLATION_API_URL=http://gemini:8000/translate
ASR_SEND_INTERIM=true
TRANSLATE_INTERIM=false
ASR_PARTIAL_MIN_INTERVAL_MS=100
TRANSLATION_CONCURRENCY=3
HTTP_TIMEOUT=10

# Ngrok authentication token - get it from https://dashboard.ngrok.com/get-started/your-authtoken
NGROK_AUTHTOKEN=39NgxzLFjPed6ehOWzugBV9scAA_2xhPRTFZLXuurBZDaGGht

# Zoom Closed Caption (optional) - Get the caption URL from Zoom meeting
# See: https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060372
# ZOOM_CAPTION_URL=https://wmcc.zoom.us/closedcaption?id=...
# ZOOM_CAPTION_LANG=ja
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$LaunchBat = Join-Path $AppDir "launch.bat"
$Desktop = [System.Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Real-time Translation.lnk"

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($ShortcutPath)
$sc.TargetPath = $LaunchBat
$sc.WorkingDirectory = $AppDir
$sc.Description = "Real-time Translation App"
$sc.Save()

Write-Host "Shortcut created: $ShortcutPath"
pause

@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"

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

[project]
name = "real-time-translation"
version = "0.1.0"
description = "Real-time translation application for Zoom meetings"
readme = "README.md"
requires-python = ">=3.13,<3.14"
dependencies = [
    "deepgram-sdk>=5.3.2",
    "google-genai>=1.58.0",
    "gradio>=6.3.0",
    "langchain>=1.2.6",
    "langchain-google-genai>=4.2.0",
    "langchain-openai>=0.2.0",
    "pystray>=0.19.5",
    "python-dotenv>=1.0.0",
    "sacrebleu>=2.4.0",
]

[[tool.uv.index]]
name = "testpypi"
url = "https://test.pypi.org/simple/"
explicit = true

[tool.uv.sources]
rtms = { index = "testpypi" }

[project.optional-dependencies]
zoom = ["rtms>=0.0.2"]
microphone = ["sounddevice>=0.4.7", "numpy>=1.26.0"]
dev = ["pytest>=8.0.0", "pytest-asyncio>=0.24.0", "ruff>=0.8.0"]

[project.scripts]
real-time-translation = "real_time_translation.main:main"
real-time-translation-demo = "real_time_translation.gradio_demo:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/real_time_translation"]

[tool.ruff]
line-length = 88
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"

version = 1
revision = 3
requires-python = "==3.13.*"
resolution-markers = [
    "sys_platform == 'win32'",
    "sys_platform == 'emscripten'",
    "sys_platform != 'emscripten' and sys_platform != 'win32'",
]

[[package]]
name = "aiofiles"
version = "24.1.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/0b/03/a88171e277e8caa88a4c77808c20ebb04ba74cc4681bf1e9416c862de237/aiofiles-24.1.0.tar.gz", hash = "sha256:22a075c9e5a3810f0c2e48f3008c94d68c65d763b9b03857924c99e57355166c", size = 30247, upload-time = "2024-06-24T11:02:03.584Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/a5/45/30bb92d442636f570cb5651bc661f52b610e2eec3f891a5dc3a4c3667db0/aiofiles-24.1.0-py3-none-any.whl", hash = "sha256:b4ec55f4195e3eb5d7abd1bf7e061763e864dd4954231fb8539a0ef8bb8260e5", size = 15896, upload-time = "2024-06-24T11:02:01.529Z" },
]

[[package]]
name = "annotated-doc"
version = "0.0.4"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/57/ba/046ceea27344560984e26a590f90bc7f4a75b06701f653222458922b558c/annotated_doc-0.0.4.tar.gz", hash = "sha256:fbcda96e87e9c92ad167c2e53839e57503ecfda18804ea28102353485033faa4", size = 7288, upload-time = "2025-11-10T22:07:42.062Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/1e/d3/26bf1008eb3d2daa8ef4cacc7f3bfdc11818d111f7e2d0201bc6e3b49d45/annotated_doc-0.0.4-py3-none-any.whl", hash = "sha256:571ac1dc6991c450b25a9c2d84a3705e2ae7a53467b5d111c24fa8baabbed320", size = 5303, upload-time = "2025-11-10T22:07:40.673Z" },
]

[[package]]
name = "annotated-types"
version = "0.7.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/ee/67/531ea369ba64dcff5ec9c3402f9f51bf748cec26dde048a2f973a4eea7f5/annotated_types-0.7.0.tar.gz", hash = "sha256:aff07c09a53a08bc8cfccb9c85b05f1aa9a2a6f23728d790723543408344ce89", size = 16081, upload-time = "2024-05-20T21:33:25.928Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/78/b6/6307fbef88d9b5ee7421e68d78a9f162e0da4900bc5f5793f6d3d0e34fb8/annotated_types-0.7.0-py3-none-any.whl", hash = "sha256:1f02e8b43a8fbbc3f3e0d4f0f4bfc8131bcb4eebe8849b8e5c773f3a1c582a53", size = 13643, upload-time = "2024-05-20T21:33:24.1Z" },
]

[[package]]
name = "anyio"
version = "4.12.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "idna" },
]
sdist = { url = "https://files.pythonhosted.org/packages/96/f0/5eb65b2bb0d09ac6776f2eb54adee6abe8228ea05b20a5ad0e4945de8aac/anyio-4.12.1.tar.gz", hash = "sha256:41cfcc3a4c85d3f05c932da7c26d0201ac36f72abd4435ba90d0464a3ffed703", size = 228685, upload-time = "2026-01-06T11:45:21.246Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/38/0e/27be9fdef66e72d64c0cdc3cc2823101b80585f8119b5c112c2e8f5f7dab/anyio-4.12.1-py3-none-any.whl", hash = "sha256:d405828884fc140aa80a3c667b8beed277f1dfedec42ba031bd6ac3db606ab6c", size = 113592, upload-time = "2026-01-06T11:45:19.497Z" },
]

[[package]]
name = "audioop-lts"
version = "0.2.2"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/38/53/946db57842a50b2da2e0c1e34bd37f36f5aadba1a929a3971c5d7841dbca/audioop_lts-0.2.2.tar.gz", hash = "sha256:64d0c62d88e67b98a1a5e71987b7aa7b5bcffc7dcee65b635823dbdd0a8dbbd0", size = 30686, upload-time = "2025-08-05T16:43:17.409Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/de/d4/94d277ca941de5a507b07f0b592f199c22454eeaec8f008a286b3fbbacd6/audioop_lts-0.2.2-cp313-abi3-macosx_10_13_universal2.whl", hash = "sha256:fd3d4602dc64914d462924a08c1a9816435a2155d74f325853c1f1ac3b2d9800", size = 46523, upload-time = "2025-08-05T16:42:20.836Z" },
    { url = "https://files.pythonhosted.org/packages/f8/5a/656d1c2da4b555920ce4177167bfeb8623d98765594af59702c8873f60ec/audioop_lts-0.2.2-cp313-abi3-macosx_10_13_x86_64.whl", hash = "sha256:550c114a8df0aafe9a05442a1162dfc8fec37e9af1d625ae6060fed6e756f303", size = 27455, upload-time = "2025-08-05T16:42:22.283Z" },
    { url = "https://files.pythonhosted.org/packages/1b/83/ea581e364ce7b0d41456fb79d6ee0ad482beda61faf0cab20cbd4c63a541/audioop_lts-0.2.2-cp313-abi3-macosx_11_0_arm64.whl", hash = "sha256:9a13dc409f2564de15dd68be65b462ba0dde01b19663720c68c1140c782d1d75", size = 26997, upload-time = "2025-08-05T16:42:23.849Z" },
    { url = "https://files.pythonhosted.org/packages/b8/3b/e8964210b5e216e5041593b7d33e97ee65967f17c282e8510d19c666dab4/audioop_lts-0.2.2-cp313-abi3-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", hash = "sha256:51c916108c56aa6e426ce611946f901badac950ee2ddaf302b7ed35d9958970d", size = 85844, upload-time = "2025-08-05T16:42:25.208Z" },
    { url = "https://files.pythonhosted.org/packages/c7/2e/0a1c52faf10d51def20531a59ce4c706cb7952323b11709e10de324d6493/audioop_lts-0.2.2-cp313-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:47eba38322370347b1c47024defbd36374a211e8dd5b0dcbce7b34fdb6f8847b", size = 85056, upload-time = "2025-08-05T16:42:26.559Z" },
    { url = "https://files.pythonhosted.org/packages/75/e8/cd95eef479656cb75ab05dfece8c1f8c395d17a7c651d88f8e6e291a63ab/audioop_lts-0.2.2-cp313-abi3-manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:ba7c3a7e5f23e215cb271516197030c32aef2e754252c4c70a50aaff7031a2c8", size = 93892, upload-time = "2025-08-05T16:42:27.902Z" },
    { url = "https://files.pythonhosted.org/packages/5c/1e/a0c42570b74f83efa5cca34905b3eef03f7ab09fe5637015df538a7f3345/audioop_lts-0.2.2-cp313-abi3-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl", hash = "sha256:def246fe9e180626731b26e89816e79aae2276f825420a07b4a647abaa84becc", size = 96660, upload-time = "2025-08-05T16:42:28.9Z" },
    { url = "https://files.pythonhosted.org/packages/50/d5/8a0ae607ca07dbb34027bac8db805498ee7bfecc05fd2c148cc1ed7646e7/audioop_lts-0.2.2-cp313-abi3-manylinux_2_31_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:e160bf9df356d841bb6c180eeeea1834085464626dc1b68fa4e1d59070affdc3", size = 79143, upload-time = "2025-08-05T16:42:29.929Z" },
    { url = "https://files.pythonhosted.org/packages/12/17/0d28c46179e7910bfb0bb62760ccb33edb5de973052cb2230b662c14ca2e/audioop_lts-0.2.2-cp313-abi3-musllinux_1_2_aarch64.whl", hash = "sha256:4b4cd51a57b698b2d06cb9993b7ac8dfe89a3b2878e96bc7948e9f19ff51dba6", size = 84313, upload-time = "2025-08-05T16:42:30.949Z" },
    { url = "https://files.pythonhosted.org/packages/84/ba/bd5d3806641564f2024e97ca98ea8f8811d4e01d9b9f9831474bc9e14f9e/audioop_lts-0.2.2-cp313-abi3-musllinux_1_2_ppc64le.whl", hash = "sha256:4a53aa7c16a60a6857e6b0b165261436396ef7293f8b5c9c828a3a203147ed4a", size = 93044, upload-time = "2025-08-05T16:42:31.959Z" },
    { url = "https://files.pythonhosted.org/packages/f9/5e/435ce8d5642f1f7679540d1e73c1c42d933331c0976eb397d1717d7f01a3/audioop_lts-0.2.2-cp313-abi3-musllinux_1_2_riscv64.whl", hash = "sha256:3fc38008969796f0f689f1453722a0f463da1b8a6fbee11987830bfbb664f623", size = 78766, upload-time = "2025-08-05T16:42:33.302Z" },
    { url = "https://files.pythonhosted.org/packages/ae/3b/b909e76b606cbfd53875693ec8c156e93e15a1366a012f0b7e4fb52d3c34/audioop_lts-0.2.2-cp313-abi3-musllinux_1_2_s390x.whl", hash = "sha256:15ab25dd3e620790f40e9ead897f91e79c0d3ce65fe193c8ed6c26cffdd24be7", size = 87640, upload-time = "2025-08-05T16:42:34.854Z" },
    { url = "https://files.pythonhosted.org/packages/30/e7/8f1603b4572d79b775f2140d7952f200f5e6c62904585d08a01f0a70393a/audioop_lts-0.2.2-cp313-abi3-musllinux_1_2_x86_64.whl", hash = "sha256:03f061a1915538fd96272bac9551841859dbb2e3bf73ebe4a23ef043766f5449", size = 86052, upload-time = "2025-08-05T16:42:35.839Z" },
    { url = "https://files.pythonhosted.org/packages/b5/96/c37846df657ccdda62ba1ae2b6534fa90e2e1b1742ca8dcf8ebd38c53801/audioop_lts-0.2.2-cp313-abi3-win32.whl", hash = "sha256:3bcddaaf6cc5935a300a8387c99f7a7fbbe212a11568ec6cf6e4bc458c048636", size = 26185, upload-time = "2025-08-05T16:42:37.04Z" },
    { url = "https://files.pythonhosted.org/packages/34/a5/9d78fdb5b844a83da8a71226c7bdae7cc638861085fff7a1d707cb4823fa/audioop_lts-0.2.2-cp313-abi3-win_amd64.whl", hash = "sha256:a2c2a947fae7d1062ef08c4e369e0ba2086049a5e598fda41122535557012e9e", size = 30503, upload-time = "2025-08-05T16:42:38.427Z" },
    { url = "https://files.pythonhosted.org/packages/34/25/20d8fde083123e90c61b51afb547bb0ea7e77bab50d98c0ab243d02a0e43/audioop_lts-0.2.2-cp313-abi3-win_arm64.whl", hash = "sha256:5f93a5db13927a37d2d09637ccca4b2b6b48c19cd9eda7b17a2e9f77edee6a6f", size = 24173, upload-time = "2025-08-05T16:42:39.704Z" },
    { url = "https://files.pythonhosted.org/packages/58/a7/0a764f77b5c4ac58dc13c01a580f5d32ae8c74c92020b961556a43e26d02/audioop_lts-0.2.2-cp313-cp313t-macosx_10_13_universal2.whl", hash = "sha256:73f80bf4cd5d2ca7814da30a120de1f9408ee0619cc75da87d0641273d202a09", size = 47096, upload-time = "2025-08-05T16:42:40.684Z" },
    { url = "https://files.pythonhosted.org/packages/aa/ed/ebebedde1a18848b085ad0fa54b66ceb95f1f94a3fc04f1cd1b5ccb0ed42/audioop_lts-0.2.2-cp313-cp313t-macosx_10_13_x86_64.whl", hash = "sha256:106753a83a25ee4d6f473f2be6b0966fc1c9af7e0017192f5531a3e7463dce58", size = 27748, upload-time = "2025-08-05T16:42:41.992Z" },
    { url = "https://files.pythonhosted.org/packages/cb/6e/11ca8c21af79f15dbb1c7f8017952ee8c810c438ce4e2b25638dfef2b02c/audioop_lts-0.2.2-cp313-cp313t-macosx_11_0_arm64.whl", hash = "sha256:fbdd522624141e40948ab3e8cdae6e04c748d78710e9f0f8d4dae2750831de19", size = 27329, upload-time = "2025-08-05T16:42:42.987Z" },
    { url = "https://files.pythonhosted.org/packages/84/52/0022f93d56d85eec5da6b9da6a958a1ef09e80c39f2cc0a590c6af81dcbb/audioop_lts-0.2.2-cp313-cp313t-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl", hash = "sha256:143fad0311e8209ece30a8dbddab3b65ab419cbe8c0dde6e8828da25999be911", size = 92407, upload-time = "2025-08-05T16:42:44.336Z" },
    { url = "https://files.pythonhosted.org/packages/87/1d/48a889855e67be8718adbc7a01f3c01d5743c325453a5e81cf3717664aad/audioop_lts-0.2.2-cp313-cp313t-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:dfbbc74ec68a0fd08cfec1f4b5e8cca3d3cd7de5501b01c4b5d209995033cde9", size = 91811, upload-time = "2025-08-05T16:42:45.325Z" },
    { url = "https://files.pythonhosted.org/packages/98/a6/94b7213190e8077547ffae75e13ed05edc488653c85aa5c41472c297d295/audioop_lts-0.2.2-cp313-cp313t-manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:cfcac6aa6f42397471e4943e0feb2244549db5c5d01efcd02725b96af417f3fe", size = 100470, upload-time = "2025-08-05T16:42:46.468Z" },
    { url = "https://files.pythonhosted.org/packages/e9/e9/78450d7cb921ede0cfc33426d3a8023a3bda755883c95c868ee36db8d48d/audioop_lts-0.2.2-cp313-cp313t-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl", hash = "sha256:752d76472d9804ac60f0078c79cdae8b956f293177acd2316cd1e15149aee132", size = 103878, upload-time = "2025-08-05T16:42:47.576Z" },
    { url = "https://files.pythonhosted.org/packages/4f/e2/cd5439aad4f3e34ae1ee852025dc6aa8f67a82b97641e390bf7bd9891d3e/audioop_lts-0.2.2-cp313-cp313t-manylinux_2_31_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:83c381767e2cc10e93e40281a04852facc4cd9334550e0f392f72d1c0a9c5753", size = 84867, upload-time = "2025-08-05T16:42:49.003Z" },
    { url = "https://files.pythonhosted.org/packages/68/4b/9d853e9076c43ebba0d411e8d2aa19061083349ac695a7d082540bad64d0/audioop_lts-0.2.2-cp313-cp313t-musllinux_1_2_aarch64.whl", hash = "sha256:c0022283e9556e0f3643b7c3c03f05063ca72b3063291834cca43234f20c60bb", size = 90001, upload-time = "2025-08-05T16:42:50.038Z" },
    { url = "https://files.pythonhosted.org/packages/58/26/4bae7f9d2f116ed5593989d0e521d679b0d583973d203384679323d8fa85/audioop_lts-0.2.2-cp313-cp313t-musllinux_1_2_ppc64le.whl", hash = "sha256:a2d4f1513d63c795e82948e1305f31a6d530626e5f9f2605408b300ae6095093", size = 99046, upload-time = "2025-08-05T16:42:51.111Z" },
    { url = "https://files.pythonhosted.org/packages/b2/67/a9f4fb3e250dda9e9046f8866e9fa7d52664f8985e445c6b4ad6dfb55641/audioop_lts-0.2.2-cp313-cp313t-musllinux_1_2_riscv64.whl", hash = "sha256:c9c8e68d8b4a56fda8c025e538e639f8c5953f5073886b596c93ec9b620055e7", size = 84788, upload-time = "2025-08-05T16:42:52.198Z" },
    { url = "https://files.pythonhosted.org/packages/70/f7/3de86562db0121956148bcb0fe5b506615e3bcf6e63c4357a612b910765a/audioop_lts-0.2.2-cp313-cp313t-musllinux_1_2_s390x.whl", hash = "sha256:96f19de485a2925314f5020e85911fb447ff5fbef56e8c7c6927851b95533a1c", size = 94472, upload-time = "2025-08-05T16:42:53.59Z" },
    { url = "https://files.pythonhosted.org/packages/f1/32/fd772bf9078ae1001207d2df1eef3da05bea611a87dd0e8217989b2848fa/audioop_lts-0.2.2-cp313-cp313t-musllinux_1_2_x86_64.whl", hash = "sha256:e541c3ef484852ef36545f66209444c48b28661e864ccadb29daddb6a4b8e5f5", size = 92279, upload-time = "2025-08-05T16:42:54.632Z" },
    { url = "https://files.pythonhosted.org/packages/4f/41/affea7181592ab0ab560044632571a38edaf9130b84928177823fbf3176a/audioop_lts-0.2.2-cp313-cp313t-win32.whl", hash = "sha256:d5e73fa573e273e4f2e5ff96f9043858a5e9311e94ffefd88a3186a910c70917", size = 26568, upload-time = "2025-08-05T16:42:55.627Z" },
    { url = "https://files.pythonhosted.org/packages/28/2b/0372842877016641db8fc54d5c88596b542eec2f8f6c20a36fb6612bf9ee/audioop_lts-0.2.2-cp313-cp313t-win_amd64.whl", hash = "sha256:9191d68659eda01e448188f60364c7763a7ca6653ed3f87ebb165822153a8547", size = 30942, upload-time = "2025-08-05T16:42:56.674Z" },
    { url = "https://files.pythonhosted.org/packages/ee/ca/baf2b9cc7e96c179bb4a54f30fcd83e6ecb340031bde68f486403f943768/audioop_lts-0.2.2-cp313-cp313t-win_arm64.whl", hash = "sha256:c174e322bb5783c099aaf87faeb240c8d210686b04bd61dfd05a8e5a83d88969", size = 24603, upload-time = "2025-08-05T16:42:57.571Z" },
]

[[package]]
name = "brotli"
version = "1.2.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/f7/16/c92ca344d646e71a43b8bb353f0a6490d7f6e06210f8554c8f874e454285/brotli-1.2.0.tar.gz", hash = "sha256:e310f77e41941c13340a95976fe66a8a95b01e783d430eeaf7a2f87e0a57dd0a", size = 7388632, upload-time = "2025-11-05T18:39:42.86Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/6c/d4/4ad5432ac98c73096159d9ce7ffeb82d151c2ac84adcc6168e476bb54674/brotli-1.2.0-cp313-cp313-macosx_10_13_universal2.whl", hash = "sha256:9e5825ba2c9998375530504578fd4d5d1059d09621a02065d1b6bfc41a8e05ab", size = 861523, upload-time = "2025-11-05T18:38:34.67Z" },
    { url = "https://files.pythonhosted.org/packages/91/9f/9cc5bd03ee68a85dc4bc89114f7067c056a3c14b3d95f171918c088bf88d/brotli-1.2.0-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:0cf8c3b8ba93d496b2fae778039e2f5ecc7cff99df84df337ca31d8f2252896c", size = 444289, upload-time = "2025-11-05T18:38:35.6Z" },
    { url = "https://files.pythonhosted.org/packages/2e/b6/fe84227c56a865d16a6614e2c4722864b380cb14b13f3e6bef441e73a85a/brotli-1.2.0-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:c8565e3cdc1808b1a34714b553b262c5de5fbda202285782173ec137fd13709f", size = 1528076, upload-time = "2025-11-05T18:38:36.639Z" },
    { url = "https://files.pythonhosted.org/packages/55/de/de4ae0aaca06c790371cf6e7ee93a024f6b4bb0568727da8c3de112e726c/brotli-1.2.0-cp313-cp313-manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:26e8d3ecb0ee458a9804f47f21b74845cc823fd1bb19f02272be70774f56e2a6", size = 1626880, upload-time = "2025-11-05T18:38:37.623Z" },
    { url = "https://files.pythonhosted.org/packages/5f/16/a1b22cbea436642e071adcaf8d4b350a2ad02f5e0ad0da879a1be16188a0/brotli-1.2.0-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:67a91c5187e1eec76a61625c77a6c8c785650f5b576ca732bd33ef58b0dff49c", size = 1419737, upload-time = "2025-11-05T18:38:38.729Z" },
    { url = "https://files.pythonhosted.org/packages/46/63/c968a97cbb3bdbf7f974ef5a6ab467a2879b82afbc5ffb65b8acbb744f95/brotli-1.2.0-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:4ecdb3b6dc36e6d6e14d3a1bdc6c1057c8cbf80db04031d566eb6080ce283a48", size = 1484440, upload-time = "2025-11-05T18:38:39.916Z" },
    { url = "https://files.pythonhosted.org/packages/06/9d/102c67ea5c9fc171f423e8399e585dabea29b5bc79b05572891e70013cdd/brotli-1.2.0-cp313-cp313-musllinux_1_2_ppc64le.whl", hash = "sha256:3e1b35d56856f3ed326b140d3c6d9db91740f22e14b06e840fe4bb1923439a18", size = 1593313, upload-time = "2025-11-05T18:38:41.24Z" },
    { url = "https://files.pythonhosted.org/packages/9e/4a/9526d14fa6b87bc827ba1755a8440e214ff90de03095cacd78a64abe2b7d/brotli-1.2.0-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:54a50a9dad16b32136b2241ddea9e4df159b41247b2ce6aac0b3276a66a8f1e5", size = 1487945, upload-time = "2025-11-05T18:38:42.277Z" },
    { url = "https://files.pythonhosted.org/packages/5b/e8/3fe1ffed70cbef83c5236166acaed7bb9c766509b157854c80e2f766b38c/brotli-1.2.0-cp313-cp313-win32.whl", hash = "sha256:1b1d6a4efedd53671c793be6dd760fcf2107da3a52331ad9ea429edf0902f27a", size = 334368, upload-time = "2025-11-05T18:38:43.345Z" },
    { url = "https://files.pythonhosted.org/packages/ff/91/e739587be970a113b37b821eae8097aac5a48e5f0eca438c22e4c7dd8648/brotli-1.2.0-cp313-cp313-win_amd64.whl", hash = "sha256:b63daa43d82f0cdabf98dee215b375b4058cce72871fd07934f179885aad16e8", size = 369116, upload-time = "2025-11-05T18:38:44.609Z" },
]

[[package]]
name = "certifi"
version = "2026.1.4"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/e0/2d/a891ca51311197f6ad14a7ef42e2399f36cf2f9bd44752b3dc4eab60fdc5/certifi-2026.1.4.tar.gz", hash = "sha256:ac726dd470482006e014ad384921ed6438c457018f4b3d204aea4281258b2120", size = 154268, upload-time = "2026-01-04T02:42:41.825Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/e6/ad/3cc14f097111b4de0040c83a525973216457bbeeb63739ef1ed275c1c021/certifi-2026.1.4-py3-none-any.whl", hash = "sha256:9943707519e4add1115f44c2bc244f782c0249876bf51b6599fee1ffbedd685c", size = 152900, upload-time = "2026-01-04T02:42:40.15Z" },
]

[[package]]
name = "cffi"
version = "2.0.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "pycparser", marker = "implementation_name != 'PyPy'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/eb/56/b1ba7935a17738ae8453301356628e8147c79dbb825bcbc73dc7401f9846/cffi-2.0.0.tar.gz", hash = "sha256:44d1b5909021139fe36001ae048dbdde8214afa20200eda0f64c068cac5d5529", size = 523588, upload-time = "2025-09-08T23:24:04.541Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/4b/8d/a0a47a0c9e413a658623d014e91e74a50cdd2c423f7ccfd44086ef767f90/cffi-2.0.0-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:00bdf7acc5f795150faa6957054fbbca2439db2f775ce831222b66f192f03beb", size = 185230, upload-time = "2025-09-08T23:23:00.879Z" },
    { url = "https://files.pythonhosted.org/packages/4a/d2/a6c0296814556c68ee32009d9c2ad4f85f2707cdecfd7727951ec228005d/cffi-2.0.0-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:45d5e886156860dc35862657e1494b9bae8dfa63bf56796f2fb56e1679fc0bca", size = 181043, upload-time = "2025-09-08T23:23:02.231Z" },
    { url = "https://files.pythonhosted.org/packages/b0/1e/d22cc63332bd59b06481ceaac49d6c507598642e2230f201649058a7e704/cffi-2.0.0-cp313-cp313-manylinux1_i686.manylinux2014_i686.manylinux_2_17_i686.manylinux_2_5_i686.whl", hash = "sha256:07b271772c100085dd28b74fa0cd81c8fb1a3ba18b21e03d7c27f3436a10606b", size = 212446, upload-time = "2025-09-08T23:23:03.472Z" },
    { url = "https://files.pythonhosted.org/packages/a9/f5/a2c23eb03b61a0b8747f211eb716446c826ad66818ddc7810cc2cc19b3f2/cffi-2.0.0-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.whl", hash = "sha256:d48a880098c96020b02d5a1f7d9251308510ce8858940e6fa99ece33f610838b", size = 220101, upload-time = "2025-09-08T23:23:04.792Z" },
    { url = "https://files.pythonhosted.org/packages/f2/7f/e6647792fc5850d634695bc0e6ab4111ae88e89981d35ac269956605feba/cffi-2.0.0-cp313-cp313-manylinux2014_ppc64le.manylinux_2_17_ppc64le.whl", hash = "sha256:f93fd8e5c8c0a4aa1f424d6173f14a892044054871c771f8566e4008eaa359d2", size = 207948, upload-time = "2025-09-08T23:23:06.127Z" },
    { url = "https://files.pythonhosted.org/packages/cb/1e/a5a1bd6f1fb30f22573f76533de12a00bf274abcdc55c8edab639078abb6/cffi-2.0.0-cp313-cp313-manylinux2014_s390x.manylinux_2_17_s390x.whl", hash = "sha256:dd4f05f54a52fb558f1ba9f528228066954fee3ebe629fc1660d874d040ae5a3", size = 206422, upload-time = "2025-09-08T23:23:07.753Z" },
    { url = "https://files.pythonhosted.org/packages/98/df/0a1755e750013a2081e863e7cd37e0cdd02664372c754e5560099eb7aa44/cffi-2.0.0-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:c8d3b5532fc71b7a77c09192b4a5a200ea992702734a2e9279a37f2478236f26", size = 219499, upload-time = "2025-09-08T23:23:09.648Z" },
    { url = "https://files.pythonhosted.org/packages/50/e1/a969e687fcf9ea58e6e2a928ad5e2dd88cc12f6f0ab477e9971f2309b57c/cffi-2.0.0-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:d9b29c1f0ae438d5ee9acb31cadee00a58c46cc9c0b2f9038c6b0b3470877a8c", size = 222928, upload-time = "2025-09-08T23:23:10.928Z" },
    { url = "https://files.pythonhosted.org/packages/36/54/0362578dd2c9e557a28ac77698ed67323ed5b9775ca9d3fe73fe191bb5d8/cffi-2.0.0-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:6d50360be4546678fc1b79ffe7a66265e28667840010348dd69a314145807a1b", size = 221302, upload-time = "2025-09-08T23:23:12.42Z" },
    { url = "https://files.pythonhosted.org/packages/eb/6d/bf9bda840d5f1dfdbf0feca87fbdb64a918a69bca42cfa0ba7b137c48cb8/cffi-2.0.0-cp313-cp313-win32.whl", hash = "sha256:74a03b9698e198d47562765773b4a8309919089150a0bb17d829ad7b44b60d27", size = 172909, upload-time = "2025-09-08T23:23:14.32Z" },
    { url = "https://files.pythonhosted.org/packages/37/18/6519e1ee6f5a1e579e04b9ddb6f1676c17368a7aba48299c3759bbc3c8b3/cffi-2.0.0-cp313-cp313-win_amd64.whl", hash = "sha256:19f705ada2530c1167abacb171925dd886168931e0a7b78f5bffcae5c6b5be75", size = 183402, upload-time = "2025-09-08T23:23:15.535Z" },
    { url = "https://files.pythonhosted.org/packages/cb/0e/02ceeec9a7d6ee63bb596121c2c8e9b3a9e150936f4fbef6ca1943e6137c/cffi-2.0.0-cp313-cp313-win_arm64.whl", hash = "sha256:256f80b80ca3853f90c21b23ee78cd008713787b1b1e93eae9f3d6a7134abd91", size = 177780, upload-time = "2025-09-08T23:23:16.761Z" },
]

[[package]]
name = "charset-normalizer"
version = "3.4.4"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/13/69/33ddede1939fdd074bce5434295f38fae7136463422fe4fd3e0e89b98062/charset_normalizer-3.4.4.tar.gz", hash = "sha256:94537985111c35f28720e43603b8e7b43a6ecfb2ce1d3058bbe955b73404e21a", size = 129418, upload-time = "2025-10-14T04:42:32.879Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/97/45/4b3a1239bbacd321068ea6e7ac28875b03ab8bc0aa0966452db17cd36714/charset_normalizer-3.4.4-cp313-cp313-macosx_10_13_universal2.whl", hash = "sha256:e1f185f86a6f3403aa2420e815904c67b2f9ebc443f045edd0de921108345794", size = 208091, upload-time = "2025-10-14T04:41:13.346Z" },
    { url = "https://files.pythonhosted.org/packages/7d/62/73a6d7450829655a35bb88a88fca7d736f9882a27eacdca2c6d505b57e2e/charset_normalizer-3.4.4-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:6b39f987ae8ccdf0d2642338faf2abb1862340facc796048b604ef14919e55ed", size = 147936, upload-time = "2025-10-14T04:41:14.461Z" },
    { url = "https://files.pythonhosted.org/packages/89/c5/adb8c8b3d6625bef6d88b251bbb0d95f8205831b987631ab0c8bb5d937c2/charset_normalizer-3.4.4-cp313-cp313-manylinux2014_armv7l.manylinux_2_17_armv7l.manylinux_2_31_armv7l.whl", hash = "sha256:3162d5d8ce1bb98dd51af660f2121c55d0fa541b46dff7bb9b9f86ea1d87de72", size = 144180, upload-time = "2025-10-14T04:41:15.588Z" },
    { url = "https://files.pythonhosted.org/packages/91/ed/9706e4070682d1cc219050b6048bfd293ccf67b3d4f5a4f39207453d4b99/charset_normalizer-3.4.4-cp313-cp313-manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:81d5eb2a312700f4ecaa977a8235b634ce853200e828fbadf3a9c50bab278328", size = 161346, upload-time = "2025-10-14T04:41:16.738Z" },
    { url = "https://files.pythonhosted.org/packages/d5/0d/031f0d95e4972901a2f6f09ef055751805ff541511dc1252ba3ca1f80cf5/charset_normalizer-3.4.4-cp313-cp313-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl", hash = "sha256:5bd2293095d766545ec1a8f612559f6b40abc0eb18bb2f5d1171872d34036ede", size = 158874, upload-time = "2025-10-14T04:41:17.923Z" },
    { url = "https://files.pythonhosted.org/packages/f5/83/6ab5883f57c9c801ce5e5677242328aa45592be8a00644310a008d04f922/charset_normalizer-3.4.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:a8a8b89589086a25749f471e6a900d3f662d1d3b6e2e59dcecf787b1cc3a1894", size = 153076, upload-time = "2025-10-14T04:41:19.106Z" },
    { url = "https://files.pythonhosted.org/packages/75/1e/5ff781ddf5260e387d6419959ee89ef13878229732732ee73cdae01800f2/charset_normalizer-3.4.4-cp313-cp313-manylinux_2_31_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:bc7637e2f80d8530ee4a78e878bce464f70087ce73cf7c1caf142416923b98f1", size = 150601, upload-time = "2025-10-14T04:41:20.245Z" },
    { url = "https://files.pythonhosted.org/packages/d7/57/71be810965493d3510a6ca79b90c19e48696fb1ff964da319334b12677f0/charset_normalizer-3.4.4-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:f8bf04158c6b607d747e93949aa60618b61312fe647a6369f88ce2ff16043490", size = 150376, upload-time = "2025-10-14T04:41:21.398Z" },
    { url = "https://files.pythonhosted.org/packages/e5/d5/c3d057a78c181d007014feb7e9f2e65905a6c4ef182c0ddf0de2924edd65/charset_normalizer-3.4.4-cp313-cp313-musllinux_1_2_armv7l.whl", hash = "sha256:554af85e960429cf30784dd47447d5125aaa3b99a6f0683589dbd27e2f45da44", size = 144825, upload-time = "2025-10-14T04:41:22.583Z" },
    { url = "https://files.pythonhosted.org/packages/e6/8c/d0406294828d4976f275ffbe66f00266c4b3136b7506941d87c00cab5272/charset_normalizer-3.4.4-cp313-cp313-musllinux_1_2_ppc64le.whl", hash = "sha256:74018750915ee7ad843a774364e13a3db91682f26142baddf775342c3f5b1133", size = 162583, upload-time = "2025-10-14T04:41:23.754Z" },
    { url = "https://files.pythonhosted.org/packages/d7/24/e2aa1f18c8f15c4c0e932d9287b8609dd30ad56dbe41d926bd846e22fb8d/charset_normalizer-3.4.4-cp313-cp313-musllinux_1_2_riscv64.whl", hash = "sha256:c0463276121fdee9c49b98908b3a89c39be45d86d1dbaa22957e38f6321d4ce3", size = 150366, upload-time = "2025-10-14T04:41:25.27Z" },
    { url = "https://files.pythonhosted.org/packages/e4/5b/1e6160c7739aad1e2df054300cc618b06bf784a7a164b0f238360721ab86/charset_normalizer-3.4.4-cp313-cp313-musllinux_1_2_s390x.whl", hash = "sha256:362d61fd13843997c1c446760ef36f240cf81d3ebf74ac62652aebaf7838561e", size = 160300, upload-time = "2025-10-14T04:41:26.725Z" },
    { url = "https://files.pythonhosted.org/packages/7a/10/f882167cd207fbdd743e55534d5d9620e095089d176d55cb22d5322f2afd/charset_normalizer-3.4.4-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:9a26f18905b8dd5d685d6d07b0cdf98a79f3c7a918906af7cc143ea2e164c8bc", size = 154465, upload-time = "2025-10-14T04:41:28.322Z" },
    { url = "https://files.pythonhosted.org/packages/89/66/c7a9e1b7429be72123441bfdbaf2bc13faab3f90b933f664db506dea5915/charset_normalizer-3.4.4-cp313-cp313-win32.whl", hash = "sha256:9b35f4c90079ff2e2edc5b26c0c77925e5d2d255c42c74fdb70fb49b172726ac", size = 99404, upload-time = "2025-10-14T04:41:29.95Z" },
    { url = "https://files.pythonhosted.org/packages/c4/26/b9924fa27db384bdcd97ab83b4f0a8058d96ad9626ead570674d5e737d90/charset_normalizer-3.4.4-cp313-cp313-win_amd64.whl", hash = "sha256:b435cba5f4f750aa6c0a0d92c541fb79f69a387c91e61f1795227e4ed9cece14", size = 107092, upload-time = "2025-10-14T04:41:31.188Z" },
    { url = "https://files.pythonhosted.org/packages/af/8f/3ed4bfa0c0c72a7ca17f0380cd9e4dd842b09f664e780c13cff1dcf2ef1b/charset_normalizer-3.4.4-cp313-cp313-win_arm64.whl", hash = "sha256:542d2cee80be6f80247095cc36c418f7bddd14f4a6de45af91dfad36d817bba2", size = 100408, upload-time = "2025-10-14T04:41:32.624Z" },
    { url = "https://files.pythonhosted.org/packages/0a/4c/925909008ed5a988ccbb72dcc897407e5d6d3bd72410d69e051fc0c14647/charset_normalizer-3.4.4-py3-none-any.whl", hash = "sha256:7a32c560861a02ff789ad905a2fe94e3f840803362c84fecf1851cb4cf3dc37f", size = 53402, upload-time = "2025-10-14T04:42:31.76Z" },
]

[[package]]
name = "click"
version = "8.3.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "colorama", marker = "sys_platform == 'win32'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/3d/fa/656b739db8587d7b5dfa22e22ed02566950fbfbcdc20311993483657a5c0/click-8.3.1.tar.gz", hash = "sha256:12ff4785d337a1bb490bb7e9c2b1ee5da3112e94a8622f26a6c77f5d2fc6842a", size = 295065, upload-time = "2025-11-15T20:45:42.706Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/98/78/01c019cdb5d6498122777c1a43056ebb3ebfeef2076d9d026bfe15583b2b/click-8.3.1-py3-none-any.whl", hash = "sha256:981153a64e25f12d547d3426c367a4857371575ee7ad18df2a6183ab0545b2a6", size = 108274, upload-time = "2025-11-15T20:45:41.139Z" },
]

[[package]]
name = "colorama"
version = "0.4.6"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/d8/53/6f443c9a4a8358a93a6792e2acffb9d9d5cb0a5cfd8802644b7b1c9a02e4/colorama-0.4.6.tar.gz", hash = "sha256:08695f5cb7ed6e0531a20572697297273c47b8cae5a63ffc6d6ed5c201be6e44", size = 27697, upload-time = "2022-10-25T02:36:22.414Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/d1/d6/3965ed04c63042e047cb6a3e6ed1a63a35087b6a609aa3a15ed8ac56c221/colorama-0.4.6-py2.py3-none-any.whl", hash = "sha256:4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6", size = 25335, upload-time = "2022-10-25T02:36:20.889Z" },
]

[[package]]
name = "cryptography"
version = "46.0.5"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "cffi", marker = "platform_python_implementation != 'PyPy'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/60/04/ee2a9e8542e4fa2773b81771ff8349ff19cdd56b7258a0cc442639052edb/cryptography-46.0.5.tar.gz", hash = "sha256:abace499247268e3757271b2f1e244b36b06f8515cf27c4d49468fc9eb16e93d", size = 750064, upload-time = "2026-02-10T19:18:38.255Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/f7/81/b0bb27f2ba931a65409c6b8a8b358a7f03c0e46eceacddff55f7c84b1f3b/cryptography-46.0.5-cp311-abi3-macosx_10_9_universal2.whl", hash = "sha256:351695ada9ea9618b3500b490ad54c739860883df6c1f555e088eaf25b1bbaad", size = 7176289, upload-time = "2026-02-10T19:17:08.274Z" },
    { url = "https://files.pythonhosted.org/packages/ff/9e/6b4397a3e3d15123de3b1806ef342522393d50736c13b20ec4c9ea6693a6/cryptography-46.0.5-cp311-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.whl", hash = "sha256:c18ff11e86df2e28854939acde2d003f7984f721eba450b56a200ad90eeb0e6b", size = 4275637, upload-time = "2026-02-10T19:17:10.53Z" },
    { url = "https://files.pythonhosted.org/packages/63/e7/471ab61099a3920b0c77852ea3f0ea611c9702f651600397ac567848b897/cryptography-46.0.5-cp311-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:4d7e3d356b8cd4ea5aff04f129d5f66ebdc7b6f8eae802b93739ed520c47c79b", size = 4424742, upload-time = "2026-02-10T19:17:12.388Z" },
    { url = "https://files.pythonhosted.org/packages/37/53/a18500f270342d66bf7e4d9f091114e31e5ee9e7375a5aba2e85a91e0044/cryptography-46.0.5-cp311-abi3-manylinux_2_28_aarch64.whl", hash = "sha256:50bfb6925eff619c9c023b967d5b77a54e04256c4281b0e21336a130cd7fc263", size = 4277528, upload-time = "2026-02-10T19:17:13.853Z" },
    { url = "https://files.pythonhosted.org/packages/22/29/c2e812ebc38c57b40e7c583895e73c8c5adb4d1e4a0cc4c5a4fdab2b1acc/cryptography-46.0.5-cp311-abi3-manylinux_2_28_ppc64le.whl", hash = "sha256:803812e111e75d1aa73690d2facc295eaefd4439be1023fefc4995eaea2af90d", size = 4947993, upload-time = "2026-02-10T19:17:15.618Z" },
    { url = "https://files.pythonhosted.org/packages/6b/e7/237155ae19a9023de7e30ec64e5d99a9431a567407ac21170a046d22a5a3/cryptography-46.0.5-cp311-abi3-manylinux_2_28_x86_64.whl", hash = "sha256:3ee190460e2fbe447175cda91b88b84ae8322a104fc27766ad09428754a618ed", size = 4456855, upload-time = "2026-02-10T19:17:17.221Z" },
    { url = "https://files.pythonhosted.org/packages/2d/87/fc628a7ad85b81206738abbd213b07702bcbdada1dd43f72236ef3cffbb5/cryptography-46.0.5-cp311-abi3-manylinux_2_31_armv7l.whl", hash = "sha256:f145bba11b878005c496e93e257c1e88f154d278d2638e6450d17e0f31e558d2", size = 3984635, upload-time = "2026-02-10T19:17:18.792Z" },
    { url = "https://files.pythonhosted.org/packages/84/29/65b55622bde135aedf4565dc509d99b560ee4095e56989e815f8fd2aa910/cryptography-46.0.5-cp311-abi3-manylinux_2_34_aarch64.whl", hash = "sha256:e9251e3be159d1020c4030bd2e5f84d6a43fe54b6c19c12f51cde9542a2817b2", size = 4277038, upload-time = "2026-02-10T19:17:20.256Z" },
    { url = "https://files.pythonhosted.org/packages/bc/36/45e76c68d7311432741faf1fbf7fac8a196a0a735ca21f504c75d37e2558/cryptography-46.0.5-cp311-abi3-manylinux_2_34_ppc64le.whl", hash = "sha256:47fb8a66058b80e509c47118ef8a75d14c455e81ac369050f20ba0d23e77fee0", size = 4912181, upload-time = "2026-02-10T19:17:21.825Z" },
    { url = "https://files.pythonhosted.org/packages/6d/1a/c1ba8fead184d6e3d5afcf03d569acac5ad063f3ac9fb7258af158f7e378/cryptography-46.0.5-cp311-abi3-manylinux_2_34_x86_64.whl", hash = "sha256:4c3341037c136030cb46e4b1e17b7418ea4cbd9dd207e4a6f3b2b24e0d4ac731", size = 4456482, upload-time = "2026-02-10T19:17:25.133Z" },
    { url = "https://files.pythonhosted.org/packages/f9/e5/3fb22e37f66827ced3b902cf895e6a6bc1d095b5b26be26bd13c441fdf19/cryptography-46.0.5-cp311-abi3-musllinux_1_2_aarch64.whl", hash = "sha256:890bcb4abd5a2d3f852196437129eb3667d62630333aacc13dfd470fad3aaa82", size = 4405497, upload-time = "2026-02-10T19:17:26.66Z" },
    { url = "https://files.pythonhosted.org/packages/1a/df/9d58bb32b1121a8a2f27383fabae4d63080c7ca60b9b5c88be742be04ee7/cryptography-46.0.5-cp311-abi3-musllinux_1_2_x86_64.whl", hash = "sha256:80a8d7bfdf38f87ca30a5391c0c9ce4ed2926918e017c29ddf643d0ed2778ea1", size = 4667819, upload-time = "2026-02-10T19:17:28.569Z" },
    { url = "https://files.pythonhosted.org/packages/ea/ed/325d2a490c5e94038cdb0117da9397ece1f11201f425c4e9c57fe5b9f08b/cryptography-46.0.5-cp311-abi3-win32.whl", hash = "sha256:60ee7e19e95104d4c03871d7d7dfb3d22ef8a9b9c6778c94e1c8fcc8365afd48", size = 3028230, upload-time = "2026-02-10T19:17:30.518Z" },
    { url = "https://files.pythonhosted.org/packages/e9/5a/ac0f49e48063ab4255d9e3b79f5def51697fce1a95ea1370f03dc9db76f6/cryptography-46.0.5-cp311-abi3-win_amd64.whl", hash = "sha256:38946c54b16c885c72c4f59846be9743d699eee2b69b6988e0a00a01f46a61a4", size = 3480909, upload-time = "2026-02-10T19:17:32.083Z" },
    { url = "https://files.pythonhosted.org/packages/e2/fa/a66aa722105ad6a458bebd64086ca2b72cdd361fed31763d20390f6f1389/cryptography-46.0.5-cp38-abi3-macosx_10_9_universal2.whl", hash = "sha256:4108d4c09fbbf2789d0c926eb4152ae1760d5a2d97612b92d508d96c861e4d31", size = 7170514, upload-time = "2026-02-10T19:17:56.267Z" },
    { url = "https://files.pythonhosted.org/packages/0f/04/c85bdeab78c8bc77b701bf0d9bdcf514c044e18a46dcff330df5448631b0/cryptography-46.0.5-cp38-abi3-manylinux2014_aarch64.manylinux_2_17_aarch64.whl", hash = "sha256:7d1f30a86d2757199cb2d56e48cce14deddf1f9c95f1ef1b64ee91ea43fe2e18", size = 4275349, upload-time = "2026-02-10T19:17:58.419Z" },
    { url = "https://files.pythonhosted.org/packages/5c/32/9b87132a2f91ee7f5223b091dc963055503e9b442c98fc0b8a5ca765fab0/cryptography-46.0.5-cp38-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:039917b0dc418bb9f6edce8a906572d69e74bd330b0b3fea4f79dab7f8ddd235", size = 4420667, upload-time = "2026-02-10T19:18:00.619Z" },
    { url = "https://files.pythonhosted.org/packages/a1/a6/a7cb7010bec4b7c5692ca6f024150371b295ee1c108bdc1c400e4c44562b/cryptography-46.0.5-cp38-abi3-manylinux_2_28_aarch64.whl", hash = "sha256:ba2a27ff02f48193fc4daeadf8ad2590516fa3d0adeeb34336b96f7fa64c1e3a", size = 4276980, upload-time = "2026-02-10T19:18:02.379Z" },
    { url = "https://files.pythonhosted.org/packages/8e/7c/c4f45e0eeff9b91e3f12dbd0e165fcf2a38847288fcfd889deea99fb7b6d/cryptography-46.0.5-cp38-abi3-manylinux_2_28_ppc64le.whl", hash = "sha256:61aa400dce22cb001a98014f647dc21cda08f7915ceb95df0c9eaf84b4b6af76", size = 4939143, upload-time = "2026-02-10T19:18:03.964Z" },
    { url = "https://files.pythonhosted.org/packages/37/19/e1b8f964a834eddb44fa1b9a9976f4e414cbb7aa62809b6760c8803d22d1/cryptography-46.0.5-cp38-abi3-manylinux_2_28_x86_64.whl", hash = "sha256:3ce58ba46e1bc2aac4f7d9290223cead56743fa6ab94a5d53292ffaac6a91614", size = 4453674, upload-time = "2026-02-10T19:18:05.588Z" },
    { url = "https://files.pythonhosted.org/packages/db/ed/db15d3956f65264ca204625597c410d420e26530c4e2943e05a0d2f24d51/cryptography-46.0.5-cp38-abi3-manylinux_2_31_armv7l.whl", hash = "sha256:420d0e909050490d04359e7fdb5ed7e667ca5c3c402b809ae2563d7e66a92229", size = 3978801, upload-time = "2026-02-10T19:18:07.167Z" },
    { url = "https://files.pythonhosted.org/packages/41/e2/df40a31d82df0a70a0daf69791f91dbb70e47644c58581d654879b382d11/cryptography-46.0.5-cp38-abi3-manylinux_2_34_aarch64.whl", hash = "sha256:582f5fcd2afa31622f317f80426a027f30dc792e9c80ffee87b993200ea115f1", size = 4276755, upload-time = "2026-02-10T19:18:09.813Z" },
    { url = "https://files.pythonhosted.org/packages/33/45/726809d1176959f4a896b86907b98ff4391a8aa29c0aaaf9450a8a10630e/cryptography-46.0.5-cp38-abi3-manylinux_2_34_ppc64le.whl", hash = "sha256:bfd56bb4b37ed4f330b82402f6f435845a5f5648edf1ad497da51a8452d5d62d", size = 4901539, upload-time = "2026-02-10T19:18:11.263Z" },
    { url = "https://files.pythonhosted.org/packages/99/0f/a3076874e9c88ecb2ecc31382f6e7c21b428ede6f55aafa1aa272613e3cd/cryptography-46.0.5-cp38-abi3-manylinux_2_34_x86_64.whl", hash = "sha256:a3d507bb6a513ca96ba84443226af944b0f7f47dcc9a399d110cd6146481d24c", size = 4452794, upload-time = "2026-02-10T19:18:12.914Z" },
    { url = "https://files.pythonhosted.org/packages/02/ef/ffeb542d3683d24194a38f66ca17c0a4b8bf10631feef44a7ef64e631b1a/cryptography-46.0.5-cp38-abi3-musllinux_1_2_aarch64.whl", hash = "sha256:9f16fbdf4da055efb21c22d81b89f155f02ba420558db21288b3d0035bafd5f4", size = 4404160, upload-time = "2026-02-10T19:18:14.375Z" },
    { url = "https://files.pythonhosted.org/packages/96/93/682d2b43c1d5f1406ed048f377c0fc9fc8f7b0447a478d5c65ab3d3a66eb/cryptography-46.0.5-cp38-abi3-musllinux_1_2_x86_64.whl", hash = "sha256:ced80795227d70549a411a4ab66e8ce307899fad2220ce5ab2f296e687eacde9", size = 4667123, upload-time = "2026-02-10T19:18:15.886Z" },
    { url = "https://files.pythonhosted.org/packages/45/2d/9c5f2926cb5300a8eefc3f4f0b3f3df39db7f7ce40c8365444c49363cbda/cryptography-46.0.5-cp38-abi3-win32.whl", hash = "sha256:02f547fce831f5096c9a567fd41bc12ca8f11df260959ecc7c3202555cc47a72", size = 3010220, upload-time = "2026-02-10T19:18:17.361Z" },
    { url = "https://files.pythonhosted.org/packages/48/ef/0c2f4a8e31018a986949d34a01115dd057bf536905dca38897bacd21fac3/cryptography-46.0.5-cp38-abi3-win_amd64.whl", hash = "sha256:556e106ee01aa13484ce9b0239bca667be5004efb0aabbed28d353df86445595", size = 3467050, upload-time = "2026-02-10T19:18:18.899Z" },
]

[[package]]
name = "deepgram-sdk"
version = "5.3.2"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "httpx" },
    { name = "pydantic" },
    { name = "pydantic-core" },
    { name = "typing-extensions" },
    { name = "websockets" },
]
sdist = { url = "https://files.pythonhosted.org/packages/db/03/fe8cf3a3b5fe6d7bfbe8a1230a04e5e057bf391f5747a73aa8c1e8bf96b2/deepgram_sdk-5.3.2.tar.gz", hash = "sha256:bec6e956cb4bd9ab597b0ea9003d4ee1d364d714a65dc03372f769ab077610b3", size = 153072, upload-time = "2026-01-29T23:51:32.028Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/f8/c6/995349af0079c36fea632ffe056385095f1064cd499921bd0cea8bc79361/deepgram_sdk-5.3.2-py3-none-any.whl", hash = "sha256:c55fc2449dd82bc23a08215872d7e085142026e6f02a92332706ac8d6ce2c1ab", size = 391225, upload-time = "2026-01-29T23:51:30.325Z" },
]

[[package]]
name = "distro"
version = "1.9.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/fc/f8/98eea607f65de6527f8a2e8885fc8015d3e6f5775df186e443e0964a11c3/distro-1.9.0.tar.gz", hash = "sha256:2fa77c6fd8940f116ee1d6b94a2f90b13b5ea8d019b98bc8bafdcabcdd9bdbed", size = 60722, upload-time = "2023-12-24T09:54:32.31Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/12/b3/231ffd4ab1fc9d679809f356cebee130ac7daa00d6d6f3206dd4fd137e9e/distro-1.9.0-py3-none-any.whl", hash = "sha256:7bffd925d65168f85027d8da9af6bddab658135b840670a223589bc0c8ef02b2", size = 20277, upload-time = "2023-12-24T09:54:30.421Z" },
]

[[package]]
name = "fastapi"
version = "0.129.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "annotated-doc" },
    { name = "pydantic" },
    { name = "starlette" },
    { name = "typing-extensions" },
    { name = "typing-inspection" },
]
sdist = { url = "https://files.pythonhosted.org/packages/48/47/75f6bea02e797abff1bca968d5997793898032d9923c1935ae2efdece642/fastapi-0.129.0.tar.gz", hash = "sha256:61315cebd2e65df5f97ec298c888f9de30430dd0612d59d6480beafbc10655af", size = 375450, upload-time = "2026-02-12T13:54:52.541Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/9e/dd/d0ee25348ac58245ee9f90b6f3cbb666bf01f69be7e0911f9851bddbda16/fastapi-0.129.0-py3-none-any.whl", hash = "sha256:b4946880e48f462692b31c083be0432275cbfb6e2274566b1be91479cc1a84ec", size = 102950, upload-time = "2026-02-12T13:54:54.528Z" },
]

[[package]]
name = "ffmpy"
version = "1.0.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/7d/d2/1c4c582d71bcc65c76fa69fab85de6257d50fdf6fd4a2317c53917e9a581/ffmpy-1.0.0.tar.gz", hash = "sha256:b12932e95435c8820f1cd041024402765f821971e4bae753b327fc02a6e12f8b", size = 5101, upload-time = "2025-11-11T06:24:23.856Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/55/56/dd3669eccebb6d8ac81e624542ebd53fe6f08e1b8f2f8d50aeb7e3b83f99/ffmpy-1.0.0-py3-none-any.whl", hash = "sha256:5640e5f0fd03fb6236d0e119b16ccf6522db1c826fdf35dcb87087b60fd7504f", size = 5614, upload-time = "2025-11-11T06:24:22.818Z" },
]

[[package]]
name = "filelock"
version = "3.24.2"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/02/a8/dae62680be63cbb3ff87cfa2f51cf766269514ea5488479d42fec5aa6f3a/filelock-3.24.2.tar.gz", hash = "sha256:c22803117490f156e59fafce621f0550a7a853e2bbf4f87f112b11d469b6c81b", size = 37601, upload-time = "2026-02-16T02:50:45.614Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/e7/04/a94ebfb4eaaa08db56725a40de2887e95de4e8641b9e902c311bfa00aa39/filelock-3.24.2-py3-none-any.whl", hash = "sha256:667d7dc0b7d1e1064dd5f8f8e80bdac157a6482e8d2e02cd16fd3b6b33bd6556", size = 24152, upload-time = "2026-02-16T02:50:44Z" },
]

[[package]]
name = "filetype"
version = "1.2.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/bb/29/745f7d30d47fe0f251d3ad3dc2978a23141917661998763bebb6da007eb1/filetype-1.2.0.tar.gz", hash = "sha256:66b56cd6474bf41d8c54660347d37afcc3f7d1970648de365c102ef77548aadb", size = 998020, upload-time = "2022-11-02T17:34:04.141Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/18/79/1b8fa1bb3568781e84c9200f951c735f3f157429f44be0495da55894d620/filetype-1.2.0-py2.py3-none-any.whl", hash = "sha256:7ce71b6880181241cf7ac8697a2f1eb6a8bd9b429f7ad6d27b8db9ba5f1c2d25", size = 19970, upload-time = "2022-11-02T17:34:01.425Z" },
]

[[package]]
name = "fsspec"
version = "2026.2.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/51/7c/f60c259dcbf4f0c47cc4ddb8f7720d2dcdc8888c8e5ad84c73ea4531cc5b/fsspec-2026.2.0.tar.gz", hash = "sha256:6544e34b16869f5aacd5b90bdf1a71acb37792ea3ddf6125ee69a22a53fb8bff", size = 313441, upload-time = "2026-02-05T21:50:53.743Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/e6/ab/fb21f4c939bb440104cc2b396d3be1d9b7a9fd3c6c2a53d98c45b3d7c954/fsspec-2026.2.0-py3-none-any.whl", hash = "sha256:98de475b5cb3bd66bedd5c4679e87b4fdfe1a3bf4d707b151b3c07e58c9a2437", size = 202505, upload-time = "2026-02-05T21:50:51.819Z" },
]

[[package]]
name = "google-auth"
version = "2.48.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "cryptography" },
    { name = "pyasn1-modules" },
    { name = "rsa" },
]
sdist = { url = "https://files.pythonhosted.org/packages/0c/41/242044323fbd746615884b1c16639749e73665b718209946ebad7ba8a813/google_auth-2.48.0.tar.gz", hash = "sha256:4f7e706b0cd3208a3d940a19a822c37a476ddba5450156c3e6624a71f7c841ce", size = 326522, upload-time = "2026-01-26T19:22:47.157Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/83/1d/d6466de3a5249d35e832a52834115ca9d1d0de6abc22065f049707516d47/google_auth-2.48.0-py3-none-any.whl", hash = "sha256:2e2a537873d449434252a9632c28bfc268b0adb1e53f9fb62afc5333a975903f", size = 236499, upload-time = "2026-01-26T19:22:45.099Z" },
]

[package.optional-dependencies]
requests = [
    { name = "requests" },
]

[[package]]
name = "google-genai"
version = "1.63.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "anyio" },
    { name = "distro" },
    { name = "google-auth", extra = ["requests"] },
    { name = "httpx" },
    { name = "pydantic" },
    { name = "requests" },
    { name = "sniffio" },
    { name = "tenacity" },
    { name = "typing-extensions" },
    { name = "websockets" },
]
sdist = { url = "https://files.pythonhosted.org/packages/46/d7/07ec5dadd0741f09e89f3ff5f0ce051ce2aa3a76797699d661dc88def077/google_genai-1.63.0.tar.gz", hash = "sha256:dc76cab810932df33cbec6c7ef3ce1538db5bef27aaf78df62ac38666c476294", size = 491970, upload-time = "2026-02-11T23:46:28.472Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/82/c8/ba32159e553fab787708c612cf0c3a899dafe7aca81115d841766e3bfe69/google_genai-1.63.0-py3-none-any.whl", hash = "sha256:6206c13fc20f332703ca7375bea7c191c82f95d6781c29936c6982d86599b359", size = 724747, upload-time = "2026-02-11T23:46:26.697Z" },
]

[[package]]
name = "gradio"
version = "6.6.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "aiofiles" },
    { name = "anyio" },
    { name = "audioop-lts" },
    { name = "brotli" },
    { name = "fastapi" },
    { name = "ffmpy" },
    { name = "gradio-client" },
    { name = "groovy" },
    { name = "httpx" },
    { name = "huggingface-hub" },
    { name = "jinja2" },
    { name = "markupsafe" },
    { name = "numpy" },
    { name = "orjson" },
    { name = "packaging" },
    { name = "pandas" },
    { name = "pillow" },
    { name = "pydantic" },
    { name = "pydub" },
    { name = "python-multipart" },
    { name = "pytz" },
    { name = "pyyaml" },
    { name = "safehttpx" },
    { name = "semantic-version" },
    { name = "starlette" },
    { name = "tomlkit" },
    { name = "typer" },
    { name = "typing-extensions" },
    { name = "uvicorn" },
]
sdist = { url = "https://files.pythonhosted.org/packages/11/f8/81a453b139935b70bf54efd1f4ce2be9be491ab638d907d0a94fd73af1a0/gradio-6.6.0.tar.gz", hash = "sha256:1c6c76dcc725a32c2a9e2b8732db935513c519694f9f9e2472a4e2ecc0075539", size = 40104446, upload-time = "2026-02-17T22:33:00.671Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/86/1b/2c79424d17bd2240c5292597f81c5def69b3e8ae35eaa6f86ca783d21118/gradio-6.6.0-py3-none-any.whl", hash = "sha256:c6ed21ecb757dca5cce1d074e4cae5cf3e72ca98ea00cbcd4fda62a7880ac4e0", size = 24150475, upload-time = "2026-02-17T22:32:57.131Z" },
]

[[package]]
name = "gradio-client"
version = "2.1.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "fsspec" },
    { name = "httpx" },
    { name = "huggingface-hub" },
    { name = "packaging" },
    { name = "typing-extensions" },
]
sdist = { url = "https://files.pythonhosted.org/packages/84/b2/3ce826ddf275677324970ea09357d6854b2a09a8b85f4e0050c38ae3888e/gradio_client-2.1.0.tar.gz", hash = "sha256:779c2e53ebbeea92cb3c3945c37d75ae2b6464995b8e435dd7df1a769934df54", size = 55369, upload-time = "2026-02-17T22:33:11.937Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/83/c0/dbb8a7b9b6291b81d5d95057c81d555bdd189889d4a0f22e4da2b87561f5/gradio_client-2.1.0-py3-none-any.whl", hash = "sha256:40cdf3bae609e1ba95da4b97156748f752feb183323b5d2847f96483147cbccf", size = 55989, upload-time = "2026-02-17T22:33:10.321Z" },
]

[[package]]
name = "groovy"
version = "0.1.2"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/52/36/bbdede67400277bef33d3ec0e6a31750da972c469f75966b4930c753218f/groovy-0.1.2.tar.gz", hash = "sha256:25c1dc09b3f9d7e292458aa762c6beb96ea037071bf5e917fc81fb78d2231083", size = 17325, upload-time = "2025-02-28T20:24:56.068Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/28/27/3d6dcadc8a3214d8522c1e7f6a19554e33659be44546d44a2f7572ac7d2a/groovy-0.1.2-py3-none-any.whl", hash = "sha256:7f7975bab18c729a257a8b1ae9dcd70b7cafb1720481beae47719af57c35fa64", size = 14090, upload-time = "2025-02-28T20:24:55.152Z" },
]

[[package]]
name = "h11"
version = "0.16.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/01/ee/02a2c011bdab74c6fb3c75474d40b3052059d95df7e73351460c8588d963/h11-0.16.0.tar.gz", hash = "sha256:4e35b956cf45792e4caa5885e69fba00bdbc6ffafbfa020300e549b208ee5ff1", size = 101250, upload-time = "2025-04-24T03:35:25.427Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/04/4b/29cac41a4d98d144bf5f6d33995617b185d14b22401f75ca86f384e87ff1/h11-0.16.0-py3-none-any.whl", hash = "sha256:63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86", size = 37515, upload-time = "2025-04-24T03:35:24.344Z" },
]

[[package]]
name = "hf-xet"
version = "1.2.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/5e/6e/0f11bacf08a67f7fb5ee09740f2ca54163863b07b70d579356e9222ce5d8/hf_xet-1.2.0.tar.gz", hash = "sha256:a8c27070ca547293b6890c4bf389f713f80e8c478631432962bb7f4bc0bd7d7f", size = 506020, upload-time = "2025-10-24T19:04:32.129Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/9e/a5/85ef910a0aa034a2abcfadc360ab5ac6f6bc4e9112349bd40ca97551cff0/hf_xet-1.2.0-cp313-cp313t-macosx_10_12_x86_64.whl", hash = "sha256:ceeefcd1b7aed4956ae8499e2199607765fbd1c60510752003b6cc0b8413b649", size = 2861870, upload-time = "2025-10-24T19:04:11.422Z" },
    { url = "https://files.pythonhosted.org/packages/ea/40/e2e0a7eb9a51fe8828ba2d47fe22a7e74914ea8a0db68a18c3aa7449c767/hf_xet-1.2.0-cp313-cp313t-macosx_11_0_arm64.whl", hash = "sha256:b70218dd548e9840224df5638fdc94bd033552963cfa97f9170829381179c813", size = 2717584, upload-time = "2025-10-24T19:04:09.586Z" },
    { url = "https://files.pythonhosted.org/packages/a5/7d/daf7f8bc4594fdd59a8a596f9e3886133fdc68e675292218a5e4c1b7e834/hf_xet-1.2.0-cp313-cp313t-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:7d40b18769bb9a8bc82a9ede575ce1a44c75eb80e7375a01d76259089529b5dc", size = 3315004, upload-time = "2025-10-24T19:04:00.314Z" },
    { url = "https://files.pythonhosted.org/packages/b1/ba/45ea2f605fbf6d81c8b21e4d970b168b18a53515923010c312c06cd83164/hf_xet-1.2.0-cp313-cp313t-manylinux_2_28_aarch64.whl", hash = "sha256:cd3a6027d59cfb60177c12d6424e31f4b5ff13d8e3a1247b3a584bf8977e6df5", size = 3222636, upload-time = "2025-10-24T19:03:58.111Z" },
    { url = "https://files.pythonhosted.org/packages/4a/1d/04513e3cab8f29ab8c109d309ddd21a2705afab9d52f2ba1151e0c14f086/hf_xet-1.2.0-cp313-cp313t-musllinux_1_2_aarch64.whl", hash = "sha256:6de1fc44f58f6dd937956c8d304d8c2dea264c80680bcfa61ca4a15e7b76780f", size = 3408448, upload-time = "2025-10-24T19:04:20.951Z" },
    { url = "https://files.pythonhosted.org/packages/f0/7c/60a2756d7feec7387db3a1176c632357632fbe7849fce576c5559d4520c7/hf_xet-1.2.0-cp313-cp313t-musllinux_1_2_x86_64.whl", hash = "sha256:f182f264ed2acd566c514e45da9f2119110e48a87a327ca271027904c70c5832", size = 3503401, upload-time = "2025-10-24T19:04:22.549Z" },
    { url = "https://files.pythonhosted.org/packages/4e/64/48fffbd67fb418ab07451e4ce641a70de1c40c10a13e25325e24858ebe5a/hf_xet-1.2.0-cp313-cp313t-win_amd64.whl", hash = "sha256:293a7a3787e5c95d7be1857358a9130694a9c6021de3f27fa233f37267174382", size = 2900866, upload-time = "2025-10-24T19:04:33.461Z" },
    { url = "https://files.pythonhosted.org/packages/96/2d/22338486473df5923a9ab7107d375dbef9173c338ebef5098ef593d2b560/hf_xet-1.2.0-cp37-abi3-macosx_10_12_x86_64.whl", hash = "sha256:46740d4ac024a7ca9b22bebf77460ff43332868b661186a8e46c227fdae01848", size = 2866099, upload-time = "2025-10-24T19:04:15.366Z" },
    { url = "https://files.pythonhosted.org/packages/7f/8c/c5becfa53234299bc2210ba314eaaae36c2875e0045809b82e40a9544f0c/hf_xet-1.2.0-cp37-abi3-macosx_11_0_arm64.whl", hash = "sha256:27df617a076420d8845bea087f59303da8be17ed7ec0cd7ee3b9b9f579dff0e4", size = 2722178, upload-time = "2025-10-24T19:04:13.695Z" },
    { url = "https://files.pythonhosted.org/packages/9a/92/cf3ab0b652b082e66876d08da57fcc6fa2f0e6c70dfbbafbd470bb73eb47/hf_xet-1.2.0-cp37-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:3651fd5bfe0281951b988c0facbe726aa5e347b103a675f49a3fa8144c7968fd", size = 3320214, upload-time = "2025-10-24T19:04:03.596Z" },
    { url = "https://files.pythonhosted.org/packages/46/92/3f7ec4a1b6a65bf45b059b6d4a5d38988f63e193056de2f420137e3c3244/hf_xet-1.2.0-cp37-abi3-manylinux_2_28_aarch64.whl", hash = "sha256:d06fa97c8562fb3ee7a378dd9b51e343bc5bc8190254202c9771029152f5e08c", size = 3229054, upload-time = "2025-10-24T19:04:01.949Z" },
    { url = "https://files.pythonhosted.org/packages/0b/dd/7ac658d54b9fb7999a0ccb07ad863b413cbaf5cf172f48ebcd9497ec7263/hf_xet-1.2.0-cp37-abi3-musllinux_1_2_aarch64.whl", hash = "sha256:4c1428c9ae73ec0939410ec73023c4f842927f39db09b063b9482dac5a3bb737", size = 3413812, upload-time = "2025-10-24T19:04:24.585Z" },
    { url = "https://files.pythonhosted.org/packages/92/68/89ac4e5b12a9ff6286a12174c8538a5930e2ed662091dd2572bbe0a18c8a/hf_xet-1.2.0-cp37-abi3-musllinux_1_2_x86_64.whl", hash = "sha256:a55558084c16b09b5ed32ab9ed38421e2d87cf3f1f89815764d1177081b99865", size = 3508920, upload-time = "2025-10-24T19:04:26.927Z" },
    { url = "https://files.pythonhosted.org/packages/cb/44/870d44b30e1dcfb6a65932e3e1506c103a8a5aea9103c337e7a53180322c/hf_xet-1.2.0-cp37-abi3-win_amd64.whl", hash = "sha256:e6584a52253f72c9f52f9e549d5895ca7a471608495c4ecaa6cc73dba2b24d69", size = 2905735, upload-time = "2025-10-24T19:04:35.928Z" },
]

[[package]]
name = "httpcore"
version = "1.0.9"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "certifi" },
    { name = "h11" },
]
sdist = { url = "https://files.pythonhosted.org/packages/06/94/82699a10bca87a5556c9c59b5963f2d039dbd239f25bc2a63907a05a14cb/httpcore-1.0.9.tar.gz", hash = "sha256:6e34463af53fd2ab5d807f399a9b45ea31c3dfa2276f15a2c3f00afff6e176e8", size = 85484, upload-time = "2025-04-24T22:06:22.219Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/7e/f5/f66802a942d491edb555dd61e3a9961140fd64c90bce1eafd741609d334d/httpcore-1.0.9-py3-none-any.whl", hash = "sha256:2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55", size = 78784, upload-time = "2025-04-24T22:06:20.566Z" },
]

[[package]]
name = "httpx"
version = "0.28.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "anyio" },
    { name = "certifi" },
    { name = "httpcore" },
    { name = "idna" },
]
sdist = { url = "https://files.pythonhosted.org/packages/b1/df/48c586a5fe32a0f01324ee087459e112ebb7224f646c0b5023f5e79e9956/httpx-0.28.1.tar.gz", hash = "sha256:75e98c5f16b0f35b567856f597f06ff2270a374470a5c2392242528e3e3e42fc", size = 141406, upload-time = "2024-12-06T15:37:23.222Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/2a/39/e50c7c3a983047577ee07d2a9e53faf5a69493943ec3f6a384bdc792deb2/httpx-0.28.1-py3-none-any.whl", hash = "sha256:d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad", size = 73517, upload-time = "2024-12-06T15:37:21.509Z" },
]

[[package]]
name = "huggingface-hub"
version = "1.4.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "filelock" },
    { name = "fsspec" },
    { name = "hf-xet", marker = "platform_machine == 'AMD64' or platform_machine == 'aarch64' or platform_machine == 'amd64' or platform_machine == 'arm64' or platform_machine == 'x86_64'" },
    { name = "httpx" },
    { name = "packaging" },
    { name = "pyyaml" },
    { name = "shellingham" },
    { name = "tqdm" },
    { name = "typer-slim" },
    { name = "typing-extensions" },
]
sdist = { url = "https://files.pythonhosted.org/packages/c4/fc/eb9bc06130e8bbda6a616e1b80a7aa127681c448d6b49806f61db2670b61/huggingface_hub-1.4.1.tar.gz", hash = "sha256:b41131ec35e631e7383ab26d6146b8d8972abc8b6309b963b306fbcca87f5ed5", size = 642156, upload-time = "2026-02-06T09:20:03.013Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/d5/ae/2f6d96b4e6c5478d87d606a1934b5d436c4a2bce6bb7c6fdece891c128e3/huggingface_hub-1.4.1-py3-none-any.whl", hash = "sha256:9931d075fb7a79af5abc487106414ec5fba2c0ae86104c0c62fd6cae38873d18", size = 553326, upload-time = "2026-02-06T09:20:00.728Z" },
]

[[package]]
name = "idna"
version = "3.11"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/6f/6d/0703ccc57f3a7233505399edb88de3cbd678da106337b9fcde432b65ed60/idna-3.11.tar.gz", hash = "sha256:795dafcc9c04ed0c1fb032c2aa73654d8e8c5023a7df64a53f39190ada629902", size = 194582, upload-time = "2025-10-12T14:55:20.501Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/0e/61/66938bbb5fc52dbdf84594873d5b51fb1f7c7794e9c0f5bd885f30bc507b/idna-3.11-py3-none-any.whl", hash = "sha256:771a87f49d9defaf64091e6e6fe9c18d4833f140bd19464795bc32d966ca37ea", size = 71008, upload-time = "2025-10-12T14:55:18.883Z" },
]

[[package]]
name = "iniconfig"
version = "2.3.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/72/34/14ca021ce8e5dfedc35312d08ba8bf51fdd999c576889fc2c24cb97f4f10/iniconfig-2.3.0.tar.gz", hash = "sha256:c76315c77db068650d49c5b56314774a7804df16fee4402c1f19d6d15d8c4730", size = 20503, upload-time = "2025-10-18T21:55:43.219Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/cb/b1/3846dd7f199d53cb17f49cba7e651e9ce294d8497c8c150530ed11865bb8/iniconfig-2.3.0-py3-none-any.whl", hash = "sha256:f631c04d2c48c52b84d0d0549c99ff3859c98df65b3101406327ecc7d53fbf12", size = 7484, upload-time = "2025-10-18T21:55:41.639Z" },
]

[[package]]
name = "jinja2"
version = "3.1.6"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "markupsafe" },
]
sdist = { url = "https://files.pythonhosted.org/packages/df/bf/f7da0350254c0ed7c72f3e33cef02e048281fec7ecec5f032d4aac52226b/jinja2-3.1.6.tar.gz", hash = "sha256:0137fb05990d35f1275a587e9aee6d56da821fc83491a0fb838183be43f66d6d", size = 245115, upload-time = "2025-03-05T20:05:02.478Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/62/a1/3d680cbfd5f4b8f15abc1d571870c5fc3e594bb582bc3b64ea099db13e56/jinja2-3.1.6-py3-none-any.whl", hash = "sha256:85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67", size = 134899, upload-time = "2025-03-05T20:05:00.369Z" },
]

[[package]]
name = "jiter"
version = "0.13.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/0d/5e/4ec91646aee381d01cdb9974e30882c9cd3b8c5d1079d6b5ff4af522439a/jiter-0.13.0.tar.gz", hash = "sha256:f2839f9c2c7e2dffc1bc5929a510e14ce0a946be9365fd1219e7ef342dae14f4", size = 164847, upload-time = "2026-02-02T12:37:56.441Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/91/9c/7ee5a6ff4b9991e1a45263bfc46731634c4a2bde27dfda6c8251df2d958c/jiter-0.13.0-cp313-cp313-macosx_10_12_x86_64.whl", hash = "sha256:1f8a55b848cbabf97d861495cd65f1e5c590246fabca8b48e1747c4dfc8f85bf", size = 306897, upload-time = "2026-02-02T12:36:16.748Z" },
    { url = "https://files.pythonhosted.org/packages/7c/02/be5b870d1d2be5dd6a91bdfb90f248fbb7dcbd21338f092c6b89817c3dbf/jiter-0.13.0-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:f556aa591c00f2c45eb1b89f68f52441a016034d18b65da60e2d2875bbbf344a", size = 317507, upload-time = "2026-02-02T12:36:18.351Z" },
    { url = "https://files.pythonhosted.org/packages/da/92/b25d2ec333615f5f284f3a4024f7ce68cfa0604c322c6808b2344c7f5d2b/jiter-0.13.0-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:f7e1d61da332ec412350463891923f960c3073cf1aae93b538f0bb4c8cd46efb", size = 350560, upload-time = "2026-02-02T12:36:19.746Z" },
    { url = "https://files.pythonhosted.org/packages/be/ec/74dcb99fef0aca9fbe56b303bf79f6bd839010cb18ad41000bf6cc71eec0/jiter-0.13.0-cp313-cp313-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:3097d665a27bc96fd9bbf7f86178037db139f319f785e4757ce7ccbf390db6c2", size = 363232, upload-time = "2026-02-02T12:36:21.243Z" },
    { url = "https://files.pythonhosted.org/packages/1b/37/f17375e0bb2f6a812d4dd92d7616e41917f740f3e71343627da9db2824ce/jiter-0.13.0-cp313-cp313-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:9d01ecc3a8cbdb6f25a37bd500510550b64ddf9f7d64a107d92f3ccb25035d0f", size = 483727, upload-time = "2026-02-02T12:36:22.688Z" },
    { url = "https://files.pythonhosted.org/packages/77/d2/a71160a5ae1a1e66c1395b37ef77da67513b0adba73b993a27fbe47eb048/jiter-0.13.0-cp313-cp313-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:ed9bbc30f5d60a3bdf63ae76beb3f9db280d7f195dfcfa61af792d6ce912d159", size = 370799, upload-time = "2026-02-02T12:36:24.106Z" },
    { url = "https://files.pythonhosted.org/packages/01/99/ed5e478ff0eb4e8aa5fd998f9d69603c9fd3f32de3bd16c2b1194f68361c/jiter-0.13.0-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:98fbafb6e88256f4454de33c1f40203d09fc33ed19162a68b3b257b29ca7f663", size = 359120, upload-time = "2026-02-02T12:36:25.519Z" },
    { url = "https://files.pythonhosted.org/packages/16/be/7ffd08203277a813f732ba897352797fa9493faf8dc7995b31f3d9cb9488/jiter-0.13.0-cp313-cp313-manylinux_2_5_i686.manylinux1_i686.whl", hash = "sha256:5467696f6b827f1116556cb0db620440380434591e93ecee7fd14d1a491b6daa", size = 390664, upload-time = "2026-02-02T12:36:26.866Z" },
    { url = "https://files.pythonhosted.org/packages/d1/84/e0787856196d6d346264d6dcccb01f741e5f0bd014c1d9a2ebe149caf4f3/jiter-0.13.0-cp313-cp313-musllinux_1_1_aarch64.whl", hash = "sha256:2d08c9475d48b92892583df9da592a0e2ac49bcd41fae1fec4f39ba6cf107820", size = 513543, upload-time = "2026-02-02T12:36:28.217Z" },
    { url = "https://files.pythonhosted.org/packages/65/50/ecbd258181c4313cf79bca6c88fb63207d04d5bf5e4f65174114d072aa55/jiter-0.13.0-cp313-cp313-musllinux_1_1_x86_64.whl", hash = "sha256:aed40e099404721d7fcaf5b89bd3b4568a4666358bcac7b6b15c09fb6252ab68", size = 547262, upload-time = "2026-02-02T12:36:29.678Z" },
    { url = "https://files.pythonhosted.org/packages/27/da/68f38d12e7111d2016cd198161b36e1f042bd115c169255bcb7ec823a3bf/jiter-0.13.0-cp313-cp313-win32.whl", hash = "sha256:36ebfbcffafb146d0e6ffb3e74d51e03d9c35ce7c625c8066cdbfc7b953bdc72", size = 200630, upload-time = "2026-02-02T12:36:31.808Z" },
    { url = "https://files.pythonhosted.org/packages/25/65/3bd1a972c9a08ecd22eb3b08a95d1941ebe6938aea620c246cf426ae09c2/jiter-0.13.0-cp313-cp313-win_amd64.whl", hash = "sha256:8d76029f077379374cf0dbc78dbe45b38dec4a2eb78b08b5194ce836b2517afc", size = 202602, upload-time = "2026-02-02T12:36:33.679Z" },
    { url = "https://files.pythonhosted.org/packages/15/fe/13bd3678a311aa67686bb303654792c48206a112068f8b0b21426eb6851e/jiter-0.13.0-cp313-cp313-win_arm64.whl", hash = "sha256:bb7613e1a427cfcb6ea4544f9ac566b93d5bf67e0d48c787eca673ff9c9dff2b", size = 185939, upload-time = "2026-02-02T12:36:35.065Z" },
    { url = "https://files.pythonhosted.org/packages/49/19/a929ec002ad3228bc97ca01dbb14f7632fffdc84a95ec92ceaf4145688ae/jiter-0.13.0-cp313-cp313t-macosx_11_0_arm64.whl", hash = "sha256:fa476ab5dd49f3bf3a168e05f89358c75a17608dbabb080ef65f96b27c19ab10", size = 316616, upload-time = "2026-02-02T12:36:36.579Z" },
    { url = "https://files.pythonhosted.org/packages/52/56/d19a9a194afa37c1728831e5fb81b7722c3de18a3109e8f282bfc23e587a/jiter-0.13.0-cp313-cp313t-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:ade8cb6ff5632a62b7dbd4757d8c5573f7a2e9ae285d6b5b841707d8363205ef", size = 346850, upload-time = "2026-02-02T12:36:38.058Z" },
    { url = "https://files.pythonhosted.org/packages/36/4a/94e831c6bf287754a8a019cb966ed39ff8be6ab78cadecf08df3bb02d505/jiter-0.13.0-cp313-cp313t-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:9950290340acc1adaded363edd94baebcee7dabdfa8bee4790794cd5cfad2af6", size = 358551, upload-time = "2026-02-02T12:36:39.417Z" },
    { url = "https://files.pythonhosted.org/packages/a2/ec/a4c72c822695fa80e55d2b4142b73f0012035d9fcf90eccc56bc060db37c/jiter-0.13.0-cp313-cp313t-win_amd64.whl", hash = "sha256:2b4972c6df33731aac0742b64fd0d18e0a69bc7d6e03108ce7d40c85fd9e3e6d", size = 201950, upload-time = "2026-02-02T12:36:40.791Z" },
    { url = "https://files.pythonhosted.org/packages/b6/00/393553ec27b824fbc29047e9c7cd4a3951d7fbe4a76743f17e44034fa4e4/jiter-0.13.0-cp313-cp313t-win_arm64.whl", hash = "sha256:701a1e77d1e593c1b435315ff625fd071f0998c5f02792038a5ca98899261b7d", size = 185852, upload-time = "2026-02-02T12:36:42.077Z" },
]

[[package]]
name = "jsonpatch"
version = "1.33"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "jsonpointer" },
]
sdist = { url = "https://files.pythonhosted.org/packages/42/78/18813351fe5d63acad16aec57f94ec2b70a09e53ca98145589e185423873/jsonpatch-1.33.tar.gz", hash = "sha256:9fcd4009c41e6d12348b4a0ff2563ba56a2923a7dfee731d004e212e1ee5030c", size = 21699, upload-time = "2023-06-26T12:07:29.144Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/73/07/02e16ed01e04a374e644b575638ec7987ae846d25ad97bcc9945a3ee4b0e/jsonpatch-1.33-py2.py3-none-any.whl", hash = "sha256:0ae28c0cd062bbd8b8ecc26d7d164fbbea9652a1a3693f3b956c1eae5145dade", size = 12898, upload-time = "2023-06-16T21:01:28.466Z" },
]

[[package]]
name = "jsonpointer"
version = "3.0.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/6a/0a/eebeb1fa92507ea94016a2a790b93c2ae41a7e18778f85471dc54475ed25/jsonpointer-3.0.0.tar.gz", hash = "sha256:2b2d729f2091522d61c3b31f82e11870f60b68f43fbc705cb76bf4b832af59ef", size = 9114, upload-time = "2024-06-10T19:24:42.462Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/71/92/5e77f98553e9e75130c78900d000368476aed74276eb8ae8796f65f00918/jsonpointer-3.0.0-py2.py3-none-any.whl", hash = "sha256:13e088adc14fca8b6aa8177c044e12701e6ad4b28ff10e65f2267a90109c9942", size = 7595, upload-time = "2024-06-10T19:24:40.698Z" },
]

[[package]]
name = "langchain"
version = "1.2.10"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "langchain-core" },
    { name = "langgraph" },
    { name = "pydantic" },
]
sdist = { url = "https://files.pythonhosted.org/packages/16/22/a4d4ac98fc2e393537130bbfba0d71a8113e6f884d96f935923e247397fe/langchain-1.2.10.tar.gz", hash = "sha256:bdcd7218d9c79a413cf15e106e4eb94408ac0963df9333ccd095b9ed43bf3be7", size = 570071, upload-time = "2026-02-10T14:56:49.74Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/7c/06/c3394327f815fade875724c0f6cff529777c96a1e17fea066deb997f8cf5/langchain-1.2.10-py3-none-any.whl", hash = "sha256:e07a377204451fffaed88276b8193e894893b1003e25c5bca6539288ccca3698", size = 111738, upload-time = "2026-02-10T14:56:47.985Z" },
]

[[package]]
name = "langchain-core"
version = "1.2.13"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "jsonpatch" },
    { name = "langsmith" },
    { name = "packaging" },
    { name = "pydantic" },
    { name = "pyyaml" },
    { name = "tenacity" },
    { name = "typing-extensions" },
    { name = "uuid-utils" },
]
sdist = { url = "https://files.pythonhosted.org/packages/fb/bb/c501ca60556c11ac80d1454bdcac63cb33583ce4e64fc4535ad5a7d5c6ba/langchain_core-1.2.13.tar.gz", hash = "sha256:d2773d0d0130a356378db9a858cfeef64c3d64bc03722f1d4d6c40eb46fdf01b", size = 831612, upload-time = "2026-02-15T07:45:57.014Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/12/ab/60fd69e5d55f67d422baefddaaca523c42cd7510ab6aeb17db6ae57fb107/langchain_core-1.2.13-py3-none-any.whl", hash = "sha256:b31823e28d3eff1e237096d0bd3bf80c6f9624eb471a9496dbfbd427779f8d82", size = 500485, upload-time = "2026-02-15T07:45:55.422Z" },
]

[[package]]
name = "langchain-google-genai"
version = "4.2.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "filetype" },
    { name = "google-genai" },
    { name = "langchain-core" },
    { name = "pydantic" },
]
sdist = { url = "https://files.pythonhosted.org/packages/d8/0b/eae2305e207574dc633983a8a82a745e0ede1bce1f3a9daff24d2341fadc/langchain_google_genai-4.2.0.tar.gz", hash = "sha256:9a8d9bfc35354983ed29079cefff53c3e7c9c2a44b6ba75cc8f13a0cf8b55c33", size = 277361, upload-time = "2026-01-13T20:41:17.63Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/22/51/39942c0083139652494bb354dddf0ed397703a4882302f7b48aeca531c96/langchain_google_genai-4.2.0-py3-none-any.whl", hash = "sha256:856041aaafceff65a4ef0d5acf5731f2db95229ff041132af011aec51e8279d9", size = 66452, upload-time = "2026-01-13T20:41:16.296Z" },
]

[[package]]
name = "langchain-openai"
version = "1.1.10"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "langchain-core" },
    { name = "openai" },
    { name = "tiktoken" },
]
sdist = { url = "https://files.pythonhosted.org/packages/d6/0f/01147f842499338ae3b0dd0a351fb83006d9ed623cf3a999bd68ba5bbe2d/langchain_openai-1.1.10.tar.gz", hash = "sha256:ca6fae7cf19425acc81814efed59c7d205ec9a1f284fd1d08aae9bda85d6501b", size = 1059755, upload-time = "2026-02-17T18:03:44.506Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/72/17/3785cbcdc81c451179247e4176d2697879cb4f45ab2c59d949ca574e072d/langchain_openai-1.1.10-py3-none-any.whl", hash = "sha256:d91b2c09e9fbc70f7af45345d3aa477744962d41c73a029beb46b4f83b824827", size = 87205, upload-time = "2026-02-17T18:03:43.502Z" },
]

[[package]]
name = "langgraph"
version = "1.0.8"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "langchain-core" },
    { name = "langgraph-checkpoint" },
    { name = "langgraph-prebuilt" },
    { name = "langgraph-sdk" },
    { name = "pydantic" },
    { name = "xxhash" },
]
sdist = { url = "https://files.pythonhosted.org/packages/ca/49/e9551965d8a44dd9afdc55cbcdc5a9bd18bee6918cc2395b225d40adb77c/langgraph-1.0.8.tar.gz", hash = "sha256:2630fc578846995114fd659f8b14df9eff5a4e78c49413f67718725e88ceb544", size = 498708, upload-time = "2026-02-06T12:31:13.776Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/9a/72/b0d7fc1007821a08dfc03ce232f39f209aa4aa46414ea3d125b24e35093a/langgraph-1.0.8-py3-none-any.whl", hash = "sha256:da737177c024caad7e5262642bece4f54edf4cba2c905a1d1338963f41cf0904", size = 158144, upload-time = "2026-02-06T12:31:12.489Z" },
]

[[package]]
name = "langgraph-checkpoint"
version = "4.0.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "langchain-core" },
    { name = "ormsgpack" },
]
sdist = { url = "https://files.pythonhosted.org/packages/98/76/55a18c59dedf39688d72c4b06af73a5e3ea0d1a01bc867b88fbf0659f203/langgraph_checkpoint-4.0.0.tar.gz", hash = "sha256:814d1bd050fac029476558d8e68d87bce9009a0262d04a2c14b918255954a624", size = 137320, upload-time = "2026-01-12T20:30:26.38Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/4a/de/ddd53b7032e623f3c7bcdab2b44e8bf635e468f62e10e5ff1946f62c9356/langgraph_checkpoint-4.0.0-py3-none-any.whl", hash = "sha256:3fa9b2635a7c5ac28b338f631abf6a030c3b508b7b9ce17c22611513b589c784", size = 46329, upload-time = "2026-01-12T20:30:25.2Z" },
]

[[package]]
name = "langgraph-prebuilt"
version = "1.0.7"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "langchain-core" },
    { name = "langgraph-checkpoint" },
]
sdist = { url = "https://files.pythonhosted.org/packages/a7/59/711aecd1a50999456850dc328f3cad72b4372d8218838d8d5326f80cb76f/langgraph_prebuilt-1.0.7.tar.gz", hash = "sha256:38e097e06de810de4d0e028ffc0e432bb56d1fb417620fb1dfdc76c5e03e4bf9", size = 163692, upload-time = "2026-01-22T16:45:22.801Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/47/49/5e37abb3f38a17a3487634abc2a5da87c208cc1d14577eb8d7184b25c886/langgraph_prebuilt-1.0.7-py3-none-any.whl", hash = "sha256:e14923516504405bb5edc3977085bc9622c35476b50c1808544490e13871fe7c", size = 35324, upload-time = "2026-01-22T16:45:21.784Z" },
]

[[package]]
name = "langgraph-sdk"
version = "0.3.6"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "httpx" },
    { name = "orjson" },
]
sdist = { url = "https://files.pythonhosted.org/packages/3e/ec/477fa8b408f948b145d90fd935c0a9f37945fa5ec1dfabfc71e7cafba6d8/langgraph_sdk-0.3.6.tar.gz", hash = "sha256:7650f607f89c1586db5bee391b1a8754cbe1fc83b721ff2f1450f8906e790bd7", size = 182666, upload-time = "2026-02-14T19:46:03.752Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/d8/61/12508e12652edd1874327271a5a8834c728a605f53a1a1c945f13ab69664/langgraph_sdk-0.3.6-py3-none-any.whl", hash = "sha256:7df2fd552ad7262d0baf8e1f849dce1d62186e76dcdd36db9dc5bdfa5c3fc20f", size = 88277, upload-time = "2026-02-14T19:46:02.48Z" },
]

[[package]]
name = "langsmith"
version = "0.7.3"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "httpx" },
    { name = "orjson", marker = "platform_python_implementation != 'PyPy'" },
    { name = "packaging" },
    { name = "pydantic" },
    { name = "requests" },
    { name = "requests-toolbelt" },
    { name = "uuid-utils" },
    { name = "xxhash" },
    { name = "zstandard" },
]
sdist = { url = "https://files.pythonhosted.org/packages/8d/bc/8172fefad4f2da888a6d564a27d1fb7d4dbf3c640899c2b40c46235cbe98/langsmith-0.7.3.tar.gz", hash = "sha256:0223b97021af62d2cf53c8a378a27bd22e90a7327e45b353e0069ae60d5d6f9e", size = 988575, upload-time = "2026-02-13T23:25:32.916Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/f4/9d/5a68b6b5e313ffabbb9725d18a71edb48177fd6d3ad329c07801d2a8e862/langsmith-0.7.3-py3-none-any.whl", hash = "sha256:03659bf9274e6efcead361c9c31a7849ea565ae0d6c0d73e1d8b239029eff3be", size = 325718, upload-time = "2026-02-13T23:25:31.52Z" },
]

[[package]]
name = "lxml"
version = "6.0.2"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/aa/88/262177de60548e5a2bfc46ad28232c9e9cbde697bd94132aeb80364675cb/lxml-6.0.2.tar.gz", hash = "sha256:cd79f3367bd74b317dda655dc8fcfa304d9eb6e4fb06b7168c5cf27f96e0cd62", size = 4073426, upload-time = "2025-09-22T04:04:59.287Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/53/fd/4e8f0540608977aea078bf6d79f128e0e2c2bba8af1acf775c30baa70460/lxml-6.0.2-cp313-cp313-macosx_10_13_universal2.whl", hash = "sha256:9b33d21594afab46f37ae58dfadd06636f154923c4e8a4d754b0127554eb2e77", size = 8648494, upload-time = "2025-09-22T04:01:54.242Z" },
    { url = "https://files.pythonhosted.org/packages/5d/f4/2a94a3d3dfd6c6b433501b8d470a1960a20ecce93245cf2db1706adf6c19/lxml-6.0.2-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:6c8963287d7a4c5c9a432ff487c52e9c5618667179c18a204bdedb27310f022f", size = 4661146, upload-time = "2025-09-22T04:01:56.282Z" },
    { url = "https://files.pythonhosted.org/packages/25/2e/4efa677fa6b322013035d38016f6ae859d06cac67437ca7dc708a6af7028/lxml-6.0.2-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.whl", hash = "sha256:1941354d92699fb5ffe6ed7b32f9649e43c2feb4b97205f75866f7d21aa91452", size = 4946932, upload-time = "2025-09-22T04:01:58.989Z" },
    { url = "https://files.pythonhosted.org/packages/ce/0f/526e78a6d38d109fdbaa5049c62e1d32fdd70c75fb61c4eadf3045d3d124/lxml-6.0.2-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:bb2f6ca0ae2d983ded09357b84af659c954722bbf04dea98030064996d156048", size = 5100060, upload-time = "2025-09-22T04:02:00.812Z" },
    { url = "https://files.pythonhosted.org/packages/81/76/99de58d81fa702cc0ea7edae4f4640416c2062813a00ff24bd70ac1d9c9b/lxml-6.0.2-cp313-cp313-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:eb2a12d704f180a902d7fa778c6d71f36ceb7b0d317f34cdc76a5d05aa1dd1df", size = 5019000, upload-time = "2025-09-22T04:02:02.671Z" },
    { url = "https://files.pythonhosted.org/packages/b5/35/9e57d25482bc9a9882cb0037fdb9cc18f4b79d85df94fa9d2a89562f1d25/lxml-6.0.2-cp313-cp313-manylinux_2_26_i686.manylinux_2_28_i686.whl", hash = "sha256:6ec0e3f745021bfed19c456647f0298d60a24c9ff86d9d051f52b509663feeb1", size = 5348496, upload-time = "2025-09-22T04:02:04.904Z" },
    { url = "https://files.pythonhosted.org/packages/a6/8e/cb99bd0b83ccc3e8f0f528e9aa1f7a9965dfec08c617070c5db8d63a87ce/lxml-6.0.2-cp313-cp313-manylinux_2_26_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:846ae9a12d54e368933b9759052d6206a9e8b250291109c48e350c1f1f49d916", size = 5643779, upload-time = "2025-09-22T04:02:06.689Z" },
    { url = "https://files.pythonhosted.org/packages/d0/34/9e591954939276bb679b73773836c6684c22e56d05980e31d52a9a8deb18/lxml-6.0.2-cp313-cp313-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:ef9266d2aa545d7374938fb5c484531ef5a2ec7f2d573e62f8ce722c735685fd", size = 5244072, upload-time = "2025-09-22T04:02:08.587Z" },
    { url = "https://files.pythonhosted.org/packages/8d/27/b29ff065f9aaca443ee377aff699714fcbffb371b4fce5ac4ca759e436d5/lxml-6.0.2-cp313-cp313-manylinux_2_31_armv7l.whl", hash = "sha256:4077b7c79f31755df33b795dc12119cb557a0106bfdab0d2c2d97bd3cf3dffa6", size = 4718675, upload-time = "2025-09-22T04:02:10.783Z" },
    { url = "https://files.pythonhosted.org/packages/2b/9f/f756f9c2cd27caa1a6ef8c32ae47aadea697f5c2c6d07b0dae133c244fbe/lxml-6.0.2-cp313-cp313-manylinux_2_38_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:a7c5d5e5f1081955358533be077166ee97ed2571d6a66bdba6ec2f609a715d1a", size = 5255171, upload-time = "2025-09-22T04:02:12.631Z" },
    { url = "https://files.pythonhosted.org/packages/61/46/bb85ea42d2cb1bd8395484fd72f38e3389611aa496ac7772da9205bbda0e/lxml-6.0.2-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:8f8d0cbd0674ee89863a523e6994ac25fd5be9c8486acfc3e5ccea679bad2679", size = 5057175, upload-time = "2025-09-22T04:02:14.718Z" },
    { url = "https://files.pythonhosted.org/packages/95/0c/443fc476dcc8e41577f0af70458c50fe299a97bb6b7505bb1ae09aa7f9ac/lxml-6.0.2-cp313-cp313-musllinux_1_2_armv7l.whl", hash = "sha256:2cbcbf6d6e924c28f04a43f3b6f6e272312a090f269eff68a2982e13e5d57659", size = 4785688, upload-time = "2025-09-22T04:02:16.957Z" },
    { url = "https://files.pythonhosted.org/packages/48/78/6ef0b359d45bb9697bc5a626e1992fa5d27aa3f8004b137b2314793b50a0/lxml-6.0.2-cp313-cp313-musllinux_1_2_ppc64le.whl", hash = "sha256:dfb874cfa53340009af6bdd7e54ebc0d21012a60a4e65d927c2e477112e63484", size = 5660655, upload-time = "2025-09-22T04:02:18.815Z" },
    { url = "https://files.pythonhosted.org/packages/ff/ea/e1d33808f386bc1339d08c0dcada6e4712d4ed8e93fcad5f057070b7988a/lxml-6.0.2-cp313-cp313-musllinux_1_2_riscv64.whl", hash = "sha256:fb8dae0b6b8b7f9e96c26fdd8121522ce5de9bb5538010870bd538683d30e9a2", size = 5247695, upload-time = "2025-09-22T04:02:20.593Z" },
    { url = "https://files.pythonhosted.org/packages/4f/47/eba75dfd8183673725255247a603b4ad606f4ae657b60c6c145b381697da/lxml-6.0.2-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:358d9adae670b63e95bc59747c72f4dc97c9ec58881d4627fe0120da0f90d314", size = 5269841, upload-time = "2025-09-22T04:02:22.489Z" },
    { url = "https://files.pythonhosted.org/packages/76/04/5c5e2b8577bc936e219becb2e98cdb1aca14a4921a12995b9d0c523502ae/lxml-6.0.2-cp313-cp313-win32.whl", hash = "sha256:e8cd2415f372e7e5a789d743d133ae474290a90b9023197fd78f32e2dc6873e2", size = 3610700, upload-time = "2025-09-22T04:02:24.465Z" },
    { url = "https://files.pythonhosted.org/packages/fe/0a/4643ccc6bb8b143e9f9640aa54e38255f9d3b45feb2cbe7ae2ca47e8782e/lxml-6.0.2-cp313-cp313-win_amd64.whl", hash = "sha256:b30d46379644fbfc3ab81f8f82ae4de55179414651f110a1514f0b1f8f6cb2d7", size = 4010347, upload-time = "2025-09-22T04:02:26.286Z" },
    { url = "https://files.pythonhosted.org/packages/31/ef/dcf1d29c3f530577f61e5fe2f1bd72929acf779953668a8a47a479ae6f26/lxml-6.0.2-cp313-cp313-win_arm64.whl", hash = "sha256:13dcecc9946dca97b11b7c40d29fba63b55ab4170d3c0cf8c0c164343b9bfdcf", size = 3671248, upload-time = "2025-09-22T04:02:27.918Z" },
]

[[package]]
name = "markdown-it-py"
version = "4.0.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "mdurl" },
]
sdist = { url = "https://files.pythonhosted.org/packages/5b/f5/4ec618ed16cc4f8fb3b701563655a69816155e79e24a17b651541804721d/markdown_it_py-4.0.0.tar.gz", hash = "sha256:cb0a2b4aa34f932c007117b194e945bd74e0ec24133ceb5bac59009cda1cb9f3", size = 73070, upload-time = "2025-08-11T12:57:52.854Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/94/54/e7d793b573f298e1c9013b8c4dade17d481164aa517d1d7148619c2cedbf/markdown_it_py-4.0.0-py3-none-any.whl", hash = "sha256:87327c59b172c5011896038353a81343b6754500a08cd7a4973bb48c6d578147", size = 87321, upload-time = "2025-08-11T12:57:51.923Z" },
]

[[package]]
name = "markupsafe"
version = "3.0.3"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/7e/99/7690b6d4034fffd95959cbe0c02de8deb3098cc577c67bb6a24fe5d7caa7/markupsafe-3.0.3.tar.gz", hash = "sha256:722695808f4b6457b320fdc131280796bdceb04ab50fe1795cd540799ebe1698", size = 80313, upload-time = "2025-09-27T18:37:40.426Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/38/2f/907b9c7bbba283e68f20259574b13d005c121a0fa4c175f9bed27c4597ff/markupsafe-3.0.3-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:e1cf1972137e83c5d4c136c43ced9ac51d0e124706ee1c8aa8532c1287fa8795", size = 11622, upload-time = "2025-09-27T18:36:41.777Z" },
    { url = "https://files.pythonhosted.org/packages/9c/d9/5f7756922cdd676869eca1c4e3c0cd0df60ed30199ffd775e319089cb3ed/markupsafe-3.0.3-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:116bb52f642a37c115f517494ea5feb03889e04df47eeff5b130b1808ce7c219", size = 12029, upload-time = "2025-09-27T18:36:43.257Z" },
    { url = "https://files.pythonhosted.org/packages/00/07/575a68c754943058c78f30db02ee03a64b3c638586fba6a6dd56830b30a3/markupsafe-3.0.3-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:133a43e73a802c5562be9bbcd03d090aa5a1fe899db609c29e8c8d815c5f6de6", size = 24374, upload-time = "2025-09-27T18:36:44.508Z" },
    { url = "https://files.pythonhosted.org/packages/a9/21/9b05698b46f218fc0e118e1f8168395c65c8a2c750ae2bab54fc4bd4e0e8/markupsafe-3.0.3-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:ccfcd093f13f0f0b7fdd0f198b90053bf7b2f02a3927a30e63f3ccc9df56b676", size = 22980, upload-time = "2025-09-27T18:36:45.385Z" },
    { url = "https://files.pythonhosted.org/packages/7f/71/544260864f893f18b6827315b988c146b559391e6e7e8f7252839b1b846a/markupsafe-3.0.3-cp313-cp313-manylinux_2_31_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:509fa21c6deb7a7a273d629cf5ec029bc209d1a51178615ddf718f5918992ab9", size = 21990, upload-time = "2025-09-27T18:36:46.916Z" },
    { url = "https://files.pythonhosted.org/packages/c2/28/b50fc2f74d1ad761af2f5dcce7492648b983d00a65b8c0e0cb457c82ebbe/markupsafe-3.0.3-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:a4afe79fb3de0b7097d81da19090f4df4f8d3a2b3adaa8764138aac2e44f3af1", size = 23784, upload-time = "2025-09-27T18:36:47.884Z" },
    { url = "https://files.pythonhosted.org/packages/ed/76/104b2aa106a208da8b17a2fb72e033a5a9d7073c68f7e508b94916ed47a9/markupsafe-3.0.3-cp313-cp313-musllinux_1_2_riscv64.whl", hash = "sha256:795e7751525cae078558e679d646ae45574b47ed6e7771863fcc079a6171a0fc", size = 21588, upload-time = "2025-09-27T18:36:48.82Z" },
    { url = "https://files.pythonhosted.org/packages/b5/99/16a5eb2d140087ebd97180d95249b00a03aa87e29cc224056274f2e45fd6/markupsafe-3.0.3-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:8485f406a96febb5140bfeca44a73e3ce5116b2501ac54fe953e488fb1d03b12", size = 23041, upload-time = "2025-09-27T18:36:49.797Z" },
    { url = "https://files.pythonhosted.org/packages/19/bc/e7140ed90c5d61d77cea142eed9f9c303f4c4806f60a1044c13e3f1471d0/markupsafe-3.0.3-cp313-cp313-win32.whl", hash = "sha256:bdd37121970bfd8be76c5fb069c7751683bdf373db1ed6c010162b2a130248ed", size = 14543, upload-time = "2025-09-27T18:36:51.584Z" },
    { url = "https://files.pythonhosted.org/packages/05/73/c4abe620b841b6b791f2edc248f556900667a5a1cf023a6646967ae98335/markupsafe-3.0.3-cp313-cp313-win_amd64.whl", hash = "sha256:9a1abfdc021a164803f4d485104931fb8f8c1efd55bc6b748d2f5774e78b62c5", size = 15113, upload-time = "2025-09-27T18:36:52.537Z" },
    { url = "https://files.pythonhosted.org/packages/f0/3a/fa34a0f7cfef23cf9500d68cb7c32dd64ffd58a12b09225fb03dd37d5b80/markupsafe-3.0.3-cp313-cp313-win_arm64.whl", hash = "sha256:7e68f88e5b8799aa49c85cd116c932a1ac15caaa3f5db09087854d218359e485", size = 13911, upload-time = "2025-09-27T18:36:53.513Z" },
    { url = "https://files.pythonhosted.org/packages/e4/d7/e05cd7efe43a88a17a37b3ae96e79a19e846f3f456fe79c57ca61356ef01/markupsafe-3.0.3-cp313-cp313t-macosx_10_13_x86_64.whl", hash = "sha256:218551f6df4868a8d527e3062d0fb968682fe92054e89978594c28e642c43a73", size = 11658, upload-time = "2025-09-27T18:36:54.819Z" },
    { url = "https://files.pythonhosted.org/packages/99/9e/e412117548182ce2148bdeacdda3bb494260c0b0184360fe0d56389b523b/markupsafe-3.0.3-cp313-cp313t-macosx_11_0_arm64.whl", hash = "sha256:3524b778fe5cfb3452a09d31e7b5adefeea8c5be1d43c4f810ba09f2ceb29d37", size = 12066, upload-time = "2025-09-27T18:36:55.714Z" },
    { url = "https://files.pythonhosted.org/packages/bc/e6/fa0ffcda717ef64a5108eaa7b4f5ed28d56122c9a6d70ab8b72f9f715c80/markupsafe-3.0.3-cp313-cp313t-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:4e885a3d1efa2eadc93c894a21770e4bc67899e3543680313b09f139e149ab19", size = 25639, upload-time = "2025-09-27T18:36:56.908Z" },
    { url = "https://files.pythonhosted.org/packages/96/ec/2102e881fe9d25fc16cb4b25d5f5cde50970967ffa5dddafdb771237062d/markupsafe-3.0.3-cp313-cp313t-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:8709b08f4a89aa7586de0aadc8da56180242ee0ada3999749b183aa23df95025", size = 23569, upload-time = "2025-09-27T18:36:57.913Z" },
    { url = "https://files.pythonhosted.org/packages/4b/30/6f2fce1f1f205fc9323255b216ca8a235b15860c34b6798f810f05828e32/markupsafe-3.0.3-cp313-cp313t-manylinux_2_31_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:b8512a91625c9b3da6f127803b166b629725e68af71f8184ae7e7d54686a56d6", size = 23284, upload-time = "2025-09-27T18:36:58.833Z" },
    { url = "https://files.pythonhosted.org/packages/58/47/4a0ccea4ab9f5dcb6f79c0236d954acb382202721e704223a8aafa38b5c8/markupsafe-3.0.3-cp313-cp313t-musllinux_1_2_aarch64.whl", hash = "sha256:9b79b7a16f7fedff2495d684f2b59b0457c3b493778c9eed31111be64d58279f", size = 24801, upload-time = "2025-09-27T18:36:59.739Z" },
    { url = "https://files.pythonhosted.org/packages/6a/70/3780e9b72180b6fecb83a4814d84c3bf4b4ae4bf0b19c27196104149734c/markupsafe-3.0.3-cp313-cp313t-musllinux_1_2_riscv64.whl", hash = "sha256:12c63dfb4a98206f045aa9563db46507995f7ef6d83b2f68eda65c307c6829eb", size = 22769, upload-time = "2025-09-27T18:37:00.719Z" },
    { url = "https://files.pythonhosted.org/packages/98/c5/c03c7f4125180fc215220c035beac6b9cb684bc7a067c84fc69414d315f5/markupsafe-3.0.3-cp313-cp313t-musllinux_1_2_x86_64.whl", hash = "sha256:8f71bc33915be5186016f675cd83a1e08523649b0e33efdb898db577ef5bb009", size = 23642, upload-time = "2025-09-27T18:37:01.673Z" },
    { url = "https://files.pythonhosted.org/packages/80/d6/2d1b89f6ca4bff1036499b1e29a1d02d282259f3681540e16563f27ebc23/markupsafe-3.0.3-cp313-cp313t-win32.whl", hash = "sha256:69c0b73548bc525c8cb9a251cddf1931d1db4d2258e9599c28c07ef3580ef354", size = 14612, upload-time = "2025-09-27T18:37:02.639Z" },
    { url = "https://files.pythonhosted.org/packages/2b/98/e48a4bfba0a0ffcf9925fe2d69240bfaa19c6f7507b8cd09c70684a53c1e/markupsafe-3.0.3-cp313-cp313t-win_amd64.whl", hash = "sha256:1b4b79e8ebf6b55351f0d91fe80f893b4743f104bff22e90697db1590e47a218", size = 15200, upload-time = "2025-09-27T18:37:03.582Z" },
    { url = "https://files.pythonhosted.org/packages/0e/72/e3cc540f351f316e9ed0f092757459afbc595824ca724cbc5a5d4263713f/markupsafe-3.0.3-cp313-cp313t-win_arm64.whl", hash = "sha256:ad2cf8aa28b8c020ab2fc8287b0f823d0a7d8630784c31e9ee5edea20f406287", size = 13973, upload-time = "2025-09-27T18:37:04.929Z" },
]

[[package]]
name = "mdurl"
version = "0.1.2"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/d6/54/cfe61301667036ec958cb99bd3efefba235e65cdeb9c84d24a8293ba1d90/mdurl-0.1.2.tar.gz", hash = "sha256:bb413d29f5eea38f31dd4754dd7377d4465116fb207585f97bf925588687c1ba", size = 8729, upload-time = "2022-08-14T12:40:10.846Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/b3/38/89ba8ad64ae25be8de66a6d463314cf1eb366222074cfda9ee839c56a4b4/mdurl-0.1.2-py3-none-any.whl", hash = "sha256:84008a41e51615a49fc9966191ff91509e3c40b939176e643fd50a5c2196b8f8", size = 9979, upload-time = "2022-08-14T12:40:09.779Z" },
]

[[package]]
name = "numpy"
version = "2.4.2"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/57/fd/0005efbd0af48e55eb3c7208af93f2862d4b1a56cd78e84309a2d959208d/numpy-2.4.2.tar.gz", hash = "sha256:659a6107e31a83c4e33f763942275fd278b21d095094044eb35569e86a21ddae", size = 20723651, upload-time = "2026-01-31T23:13:10.135Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/a1/22/815b9fe25d1d7ae7d492152adbc7226d3eff731dffc38fe970589fcaaa38/numpy-2.4.2-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:25f2059807faea4b077a2b6837391b5d830864b3543627f381821c646f31a63c", size = 16663696, upload-time = "2026-01-31T23:11:17.516Z" },
    { url = "https://files.pythonhosted.org/packages/09/f0/817d03a03f93ba9c6c8993de509277d84e69f9453601915e4a69554102a1/numpy-2.4.2-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:bd3a7a9f5847d2fb8c2c6d1c862fa109c31a9abeca1a3c2bd5a64572955b2979", size = 14688322, upload-time = "2026-01-31T23:11:19.883Z" },
    { url = "https://files.pythonhosted.org/packages/da/b4/f805ab79293c728b9a99438775ce51885fd4f31b76178767cfc718701a39/numpy-2.4.2-cp313-cp313-macosx_14_0_arm64.whl", hash = "sha256:8e4549f8a3c6d13d55041925e912bfd834285ef1dd64d6bc7d542583355e2e98", size = 5198157, upload-time = "2026-01-31T23:11:22.375Z" },
    { url = "https://files.pythonhosted.org/packages/74/09/826e4289844eccdcd64aac27d13b0fd3f32039915dd5b9ba01baae1f436c/numpy-2.4.2-cp313-cp313-macosx_14_0_x86_64.whl", hash = "sha256:aea4f66ff44dfddf8c2cffd66ba6538c5ec67d389285292fe428cb2c738c8aef", size = 6546330, upload-time = "2026-01-31T23:11:23.958Z" },
    { url = "https://files.pythonhosted.org/packages/19/fb/cbfdbfa3057a10aea5422c558ac57538e6acc87ec1669e666d32ac198da7/numpy-2.4.2-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:c3cd545784805de05aafe1dde61752ea49a359ccba9760c1e5d1c88a93bbf2b7", size = 15660968, upload-time = "2026-01-31T23:11:25.713Z" },
    { url = "https://files.pythonhosted.org/packages/04/dc/46066ce18d01645541f0186877377b9371b8fa8017fa8262002b4ef22612/numpy-2.4.2-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:d0d9b7c93578baafcbc5f0b83eaf17b79d345c6f36917ba0c67f45226911d499", size = 16607311, upload-time = "2026-01-31T23:11:28.117Z" },
    { url = "https://files.pythonhosted.org/packages/14/d9/4b5adfc39a43fa6bf918c6d544bc60c05236cc2f6339847fc5b35e6cb5b0/numpy-2.4.2-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:f74f0f7779cc7ae07d1810aab8ac6b1464c3eafb9e283a40da7309d5e6e48fbb", size = 17012850, upload-time = "2026-01-31T23:11:30.888Z" },
    { url = "https://files.pythonhosted.org/packages/b7/20/adb6e6adde6d0130046e6fdfb7675cc62bc2f6b7b02239a09eb58435753d/numpy-2.4.2-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:c7ac672d699bf36275c035e16b65539931347d68b70667d28984c9fb34e07fa7", size = 18334210, upload-time = "2026-01-31T23:11:33.214Z" },
    { url = "https://files.pythonhosted.org/packages/78/0e/0a73b3dff26803a8c02baa76398015ea2a5434d9b8265a7898a6028c1591/numpy-2.4.2-cp313-cp313-win32.whl", hash = "sha256:8e9afaeb0beff068b4d9cd20d322ba0ee1cecfb0b08db145e4ab4dd44a6b5110", size = 5958199, upload-time = "2026-01-31T23:11:35.385Z" },
    { url = "https://files.pythonhosted.org/packages/43/bc/6352f343522fcb2c04dbaf94cb30cca6fd32c1a750c06ad6231b4293708c/numpy-2.4.2-cp313-cp313-win_amd64.whl", hash = "sha256:7df2de1e4fba69a51c06c28f5a3de36731eb9639feb8e1cf7e4a7b0daf4cf622", size = 12310848, upload-time = "2026-01-31T23:11:38.001Z" },
    { url = "https://files.pythonhosted.org/packages/6e/8d/6da186483e308da5da1cc6918ce913dcfe14ffde98e710bfeff2a6158d4e/numpy-2.4.2-cp313-cp313-win_arm64.whl", hash = "sha256:0fece1d1f0a89c16b03442eae5c56dc0be0c7883b5d388e0c03f53019a4bfd71", size = 10221082, upload-time = "2026-01-31T23:11:40.392Z" },
    { url = "https://files.pythonhosted.org/packages/25/a1/9510aa43555b44781968935c7548a8926274f815de42ad3997e9e83680dd/numpy-2.4.2-cp313-cp313t-macosx_11_0_arm64.whl", hash = "sha256:5633c0da313330fd20c484c78cdd3f9b175b55e1a766c4a174230c6b70ad8262", size = 14815866, upload-time = "2026-01-31T23:11:42.495Z" },
    { url = "https://files.pythonhosted.org/packages/36/30/6bbb5e76631a5ae46e7923dd16ca9d3f1c93cfa8d4ed79a129814a9d8db3/numpy-2.4.2-cp313-cp313t-macosx_14_0_arm64.whl", hash = "sha256:d9f64d786b3b1dd742c946c42d15b07497ed14af1a1f3ce840cce27daa0ce913", size = 5325631, upload-time = "2026-01-31T23:11:44.7Z" },
    { url = "https://files.pythonhosted.org/packages/46/00/3a490938800c1923b567b3a15cd17896e68052e2145d8662aaf3e1ffc58f/numpy-2.4.2-cp313-cp313t-macosx_14_0_x86_64.whl", hash = "sha256:b21041e8cb6a1eb5312dd1d2f80a94d91efffb7a06b70597d44f1bd2dfc315ab", size = 6646254, upload-time = "2026-01-31T23:11:46.341Z" },
    { url = "https://files.pythonhosted.org/packages/d3/e9/fac0890149898a9b609caa5af7455a948b544746e4b8fe7c212c8edd71f8/numpy-2.4.2-cp313-cp313t-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:00ab83c56211a1d7c07c25e3217ea6695e50a3e2f255053686b081dc0b091a82", size = 15720138, upload-time = "2026-01-31T23:11:48.082Z" },
    { url = "https://files.pythonhosted.org/packages/ea/5c/08887c54e68e1e28df53709f1893ce92932cc6f01f7c3d4dc952f61ffd4e/numpy-2.4.2-cp313-cp313t-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:2fb882da679409066b4603579619341c6d6898fc83a8995199d5249f986e8e8f", size = 16655398, upload-time = "2026-01-31T23:11:50.293Z" },
    { url = "https://files.pythonhosted.org/packages/4d/89/253db0fa0e66e9129c745e4ef25631dc37d5f1314dad2b53e907b8538e6d/numpy-2.4.2-cp313-cp313t-musllinux_1_2_aarch64.whl", hash = "sha256:66cb9422236317f9d44b67b4d18f44efe6e9c7f8794ac0462978513359461554", size = 17079064, upload-time = "2026-01-31T23:11:52.927Z" },
    { url = "https://files.pythonhosted.org/packages/2a/d5/cbade46ce97c59c6c3da525e8d95b7abe8a42974a1dc5c1d489c10433e88/numpy-2.4.2-cp313-cp313t-musllinux_1_2_x86_64.whl", hash = "sha256:0f01dcf33e73d80bd8dc0f20a71303abbafa26a19e23f6b68d1aa9990af90257", size = 18379680, upload-time = "2026-01-31T23:11:55.22Z" },
    { url = "https://files.pythonhosted.org/packages/40/62/48f99ae172a4b63d981babe683685030e8a3df4f246c893ea5c6ef99f018/numpy-2.4.2-cp313-cp313t-win32.whl", hash = "sha256:52b913ec40ff7ae845687b0b34d8d93b60cb66dcee06996dd5c99f2fc9328657", size = 6082433, upload-time = "2026-01-31T23:11:58.096Z" },
    { url = "https://files.pythonhosted.org/packages/07/38/e054a61cfe48ad9f1ed0d188e78b7e26859d0b60ef21cd9de4897cdb5326/numpy-2.4.2-cp313-cp313t-win_amd64.whl", hash = "sha256:5eea80d908b2c1f91486eb95b3fb6fab187e569ec9752ab7d9333d2e66bf2d6b", size = 12451181, upload-time = "2026-01-31T23:11:59.782Z" },
    { url = "https://files.pythonhosted.org/packages/6e/a4/a05c3a6418575e185dd84d0b9680b6bb2e2dc3e4202f036b7b4e22d6e9dc/numpy-2.4.2-cp313-cp313t-win_arm64.whl", hash = "sha256:fd49860271d52127d61197bb50b64f58454e9f578cb4b2c001a6de8b1f50b0b1", size = 10290756, upload-time = "2026-01-31T23:12:02.438Z" },
]

[[package]]
name = "openai"
version = "2.21.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "anyio" },
    { name = "distro" },
    { name = "httpx" },
    { name = "jiter" },
    { name = "pydantic" },
    { name = "sniffio" },
    { name = "tqdm" },
    { name = "typing-extensions" },
]
sdist = { url = "https://files.pythonhosted.org/packages/92/e5/3d197a0947a166649f566706d7a4c8f7fe38f1fa7b24c9bcffe4c7591d44/openai-2.21.0.tar.gz", hash = "sha256:81b48ce4b8bbb2cc3af02047ceb19561f7b1dc0d4e52d1de7f02abfd15aa59b7", size = 644374, upload-time = "2026-02-14T00:12:01.577Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/cc/56/0a89092a453bb2c676d66abee44f863e742b2110d4dbb1dbcca3f7e5fc33/openai-2.21.0-py3-none-any.whl", hash = "sha256:0bc1c775e5b1536c294eded39ee08f8407656537ccc71b1004104fe1602e267c", size = 1103065, upload-time = "2026-02-14T00:11:59.603Z" },
]

[[package]]
name = "orjson"
version = "3.11.7"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/53/45/b268004f745ede84e5798b48ee12b05129d19235d0e15267aa57dcdb400b/orjson-3.11.7.tar.gz", hash = "sha256:9b1a67243945819ce55d24a30b59d6a168e86220452d2c96f4d1f093e71c0c49", size = 6144992, upload-time = "2026-02-02T15:38:49.29Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/89/25/6e0e52cac5aab51d7b6dcd257e855e1dec1c2060f6b28566c509b4665f62/orjson-3.11.7-cp313-cp313-macosx_10_15_x86_64.macosx_11_0_arm64.macosx_10_15_universal2.whl", hash = "sha256:1d98b30cc1313d52d4af17d9c3d307b08389752ec5f2e5febdfada70b0f8c733", size = 228390, upload-time = "2026-02-02T15:38:06.8Z" },
    { url = "https://files.pythonhosted.org/packages/a5/29/a77f48d2fc8a05bbc529e5ff481fb43d914f9e383ea2469d4f3d51df3d00/orjson-3.11.7-cp313-cp313-macosx_15_0_arm64.whl", hash = "sha256:d897e81f8d0cbd2abb82226d1860ad2e1ab3ff16d7b08c96ca00df9d45409ef4", size = 125189, upload-time = "2026-02-02T15:38:08.181Z" },
    { url = "https://files.pythonhosted.org/packages/89/25/0a16e0729a0e6a1504f9d1a13cdd365f030068aab64cec6958396b9969d7/orjson-3.11.7-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:814be4b49b228cfc0b3c565acf642dd7d13538f966e3ccde61f4f55be3e20785", size = 128106, upload-time = "2026-02-02T15:38:09.41Z" },
    { url = "https://files.pythonhosted.org/packages/66/da/a2e505469d60666a05ab373f1a6322eb671cb2ba3a0ccfc7d4bc97196787/orjson-3.11.7-cp313-cp313-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:d06e5c5fed5caedd2e540d62e5b1c25e8c82431b9e577c33537e5fa4aa909539", size = 123363, upload-time = "2026-02-02T15:38:10.73Z" },
    { url = "https://files.pythonhosted.org/packages/23/bf/ed73f88396ea35c71b38961734ea4a4746f7ca0768bf28fd551d37e48dd0/orjson-3.11.7-cp313-cp313-manylinux_2_17_i686.manylinux2014_i686.whl", hash = "sha256:31c80ce534ac4ea3739c5ee751270646cbc46e45aea7576a38ffec040b4029a1", size = 129007, upload-time = "2026-02-02T15:38:12.138Z" },
    { url = "https://files.pythonhosted.org/packages/73/3c/b05d80716f0225fc9008fbf8ab22841dcc268a626aa550561743714ce3bf/orjson-3.11.7-cp313-cp313-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:f50979824bde13d32b4320eedd513431c921102796d86be3eee0b58e58a3ecd1", size = 141667, upload-time = "2026-02-02T15:38:13.398Z" },
    { url = "https://files.pythonhosted.org/packages/61/e8/0be9b0addd9bf86abfc938e97441dcd0375d494594b1c8ad10fe57479617/orjson-3.11.7-cp313-cp313-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:9e54f3808e2b6b945078c41aa8d9b5834b28c50843846e97807e5adb75fa9705", size = 130832, upload-time = "2026-02-02T15:38:14.698Z" },
    { url = "https://files.pythonhosted.org/packages/c9/ec/c68e3b9021a31d9ec15a94931db1410136af862955854ed5dd7e7e4f5bff/orjson-3.11.7-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:a12b80df61aab7b98b490fe9e4879925ba666fccdfcd175252ce4d9035865ace", size = 133373, upload-time = "2026-02-02T15:38:16.109Z" },
    { url = "https://files.pythonhosted.org/packages/d2/45/f3466739aaafa570cc8e77c6dbb853c48bf56e3b43738020e2661e08b0ac/orjson-3.11.7-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:996b65230271f1a97026fd0e6a753f51fbc0c335d2ad0c6201f711b0da32693b", size = 138307, upload-time = "2026-02-02T15:38:17.453Z" },
    { url = "https://files.pythonhosted.org/packages/e1/84/9f7f02288da1ffb31405c1be07657afd1eecbcb4b64ee2817b6fe0f785fa/orjson-3.11.7-cp313-cp313-musllinux_1_2_armv7l.whl", hash = "sha256:ab49d4b2a6a1d415ddb9f37a21e02e0d5dbfe10b7870b21bf779fc21e9156157", size = 408695, upload-time = "2026-02-02T15:38:18.831Z" },
    { url = "https://files.pythonhosted.org/packages/18/07/9dd2f0c0104f1a0295ffbe912bc8d63307a539b900dd9e2c48ef7810d971/orjson-3.11.7-cp313-cp313-musllinux_1_2_i686.whl", hash = "sha256:390a1dce0c055ddf8adb6aa94a73b45a4a7d7177b5c584b8d1c1947f2ba60fb3", size = 144099, upload-time = "2026-02-02T15:38:20.28Z" },
    { url = "https://files.pythonhosted.org/packages/a5/66/857a8e4a3292e1f7b1b202883bcdeb43a91566cf59a93f97c53b44bd6801/orjson-3.11.7-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:1eb80451a9c351a71dfaf5b7ccc13ad065405217726b59fdbeadbcc544f9d223", size = 134806, upload-time = "2026-02-02T15:38:22.186Z" },
    { url = "https://files.pythonhosted.org/packages/0a/5b/6ebcf3defc1aab3a338ca777214966851e92efb1f30dc7fc8285216e6d1b/orjson-3.11.7-cp313-cp313-win32.whl", hash = "sha256:7477aa6a6ec6139c5cb1cc7b214643592169a5494d200397c7fc95d740d5fcf3", size = 127914, upload-time = "2026-02-02T15:38:23.511Z" },
    { url = "https://files.pythonhosted.org/packages/00/04/c6f72daca5092e3117840a1b1e88dfc809cc1470cf0734890d0366b684a1/orjson-3.11.7-cp313-cp313-win_amd64.whl", hash = "sha256:b9f95dcdea9d4f805daa9ddf02617a89e484c6985fa03055459f90e87d7a0757", size = 124986, upload-time = "2026-02-02T15:38:24.836Z" },
    { url = "https://files.pythonhosted.org/packages/03/ba/077a0f6f1085d6b806937246860fafbd5b17f3919c70ee3f3d8d9c713f38/orjson-3.11.7-cp313-cp313-win_arm64.whl", hash = "sha256:800988273a014a0541483dc81021247d7eacb0c845a9d1a34a422bc718f41539", size = 126045, upload-time = "2026-02-02T15:38:26.216Z" },
]

[[package]]
name = "ormsgpack"
version = "1.12.2"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/12/0c/f1761e21486942ab9bb6feaebc610fa074f7c5e496e6962dea5873348077/ormsgpack-1.12.2.tar.gz", hash = "sha256:944a2233640273bee67521795a73cf1e959538e0dfb7ac635505010455e53b33", size = 39031, upload-time = "2026-01-18T20:55:28.023Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/eb/29/bb0eba3288c0449efbb013e9c6f58aea79cf5cb9ee1921f8865f04c1a9d7/ormsgpack-1.12.2-cp313-cp313-macosx_10_12_x86_64.macosx_11_0_arm64.macosx_10_12_universal2.whl", hash = "sha256:5ea60cb5f210b1cfbad8c002948d73447508e629ec375acb82910e3efa8ff355", size = 378661, upload-time = "2026-01-18T20:55:57.765Z" },
    { url = "https://files.pythonhosted.org/packages/6e/31/5efa31346affdac489acade2926989e019e8ca98129658a183e3add7af5e/ormsgpack-1.12.2-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:f3601f19afdbea273ed70b06495e5794606a8b690a568d6c996a90d7255e51c1", size = 203194, upload-time = "2026-01-18T20:56:08.252Z" },
    { url = "https://files.pythonhosted.org/packages/eb/56/d0087278beef833187e0167f8527235ebe6f6ffc2a143e9de12a98b1ce87/ormsgpack-1.12.2-cp313-cp313-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:29a9f17a3dac6054c0dce7925e0f4995c727f7c41859adf9b5572180f640d172", size = 210778, upload-time = "2026-01-18T20:55:17.694Z" },
    { url = "https://files.pythonhosted.org/packages/1c/a2/072343e1413d9443e5a252a8eb591c2d5b1bffbe5e7bfc78c069361b92eb/ormsgpack-1.12.2-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:39c1bd2092880e413902910388be8715f70b9f15f20779d44e673033a6146f2d", size = 212592, upload-time = "2026-01-18T20:55:32.747Z" },
    { url = "https://files.pythonhosted.org/packages/a2/8b/a0da3b98a91d41187a63b02dda14267eefc2a74fcb43cc2701066cf1510e/ormsgpack-1.12.2-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:50b7249244382209877deedeee838aef1542f3d0fc28b8fe71ca9d7e1896a0d7", size = 387164, upload-time = "2026-01-18T20:55:40.853Z" },
    { url = "https://files.pythonhosted.org/packages/19/bb/6d226bc4cf9fc20d8eb1d976d027a3f7c3491e8f08289a2e76abe96a65f3/ormsgpack-1.12.2-cp313-cp313-musllinux_1_2_armv7l.whl", hash = "sha256:5af04800d844451cf102a59c74a841324868d3f1625c296a06cc655c542a6685", size = 482516, upload-time = "2026-01-18T20:55:42.033Z" },
    { url = "https://files.pythonhosted.org/packages/fb/f1/bb2c7223398543dedb3dbf8bb93aaa737b387de61c5feaad6f908841b782/ormsgpack-1.12.2-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:cec70477d4371cd524534cd16472d8b9cc187e0e3043a8790545a9a9b296c258", size = 425539, upload-time = "2026-01-18T20:55:24.727Z" },
    { url = "https://files.pythonhosted.org/packages/7b/e8/0fb45f57a2ada1fed374f7494c8cd55e2f88ccd0ab0a669aa3468716bf5f/ormsgpack-1.12.2-cp313-cp313-win_amd64.whl", hash = "sha256:21f4276caca5c03a818041d637e4019bc84f9d6ca8baa5ea03e5cc8bf56140e9", size = 117459, upload-time = "2026-01-18T20:55:56.876Z" },
    { url = "https://files.pythonhosted.org/packages/7a/d4/0cfeea1e960d550a131001a7f38a5132c7ae3ebde4c82af1f364ccc5d904/ormsgpack-1.12.2-cp313-cp313-win_arm64.whl", hash = "sha256:baca4b6773d20a82e36d6fd25f341064244f9f86a13dead95dd7d7f996f51709", size = 111577, upload-time = "2026-01-18T20:55:43.605Z" },
]

[[package]]
name = "packaging"
version = "26.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/65/ee/299d360cdc32edc7d2cf530f3accf79c4fca01e96ffc950d8a52213bd8e4/packaging-26.0.tar.gz", hash = "sha256:00243ae351a257117b6a241061796684b084ed1c516a08c48a3f7e147a9d80b4", size = 143416, upload-time = "2026-01-21T20:50:39.064Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/b7/b9/c538f279a4e237a006a2c98387d081e9eb060d203d8ed34467cc0f0b9b53/packaging-26.0-py3-none-any.whl", hash = "sha256:b36f1fef9334a5588b4166f8bcd26a14e521f2b55e6b9de3aaa80d3ff7a37529", size = 74366, upload-time = "2026-01-21T20:50:37.788Z" },
]

[[package]]
name = "pandas"
version = "3.0.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "numpy" },
    { name = "python-dateutil" },
    { name = "tzdata", marker = "sys_platform == 'emscripten' or sys_platform == 'win32'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/2e/0c/b28ed414f080ee0ad153f848586d61d1878f91689950f037f976ce15f6c8/pandas-3.0.1.tar.gz", hash = "sha256:4186a699674af418f655dbd420ed87f50d56b4cd6603784279d9eef6627823c8", size = 4641901, upload-time = "2026-02-17T22:20:16.434Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/0b/48/aad6ec4f8d007534c091e9a7172b3ec1b1ee6d99a9cbb936b5eab6c6cf58/pandas-3.0.1-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:5272627187b5d9c20e55d27caf5f2cd23e286aba25cadf73c8590e432e2b7262", size = 10317509, upload-time = "2026-02-17T22:18:59.498Z" },
    { url = "https://files.pythonhosted.org/packages/a8/14/5990826f779f79148ae9d3a2c39593dc04d61d5d90541e71b5749f35af95/pandas-3.0.1-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:661e0f665932af88c7877f31da0dc743fe9c8f2524bdffe23d24fdcb67ef9d56", size = 9860561, upload-time = "2026-02-17T22:19:02.265Z" },
    { url = "https://files.pythonhosted.org/packages/fa/80/f01ff54664b6d70fed71475543d108a9b7c888e923ad210795bef04ffb7d/pandas-3.0.1-cp313-cp313-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:75e6e292ff898679e47a2199172593d9f6107fd2dd3617c22c2946e97d5df46e", size = 10365506, upload-time = "2026-02-17T22:19:05.017Z" },
    { url = "https://files.pythonhosted.org/packages/f2/85/ab6d04733a7d6ff32bfc8382bf1b07078228f5d6ebec5266b91bfc5c4ff7/pandas-3.0.1-cp313-cp313-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:1ff8cf1d2896e34343197685f432450ec99a85ba8d90cce2030c5eee2ef98791", size = 10873196, upload-time = "2026-02-17T22:19:07.204Z" },
    { url = "https://files.pythonhosted.org/packages/48/a9/9301c83d0b47c23ac5deab91c6b39fd98d5b5db4d93b25df8d381451828f/pandas-3.0.1-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:eca8b4510f6763f3d37359c2105df03a7a221a508f30e396a51d0713d462e68a", size = 11370859, upload-time = "2026-02-17T22:19:09.436Z" },
    { url = "https://files.pythonhosted.org/packages/59/fe/0c1fc5bd2d29c7db2ab372330063ad555fb83e08422829c785f5ec2176ca/pandas-3.0.1-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:06aff2ad6f0b94a17822cf8b83bbb563b090ed82ff4fe7712db2ce57cd50d9b8", size = 11924584, upload-time = "2026-02-17T22:19:11.562Z" },
    { url = "https://files.pythonhosted.org/packages/d6/7d/216a1588b65a7aa5f4535570418a599d943c85afb1d95b0876fc00aa1468/pandas-3.0.1-cp313-cp313-win_amd64.whl", hash = "sha256:9fea306c783e28884c29057a1d9baa11a349bbf99538ec1da44c8476563d1b25", size = 9742769, upload-time = "2026-02-17T22:19:13.926Z" },
    { url = "https://files.pythonhosted.org/packages/c4/cb/810a22a6af9a4e97c8ab1c946b47f3489c5bca5adc483ce0ffc84c9cc768/pandas-3.0.1-cp313-cp313-win_arm64.whl", hash = "sha256:a8d37a43c52917427e897cb2e429f67a449327394396a81034a4449b99afda59", size = 9043855, upload-time = "2026-02-17T22:19:16.09Z" },
    { url = "https://files.pythonhosted.org/packages/92/fa/423c89086cca1f039cf1253c3ff5b90f157b5b3757314aa635f6bf3e30aa/pandas-3.0.1-cp313-cp313t-macosx_10_13_x86_64.whl", hash = "sha256:d54855f04f8246ed7b6fc96b05d4871591143c46c0b6f4af874764ed0d2d6f06", size = 10752673, upload-time = "2026-02-17T22:19:18.304Z" },
    { url = "https://files.pythonhosted.org/packages/22/23/b5a08ec1f40020397f0faba72f1e2c11f7596a6169c7b3e800abff0e433f/pandas-3.0.1-cp313-cp313t-macosx_11_0_arm64.whl", hash = "sha256:4e1b677accee34a09e0dc2ce5624e4a58a1870ffe56fc021e9caf7f23cd7668f", size = 10404967, upload-time = "2026-02-17T22:19:20.726Z" },
    { url = "https://files.pythonhosted.org/packages/5c/81/94841f1bb4afdc2b52a99daa895ac2c61600bb72e26525ecc9543d453ebc/pandas-3.0.1-cp313-cp313t-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:a9cabbdcd03f1b6cd254d6dda8ae09b0252524be1592594c00b7895916cb1324", size = 10320575, upload-time = "2026-02-17T22:19:24.919Z" },
    { url = "https://files.pythonhosted.org/packages/0a/8b/2ae37d66a5342a83adadfd0cb0b4bf9c3c7925424dd5f40d15d6cfaa35ee/pandas-3.0.1-cp313-cp313t-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:5ae2ab1f166668b41e770650101e7090824fd34d17915dd9cd479f5c5e0065e9", size = 10710921, upload-time = "2026-02-17T22:19:27.181Z" },
    { url = "https://files.pythonhosted.org/packages/a2/61/772b2e2757855e232b7ccf7cb8079a5711becb3a97f291c953def15a833f/pandas-3.0.1-cp313-cp313t-musllinux_1_2_aarch64.whl", hash = "sha256:6bf0603c2e30e2cafac32807b06435f28741135cb8697eae8b28c7d492fc7d76", size = 11334191, upload-time = "2026-02-17T22:19:29.411Z" },
    { url = "https://files.pythonhosted.org/packages/1b/08/b16c6df3ef555d8495d1d265a7963b65be166785d28f06a350913a4fac78/pandas-3.0.1-cp313-cp313t-musllinux_1_2_x86_64.whl", hash = "sha256:6c426422973973cae1f4a23e51d4ae85974f44871b24844e4f7de752dd877098", size = 11782256, upload-time = "2026-02-17T22:19:32.34Z" },
    { url = "https://files.pythonhosted.org/packages/55/80/178af0594890dee17e239fca96d3d8670ba0f5ff59b7d0439850924a9c09/pandas-3.0.1-cp313-cp313t-win_amd64.whl", hash = "sha256:b03f91ae8c10a85c1613102c7bef5229b5379f343030a3ccefeca8a33414cf35", size = 10485047, upload-time = "2026-02-17T22:19:34.605Z" },
]

[[package]]
name = "pillow"
version = "12.1.1"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/1f/42/5c74462b4fd957fcd7b13b04fb3205ff8349236ea74c7c375766d6c82288/pillow-12.1.1.tar.gz", hash = "sha256:9ad8fa5937ab05218e2b6a4cff30295ad35afd2f83ac592e68c0d871bb0fdbc4", size = 46980264, upload-time = "2026-02-11T04:23:07.146Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/d5/11/6db24d4bd7685583caeae54b7009584e38da3c3d4488ed4cd25b439de486/pillow-12.1.1-cp313-cp313-ios_13_0_arm64_iphoneos.whl", hash = "sha256:d242e8ac078781f1de88bf823d70c1a9b3c7950a44cdf4b7c012e22ccbcd8e4e", size = 4062689, upload-time = "2026-02-11T04:21:06.804Z" },
    { url = "https://files.pythonhosted.org/packages/33/c0/ce6d3b1fe190f0021203e0d9b5b99e57843e345f15f9ef22fcd43842fd21/pillow-12.1.1-cp313-cp313-ios_13_0_arm64_iphonesimulator.whl", hash = "sha256:02f84dfad02693676692746df05b89cf25597560db2857363a208e393429f5e9", size = 4138535, upload-time = "2026-02-11T04:21:08.452Z" },
    { url = "https://files.pythonhosted.org/packages/a0/c6/d5eb6a4fb32a3f9c21a8c7613ec706534ea1cf9f4b3663e99f0d83f6fca8/pillow-12.1.1-cp313-cp313-ios_13_0_x86_64_iphonesimulator.whl", hash = "sha256:e65498daf4b583091ccbb2556c7000abf0f3349fcd57ef7adc9a84a394ed29f6", size = 3601364, upload-time = "2026-02-11T04:21:10.194Z" },
    { url = "https://files.pythonhosted.org/packages/14/a1/16c4b823838ba4c9c52c0e6bbda903a3fe5a1bdbf1b8eb4fff7156f3e318/pillow-12.1.1-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:6c6db3b84c87d48d0088943bf33440e0c42370b99b1c2a7989216f7b42eede60", size = 5262561, upload-time = "2026-02-11T04:21:11.742Z" },
    { url = "https://files.pythonhosted.org/packages/bb/ad/ad9dc98ff24f485008aa5cdedaf1a219876f6f6c42a4626c08bc4e80b120/pillow-12.1.1-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:8b7e5304e34942bf62e15184219a7b5ad4ff7f3bb5cca4d984f37df1a0e1aee2", size = 4657460, upload-time = "2026-02-11T04:21:13.786Z" },
    { url = "https://files.pythonhosted.org/packages/9e/1b/f1a4ea9a895b5732152789326202a82464d5254759fbacae4deea3069334/pillow-12.1.1-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.whl", hash = "sha256:18e5bddd742a44b7e6b1e773ab5db102bd7a94c32555ba656e76d319d19c3850", size = 6232698, upload-time = "2026-02-11T04:21:15.949Z" },
    { url = "https://files.pythonhosted.org/packages/95/f4/86f51b8745070daf21fd2e5b1fe0eb35d4db9ca26e6d58366562fb56a743/pillow-12.1.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:fc44ef1f3de4f45b50ccf9136999d71abb99dca7706bc75d222ed350b9fd2289", size = 8041706, upload-time = "2026-02-11T04:21:17.723Z" },
    { url = "https://files.pythonhosted.org/packages/29/9b/d6ecd956bb1266dd1045e995cce9b8d77759e740953a1c9aad9502a0461e/pillow-12.1.1-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:5a8eb7ed8d4198bccbd07058416eeec51686b498e784eda166395a23eb99138e", size = 6346621, upload-time = "2026-02-11T04:21:19.547Z" },
    { url = "https://files.pythonhosted.org/packages/71/24/538bff45bde96535d7d998c6fed1a751c75ac7c53c37c90dc2601b243893/pillow-12.1.1-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:47b94983da0c642de92ced1702c5b6c292a84bd3a8e1d1702ff923f183594717", size = 7038069, upload-time = "2026-02-11T04:21:21.378Z" },
    { url = "https://files.pythonhosted.org/packages/94/0e/58cb1a6bc48f746bc4cb3adb8cabff73e2742c92b3bf7a220b7cf69b9177/pillow-12.1.1-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:518a48c2aab7ce596d3bf79d0e275661b846e86e4d0e7dec34712c30fe07f02a", size = 6460040, upload-time = "2026-02-11T04:21:23.148Z" },
    { url = "https://files.pythonhosted.org/packages/6c/57/9045cb3ff11eeb6c1adce3b2d60d7d299d7b273a2e6c8381a524abfdc474/pillow-12.1.1-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:a550ae29b95c6dc13cf69e2c9dc5747f814c54eeb2e32d683e5e93af56caa029", size = 7164523, upload-time = "2026-02-11T04:21:25.01Z" },
    { url = "https://files.pythonhosted.org/packages/73/f2/9be9cb99f2175f0d4dbadd6616ce1bf068ee54a28277ea1bf1fbf729c250/pillow-12.1.1-cp313-cp313-win32.whl", hash = "sha256:a003d7422449f6d1e3a34e3dd4110c22148336918ddbfc6a32581cd54b2e0b2b", size = 6332552, upload-time = "2026-02-11T04:21:27.238Z" },
    { url = "https://files.pythonhosted.org/packages/3f/eb/b0834ad8b583d7d9d42b80becff092082a1c3c156bb582590fcc973f1c7c/pillow-12.1.1-cp313-cp313-win_amd64.whl", hash = "sha256:344cf1e3dab3be4b1fa08e449323d98a2a3f819ad20f4b22e77a0ede31f0faa1", size = 7040108, upload-time = "2026-02-11T04:21:29.462Z" },
    { url = "https://files.pythonhosted.org/packages/d5/7d/fc09634e2aabdd0feabaff4a32f4a7d97789223e7c2042fd805ea4b4d2c2/pillow-12.1.1-cp313-cp313-win_arm64.whl", hash = "sha256:5c0dd1636633e7e6a0afe7bf6a51a14992b7f8e60de5789018ebbdfae55b040a", size = 2453712, upload-time = "2026-02-11T04:21:31.072Z" },
    { url = "https://files.pythonhosted.org/packages/19/2a/b9d62794fc8a0dd14c1943df68347badbd5511103e0d04c035ffe5cf2255/pillow-12.1.1-cp313-cp313t-macosx_10_13_x86_64.whl", hash = "sha256:0330d233c1a0ead844fc097a7d16c0abff4c12e856c0b325f231820fee1f39da", size = 5264880, upload-time = "2026-02-11T04:21:32.865Z" },
    { url = "https://files.pythonhosted.org/packages/26/9d/e03d857d1347fa5ed9247e123fcd2a97b6220e15e9cb73ca0a8d91702c6e/pillow-12.1.1-cp313-cp313t-macosx_11_0_arm64.whl", hash = "sha256:5dae5f21afb91322f2ff791895ddd8889e5e947ff59f71b46041c8ce6db790bc", size = 4660616, upload-time = "2026-02-11T04:21:34.97Z" },
    { url = "https://files.pythonhosted.org/packages/f7/ec/8a6d22afd02570d30954e043f09c32772bfe143ba9285e2fdb11284952cd/pillow-12.1.1-cp313-cp313t-manylinux2014_aarch64.manylinux_2_17_aarch64.whl", hash = "sha256:2e0c664be47252947d870ac0d327fea7e63985a08794758aa8af5b6cb6ec0c9c", size = 6269008, upload-time = "2026-02-11T04:21:36.623Z" },
    { url = "https://files.pythonhosted.org/packages/3d/1d/6d875422c9f28a4a361f495a5f68d9de4a66941dc2c619103ca335fa6446/pillow-12.1.1-cp313-cp313t-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:691ab2ac363b8217f7d31b3497108fb1f50faab2f75dfb03284ec2f217e87bf8", size = 8073226, upload-time = "2026-02-11T04:21:38.585Z" },
    { url = "https://files.pythonhosted.org/packages/a1/cd/134b0b6ee5eda6dc09e25e24b40fdafe11a520bc725c1d0bbaa5e00bf95b/pillow-12.1.1-cp313-cp313t-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:e9e8064fb1cc019296958595f6db671fba95209e3ceb0c4734c9baf97de04b20", size = 6380136, upload-time = "2026-02-11T04:21:40.562Z" },
    { url = "https://files.pythonhosted.org/packages/7a/a9/7628f013f18f001c1b98d8fffe3452f306a70dc6aba7d931019e0492f45e/pillow-12.1.1-cp313-cp313t-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:472a8d7ded663e6162dafdf20015c486a7009483ca671cece7a9279b512fcb13", size = 7067129, upload-time = "2026-02-11T04:21:42.521Z" },
    { url = "https://files.pythonhosted.org/packages/1e/f8/66ab30a2193b277785601e82ee2d49f68ea575d9637e5e234faaa98efa4c/pillow-12.1.1-cp313-cp313t-musllinux_1_2_aarch64.whl", hash = "sha256:89b54027a766529136a06cfebeecb3a04900397a3590fd252160b888479517bf", size = 6491807, upload-time = "2026-02-11T04:21:44.22Z" },
    { url = "https://files.pythonhosted.org/packages/da/0b/a877a6627dc8318fdb84e357c5e1a758c0941ab1ddffdafd231983788579/pillow-12.1.1-cp313-cp313t-musllinux_1_2_x86_64.whl", hash = "sha256:86172b0831b82ce4f7877f280055892b31179e1576aa00d0df3bb1bbf8c3e524", size = 7190954, upload-time = "2026-02-11T04:21:46.114Z" },
    { url = "https://files.pythonhosted.org/packages/83/43/6f732ff85743cf746b1361b91665d9f5155e1483817f693f8d57ea93147f/pillow-12.1.1-cp313-cp313t-win32.whl", hash = "sha256:44ce27545b6efcf0fdbdceb31c9a5bdea9333e664cda58a7e674bb74608b3986", size = 6336441, upload-time = "2026-02-11T04:21:48.22Z" },
    { url = "https://files.pythonhosted.org/packages/3b/44/e865ef3986611bb75bfabdf94a590016ea327833f434558801122979cd0e/pillow-12.1.1-cp313-cp313t-win_amd64.whl", hash = "sha256:a285e3eb7a5a45a2ff504e31f4a8d1b12ef62e84e5411c6804a42197c1cf586c", size = 7045383, upload-time = "2026-02-11T04:21:50.015Z" },
    { url = "https://files.pythonhosted.org/packages/a8/c6/f4fb24268d0c6908b9f04143697ea18b0379490cb74ba9e8d41b898bd005/pillow-12.1.1-cp313-cp313t-win_arm64.whl", hash = "sha256:cc7d296b5ea4d29e6570dabeaed58d31c3fea35a633a69679fb03d7664f43fb3", size = 2456104, upload-time = "2026-02-11T04:21:51.633Z" },
]

[[package]]
name = "pluggy"
version = "1.6.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/f9/e2/3e91f31a7d2b083fe6ef3fa267035b518369d9511ffab804f839851d2779/pluggy-1.6.0.tar.gz", hash = "sha256:7dcc130b76258d33b90f61b658791dede3486c3e6bfb003ee5c9bfb396dd22f3", size = 69412, upload-time = "2025-05-15T12:30:07.975Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/54/20/4d324d65cc6d9205fabedc306948156824eb9f0ee1633355a8f7ec5c66bf/pluggy-1.6.0-py3-none-any.whl", hash = "sha256:e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746", size = 20538, upload-time = "2025-05-15T12:30:06.134Z" },
]

[[package]]
name = "portalocker"
version = "3.2.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "pywin32", marker = "sys_platform == 'win32'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/5e/77/65b857a69ed876e1951e88aaba60f5ce6120c33703f7cb61a3c894b8c1b6/portalocker-3.2.0.tar.gz", hash = "sha256:1f3002956a54a8c3730586c5c77bf18fae4149e07eaf1c29fc3faf4d5a3f89ac", size = 95644, upload-time = "2025-06-14T13:20:40.03Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/4b/a6/38c8e2f318bf67d338f4d629e93b0b4b9af331f455f0390ea8ce4a099b26/portalocker-3.2.0-py3-none-any.whl", hash = "sha256:3cdc5f565312224bc570c49337bd21428bba0ef363bbcf58b9ef4a9f11779968", size = 22424, upload-time = "2025-06-14T13:20:38.083Z" },
]

[[package]]
name = "pyasn1"
version = "0.6.2"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/fe/b6/6e630dff89739fcd427e3f72b3d905ce0acb85a45d4ec3e2678718a3487f/pyasn1-0.6.2.tar.gz", hash = "sha256:9b59a2b25ba7e4f8197db7686c09fb33e658b98339fadb826e9512629017833b", size = 146586, upload-time = "2026-01-16T18:04:18.534Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/44/b5/a96872e5184f354da9c84ae119971a0a4c221fe9b27a4d94bd43f2596727/pyasn1-0.6.2-py3-none-any.whl", hash = "sha256:1eb26d860996a18e9b6ed05e7aae0e9fc21619fcee6af91cca9bad4fbea224bf", size = 83371, upload-time = "2026-01-16T18:04:17.174Z" },
]

[[package]]
name = "pyasn1-modules"
version = "0.4.2"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "pyasn1" },
]
sdist = { url = "https://files.pythonhosted.org/packages/e9/e6/78ebbb10a8c8e4b61a59249394a4a594c1a7af95593dc933a349c8d00964/pyasn1_modules-0.4.2.tar.gz", hash = "sha256:677091de870a80aae844b1ca6134f54652fa2c8c5a52aa396440ac3106e941e6", size = 307892, upload-time = "2025-03-28T02:41:22.17Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/47/8d/d529b5d697919ba8c11ad626e835d4039be708a35b0d22de83a269a6682c/pyasn1_modules-0.4.2-py3-none-any.whl", hash = "sha256:29253a9207ce32b64c3ac6600edc75368f98473906e8fd1043bd6b5b1de2c14a", size = 181259, upload-time = "2025-03-28T02:41:19.028Z" },
]

[[package]]
name = "pycparser"
version = "3.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/1b/7d/92392ff7815c21062bea51aa7b87d45576f649f16458d78b7cf94b9ab2e6/pycparser-3.0.tar.gz", hash = "sha256:600f49d217304a5902ac3c37e1281c9fe94e4d0489de643a9504c5cdfdfc6b29", size = 103492, upload-time = "2026-01-21T14:26:51.89Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/0c/c3/44f3fbbfa403ea2a7c779186dc20772604442dde72947e7d01069cbe98e3/pycparser-3.0-py3-none-any.whl", hash = "sha256:b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992", size = 48172, upload-time = "2026-01-21T14:26:50.693Z" },
]

[[package]]
name = "pydantic"
version = "2.12.5"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "annotated-types" },
    { name = "pydantic-core" },
    { name = "typing-extensions" },
    { name = "typing-inspection" },
]
sdist = { url = "https://files.pythonhosted.org/packages/69/44/36f1a6e523abc58ae5f928898e4aca2e0ea509b5aa6f6f392a5d882be928/pydantic-2.12.5.tar.gz", hash = "sha256:4d351024c75c0f085a9febbb665ce8c0c6ec5d30e903bdb6394b7ede26aebb49", size = 821591, upload-time = "2025-11-26T15:11:46.471Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/5a/87/b70ad306ebb6f9b585f114d0ac2137d792b48be34d732d60e597c2f8465a/pydantic-2.12.5-py3-none-any.whl", hash = "sha256:e561593fccf61e8a20fc46dfc2dfe075b8be7d0188df33f221ad1f0139180f9d", size = 463580, upload-time = "2025-11-26T15:11:44.605Z" },
]

[[package]]
name = "pydantic-core"
version = "2.41.5"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "typing-extensions" },
]
sdist = { url = "https://files.pythonhosted.org/packages/71/70/23b021c950c2addd24ec408e9ab05d59b035b39d97cdc1130e1bce647bb6/pydantic_core-2.41.5.tar.gz", hash = "sha256:08daa51ea16ad373ffd5e7606252cc32f07bc72b28284b6bc9c6df804816476e", size = 460952, upload-time = "2025-11-04T13:43:49.098Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/87/06/8806241ff1f70d9939f9af039c6c35f2360cf16e93c2ca76f184e76b1564/pydantic_core-2.41.5-cp313-cp313-macosx_10_12_x86_64.whl", hash = "sha256:941103c9be18ac8daf7b7adca8228f8ed6bb7a1849020f643b3a14d15b1924d9", size = 2120403, upload-time = "2025-11-04T13:40:25.248Z" },
    { url = "https://files.pythonhosted.org/packages/94/02/abfa0e0bda67faa65fef1c84971c7e45928e108fe24333c81f3bfe35d5f5/pydantic_core-2.41.5-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:112e305c3314f40c93998e567879e887a3160bb8689ef3d2c04b6cc62c33ac34", size = 1896206, upload-time = "2025-11-04T13:40:27.099Z" },
    { url = "https://files.pythonhosted.org/packages/15/df/a4c740c0943e93e6500f9eb23f4ca7ec9bf71b19e608ae5b579678c8d02f/pydantic_core-2.41.5-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:0cbaad15cb0c90aa221d43c00e77bb33c93e8d36e0bf74760cd00e732d10a6a0", size = 1919307, upload-time = "2025-11-04T13:40:29.806Z" },
    { url = "https://files.pythonhosted.org/packages/9a/e3/6324802931ae1d123528988e0e86587c2072ac2e5394b4bc2bc34b61ff6e/pydantic_core-2.41.5-cp313-cp313-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:03ca43e12fab6023fc79d28ca6b39b05f794ad08ec2feccc59a339b02f2b3d33", size = 2063258, upload-time = "2025-11-04T13:40:33.544Z" },
    { url = "https://files.pythonhosted.org/packages/c9/d4/2230d7151d4957dd79c3044ea26346c148c98fbf0ee6ebd41056f2d62ab5/pydantic_core-2.41.5-cp313-cp313-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:dc799088c08fa04e43144b164feb0c13f9a0bc40503f8df3e9fde58a3c0c101e", size = 2214917, upload-time = "2025-11-04T13:40:35.479Z" },
    { url = "https://files.pythonhosted.org/packages/e6/9f/eaac5df17a3672fef0081b6c1bb0b82b33ee89aa5cec0d7b05f52fd4a1fa/pydantic_core-2.41.5-cp313-cp313-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:97aeba56665b4c3235a0e52b2c2f5ae9cd071b8a8310ad27bddb3f7fb30e9aa2", size = 2332186, upload-time = "2025-11-04T13:40:37.436Z" },
    { url = "https://files.pythonhosted.org/packages/cf/4e/35a80cae583a37cf15604b44240e45c05e04e86f9cfd766623149297e971/pydantic_core-2.41.5-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:406bf18d345822d6c21366031003612b9c77b3e29ffdb0f612367352aab7d586", size = 2073164, upload-time = "2025-11-04T13:40:40.289Z" },
    { url = "https://files.pythonhosted.org/packages/bf/e3/f6e262673c6140dd3305d144d032f7bd5f7497d3871c1428521f19f9efa2/pydantic_core-2.41.5-cp313-cp313-manylinux_2_5_i686.manylinux1_i686.whl", hash = "sha256:b93590ae81f7010dbe380cdeab6f515902ebcbefe0b9327cc4804d74e93ae69d", size = 2179146, upload-time = "2025-11-04T13:40:42.809Z" },
    { url = "https://files.pythonhosted.org/packages/75/c7/20bd7fc05f0c6ea2056a4565c6f36f8968c0924f19b7d97bbfea55780e73/pydantic_core-2.41.5-cp313-cp313-musllinux_1_1_aarch64.whl", hash = "sha256:01a3d0ab748ee531f4ea6c3e48ad9dac84ddba4b0d82291f87248f2f9de8d740", size = 2137788, upload-time = "2025-11-04T13:40:44.752Z" },
    { url = "https://files.pythonhosted.org/packages/3a/8d/34318ef985c45196e004bc46c6eab2eda437e744c124ef0dbe1ff2c9d06b/pydantic_core-2.41.5-cp313-cp313-musllinux_1_1_armv7l.whl", hash = "sha256:6561e94ba9dacc9c61bce40e2d6bdc3bfaa0259d3ff36ace3b1e6901936d2e3e", size = 2340133, upload-time = "2025-11-04T13:40:46.66Z" },
    { url = "https://files.pythonhosted.org/packages/9c/59/013626bf8c78a5a5d9350d12e7697d3d4de951a75565496abd40ccd46bee/pydantic_core-2.41.5-cp313-cp313-musllinux_1_1_x86_64.whl", hash = "sha256:915c3d10f81bec3a74fbd4faebe8391013ba61e5a1a8d48c4455b923bdda7858", size = 2324852, upload-time = "2025-11-04T13:40:48.575Z" },
    { url = "https://files.pythonhosted.org/packages/1a/d9/c248c103856f807ef70c18a4f986693a46a8ffe1602e5d361485da502d20/pydantic_core-2.41.5-cp313-cp313-win32.whl", hash = "sha256:650ae77860b45cfa6e2cdafc42618ceafab3a2d9a3811fcfbd3bbf8ac3c40d36", size = 1994679, upload-time = "2025-11-04T13:40:50.619Z" },
    { url = "https://files.pythonhosted.org/packages/9e/8b/341991b158ddab181cff136acd2552c9f35bd30380422a639c0671e99a91/pydantic_core-2.41.5-cp313-cp313-win_amd64.whl", hash = "sha256:79ec52ec461e99e13791ec6508c722742ad745571f234ea6255bed38c6480f11", size = 2019766, upload-time = "2025-11-04T13:40:52.631Z" },
    { url = "https://files.pythonhosted.org/packages/73/7d/f2f9db34af103bea3e09735bb40b021788a5e834c81eedb541991badf8f5/pydantic_core-2.41.5-cp313-cp313-win_arm64.whl", hash = "sha256:3f84d5c1b4ab906093bdc1ff10484838aca54ef08de4afa9de0f5f14d69639cd", size = 1981005, upload-time = "2025-11-04T13:40:54.734Z" },
]

[[package]]
name = "pydub"
version = "0.25.1"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/fe/9a/e6bca0eed82db26562c73b5076539a4a08d3cffd19c3cc5913a3e61145fd/pydub-0.25.1.tar.gz", hash = "sha256:980a33ce9949cab2a569606b65674d748ecbca4f0796887fd6f46173a7b0d30f", size = 38326, upload-time = "2021-03-10T02:09:54.659Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/a6/53/d78dc063216e62fc55f6b2eebb447f6a4b0a59f55c8406376f76bf959b08/pydub-0.25.1-py2.py3-none-any.whl", hash = "sha256:65617e33033874b59d87db603aa1ed450633288aefead953b30bded59cb599a6", size = 32327, upload-time = "2021-03-10T02:09:53.503Z" },
]

[[package]]
name = "pygments"
version = "2.19.2"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/b0/77/a5b8c569bf593b0140bde72ea885a803b82086995367bf2037de0159d924/pygments-2.19.2.tar.gz", hash = "sha256:636cb2477cec7f8952536970bc533bc43743542f70392ae026374600add5b887", size = 4968631, upload-time = "2025-06-21T13:39:12.283Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/c7/21/705964c7812476f378728bdf590ca4b771ec72385c533964653c68e86bdc/pygments-2.19.2-py3-none-any.whl", hash = "sha256:86540386c03d588bb81d44bc3928634ff26449851e99741617ecb9037ee5ec0b", size = 1225217, upload-time = "2025-06-21T13:39:07.939Z" },
]

[[package]]
name = "pyobjc-core"
version = "12.1"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/b8/b6/d5612eb40be4fd5ef88c259339e6313f46ba67577a95d86c3470b951fce0/pyobjc_core-12.1.tar.gz", hash = "sha256:2bb3903f5387f72422145e1466b3ac3f7f0ef2e9960afa9bcd8961c5cbf8bd21", size = 1000532, upload-time = "2025-11-14T10:08:28.292Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/f4/d2/29e5e536adc07bc3d33dd09f3f7cf844bf7b4981820dc2a91dd810f3c782/pyobjc_core-12.1-cp313-cp313-macosx_10_13_universal2.whl", hash = "sha256:01c0cf500596f03e21c23aef9b5f326b9fb1f8f118cf0d8b66749b6cf4cbb37a", size = 677370, upload-time = "2025-11-14T09:33:05.273Z" },
    { url = "https://files.pythonhosted.org/packages/1b/f0/4b4ed8924cd04e425f2a07269943018d43949afad1c348c3ed4d9d032787/pyobjc_core-12.1-cp313-cp313t-macosx_10_13_universal2.whl", hash = "sha256:177aaca84bb369a483e4961186704f64b2697708046745f8167e818d968c88fc", size = 719586, upload-time = "2025-11-14T09:33:53.302Z" },
]

[[package]]
name = "pyobjc-framework-cocoa"
version = "12.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "pyobjc-core", marker = "sys_platform != 'emscripten' and sys_platform != 'win32'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/02/a3/16ca9a15e77c061a9250afbae2eae26f2e1579eb8ca9462ae2d2c71e1169/pyobjc_framework_cocoa-12.1.tar.gz", hash = "sha256:5556c87db95711b985d5efdaaf01c917ddd41d148b1e52a0c66b1a2e2c5c1640", size = 2772191, upload-time = "2025-11-14T10:13:02.069Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/ad/31/0c2e734165abb46215797bd830c4bdcb780b699854b15f2b6240515edcc6/pyobjc_framework_cocoa-12.1-cp313-cp313-macosx_10_13_universal2.whl", hash = "sha256:5a3dcd491cacc2f5a197142b3c556d8aafa3963011110102a093349017705118", size = 384689, upload-time = "2025-11-14T09:41:41.478Z" },
    { url = "https://files.pythonhosted.org/packages/23/3b/b9f61be7b9f9b4e0a6db18b3c35c4c4d589f2d04e963e2174d38c6555a92/pyobjc_framework_cocoa-12.1-cp313-cp313t-macosx_10_13_universal2.whl", hash = "sha256:914b74328c22d8ca261d78c23ef2befc29776e0b85555973927b338c5734ca44", size = 388843, upload-time = "2025-11-14T09:42:05.719Z" },
]

[[package]]
name = "pyobjc-framework-quartz"
version = "12.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "pyobjc-core", marker = "sys_platform != 'emscripten' and sys_platform != 'win32'" },
    { name = "pyobjc-framework-cocoa", marker = "sys_platform != 'emscripten' and sys_platform != 'win32'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/94/18/cc59f3d4355c9456fc945eae7fe8797003c4da99212dd531ad1b0de8a0c6/pyobjc_framework_quartz-12.1.tar.gz", hash = "sha256:27f782f3513ac88ec9b6c82d9767eef95a5cf4175ce88a1e5a65875fee799608", size = 3159099, upload-time = "2025-11-14T10:21:24.31Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/ba/2d/e8f495328101898c16c32ac10e7b14b08ff2c443a756a76fd1271915f097/pyobjc_framework_quartz-12.1-cp313-cp313-macosx_10_13_universal2.whl", hash = "sha256:629b7971b1b43a11617f1460cd218bd308dfea247cd4ee3842eb40ca6f588860", size = 219206, upload-time = "2025-11-14T10:00:15.623Z" },
    { url = "https://files.pythonhosted.org/packages/67/43/b1f0ad3b842ab150a7e6b7d97f6257eab6af241b4c7d14cb8e7fde9214b8/pyobjc_framework_quartz-12.1-cp313-cp313t-macosx_10_13_universal2.whl", hash = "sha256:53b84e880c358ba1ddcd7e8d5ea0407d760eca58b96f0d344829162cda5f37b3", size = 224317, upload-time = "2025-11-14T10:00:30.703Z" },
]

[[package]]
name = "pystray"
version = "0.19.5"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "pillow" },
    { name = "pyobjc-framework-quartz", marker = "sys_platform == 'darwin'" },
    { name = "python-xlib", marker = "sys_platform == 'linux'" },
    { name = "six" },
]
wheels = [
    { url = "https://files.pythonhosted.org/packages/5c/64/927a4b9024196a4799eba0180e0ca31568426f258a4a5c90f87a97f51d28/pystray-0.19.5-py2.py3-none-any.whl", hash = "sha256:a0c2229d02cf87207297c22d86ffc57c86c227517b038c0d3c59df79295ac617", size = 49068, upload-time = "2023-09-17T13:44:26.872Z" },
]

[[package]]
name = "pytest"
version = "9.0.2"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "colorama", marker = "sys_platform == 'win32'" },
    { name = "iniconfig" },
    { name = "packaging" },
    { name = "pluggy" },
    { name = "pygments" },
]
sdist = { url = "https://files.pythonhosted.org/packages/d1/db/7ef3487e0fb0049ddb5ce41d3a49c235bf9ad299b6a25d5780a89f19230f/pytest-9.0.2.tar.gz", hash = "sha256:75186651a92bd89611d1d9fc20f0b4345fd827c41ccd5c299a868a05d70edf11", size = 1568901, upload-time = "2025-12-06T21:30:51.014Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/3b/ab/b3226f0bd7cdcf710fbede2b3548584366da3b19b5021e74f5bde2a8fa3f/pytest-9.0.2-py3-none-any.whl", hash = "sha256:711ffd45bf766d5264d487b917733b453d917afd2b0ad65223959f59089f875b", size = 374801, upload-time = "2025-12-06T21:30:49.154Z" },
]

[[package]]
name = "pytest-asyncio"
version = "1.3.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "pytest" },
]
sdist = { url = "https://files.pythonhosted.org/packages/90/2c/8af215c0f776415f3590cac4f9086ccefd6fd463befeae41cd4d3f193e5a/pytest_asyncio-1.3.0.tar.gz", hash = "sha256:d7f52f36d231b80ee124cd216ffb19369aa168fc10095013c6b014a34d3ee9e5", size = 50087, upload-time = "2025-11-10T16:07:47.256Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/e5/35/f8b19922b6a25bc0880171a2f1a003eaeb93657475193ab516fd87cac9da/pytest_asyncio-1.3.0-py3-none-any.whl", hash = "sha256:611e26147c7f77640e6d0a92a38ed17c3e9848063698d5c93d5aa7aa11cebff5", size = 15075, upload-time = "2025-11-10T16:07:45.537Z" },
]

[[package]]
name = "python-dateutil"
version = "2.9.0.post0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "six" },
]
sdist = { url = "https://files.pythonhosted.org/packages/66/c0/0c8b6ad9f17a802ee498c46e004a0eb49bc148f2fd230864601a86dcf6db/python-dateutil-2.9.0.post0.tar.gz", hash = "sha256:37dd54208da7e1cd875388217d5e00ebd4179249f90fb72437e91a35459a0ad3", size = 342432, upload-time = "2024-03-01T18:36:20.211Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/ec/57/56b9bcc3c9c6a792fcbaf139543cee77261f3651ca9da0c93f5c1221264b/python_dateutil-2.9.0.post0-py2.py3-none-any.whl", hash = "sha256:a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427", size = 229892, upload-time = "2024-03-01T18:36:18.57Z" },
]

[[package]]
name = "python-dotenv"
version = "1.2.1"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/f0/26/19cadc79a718c5edbec86fd4919a6b6d3f681039a2f6d66d14be94e75fb9/python_dotenv-1.2.1.tar.gz", hash = "sha256:42667e897e16ab0d66954af0e60a9caa94f0fd4ecf3aaf6d2d260eec1aa36ad6", size = 44221, upload-time = "2025-10-26T15:12:10.434Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/14/1b/a298b06749107c305e1fe0f814c6c74aea7b2f1e10989cb30f544a1b3253/python_dotenv-1.2.1-py3-none-any.whl", hash = "sha256:b81ee9561e9ca4004139c6cbba3a238c32b03e4894671e181b671e8cb8425d61", size = 21230, upload-time = "2025-10-26T15:12:09.109Z" },
]

[[package]]
name = "python-multipart"
version = "0.0.22"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/94/01/979e98d542a70714b0cb2b6728ed0b7c46792b695e3eaec3e20711271ca3/python_multipart-0.0.22.tar.gz", hash = "sha256:7340bef99a7e0032613f56dc36027b959fd3b30a787ed62d310e951f7c3a3a58", size = 37612, upload-time = "2026-01-25T10:15:56.219Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/1b/d0/397f9626e711ff749a95d96b7af99b9c566a9bb5129b8e4c10fc4d100304/python_multipart-0.0.22-py3-none-any.whl", hash = "sha256:2b2cd894c83d21bf49d702499531c7bafd057d730c201782048f7945d82de155", size = 24579, upload-time = "2026-01-25T10:15:54.811Z" },
]

[[package]]
name = "python-xlib"
version = "0.33"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "six", marker = "sys_platform != 'emscripten' and sys_platform != 'win32'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/86/f5/8c0653e5bb54e0cbdfe27bf32d41f27bc4e12faa8742778c17f2a71be2c0/python-xlib-0.33.tar.gz", hash = "sha256:55af7906a2c75ce6cb280a584776080602444f75815a7aff4d287bb2d7018b32", size = 269068, upload-time = "2022-12-25T18:53:00.824Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/fc/b8/ff33610932e0ee81ae7f1269c890f697d56ff74b9f5b2ee5d9b7fa2c5355/python_xlib-0.33-py2.py3-none-any.whl", hash = "sha256:c3534038d42e0df2f1392a1b30a15a4ff5fdc2b86cfa94f072bf11b10a164398", size = 182185, upload-time = "2022-12-25T18:52:58.662Z" },
]

[[package]]
name = "pytz"
version = "2025.2"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/f8/bf/abbd3cdfb8fbc7fb3d4d38d320f2441b1e7cbe29be4f23797b4a2b5d8aac/pytz-2025.2.tar.gz", hash = "sha256:360b9e3dbb49a209c21ad61809c7fb453643e048b38924c765813546746e81c3", size = 320884, upload-time = "2025-03-25T02:25:00.538Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/81/c4/34e93fe5f5429d7570ec1fa436f1986fb1f00c3e0f43a589fe2bbcd22c3f/pytz-2025.2-py2.py3-none-any.whl", hash = "sha256:5ddf76296dd8c44c26eb8f4b6f35488f3ccbf6fbbd7adee0b7262d43f0ec2f00", size = 509225, upload-time = "2025-03-25T02:24:58.468Z" },
]

[[package]]
name = "pywin32"
version = "311"
source = { registry = "https://pypi.org/simple" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/a5/be/3fd5de0979fcb3994bfee0d65ed8ca9506a8a1260651b86174f6a86f52b3/pywin32-311-cp313-cp313-win32.whl", hash = "sha256:f95ba5a847cba10dd8c4d8fefa9f2a6cf283b8b88ed6178fa8a6c1ab16054d0d", size = 8705700, upload-time = "2025-07-14T20:13:26.471Z" },
    { url = "https://files.pythonhosted.org/packages/e3/28/e0a1909523c6890208295a29e05c2adb2126364e289826c0a8bc7297bd5c/pywin32-311-cp313-cp313-win_amd64.whl", hash = "sha256:718a38f7e5b058e76aee1c56ddd06908116d35147e133427e59a3983f703a20d", size = 9494700, upload-time = "2025-07-14T20:13:28.243Z" },
    { url = "https://files.pythonhosted.org/packages/04/bf/90339ac0f55726dce7d794e6d79a18a91265bdf3aa70b6b9ca52f35e022a/pywin32-311-cp313-cp313-win_arm64.whl", hash = "sha256:7b4075d959648406202d92a2310cb990fea19b535c7f4a78d3f5e10b926eeb8a", size = 8709318, upload-time = "2025-07-14T20:13:30.348Z" },
]

[[package]]
name = "pyyaml"
version = "6.0.3"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz", hash = "sha256:d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f", size = 130960, upload-time = "2025-09-25T21:33:16.546Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/d1/11/0fd08f8192109f7169db964b5707a2f1e8b745d4e239b784a5a1dd80d1db/pyyaml-6.0.3-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:8da9669d359f02c0b91ccc01cac4a67f16afec0dac22c2ad09f46bee0697eba8", size = 181669, upload-time = "2025-09-25T21:32:23.673Z" },
    { url = "https://files.pythonhosted.org/packages/b1/16/95309993f1d3748cd644e02e38b75d50cbc0d9561d21f390a76242ce073f/pyyaml-6.0.3-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:2283a07e2c21a2aa78d9c4442724ec1eb15f5e42a723b99cb3d822d48f5f7ad1", size = 173252, upload-time = "2025-09-25T21:32:25.149Z" },
    { url = "https://files.pythonhosted.org/packages/50/31/b20f376d3f810b9b2371e72ef5adb33879b25edb7a6d072cb7ca0c486398/pyyaml-6.0.3-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:ee2922902c45ae8ccada2c5b501ab86c36525b883eff4255313a253a3160861c", size = 767081, upload-time = "2025-09-25T21:32:26.575Z" },
    { url = "https://files.pythonhosted.org/packages/49/1e/a55ca81e949270d5d4432fbbd19dfea5321eda7c41a849d443dc92fd1ff7/pyyaml-6.0.3-cp313-cp313-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl", hash = "sha256:a33284e20b78bd4a18c8c2282d549d10bc8408a2a7ff57653c0cf0b9be0afce5", size = 841159, upload-time = "2025-09-25T21:32:27.727Z" },
    { url = "https://files.pythonhosted.org/packages/74/27/e5b8f34d02d9995b80abcef563ea1f8b56d20134d8f4e5e81733b1feceb2/pyyaml-6.0.3-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:0f29edc409a6392443abf94b9cf89ce99889a1dd5376d94316ae5145dfedd5d6", size = 801626, upload-time = "2025-09-25T21:32:28.878Z" },
    { url = "https://files.pythonhosted.org/packages/f9/11/ba845c23988798f40e52ba45f34849aa8a1f2d4af4b798588010792ebad6/pyyaml-6.0.3-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:f7057c9a337546edc7973c0d3ba84ddcdf0daa14533c2065749c9075001090e6", size = 753613, upload-time = "2025-09-25T21:32:30.178Z" },
    { url = "https://files.pythonhosted.org/packages/3d/e0/7966e1a7bfc0a45bf0a7fb6b98ea03fc9b8d84fa7f2229e9659680b69ee3/pyyaml-6.0.3-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:eda16858a3cab07b80edaf74336ece1f986ba330fdb8ee0d6c0d68fe82bc96be", size = 794115, upload-time = "2025-09-25T21:32:31.353Z" },
    { url = "https://files.pythonhosted.org/packages/de/94/980b50a6531b3019e45ddeada0626d45fa85cbe22300844a7983285bed3b/pyyaml-6.0.3-cp313-cp313-win32.whl", hash = "sha256:d0eae10f8159e8fdad514efdc92d74fd8d682c933a6dd088030f3834bc8e6b26", size = 137427, upload-time = "2025-09-25T21:32:32.58Z" },
    { url = "https://files.pythonhosted.org/packages/97/c9/39d5b874e8b28845e4ec2202b5da735d0199dbe5b8fb85f91398814a9a46/pyyaml-6.0.3-cp313-cp313-win_amd64.whl", hash = "sha256:79005a0d97d5ddabfeeea4cf676af11e647e41d81c9a7722a193022accdb6b7c", size = 154090, upload-time = "2025-09-25T21:32:33.659Z" },
    { url = "https://files.pythonhosted.org/packages/73/e8/2bdf3ca2090f68bb3d75b44da7bbc71843b19c9f2b9cb9b0f4ab7a5a4329/pyyaml-6.0.3-cp313-cp313-win_arm64.whl", hash = "sha256:5498cd1645aa724a7c71c8f378eb29ebe23da2fc0d7a08071d89469bf1d2defb", size = 140246, upload-time = "2025-09-25T21:32:34.663Z" },
]

[[package]]
name = "real-time-translation"
version = "0.1.0"
source = { editable = "." }
dependencies = [
    { name = "deepgram-sdk" },
    { name = "google-genai" },
    { name = "gradio" },
    { name = "langchain" },
    { name = "langchain-google-genai" },
    { name = "langchain-openai" },
    { name = "pystray" },
    { name = "python-dotenv" },
    { name = "sacrebleu" },
]

[package.optional-dependencies]
dev = [
    { name = "pytest" },
    { name = "pytest-asyncio" },
    { name = "ruff" },
]
microphone = [
    { name = "numpy" },
    { name = "sounddevice" },
]
zoom = [
    { name = "rtms" },
]

[package.metadata]
requires-dist = [
    { name = "deepgram-sdk", specifier = ">=5.3.2" },
    { name = "google-genai", specifier = ">=1.58.0" },
    { name = "gradio", specifier = ">=6.3.0" },
    { name = "langchain", specifier = ">=1.2.6" },
    { name = "langchain-google-genai", specifier = ">=4.2.0" },
    { name = "langchain-openai", specifier = ">=0.2.0" },
    { name = "numpy", marker = "extra == 'microphone'", specifier = ">=1.26.0" },
    { name = "pystray", specifier = ">=0.19.5" },
    { name = "pytest", marker = "extra == 'dev'", specifier = ">=8.0.0" },
    { name = "pytest-asyncio", marker = "extra == 'dev'", specifier = ">=0.24.0" },
    { name = "python-dotenv", specifier = ">=1.0.0" },
    { name = "rtms", marker = "extra == 'zoom'", specifier = ">=0.0.2", index = "https://test.pypi.org/simple/" },
    { name = "ruff", marker = "extra == 'dev'", specifier = ">=0.8.0" },
    { name = "sacrebleu", specifier = ">=2.4.0" },
    { name = "sounddevice", marker = "extra == 'microphone'", specifier = ">=0.4.7" },
]
provides-extras = ["zoom", "microphone", "dev"]

[[package]]
name = "regex"
version = "2026.1.15"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/0b/86/07d5056945f9ec4590b518171c4254a5925832eb727b56d3c38a7476f316/regex-2026.1.15.tar.gz", hash = "sha256:164759aa25575cbc0651bef59a0b18353e54300d79ace8084c818ad8ac72b7d5", size = 414811, upload-time = "2026-01-14T23:18:02.775Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/f8/2e/6870bb16e982669b674cce3ee9ff2d1d46ab80528ee6bcc20fb2292efb60/regex-2026.1.15-cp313-cp313-macosx_10_13_universal2.whl", hash = "sha256:e69d0deeb977ffe7ed3d2e4439360089f9c3f217ada608f0f88ebd67afb6385e", size = 489164, upload-time = "2026-01-14T23:15:13.962Z" },
    { url = "https://files.pythonhosted.org/packages/dc/67/9774542e203849b0286badf67199970a44ebdb0cc5fb739f06e47ada72f8/regex-2026.1.15-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:3601ffb5375de85a16f407854d11cca8fe3f5febbe3ac78fb2866bb220c74d10", size = 291218, upload-time = "2026-01-14T23:15:15.647Z" },
    { url = "https://files.pythonhosted.org/packages/b2/87/b0cda79f22b8dee05f774922a214da109f9a4c0eca5da2c9d72d77ea062c/regex-2026.1.15-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:4c5ef43b5c2d4114eb8ea424bb8c9cec01d5d17f242af88b2448f5ee81caadbc", size = 288895, upload-time = "2026-01-14T23:15:17.788Z" },
    { url = "https://files.pythonhosted.org/packages/3b/6a/0041f0a2170d32be01ab981d6346c83a8934277d82c780d60b127331f264/regex-2026.1.15-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:968c14d4f03e10b2fd960f1d5168c1f0ac969381d3c1fcc973bc45fb06346599", size = 798680, upload-time = "2026-01-14T23:15:19.342Z" },
    { url = "https://files.pythonhosted.org/packages/58/de/30e1cfcdbe3e891324aa7568b7c968771f82190df5524fabc1138cb2d45a/regex-2026.1.15-cp313-cp313-manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:56a5595d0f892f214609c9f76b41b7428bed439d98dc961efafdd1354d42baae", size = 864210, upload-time = "2026-01-14T23:15:22.005Z" },
    { url = "https://files.pythonhosted.org/packages/64/44/4db2f5c5ca0ccd40ff052ae7b1e9731352fcdad946c2b812285a7505ca75/regex-2026.1.15-cp313-cp313-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl", hash = "sha256:0bf650f26087363434c4e560011f8e4e738f6f3e029b85d4904c50135b86cfa5", size = 912358, upload-time = "2026-01-14T23:15:24.569Z" },
    { url = "https://files.pythonhosted.org/packages/79/b6/e6a5665d43a7c42467138c8a2549be432bad22cbd206f5ec87162de74bd7/regex-2026.1.15-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:18388a62989c72ac24de75f1449d0fb0b04dfccd0a1a7c1c43af5eb503d890f6", size = 803583, upload-time = "2026-01-14T23:15:26.526Z" },
    { url = "https://files.pythonhosted.org/packages/e7/53/7cd478222169d85d74d7437e74750005e993f52f335f7c04ff7adfda3310/regex-2026.1.15-cp313-cp313-manylinux_2_31_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:6d220a2517f5893f55daac983bfa9fe998a7dbcaee4f5d27a88500f8b7873788", size = 775782, upload-time = "2026-01-14T23:15:29.352Z" },
    { url = "https://files.pythonhosted.org/packages/ca/b5/75f9a9ee4b03a7c009fe60500fe550b45df94f0955ca29af16333ef557c5/regex-2026.1.15-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:c9c08c2fbc6120e70abff5d7f28ffb4d969e14294fb2143b4b5c7d20e46d1714", size = 787978, upload-time = "2026-01-14T23:15:31.295Z" },
    { url = "https://files.pythonhosted.org/packages/72/b3/79821c826245bbe9ccbb54f6eadb7879c722fd3e0248c17bfc90bf54e123/regex-2026.1.15-cp313-cp313-musllinux_1_2_ppc64le.whl", hash = "sha256:7ef7d5d4bd49ec7364315167a4134a015f61e8266c6d446fc116a9ac4456e10d", size = 858550, upload-time = "2026-01-14T23:15:33.558Z" },
    { url = "https://files.pythonhosted.org/packages/4a/85/2ab5f77a1c465745bfbfcb3ad63178a58337ae8d5274315e2cc623a822fa/regex-2026.1.15-cp313-cp313-musllinux_1_2_riscv64.whl", hash = "sha256:6e42844ad64194fa08d5ccb75fe6a459b9b08e6d7296bd704460168d58a388f3", size = 763747, upload-time = "2026-01-14T23:15:35.206Z" },
    { url = "https://files.pythonhosted.org/packages/6d/84/c27df502d4bfe2873a3e3a7cf1bdb2b9cc10284d1a44797cf38bed790470/regex-2026.1.15-cp313-cp313-musllinux_1_2_s390x.whl", hash = "sha256:cfecdaa4b19f9ca534746eb3b55a5195d5c95b88cac32a205e981ec0a22b7d31", size = 850615, upload-time = "2026-01-14T23:15:37.523Z" },
    { url = "https://files.pythonhosted.org/packages/7d/b7/658a9782fb253680aa8ecb5ccbb51f69e088ed48142c46d9f0c99b46c575/regex-2026.1.15-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:08df9722d9b87834a3d701f3fca570b2be115654dbfd30179f30ab2f39d606d3", size = 789951, upload-time = "2026-01-14T23:15:39.582Z" },
    { url = "https://files.pythonhosted.org/packages/fc/2a/5928af114441e059f15b2f63e188bd00c6529b3051c974ade7444b85fcda/regex-2026.1.15-cp313-cp313-win32.whl", hash = "sha256:d426616dae0967ca225ab12c22274eb816558f2f99ccb4a1d52ca92e8baf180f", size = 266275, upload-time = "2026-01-14T23:15:42.108Z" },
    { url = "https://files.pythonhosted.org/packages/4f/16/5bfbb89e435897bff28cf0352a992ca719d9e55ebf8b629203c96b6ce4f7/regex-2026.1.15-cp313-cp313-win_amd64.whl", hash = "sha256:febd38857b09867d3ed3f4f1af7d241c5c50362e25ef43034995b77a50df494e", size = 277145, upload-time = "2026-01-14T23:15:44.244Z" },
    { url = "https://files.pythonhosted.org/packages/56/c1/a09ff7392ef4233296e821aec5f78c51be5e91ffde0d163059e50fd75835/regex-2026.1.15-cp313-cp313-win_arm64.whl", hash = "sha256:8e32f7896f83774f91499d239e24cebfadbc07639c1494bb7213983842348337", size = 270411, upload-time = "2026-01-14T23:15:45.858Z" },
    { url = "https://files.pythonhosted.org/packages/3c/38/0cfd5a78e5c6db00e6782fdae70458f89850ce95baa5e8694ab91d89744f/regex-2026.1.15-cp313-cp313t-macosx_10_13_universal2.whl", hash = "sha256:ec94c04149b6a7b8120f9f44565722c7ae31b7a6d2275569d2eefa76b83da3be", size = 492068, upload-time = "2026-01-14T23:15:47.616Z" },
    { url = "https://files.pythonhosted.org/packages/50/72/6c86acff16cb7c959c4355826bbf06aad670682d07c8f3998d9ef4fee7cd/regex-2026.1.15-cp313-cp313t-macosx_10_13_x86_64.whl", hash = "sha256:40c86d8046915bb9aeb15d3f3f15b6fd500b8ea4485b30e1bbc799dab3fe29f8", size = 292756, upload-time = "2026-01-14T23:15:49.307Z" },
    { url = "https://files.pythonhosted.org/packages/4e/58/df7fb69eadfe76526ddfce28abdc0af09ffe65f20c2c90932e89d705153f/regex-2026.1.15-cp313-cp313t-macosx_11_0_arm64.whl", hash = "sha256:726ea4e727aba21643205edad8f2187ec682d3305d790f73b7a51c7587b64bdd", size = 291114, upload-time = "2026-01-14T23:15:51.484Z" },
    { url = "https://files.pythonhosted.org/packages/ed/6c/a4011cd1cf96b90d2cdc7e156f91efbd26531e822a7fbb82a43c1016678e/regex-2026.1.15-cp313-cp313t-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:1cb740d044aff31898804e7bf1181cc72c03d11dfd19932b9911ffc19a79070a", size = 807524, upload-time = "2026-01-14T23:15:53.102Z" },
    { url = "https://files.pythonhosted.org/packages/1d/25/a53ffb73183f69c3e9f4355c4922b76d2840aee160af6af5fac229b6201d/regex-2026.1.15-cp313-cp313t-manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:05d75a668e9ea16f832390d22131fe1e8acc8389a694c8febc3e340b0f810b93", size = 873455, upload-time = "2026-01-14T23:15:54.956Z" },
    { url = "https://files.pythonhosted.org/packages/66/0b/8b47fc2e8f97d9b4a851736f3890a5f786443aa8901061c55f24c955f45b/regex-2026.1.15-cp313-cp313t-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl", hash = "sha256:d991483606f3dbec93287b9f35596f41aa2e92b7c2ebbb935b63f409e243c9af", size = 915007, upload-time = "2026-01-14T23:15:57.041Z" },
    { url = "https://files.pythonhosted.org/packages/c2/fa/97de0d681e6d26fabe71968dbee06dd52819e9a22fdce5dac7256c31ed84/regex-2026.1.15-cp313-cp313t-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:194312a14819d3e44628a44ed6fea6898fdbecb0550089d84c403475138d0a09", size = 812794, upload-time = "2026-01-14T23:15:58.916Z" },
    { url = "https://files.pythonhosted.org/packages/22/38/e752f94e860d429654aa2b1c51880bff8dfe8f084268258adf9151cf1f53/regex-2026.1.15-cp313-cp313t-manylinux_2_31_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:fe2fda4110a3d0bc163c2e0664be44657431440722c5c5315c65155cab92f9e5", size = 781159, upload-time = "2026-01-14T23:16:00.817Z" },
    { url = "https://files.pythonhosted.org/packages/e9/a7/d739ffaef33c378fc888302a018d7f81080393d96c476b058b8c64fd2b0d/regex-2026.1.15-cp313-cp313t-musllinux_1_2_aarch64.whl", hash = "sha256:124dc36c85d34ef2d9164da41a53c1c8c122cfb1f6e1ec377a1f27ee81deb794", size = 795558, upload-time = "2026-01-14T23:16:03.267Z" },
    { url = "https://files.pythonhosted.org/packages/3e/c4/542876f9a0ac576100fc73e9c75b779f5c31e3527576cfc9cb3009dcc58a/regex-2026.1.15-cp313-cp313t-musllinux_1_2_ppc64le.whl", hash = "sha256:a1774cd1981cd212506a23a14dba7fdeaee259f5deba2df6229966d9911e767a", size = 868427, upload-time = "2026-01-14T23:16:05.646Z" },
    { url = "https://files.pythonhosted.org/packages/fc/0f/d5655bea5b22069e32ae85a947aa564912f23758e112cdb74212848a1a1b/regex-2026.1.15-cp313-cp313t-musllinux_1_2_riscv64.whl", hash = "sha256:b5f7d8d2867152cdb625e72a530d2ccb48a3d199159144cbdd63870882fb6f80", size = 769939, upload-time = "2026-01-14T23:16:07.542Z" },
    { url = "https://files.pythonhosted.org/packages/20/06/7e18a4fa9d326daeda46d471a44ef94201c46eaa26dbbb780b5d92cbfdda/regex-2026.1.15-cp313-cp313t-musllinux_1_2_s390x.whl", hash = "sha256:492534a0ab925d1db998defc3c302dae3616a2fc3fe2e08db1472348f096ddf2", size = 854753, upload-time = "2026-01-14T23:16:10.395Z" },
    { url = "https://files.pythonhosted.org/packages/3b/67/dc8946ef3965e166f558ef3b47f492bc364e96a265eb4a2bb3ca765c8e46/regex-2026.1.15-cp313-cp313t-musllinux_1_2_x86_64.whl", hash = "sha256:c661fc820cfb33e166bf2450d3dadbda47c8d8981898adb9b6fe24e5e582ba60", size = 799559, upload-time = "2026-01-14T23:16:12.347Z" },
    { url = "https://files.pythonhosted.org/packages/a5/61/1bba81ff6d50c86c65d9fd84ce9699dd106438ee4cdb105bf60374ee8412/regex-2026.1.15-cp313-cp313t-win32.whl", hash = "sha256:99ad739c3686085e614bf77a508e26954ff1b8f14da0e3765ff7abbf7799f952", size = 268879, upload-time = "2026-01-14T23:16:14.049Z" },
    { url = "https://files.pythonhosted.org/packages/e9/5e/cef7d4c5fb0ea3ac5c775fd37db5747f7378b29526cc83f572198924ff47/regex-2026.1.15-cp313-cp313t-win_amd64.whl", hash = "sha256:32655d17905e7ff8ba5c764c43cb124e34a9245e45b83c22e81041e1071aee10", size = 280317, upload-time = "2026-01-14T23:16:15.718Z" },
    { url = "https://files.pythonhosted.org/packages/b4/52/4317f7a5988544e34ab57b4bde0f04944c4786128c933fb09825924d3e82/regex-2026.1.15-cp313-cp313t-win_arm64.whl", hash = "sha256:b2a13dd6a95e95a489ca242319d18fc02e07ceb28fa9ad146385194d95b3c829", size = 271551, upload-time = "2026-01-14T23:16:17.533Z" },
]

[[package]]
name = "requests"
version = "2.32.5"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "certifi" },
    { name = "charset-normalizer" },
    { name = "idna" },
    { name = "urllib3" },
]
sdist = { url = "https://files.pythonhosted.org/packages/c9/74/b3ff8e6c8446842c3f5c837e9c3dfcfe2018ea6ecef224c710c85ef728f4/requests-2.32.5.tar.gz", hash = "sha256:dbba0bac56e100853db0ea71b82b4dfd5fe2bf6d3754a8893c3af500cec7d7cf", size = 134517, upload-time = "2025-08-18T20:46:02.573Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/1e/db/4254e3eabe8020b458f1a747140d32277ec7a271daf1d235b70dc0b4e6e3/requests-2.32.5-py3-none-any.whl", hash = "sha256:2462f94637a34fd532264295e186976db0f5d453d1cdd31473c85a6a161affb6", size = 64738, upload-time = "2025-08-18T20:46:00.542Z" },
]

[[package]]
name = "requests-toolbelt"
version = "1.0.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "requests" },
]
sdist = { url = "https://files.pythonhosted.org/packages/f3/61/d7545dafb7ac2230c70d38d31cbfe4cc64f7144dc41f6e4e4b78ecd9f5bb/requests-toolbelt-1.0.0.tar.gz", hash = "sha256:7681a0a3d047012b5bdc0ee37d7f8f07ebe76ab08caeccfc3921ce23c88d5bc6", size = 206888, upload-time = "2023-05-01T04:11:33.229Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/3f/51/d4db610ef29373b879047326cbf6fa98b6c1969d6f6dc423279de2b1be2c/requests_toolbelt-1.0.0-py2.py3-none-any.whl", hash = "sha256:cccfdd665f0a24fcf4726e690f65639d272bb0637b9b92dfd91a5568ccf6bd06", size = 54481, upload-time = "2023-05-01T04:11:28.427Z" },
]

[[package]]
name = "rich"
version = "14.3.2"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "markdown-it-py" },
    { name = "pygments" },
]
sdist = { url = "https://files.pythonhosted.org/packages/74/99/a4cab2acbb884f80e558b0771e97e21e939c5dfb460f488d19df485e8298/rich-14.3.2.tar.gz", hash = "sha256:e712f11c1a562a11843306f5ed999475f09ac31ffb64281f73ab29ffdda8b3b8", size = 230143, upload-time = "2026-02-01T16:20:47.908Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/ef/45/615f5babd880b4bd7d405cc0dc348234c5ffb6ed1ea33e152ede08b2072d/rich-14.3.2-py3-none-any.whl", hash = "sha256:08e67c3e90884651da3239ea668222d19bea7b589149d8014a21c633420dbb69", size = 309963, upload-time = "2026-02-01T16:20:46.078Z" },
]

[[package]]
name = "rsa"
version = "4.9.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "pyasn1" },
]
sdist = { url = "https://files.pythonhosted.org/packages/da/8a/22b7beea3ee0d44b1916c0c1cb0ee3af23b700b6da9f04991899d0c555d4/rsa-4.9.1.tar.gz", hash = "sha256:e7bdbfdb5497da4c07dfd35530e1a902659db6ff241e39d9953cad06ebd0ae75", size = 29034, upload-time = "2025-04-16T09:51:18.218Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/64/8d/0133e4eb4beed9e425d9a98ed6e081a55d195481b7632472be1af08d2f6b/rsa-4.9.1-py3-none-any.whl", hash = "sha256:68635866661c6836b8d39430f97a996acbd61bfa49406748ea243539fe239762", size = 34696, upload-time = "2025-04-16T09:51:17.142Z" },
]

[[package]]
name = "rtms"
version = "1.0.0"
source = { registry = "https://test.pypi.org/simple/" }
wheels = [
    { url = "https://test-files.pythonhosted.org/packages/33/98/880ea1bcf3473ff00ecac2e524339c994412ee9ddd77ee3348992ccd7ec0/rtms-1.0.0-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:cd9e6015ce41603d685d83eebe33de7fad641417a1dd8dd80793bd4ae57dda0c", size = 8265912, upload-time = "2026-01-22T18:54:35.423Z" },
    { url = "https://test-files.pythonhosted.org/packages/46/c3/670cd70f843ebfd4b6f1db93e2496813798681a940e32ec70eac0be30b55/rtms-1.0.0-cp313-cp313-manylinux_2_34_x86_64.whl", hash = "sha256:73d42431660b693736ec5583da8754b41a148f63333e777d8f6296a3bcdf7102", size = 5348518, upload-time = "2026-01-22T18:54:37.889Z" },
]

[[package]]
name = "ruff"
version = "0.15.1"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/04/dc/4e6ac71b511b141cf626357a3946679abeba4cf67bc7cc5a17920f31e10d/ruff-0.15.1.tar.gz", hash = "sha256:c590fe13fb57c97141ae975c03a1aedb3d3156030cabd740d6ff0b0d601e203f", size = 4540855, upload-time = "2026-02-12T23:09:09.998Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/23/bf/e6e4324238c17f9d9120a9d60aa99a7daaa21204c07fcd84e2ef03bb5fd1/ruff-0.15.1-py3-none-linux_armv6l.whl", hash = "sha256:b101ed7cf4615bda6ffe65bdb59f964e9f4a0d3f85cbf0e54f0ab76d7b90228a", size = 10367819, upload-time = "2026-02-12T23:09:03.598Z" },
    { url = "https://files.pythonhosted.org/packages/b3/ea/c8f89d32e7912269d38c58f3649e453ac32c528f93bb7f4219258be2e7ed/ruff-0.15.1-py3-none-macosx_10_12_x86_64.whl", hash = "sha256:939c995e9277e63ea632cc8d3fae17aa758526f49a9a850d2e7e758bfef46602", size = 10798618, upload-time = "2026-02-12T23:09:22.928Z" },
    { url = "https://files.pythonhosted.org/packages/5e/0f/1d0d88bc862624247d82c20c10d4c0f6bb2f346559d8af281674cf327f15/ruff-0.15.1-py3-none-macosx_11_0_arm64.whl", hash = "sha256:1d83466455fdefe60b8d9c8df81d3c1bbb2115cede53549d3b522ce2bc703899", size = 10148518, upload-time = "2026-02-12T23:08:58.339Z" },
    { url = "https://files.pythonhosted.org/packages/f5/c8/291c49cefaa4a9248e986256df2ade7add79388fe179e0691be06fae6f37/ruff-0.15.1-py3-none-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:a9457e3c3291024866222b96108ab2d8265b477e5b1534c7ddb1810904858d16", size = 10518811, upload-time = "2026-02-12T23:09:31.865Z" },
    { url = "https://files.pythonhosted.org/packages/c3/1a/f5707440e5ae43ffa5365cac8bbb91e9665f4a883f560893829cf16a606b/ruff-0.15.1-py3-none-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:92c92b003e9d4f7fbd33b1867bb15a1b785b1735069108dfc23821ba045b29bc", size = 10196169, upload-time = "2026-02-12T23:09:17.306Z" },
    { url = "https://files.pythonhosted.org/packages/2a/ff/26ddc8c4da04c8fd3ee65a89c9fb99eaa5c30394269d424461467be2271f/ruff-0.15.1-py3-none-manylinux_2_17_i686.manylinux2014_i686.whl", hash = "sha256:1fe5c41ab43e3a06778844c586251eb5a510f67125427625f9eb2b9526535779", size = 10990491, upload-time = "2026-02-12T23:09:25.503Z" },
    { url = "https://files.pythonhosted.org/packages/fc/00/50920cb385b89413f7cdb4bb9bc8fc59c1b0f30028d8bccc294189a54955/ruff-0.15.1-py3-none-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:66a6dd6df4d80dc382c6484f8ce1bcceb55c32e9f27a8b94c32f6c7331bf14fb", size = 11843280, upload-time = "2026-02-12T23:09:19.88Z" },
    { url = "https://files.pythonhosted.org/packages/5d/6d/2f5cad8380caf5632a15460c323ae326f1e1a2b5b90a6ee7519017a017ca/ruff-0.15.1-py3-none-manylinux_2_17_s390x.manylinux2014_s390x.whl", hash = "sha256:6a4a42cbb8af0bda9bcd7606b064d7c0bc311a88d141d02f78920be6acb5aa83", size = 11274336, upload-time = "2026-02-12T23:09:14.907Z" },
    { url = "https://files.pythonhosted.org/packages/a3/1d/5f56cae1d6c40b8a318513599b35ea4b075d7dc1cd1d04449578c29d1d75/ruff-0.15.1-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:4ab064052c31dddada35079901592dfba2e05f5b1e43af3954aafcbc1096a5b2", size = 11137288, upload-time = "2026-02-12T23:09:07.475Z" },
    { url = "https://files.pythonhosted.org/packages/cd/20/6f8d7d8f768c93b0382b33b9306b3b999918816da46537d5a61635514635/ruff-0.15.1-py3-none-manylinux_2_31_riscv64.whl", hash = "sha256:5631c940fe9fe91f817a4c2ea4e81f47bee3ca4aa646134a24374f3c19ad9454", size = 11070681, upload-time = "2026-02-12T23:08:55.43Z" },
    { url = "https://files.pythonhosted.org/packages/9a/67/d640ac76069f64cdea59dba02af2e00b1fa30e2103c7f8d049c0cff4cafd/ruff-0.15.1-py3-none-musllinux_1_2_aarch64.whl", hash = "sha256:68138a4ba184b4691ccdc39f7795c66b3c68160c586519e7e8444cf5a53e1b4c", size = 10486401, upload-time = "2026-02-12T23:09:27.927Z" },
    { url = "https://files.pythonhosted.org/packages/65/3d/e1429f64a3ff89297497916b88c32a5cc88eeca7e9c787072d0e7f1d3e1e/ruff-0.15.1-py3-none-musllinux_1_2_armv7l.whl", hash = "sha256:518f9af03bfc33c03bdb4cb63fabc935341bb7f54af500f92ac309ecfbba6330", size = 10197452, upload-time = "2026-02-12T23:09:12.147Z" },
    { url = "https://files.pythonhosted.org/packages/78/83/e2c3bade17dad63bf1e1c2ffaf11490603b760be149e1419b07049b36ef2/ruff-0.15.1-py3-none-musllinux_1_2_i686.whl", hash = "sha256:da79f4d6a826caaea95de0237a67e33b81e6ec2e25fc7e1993a4015dffca7c61", size = 10693900, upload-time = "2026-02-12T23:09:34.418Z" },
    { url = "https://files.pythonhosted.org/packages/a1/27/fdc0e11a813e6338e0706e8b39bb7a1d61ea5b36873b351acee7e524a72a/ruff-0.15.1-py3-none-musllinux_1_2_x86_64.whl", hash = "sha256:3dd86dccb83cd7d4dcfac303ffc277e6048600dfc22e38158afa208e8bf94a1f", size = 11227302, upload-time = "2026-02-12T23:09:36.536Z" },
    { url = "https://files.pythonhosted.org/packages/f6/58/ac864a75067dcbd3b95be5ab4eb2b601d7fbc3d3d736a27e391a4f92a5c1/ruff-0.15.1-py3-none-win32.whl", hash = "sha256:660975d9cb49b5d5278b12b03bb9951d554543a90b74ed5d366b20e2c57c2098", size = 10462555, upload-time = "2026-02-12T23:09:29.899Z" },
    { url = "https://files.pythonhosted.org/packages/e0/5e/d4ccc8a27ecdb78116feac4935dfc39d1304536f4296168f91ed3ec00cd2/ruff-0.15.1-py3-none-win_amd64.whl", hash = "sha256:c820fef9dd5d4172a6570e5721704a96c6679b80cf7be41659ed439653f62336", size = 11599956, upload-time = "2026-02-12T23:09:01.157Z" },
    { url = "https://files.pythonhosted.org/packages/2a/07/5bda6a85b220c64c65686bc85bd0bbb23b29c62b3a9f9433fa55f17cda93/ruff-0.15.1-py3-none-win_arm64.whl", hash = "sha256:5ff7d5f0f88567850f45081fac8f4ec212be8d0b963e385c3f7d0d2eb4899416", size = 10874604, upload-time = "2026-02-12T23:09:05.515Z" },
]

[[package]]
name = "sacrebleu"
version = "2.6.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "colorama" },
    { name = "lxml" },
    { name = "numpy" },
    { name = "portalocker" },
    { name = "regex" },
    { name = "tabulate" },
]
sdist = { url = "https://files.pythonhosted.org/packages/d3/ed/d7acddcff74d690c56fe26a1f7828bdde548262828d0743414ea916c40c1/sacrebleu-2.6.0.tar.gz", hash = "sha256:91499b6cd46138d95154fff1e863c2f9be57e82f0c719d8dd718d0006cf6c566", size = 1893419, upload-time = "2026-01-12T17:17:20.799Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/06/f2/6c90ccf3ad1d09a7d662a405b274f3c93b92df59c8d6a025d26aaf34d302/sacrebleu-2.6.0-py3-none-any.whl", hash = "sha256:3edc1531575cfe4ad04ce53491a9307e234af1c3f805a1f491cbec844229a8a8", size = 100785, upload-time = "2026-01-12T17:17:18.868Z" },
]

[[package]]
name = "safehttpx"
version = "0.1.7"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "httpx" },
]
sdist = { url = "https://files.pythonhosted.org/packages/89/d1/4282284d9cf1ee873607a46442da977fc3c985059315ab23610be31d5885/safehttpx-0.1.7.tar.gz", hash = "sha256:db201c0978c41eddb8bb480f3eee59dd67304fdd91646035e9d9a720049a9d23", size = 10385, upload-time = "2025-10-24T18:30:09.783Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/2e/a3/0f0b7d78e2f1eb9e8e1afbff1d2bff8d60144aee17aca51c065b516743dd/safehttpx-0.1.7-py3-none-any.whl", hash = "sha256:c4f4a162db6993464d7ca3d7cc4af0ffc6515a606dfd220b9f82c6945d869cde", size = 8959, upload-time = "2025-10-24T18:30:08.733Z" },
]

[[package]]
name = "semantic-version"
version = "2.10.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/7d/31/f2289ce78b9b473d582568c234e104d2a342fd658cc288a7553d83bb8595/semantic_version-2.10.0.tar.gz", hash = "sha256:bdabb6d336998cbb378d4b9db3a4b56a1e3235701dc05ea2690d9a997ed5041c", size = 52289, upload-time = "2022-05-26T13:35:23.454Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/6a/23/8146aad7d88f4fcb3a6218f41a60f6c2d4e3a72de72da1825dc7c8f7877c/semantic_version-2.10.0-py2.py3-none-any.whl", hash = "sha256:de78a3b8e0feda74cabc54aab2da702113e33ac9d9eb9d2389bcf1f58b7d9177", size = 15552, upload-time = "2022-05-26T13:35:21.206Z" },
]

[[package]]
name = "shellingham"
version = "1.5.4"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/58/15/8b3609fd3830ef7b27b655beb4b4e9c62313a4e8da8c676e142cc210d58e/shellingham-1.5.4.tar.gz", hash = "sha256:8dbca0739d487e5bd35ab3ca4b36e11c4078f3a234bfce294b0a0291363404de", size = 10310, upload-time = "2023-10-24T04:13:40.426Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/e0/f9/0595336914c5619e5f28a1fb793285925a8cd4b432c9da0a987836c7f822/shellingham-1.5.4-py2.py3-none-any.whl", hash = "sha256:7ecfff8f2fd72616f7481040475a65b2bf8af90a56c89140852d1120324e8686", size = 9755, upload-time = "2023-10-24T04:13:38.866Z" },
]

[[package]]
name = "six"
version = "1.17.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/94/e7/b2c673351809dca68a0e064b6af791aa332cf192da575fd474ed7d6f16a2/six-1.17.0.tar.gz", hash = "sha256:ff70335d468e7eb6ec65b95b99d3a2836546063f63acc5171de367e834932a81", size = 34031, upload-time = "2024-12-04T17:35:28.174Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/b7/ce/149a00dd41f10bc29e5921b496af8b574d8413afcd5e30dfa0ed46c2cc5e/six-1.17.0-py2.py3-none-any.whl", hash = "sha256:4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274", size = 11050, upload-time = "2024-12-04T17:35:26.475Z" },
]

[[package]]
name = "sniffio"
version = "1.3.1"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/a2/87/a6771e1546d97e7e041b6ae58d80074f81b7d5121207425c964ddf5cfdbd/sniffio-1.3.1.tar.gz", hash = "sha256:f4324edc670a0f49750a81b895f35c3adb843cca46f0530f79fc1babb23789dc", size = 20372, upload-time = "2024-02-25T23:20:04.057Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/e9/44/75a9c9421471a6c4805dbf2356f7c181a29c1879239abab1ea2cc8f38b40/sniffio-1.3.1-py3-none-any.whl", hash = "sha256:2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2", size = 10235, upload-time = "2024-02-25T23:20:01.196Z" },
]

[[package]]
name = "sounddevice"
version = "0.5.5"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "cffi" },
]
sdist = { url = "https://files.pythonhosted.org/packages/2a/f9/2592608737553638fca98e21e54bfec40bf577bb98a61b2770c912aab25e/sounddevice-0.5.5.tar.gz", hash = "sha256:22487b65198cb5bf2208755105b524f78ad173e5ab6b445bdab1c989f6698df3", size = 143191, upload-time = "2026-01-23T18:36:43.529Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/1e/0a/478e441fd049002cf308520c0d62dd8333e7c6cc8d997f0dda07b9fbcc46/sounddevice-0.5.5-py3-none-any.whl", hash = "sha256:30ff99f6c107f49d25ad16a45cacd8d91c25a1bcdd3e81a206b921a3a6405b1f", size = 32807, upload-time = "2026-01-23T18:36:35.649Z" },
    { url = "https://files.pythonhosted.org/packages/56/f9/c037c35f6d0b6bc3bc7bfb314f1d6f1f9a341328ef47cd63fc4f850a7b27/sounddevice-0.5.5-py3-none-macosx_10_6_x86_64.macosx_10_6_universal2.whl", hash = "sha256:05eb9fd6c54c38d67741441c19164c0dae8ce80453af2d8c4ad2e7823d15b722", size = 108557, upload-time = "2026-01-23T18:36:37.41Z" },
    { url = "https://files.pythonhosted.org/packages/88/a1/d19dd9889cd4bce2e233c4fac007cd8daaf5b9fe6e6a5d432cf17be0b807/sounddevice-0.5.5-py3-none-win32.whl", hash = "sha256:1234cc9b4c9df97b6cbe748146ae0ec64dd7d6e44739e8e42eaa5b595313a103", size = 317765, upload-time = "2026-01-23T18:36:39.047Z" },
    { url = "https://files.pythonhosted.org/packages/c3/0e/002ed7c4c1c2ab69031f78989d3b789fee3a7fba9e586eb2b81688bf4961/sounddevice-0.5.5-py3-none-win_amd64.whl", hash = "sha256:cfc6b2c49fb7f555591c78cb8ecf48d6a637fd5b6e1db5fec6ed9365d64b3519", size = 365324, upload-time = "2026-01-23T18:36:40.496Z" },
    { url = "https://files.pythonhosted.org/packages/4e/39/a61d4b83a7746b70d23d9173be688c0c6bfc7173772344b7442c2c155497/sounddevice-0.5.5-py3-none-win_arm64.whl", hash = "sha256:3861901ddd8230d2e0e8ae62ac320cdd4c688d81df89da036dcb812f757bb3e6", size = 317115, upload-time = "2026-01-23T18:36:42.235Z" },
]

[[package]]
name = "starlette"
version = "0.52.1"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "anyio" },
]
sdist = { url = "https://files.pythonhosted.org/packages/c4/68/79977123bb7be889ad680d79a40f339082c1978b5cfcf62c2d8d196873ac/starlette-0.52.1.tar.gz", hash = "sha256:834edd1b0a23167694292e94f597773bc3f89f362be6effee198165a35d62933", size = 2653702, upload-time = "2026-01-18T13:34:11.062Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/81/0d/13d1d239a25cbfb19e740db83143e95c772a1fe10202dda4b76792b114dd/starlette-0.52.1-py3-none-any.whl", hash = "sha256:0029d43eb3d273bc4f83a08720b4912ea4b071087a3b48db01b7c839f7954d74", size = 74272, upload-time = "2026-01-18T13:34:09.188Z" },
]

[[package]]
name = "tabulate"
version = "0.10.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/46/58/8c37dea7bbf769b20d58e7ace7e5edfe65b849442b00ffcdd56be88697c6/tabulate-0.10.0.tar.gz", hash = "sha256:e2cfde8f79420f6deeffdeda9aaec3b6bc5abce947655d17ac662b126e48a60d", size = 91754, upload-time = "2026-03-04T18:55:34.402Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/99/55/db07de81b5c630da5cbf5c7df646580ca26dfaefa593667fc6f2fe016d2e/tabulate-0.10.0-py3-none-any.whl", hash = "sha256:f0b0622e567335c8fabaaa659f1b33bcb6ddfe2e496071b743aa113f8774f2d3", size = 39814, upload-time = "2026-03-04T18:55:31.284Z" },
]

[[package]]
name = "tenacity"
version = "9.1.4"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/47/c6/ee486fd809e357697ee8a44d3d69222b344920433d3b6666ccd9b374630c/tenacity-9.1.4.tar.gz", hash = "sha256:adb31d4c263f2bd041081ab33b498309a57c77f9acf2db65aadf0898179cf93a", size = 49413, upload-time = "2026-02-07T10:45:33.841Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/d7/c1/eb8f9debc45d3b7918a32ab756658a0904732f75e555402972246b0b8e71/tenacity-9.1.4-py3-none-any.whl", hash = "sha256:6095a360c919085f28c6527de529e76a06ad89b23659fa881ae0649b867a9d55", size = 28926, upload-time = "2026-02-07T10:45:32.24Z" },
]

[[package]]
name = "tiktoken"
version = "0.12.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "regex" },
    { name = "requests" },
]
sdist = { url = "https://files.pythonhosted.org/packages/7d/ab/4d017d0f76ec3171d469d80fc03dfbb4e48a4bcaddaa831b31d526f05edc/tiktoken-0.12.0.tar.gz", hash = "sha256:b18ba7ee2b093863978fcb14f74b3707cdc8d4d4d3836853ce7ec60772139931", size = 37806, upload-time = "2025-10-06T20:22:45.419Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/00/61/441588ee21e6b5cdf59d6870f86beb9789e532ee9718c251b391b70c68d6/tiktoken-0.12.0-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:775c2c55de2310cc1bc9a3ad8826761cbdc87770e586fd7b6da7d4589e13dab3", size = 1050802, upload-time = "2025-10-06T20:22:00.96Z" },
    { url = "https://files.pythonhosted.org/packages/1f/05/dcf94486d5c5c8d34496abe271ac76c5b785507c8eae71b3708f1ad9b45a/tiktoken-0.12.0-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:a01b12f69052fbe4b080a2cfb867c4de12c704b56178edf1d1d7b273561db160", size = 993995, upload-time = "2025-10-06T20:22:02.788Z" },
    { url = "https://files.pythonhosted.org/packages/a0/70/5163fe5359b943f8db9946b62f19be2305de8c3d78a16f629d4165e2f40e/tiktoken-0.12.0-cp313-cp313-manylinux_2_28_aarch64.whl", hash = "sha256:01d99484dc93b129cd0964f9d34eee953f2737301f18b3c7257bf368d7615baa", size = 1128948, upload-time = "2025-10-06T20:22:03.814Z" },
    { url = "https://files.pythonhosted.org/packages/0c/da/c028aa0babf77315e1cef357d4d768800c5f8a6de04d0eac0f377cb619fa/tiktoken-0.12.0-cp313-cp313-manylinux_2_28_x86_64.whl", hash = "sha256:4a1a4fcd021f022bfc81904a911d3df0f6543b9e7627b51411da75ff2fe7a1be", size = 1151986, upload-time = "2025-10-06T20:22:05.173Z" },
    { url = "https://files.pythonhosted.org/packages/a0/5a/886b108b766aa53e295f7216b509be95eb7d60b166049ce2c58416b25f2a/tiktoken-0.12.0-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:981a81e39812d57031efdc9ec59fa32b2a5a5524d20d4776574c4b4bd2e9014a", size = 1194222, upload-time = "2025-10-06T20:22:06.265Z" },
    { url = "https://files.pythonhosted.org/packages/f4/f8/4db272048397636ac7a078d22773dd2795b1becee7bc4922fe6207288d57/tiktoken-0.12.0-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:9baf52f84a3f42eef3ff4e754a0db79a13a27921b457ca9832cf944c6be4f8f3", size = 1255097, upload-time = "2025-10-06T20:22:07.403Z" },
    { url = "https://files.pythonhosted.org/packages/8e/32/45d02e2e0ea2be3a9ed22afc47d93741247e75018aac967b713b2941f8ea/tiktoken-0.12.0-cp313-cp313-win_amd64.whl", hash = "sha256:b8a0cd0c789a61f31bf44851defbd609e8dd1e2c8589c614cc1060940ef1f697", size = 879117, upload-time = "2025-10-06T20:22:08.418Z" },
    { url = "https://files.pythonhosted.org/packages/ce/76/994fc868f88e016e6d05b0da5ac24582a14c47893f4474c3e9744283f1d5/tiktoken-0.12.0-cp313-cp313t-macosx_10_13_x86_64.whl", hash = "sha256:d5f89ea5680066b68bcb797ae85219c72916c922ef0fcdd3480c7d2315ffff16", size = 1050309, upload-time = "2025-10-06T20:22:10.939Z" },
    { url = "https://files.pythonhosted.org/packages/f6/b8/57ef1456504c43a849821920d582a738a461b76a047f352f18c0b26c6516/tiktoken-0.12.0-cp313-cp313t-macosx_11_0_arm64.whl", hash = "sha256:b4e7ed1c6a7a8a60a3230965bdedba8cc58f68926b835e519341413370e0399a", size = 993712, upload-time = "2025-10-06T20:22:12.115Z" },
    { url = "https://files.pythonhosted.org/packages/72/90/13da56f664286ffbae9dbcfadcc625439142675845baa62715e49b87b68b/tiktoken-0.12.0-cp313-cp313t-manylinux_2_28_aarch64.whl", hash = "sha256:fc530a28591a2d74bce821d10b418b26a094bf33839e69042a6e86ddb7a7fb27", size = 1128725, upload-time = "2025-10-06T20:22:13.541Z" },
    { url = "https://files.pythonhosted.org/packages/05/df/4f80030d44682235bdaecd7346c90f67ae87ec8f3df4a3442cb53834f7e4/tiktoken-0.12.0-cp313-cp313t-manylinux_2_28_x86_64.whl", hash = "sha256:06a9f4f49884139013b138920a4c393aa6556b2f8f536345f11819389c703ebb", size = 1151875, upload-time = "2025-10-06T20:22:14.559Z" },
    { url = "https://files.pythonhosted.org/packages/22/1f/ae535223a8c4ef4c0c1192e3f9b82da660be9eb66b9279e95c99288e9dab/tiktoken-0.12.0-cp313-cp313t-musllinux_1_2_aarch64.whl", hash = "sha256:04f0e6a985d95913cabc96a741c5ffec525a2c72e9df086ff17ebe35985c800e", size = 1194451, upload-time = "2025-10-06T20:22:15.545Z" },
    { url = "https://files.pythonhosted.org/packages/78/a7/f8ead382fce0243cb625c4f266e66c27f65ae65ee9e77f59ea1653b6d730/tiktoken-0.12.0-cp313-cp313t-musllinux_1_2_x86_64.whl", hash = "sha256:0ee8f9ae00c41770b5f9b0bb1235474768884ae157de3beb5439ca0fd70f3e25", size = 1253794, upload-time = "2025-10-06T20:22:16.624Z" },
    { url = "https://files.pythonhosted.org/packages/93/e0/6cc82a562bc6365785a3ff0af27a2a092d57c47d7a81d9e2295d8c36f011/tiktoken-0.12.0-cp313-cp313t-win_amd64.whl", hash = "sha256:dc2dd125a62cb2b3d858484d6c614d136b5b848976794edfb63688d539b8b93f", size = 878777, upload-time = "2025-10-06T20:22:18.036Z" },
]

[[package]]
name = "tomlkit"
version = "0.13.3"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/cc/18/0bbf3884e9eaa38819ebe46a7bd25dcd56b67434402b66a58c4b8e552575/tomlkit-0.13.3.tar.gz", hash = "sha256:430cf247ee57df2b94ee3fbe588e71d362a941ebb545dec29b53961d61add2a1", size = 185207, upload-time = "2025-06-05T07:13:44.947Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/bd/75/8539d011f6be8e29f339c42e633aae3cb73bffa95dd0f9adec09b9c58e85/tomlkit-0.13.3-py3-none-any.whl", hash = "sha256:c89c649d79ee40629a9fda55f8ace8c6a1b42deb912b2a8fd8d942ddadb606b0", size = 38901, upload-time = "2025-06-05T07:13:43.546Z" },
]

[[package]]
name = "tqdm"
version = "4.67.3"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "colorama", marker = "sys_platform == 'win32'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/09/a9/6ba95a270c6f1fbcd8dac228323f2777d886cb206987444e4bce66338dd4/tqdm-4.67.3.tar.gz", hash = "sha256:7d825f03f89244ef73f1d4ce193cb1774a8179fd96f31d7e1dcde62092b960bb", size = 169598, upload-time = "2026-02-03T17:35:53.048Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/16/e1/3079a9ff9b8e11b846c6ac5c8b5bfb7ff225eee721825310c91b3b50304f/tqdm-4.67.3-py3-none-any.whl", hash = "sha256:ee1e4c0e59148062281c49d80b25b67771a127c85fc9676d3be5f243206826bf", size = 78374, upload-time = "2026-02-03T17:35:50.982Z" },
]

[[package]]
name = "typer"
version = "0.24.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "annotated-doc" },
    { name = "click" },
    { name = "rich" },
    { name = "shellingham" },
]
sdist = { url = "https://files.pythonhosted.org/packages/5a/b6/3e681d3b6bb22647509bdbfdd18055d5adc0dce5c5585359fa46ff805fdc/typer-0.24.0.tar.gz", hash = "sha256:f9373dc4eff901350694f519f783c29b6d7a110fc0dcc11b1d7e353b85ca6504", size = 118380, upload-time = "2026-02-16T22:08:48.496Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/85/d0/4da85c2a45054bb661993c93524138ace4956cb075a7ae0c9d1deadc331b/typer-0.24.0-py3-none-any.whl", hash = "sha256:5fc435a9c8356f6160ed6e85a6301fdd6e3d8b2851da502050d1f92c5e9eddc8", size = 56441, upload-time = "2026-02-16T22:08:47.535Z" },
]

[[package]]
name = "typer-slim"
version = "0.24.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "typer" },
]
sdist = { url = "https://files.pythonhosted.org/packages/a7/a7/e6aecc4b4eb59598829a3b5076a93aff291b4fdaa2ded25efc4e1f4d219c/typer_slim-0.24.0.tar.gz", hash = "sha256:f0ed36127183f52ae6ced2ecb2521789995992c521a46083bfcdbb652d22ad34", size = 4776, upload-time = "2026-02-16T22:08:51.2Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/a7/24/5480c20380dfd18cf33d14784096dca45a24eae6102e91d49a718d3b6855/typer_slim-0.24.0-py3-none-any.whl", hash = "sha256:d5d7ee1ee2834d5020c7c616ed5e0d0f29b9a4b1dd283bdebae198ec09778d0e", size = 3394, upload-time = "2026-02-16T22:08:49.92Z" },
]

[[package]]
name = "typing-extensions"
version = "4.15.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/72/94/1a15dd82efb362ac84269196e94cf00f187f7ed21c242792a923cdb1c61f/typing_extensions-4.15.0.tar.gz", hash = "sha256:0cea48d173cc12fa28ecabc3b837ea3cf6f38c6d1136f85cbaaf598984861466", size = 109391, upload-time = "2025-08-25T13:49:26.313Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/18/67/36e9267722cc04a6b9f15c7f3441c2363321a3ea07da7ae0c0707beb2a9c/typing_extensions-4.15.0-py3-none-any.whl", hash = "sha256:f0fa19c6845758ab08074a0cfa8b7aecb71c999ca73d62883bc25cc018c4e548", size = 44614, upload-time = "2025-08-25T13:49:24.86Z" },
]

[[package]]
name = "typing-inspection"
version = "0.4.2"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "typing-extensions" },
]
sdist = { url = "https://files.pythonhosted.org/packages/55/e3/70399cb7dd41c10ac53367ae42139cf4b1ca5f36bb3dc6c9d33acdb43655/typing_inspection-0.4.2.tar.gz", hash = "sha256:ba561c48a67c5958007083d386c3295464928b01faa735ab8547c5692e87f464", size = 75949, upload-time = "2025-10-01T02:14:41.687Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/dc/9b/47798a6c91d8bdb567fe2698fe81e0c6b7cb7ef4d13da4114b41d239f65d/typing_inspection-0.4.2-py3-none-any.whl", hash = "sha256:4ed1cacbdc298c220f1bd249ed5287caa16f34d44ef4e9c3d0cbad5b521545e7", size = 14611, upload-time = "2025-10-01T02:14:40.154Z" },
]

[[package]]
name = "tzdata"
version = "2025.3"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/5e/a7/c202b344c5ca7daf398f3b8a477eeb205cf3b6f32e7ec3a6bac0629ca975/tzdata-2025.3.tar.gz", hash = "sha256:de39c2ca5dc7b0344f2eba86f49d614019d29f060fc4ebc8a417896a620b56a7", size = 196772, upload-time = "2025-12-13T17:45:35.667Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/c7/b0/003792df09decd6849a5e39c28b513c06e84436a54440380862b5aeff25d/tzdata-2025.3-py2.py3-none-any.whl", hash = "sha256:06a47e5700f3081aab02b2e513160914ff0694bce9947d6b76ebd6bf57cfc5d1", size = 348521, upload-time = "2025-12-13T17:45:33.889Z" },
]

[[package]]
name = "urllib3"
version = "2.6.3"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/c7/24/5f1b3bdffd70275f6661c76461e25f024d5a38a46f04aaca912426a2b1d3/urllib3-2.6.3.tar.gz", hash = "sha256:1b62b6884944a57dbe321509ab94fd4d3b307075e0c2eae991ac71ee15ad38ed", size = 435556, upload-time = "2026-01-07T16:24:43.925Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/39/08/aaaad47bc4e9dc8c725e68f9d04865dbcb2052843ff09c97b08904852d84/urllib3-2.6.3-py3-none-any.whl", hash = "sha256:bf272323e553dfb2e87d9bfd225ca7b0f467b919d7bbd355436d3fd37cb0acd4", size = 131584, upload-time = "2026-01-07T16:24:42.685Z" },
]

[[package]]
name = "uuid-utils"
version = "0.14.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/57/7c/3a926e847516e67bc6838634f2e54e24381105b4e80f9338dc35cca0086b/uuid_utils-0.14.0.tar.gz", hash = "sha256:fc5bac21e9933ea6c590433c11aa54aaca599f690c08069e364eb13a12f670b4", size = 22072, upload-time = "2026-01-20T20:37:15.729Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/a7/42/42d003f4a99ddc901eef2fd41acb3694163835e037fb6dde79ad68a72342/uuid_utils-0.14.0-cp39-abi3-macosx_10_12_x86_64.macosx_11_0_arm64.macosx_10_12_universal2.whl", hash = "sha256:f6695c0bed8b18a904321e115afe73b34444bc8451d0ce3244a1ec3b84deb0e5", size = 601786, upload-time = "2026-01-20T20:37:09.843Z" },
    { url = "https://files.pythonhosted.org/packages/96/e6/775dfb91f74b18f7207e3201eb31ee666d286579990dc69dd50db2d92813/uuid_utils-0.14.0-cp39-abi3-macosx_10_12_x86_64.whl", hash = "sha256:4f0a730bbf2d8bb2c11b93e1005e91769f2f533fa1125ed1f00fd15b6fcc732b", size = 303943, upload-time = "2026-01-20T20:37:18.767Z" },
    { url = "https://files.pythonhosted.org/packages/17/82/ea5f5e85560b08a1f30cdc65f75e76494dc7aba9773f679e7eaa27370229/uuid_utils-0.14.0-cp39-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:40ce3fd1a4fdedae618fc3edc8faf91897012469169d600133470f49fd699ed3", size = 340467, upload-time = "2026-01-20T20:37:11.794Z" },
    { url = "https://files.pythonhosted.org/packages/ca/33/54b06415767f4569882e99b6470c6c8eeb97422686a6d432464f9967fd91/uuid_utils-0.14.0-cp39-abi3-manylinux_2_17_armv7l.manylinux2014_armv7l.whl", hash = "sha256:09ae4a98416a440e78f7d9543d11b11cae4bab538b7ed94ec5da5221481748f2", size = 346333, upload-time = "2026-01-20T20:37:12.818Z" },
    { url = "https://files.pythonhosted.org/packages/cb/10/a6bce636b8f95e65dc84bf4a58ce8205b8e0a2a300a38cdbc83a3f763d27/uuid_utils-0.14.0-cp39-abi3-manylinux_2_17_ppc64le.manylinux2014_ppc64le.whl", hash = "sha256:971e8c26b90d8ae727e7f2ac3ee23e265971d448b3672882f2eb44828b2b8c3e", size = 470859, upload-time = "2026-01-20T20:37:01.512Z" },
    { url = "https://files.pythonhosted.org/packages/8a/27/84121c51ea72f013f0e03d0886bcdfa96b31c9b83c98300a7bd5cc4fa191/uuid_utils-0.14.0-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:d5cde1fa82804a8f9d2907b7aec2009d440062c63f04abbdb825fce717a5e860", size = 341988, upload-time = "2026-01-20T20:37:22.881Z" },
    { url = "https://files.pythonhosted.org/packages/90/a4/01c1c7af5e6a44f20b40183e8dac37d6ed83e7dc9e8df85370a15959b804/uuid_utils-0.14.0-cp39-abi3-manylinux_2_5_i686.manylinux1_i686.whl", hash = "sha256:c7343862a2359e0bd48a7f3dfb5105877a1728677818bb694d9f40703264a2db", size = 365784, upload-time = "2026-01-20T20:37:10.808Z" },
    { url = "https://files.pythonhosted.org/packages/04/f0/65ee43ec617b8b6b1bf2a5aecd56a069a08cca3d9340c1de86024331bde3/uuid_utils-0.14.0-cp39-abi3-musllinux_1_2_aarch64.whl", hash = "sha256:c51e4818fdb08ccec12dc7083a01f49507b4608770a0ab22368001685d59381b", size = 523750, upload-time = "2026-01-20T20:37:06.152Z" },
    { url = "https://files.pythonhosted.org/packages/95/d3/6bf503e3f135a5dfe705a65e6f89f19bccd55ac3fb16cb5d3ec5ba5388b8/uuid_utils-0.14.0-cp39-abi3-musllinux_1_2_armv7l.whl", hash = "sha256:181bbcccb6f93d80a8504b5bd47b311a1c31395139596edbc47b154b0685b533", size = 615818, upload-time = "2026-01-20T20:37:21.816Z" },
    { url = "https://files.pythonhosted.org/packages/df/6c/99937dd78d07f73bba831c8dc9469dfe4696539eba2fc269ae1b92752f9e/uuid_utils-0.14.0-cp39-abi3-musllinux_1_2_i686.whl", hash = "sha256:5c8ae96101c3524ba8dbf762b6f05e9e9d896544786c503a727c5bf5cb9af1a7", size = 580831, upload-time = "2026-01-20T20:37:19.691Z" },
    { url = "https://files.pythonhosted.org/packages/44/fa/bbc9e2c25abd09a293b9b097a0d8fc16acd6a92854f0ec080f1ea7ad8bb3/uuid_utils-0.14.0-cp39-abi3-musllinux_1_2_x86_64.whl", hash = "sha256:00ac3c6edfdaff7e1eed041f4800ae09a3361287be780d7610a90fdcde9befdc", size = 546333, upload-time = "2026-01-20T20:37:03.117Z" },
    { url = "https://files.pythonhosted.org/packages/e7/9b/e5e99b324b1b5f0c62882230455786df0bc66f67eff3b452447e703f45d2/uuid_utils-0.14.0-cp39-abi3-win32.whl", hash = "sha256:ec2fd80adf8e0e6589d40699e6f6df94c93edcc16dd999be0438dd007c77b151", size = 177319, upload-time = "2026-01-20T20:37:04.208Z" },
    { url = "https://files.pythonhosted.org/packages/d3/28/2c7d417ea483b6ff7820c948678fdf2ac98899dc7e43bb15852faa95acaf/uuid_utils-0.14.0-cp39-abi3-win_amd64.whl", hash = "sha256:efe881eb43a5504fad922644cb93d725fd8a6a6d949bd5a4b4b7d1a1587c7fd1", size = 182566, upload-time = "2026-01-20T20:37:16.868Z" },
    { url = "https://files.pythonhosted.org/packages/b8/86/49e4bdda28e962fbd7266684171ee29b3d92019116971d58783e51770745/uuid_utils-0.14.0-cp39-abi3-win_arm64.whl", hash = "sha256:32b372b8fd4ebd44d3a219e093fe981af4afdeda2994ee7db208ab065cfcd080", size = 182809, upload-time = "2026-01-20T20:37:05.139Z" },
]

[[package]]
name = "uvicorn"
version = "0.41.0"
source = { registry = "https://pypi.org/simple" }
dependencies = [
    { name = "click" },
    { name = "h11" },
]
sdist = { url = "https://files.pythonhosted.org/packages/32/ce/eeb58ae4ac36fe09e3842eb02e0eb676bf2c53ae062b98f1b2531673efdd/uvicorn-0.41.0.tar.gz", hash = "sha256:09d11cf7008da33113824ee5a1c6422d89fbc2ff476540d69a34c87fab8b571a", size = 82633, upload-time = "2026-02-16T23:07:24.1Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/83/e4/d04a086285c20886c0daad0e026f250869201013d18f81d9ff5eada73a88/uvicorn-0.41.0-py3-none-any.whl", hash = "sha256:29e35b1d2c36a04b9e180d4007ede3bcb32a85fbdfd6c6aeb3f26839de088187", size = 68783, upload-time = "2026-02-16T23:07:22.357Z" },
]

[[package]]
name = "websockets"
version = "15.0.1"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/21/e6/26d09fab466b7ca9c7737474c52be4f76a40301b08362eb2dbc19dcc16c1/websockets-15.0.1.tar.gz", hash = "sha256:82544de02076bafba038ce055ee6412d68da13ab47f0c60cab827346de828dee", size = 177016, upload-time = "2025-03-05T20:03:41.606Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/cb/9f/51f0cf64471a9d2b4d0fc6c534f323b664e7095640c34562f5182e5a7195/websockets-15.0.1-cp313-cp313-macosx_10_13_universal2.whl", hash = "sha256:ee443ef070bb3b6ed74514f5efaa37a252af57c90eb33b956d35c8e9c10a1931", size = 175440, upload-time = "2025-03-05T20:02:36.695Z" },
    { url = "https://files.pythonhosted.org/packages/8a/05/aa116ec9943c718905997412c5989f7ed671bc0188ee2ba89520e8765d7b/websockets-15.0.1-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:5a939de6b7b4e18ca683218320fc67ea886038265fd1ed30173f5ce3f8e85675", size = 173098, upload-time = "2025-03-05T20:02:37.985Z" },
    { url = "https://files.pythonhosted.org/packages/ff/0b/33cef55ff24f2d92924923c99926dcce78e7bd922d649467f0eda8368923/websockets-15.0.1-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:746ee8dba912cd6fc889a8147168991d50ed70447bf18bcda7039f7d2e3d9151", size = 173329, upload-time = "2025-03-05T20:02:39.298Z" },
    { url = "https://files.pythonhosted.org/packages/31/1d/063b25dcc01faa8fada1469bdf769de3768b7044eac9d41f734fd7b6ad6d/websockets-15.0.1-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl", hash = "sha256:595b6c3969023ecf9041b2936ac3827e4623bfa3ccf007575f04c5a6aa318c22", size = 183111, upload-time = "2025-03-05T20:02:40.595Z" },
    { url = "https://files.pythonhosted.org/packages/93/53/9a87ee494a51bf63e4ec9241c1ccc4f7c2f45fff85d5bde2ff74fcb68b9e/websockets-15.0.1-cp313-cp313-manylinux_2_5_i686.manylinux1_i686.manylinux_2_17_i686.manylinux2014_i686.whl", hash = "sha256:3c714d2fc58b5ca3e285461a4cc0c9a66bd0e24c5da9911e30158286c9b5be7f", size = 182054, upload-time = "2025-03-05T20:02:41.926Z" },
    { url = "https://files.pythonhosted.org/packages/ff/b2/83a6ddf56cdcbad4e3d841fcc55d6ba7d19aeb89c50f24dd7e859ec0805f/websockets-15.0.1-cp313-cp313-manylinux_2_5_x86_64.manylinux1_x86_64.manylinux_2_17_x86_64.manylinux2014_x86_64.whl", hash = "sha256:0f3c1e2ab208db911594ae5b4f79addeb3501604a165019dd221c0bdcabe4db8", size = 182496, upload-time = "2025-03-05T20:02:43.304Z" },
    { url = "https://files.pythonhosted.org/packages/98/41/e7038944ed0abf34c45aa4635ba28136f06052e08fc2168520bb8b25149f/websockets-15.0.1-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:229cf1d3ca6c1804400b0a9790dc66528e08a6a1feec0d5040e8b9eb14422375", size = 182829, upload-time = "2025-03-05T20:02:48.812Z" },
    { url = "https://files.pythonhosted.org/packages/e0/17/de15b6158680c7623c6ef0db361da965ab25d813ae54fcfeae2e5b9ef910/websockets-15.0.1-cp313-cp313-musllinux_1_2_i686.whl", hash = "sha256:756c56e867a90fb00177d530dca4b097dd753cde348448a1012ed6c5131f8b7d", size = 182217, upload-time = "2025-03-05T20:02:50.14Z" },
    { url = "https://files.pythonhosted.org/packages/33/2b/1f168cb6041853eef0362fb9554c3824367c5560cbdaad89ac40f8c2edfc/websockets-15.0.1-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:558d023b3df0bffe50a04e710bc87742de35060580a293c2a984299ed83bc4e4", size = 182195, upload-time = "2025-03-05T20:02:51.561Z" },
    { url = "https://files.pythonhosted.org/packages/86/eb/20b6cdf273913d0ad05a6a14aed4b9a85591c18a987a3d47f20fa13dcc47/websockets-15.0.1-cp313-cp313-win32.whl", hash = "sha256:ba9e56e8ceeeedb2e080147ba85ffcd5cd0711b89576b83784d8605a7df455fa", size = 176393, upload-time = "2025-03-05T20:02:53.814Z" },
    { url = "https://files.pythonhosted.org/packages/1b/6c/c65773d6cab416a64d191d6ee8a8b1c68a09970ea6909d16965d26bfed1e/websockets-15.0.1-cp313-cp313-win_amd64.whl", hash = "sha256:e09473f095a819042ecb2ab9465aee615bd9c2028e4ef7d933600a8401c79561", size = 176837, upload-time = "2025-03-05T20:02:55.237Z" },
    { url = "https://files.pythonhosted.org/packages/fa/a8/5b41e0da817d64113292ab1f8247140aac61cbf6cfd085d6a0fa77f4984f/websockets-15.0.1-py3-none-any.whl", hash = "sha256:f7a866fbc1e97b5c617ee4116daaa09b722101d4a3c170c787450ba409f9736f", size = 169743, upload-time = "2025-03-05T20:03:39.41Z" },
]

[[package]]
name = "xxhash"
version = "3.6.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/02/84/30869e01909fb37a6cc7e18688ee8bf1e42d57e7e0777636bd47524c43c7/xxhash-3.6.0.tar.gz", hash = "sha256:f0162a78b13a0d7617b2845b90c763339d1f1d82bb04a4b07f4ab535cc5e05d6", size = 85160, upload-time = "2025-10-02T14:37:08.097Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/33/76/35d05267ac82f53ae9b0e554da7c5e281ee61f3cad44c743f0fcd354f211/xxhash-3.6.0-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:599e64ba7f67472481ceb6ee80fa3bd828fd61ba59fb11475572cc5ee52b89ec", size = 32738, upload-time = "2025-10-02T14:34:55.839Z" },
    { url = "https://files.pythonhosted.org/packages/31/a8/3fbce1cd96534a95e35d5120637bf29b0d7f5d8fa2f6374e31b4156dd419/xxhash-3.6.0-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:7d8b8aaa30fca4f16f0c84a5c8d7ddee0e25250ec2796c973775373257dde8f1", size = 30821, upload-time = "2025-10-02T14:34:57.219Z" },
    { url = "https://files.pythonhosted.org/packages/0c/ea/d387530ca7ecfa183cb358027f1833297c6ac6098223fd14f9782cd0015c/xxhash-3.6.0-cp313-cp313-manylinux1_i686.manylinux_2_28_i686.manylinux_2_5_i686.whl", hash = "sha256:d597acf8506d6e7101a4a44a5e428977a51c0fadbbfd3c39650cca9253f6e5a6", size = 194127, upload-time = "2025-10-02T14:34:59.21Z" },
    { url = "https://files.pythonhosted.org/packages/ba/0c/71435dcb99874b09a43b8d7c54071e600a7481e42b3e3ce1eb5226a5711a/xxhash-3.6.0-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:858dc935963a33bc33490128edc1c12b0c14d9c7ebaa4e387a7869ecc4f3e263", size = 212975, upload-time = "2025-10-02T14:35:00.816Z" },
    { url = "https://files.pythonhosted.org/packages/84/7a/c2b3d071e4bb4a90b7057228a99b10d51744878f4a8a6dd643c8bd897620/xxhash-3.6.0-cp313-cp313-manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:ba284920194615cb8edf73bf52236ce2e1664ccd4a38fdb543506413529cc546", size = 212241, upload-time = "2025-10-02T14:35:02.207Z" },
    { url = "https://files.pythonhosted.org/packages/81/5f/640b6eac0128e215f177df99eadcd0f1b7c42c274ab6a394a05059694c5a/xxhash-3.6.0-cp313-cp313-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl", hash = "sha256:4b54219177f6c6674d5378bd862c6aedf64725f70dd29c472eaae154df1a2e89", size = 445471, upload-time = "2025-10-02T14:35:03.61Z" },
    { url = "https://files.pythonhosted.org/packages/5e/1e/3c3d3ef071b051cc3abbe3721ffb8365033a172613c04af2da89d5548a87/xxhash-3.6.0-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:42c36dd7dbad2f5238950c377fcbf6811b1cdb1c444fab447960030cea60504d", size = 193936, upload-time = "2025-10-02T14:35:05.013Z" },
    { url = "https://files.pythonhosted.org/packages/2c/bd/4a5f68381939219abfe1c22a9e3a5854a4f6f6f3c4983a87d255f21f2e5d/xxhash-3.6.0-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:f22927652cba98c44639ffdc7aaf35828dccf679b10b31c4ad72a5b530a18eb7", size = 210440, upload-time = "2025-10-02T14:35:06.239Z" },
    { url = "https://files.pythonhosted.org/packages/eb/37/b80fe3d5cfb9faff01a02121a0f4d565eb7237e9e5fc66e73017e74dcd36/xxhash-3.6.0-cp313-cp313-musllinux_1_2_i686.whl", hash = "sha256:b45fad44d9c5c119e9c6fbf2e1c656a46dc68e280275007bbfd3d572b21426db", size = 197990, upload-time = "2025-10-02T14:35:07.735Z" },
    { url = "https://files.pythonhosted.org/packages/d7/fd/2c0a00c97b9e18f72e1f240ad4e8f8a90fd9d408289ba9c7c495ed7dc05c/xxhash-3.6.0-cp313-cp313-musllinux_1_2_ppc64le.whl", hash = "sha256:6f2580ffab1a8b68ef2b901cde7e55fa8da5e4be0977c68f78fc80f3c143de42", size = 210689, upload-time = "2025-10-02T14:35:09.438Z" },
    { url = "https://files.pythonhosted.org/packages/93/86/5dd8076a926b9a95db3206aba20d89a7fc14dd5aac16e5c4de4b56033140/xxhash-3.6.0-cp313-cp313-musllinux_1_2_s390x.whl", hash = "sha256:40c391dd3cd041ebc3ffe6f2c862f402e306eb571422e0aa918d8070ba31da11", size = 414068, upload-time = "2025-10-02T14:35:11.162Z" },
    { url = "https://files.pythonhosted.org/packages/af/3c/0bb129170ee8f3650f08e993baee550a09593462a5cddd8e44d0011102b1/xxhash-3.6.0-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:f205badabde7aafd1a31e8ca2a3e5a763107a71c397c4481d6a804eb5063d8bd", size = 191495, upload-time = "2025-10-02T14:35:12.971Z" },
    { url = "https://files.pythonhosted.org/packages/e9/3a/6797e0114c21d1725e2577508e24006fd7ff1d8c0c502d3b52e45c1771d8/xxhash-3.6.0-cp313-cp313-win32.whl", hash = "sha256:2577b276e060b73b73a53042ea5bd5203d3e6347ce0d09f98500f418a9fcf799", size = 30620, upload-time = "2025-10-02T14:35:14.129Z" },
    { url = "https://files.pythonhosted.org/packages/86/15/9bc32671e9a38b413a76d24722a2bf8784a132c043063a8f5152d390b0f9/xxhash-3.6.0-cp313-cp313-win_amd64.whl", hash = "sha256:757320d45d2fbcce8f30c42a6b2f47862967aea7bf458b9625b4bbe7ee390392", size = 31542, upload-time = "2025-10-02T14:35:15.21Z" },
    { url = "https://files.pythonhosted.org/packages/39/c5/cc01e4f6188656e56112d6a8e0dfe298a16934b8c47a247236549a3f7695/xxhash-3.6.0-cp313-cp313-win_arm64.whl", hash = "sha256:457b8f85dec5825eed7b69c11ae86834a018b8e3df5e77783c999663da2f96d6", size = 27880, upload-time = "2025-10-02T14:35:16.315Z" },
    { url = "https://files.pythonhosted.org/packages/f3/30/25e5321c8732759e930c555176d37e24ab84365482d257c3b16362235212/xxhash-3.6.0-cp313-cp313t-macosx_10_13_x86_64.whl", hash = "sha256:a42e633d75cdad6d625434e3468126c73f13f7584545a9cf34e883aa1710e702", size = 32956, upload-time = "2025-10-02T14:35:17.413Z" },
    { url = "https://files.pythonhosted.org/packages/9f/3c/0573299560d7d9f8ab1838f1efc021a280b5ae5ae2e849034ef3dee18810/xxhash-3.6.0-cp313-cp313t-macosx_11_0_arm64.whl", hash = "sha256:568a6d743219e717b07b4e03b0a828ce593833e498c3b64752e0f5df6bfe84db", size = 31072, upload-time = "2025-10-02T14:35:18.844Z" },
    { url = "https://files.pythonhosted.org/packages/7a/1c/52d83a06e417cd9d4137722693424885cc9878249beb3a7c829e74bf7ce9/xxhash-3.6.0-cp313-cp313t-manylinux1_i686.manylinux_2_28_i686.manylinux_2_5_i686.whl", hash = "sha256:bec91b562d8012dae276af8025a55811b875baace6af510412a5e58e3121bc54", size = 196409, upload-time = "2025-10-02T14:35:20.31Z" },
    { url = "https://files.pythonhosted.org/packages/e3/8e/c6d158d12a79bbd0b878f8355432075fc82759e356ab5a111463422a239b/xxhash-3.6.0-cp313-cp313t-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:78e7f2f4c521c30ad5e786fdd6bae89d47a32672a80195467b5de0480aa97b1f", size = 215736, upload-time = "2025-10-02T14:35:21.616Z" },
    { url = "https://files.pythonhosted.org/packages/bc/68/c4c80614716345d55071a396cf03d06e34b5f4917a467faf43083c995155/xxhash-3.6.0-cp313-cp313t-manylinux2014_ppc64le.manylinux_2_17_ppc64le.manylinux_2_28_ppc64le.whl", hash = "sha256:3ed0df1b11a79856df5ffcab572cbd6b9627034c1c748c5566fa79df9048a7c5", size = 214833, upload-time = "2025-10-02T14:35:23.32Z" },
    { url = "https://files.pythonhosted.org/packages/7e/e9/ae27c8ffec8b953efa84c7c4a6c6802c263d587b9fc0d6e7cea64e08c3af/xxhash-3.6.0-cp313-cp313t-manylinux2014_s390x.manylinux_2_17_s390x.manylinux_2_28_s390x.whl", hash = "sha256:0e4edbfc7d420925b0dd5e792478ed393d6e75ff8fc219a6546fb446b6a417b1", size = 448348, upload-time = "2025-10-02T14:35:25.111Z" },
    { url = "https://files.pythonhosted.org/packages/d7/6b/33e21afb1b5b3f46b74b6bd1913639066af218d704cc0941404ca717fc57/xxhash-3.6.0-cp313-cp313t-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl", hash = "sha256:fba27a198363a7ef87f8c0f6b171ec36b674fe9053742c58dd7e3201c1ab30ee", size = 196070, upload-time = "2025-10-02T14:35:26.586Z" },
    { url = "https://files.pythonhosted.org/packages/96/b6/fcabd337bc5fa624e7203aa0fa7d0c49eed22f72e93229431752bddc83d9/xxhash-3.6.0-cp313-cp313t-musllinux_1_2_aarch64.whl", hash = "sha256:794fe9145fe60191c6532fa95063765529770edcdd67b3d537793e8004cabbfd", size = 212907, upload-time = "2025-10-02T14:35:28.087Z" },
    { url = "https://files.pythonhosted.org/packages/4b/d3/9ee6160e644d660fcf176c5825e61411c7f62648728f69c79ba237250143/xxhash-3.6.0-cp313-cp313t-musllinux_1_2_i686.whl", hash = "sha256:6105ef7e62b5ac73a837778efc331a591d8442f8ef5c7e102376506cb4ae2729", size = 200839, upload-time = "2025-10-02T14:35:29.857Z" },
    { url = "https://files.pythonhosted.org/packages/0d/98/e8de5baa5109394baf5118f5e72ab21a86387c4f89b0e77ef3e2f6b0327b/xxhash-3.6.0-cp313-cp313t-musllinux_1_2_ppc64le.whl", hash = "sha256:f01375c0e55395b814a679b3eea205db7919ac2af213f4a6682e01220e5fe292", size = 213304, upload-time = "2025-10-02T14:35:31.222Z" },
    { url = "https://files.pythonhosted.org/packages/7b/1d/71056535dec5c3177eeb53e38e3d367dd1d16e024e63b1cee208d572a033/xxhash-3.6.0-cp313-cp313t-musllinux_1_2_s390x.whl", hash = "sha256:d706dca2d24d834a4661619dcacf51a75c16d65985718d6a7d73c1eeeb903ddf", size = 416930, upload-time = "2025-10-02T14:35:32.517Z" },
    { url = "https://files.pythonhosted.org/packages/dc/6c/5cbde9de2cd967c322e651c65c543700b19e7ae3e0aae8ece3469bf9683d/xxhash-3.6.0-cp313-cp313t-musllinux_1_2_x86_64.whl", hash = "sha256:5f059d9faeacd49c0215d66f4056e1326c80503f51a1532ca336a385edadd033", size = 193787, upload-time = "2025-10-02T14:35:33.827Z" },
    { url = "https://files.pythonhosted.org/packages/19/fa/0172e350361d61febcea941b0cc541d6e6c8d65d153e85f850a7b256ff8a/xxhash-3.6.0-cp313-cp313t-win32.whl", hash = "sha256:1244460adc3a9be84731d72b8e80625788e5815b68da3da8b83f78115a40a7ec", size = 30916, upload-time = "2025-10-02T14:35:35.107Z" },
    { url = "https://files.pythonhosted.org/packages/ad/e6/e8cf858a2b19d6d45820f072eff1bea413910592ff17157cabc5f1227a16/xxhash-3.6.0-cp313-cp313t-win_amd64.whl", hash = "sha256:b1e420ef35c503869c4064f4a2f2b08ad6431ab7b229a05cce39d74268bca6b8", size = 31799, upload-time = "2025-10-02T14:35:36.165Z" },
    { url = "https://files.pythonhosted.org/packages/56/15/064b197e855bfb7b343210e82490ae672f8bc7cdf3ddb02e92f64304ee8a/xxhash-3.6.0-cp313-cp313t-win_arm64.whl", hash = "sha256:ec44b73a4220623235f67a996c862049f375df3b1052d9899f40a6382c32d746", size = 28044, upload-time = "2025-10-02T14:35:37.195Z" },
]

[[package]]
name = "zstandard"
version = "0.25.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/fd/aa/3e0508d5a5dd96529cdc5a97011299056e14c6505b678fd58938792794b1/zstandard-0.25.0.tar.gz", hash = "sha256:7713e1179d162cf5c7906da876ec2ccb9c3a9dcbdffef0cc7f70c3667a205f0b", size = 711513, upload-time = "2025-09-14T22:15:54.002Z" }
wheels = [
    { url = "https://files.pythonhosted.org/packages/35/0b/8df9c4ad06af91d39e94fa96cc010a24ac4ef1378d3efab9223cc8593d40/zstandard-0.25.0-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:ec996f12524f88e151c339688c3897194821d7f03081ab35d31d1e12ec975e94", size = 795735, upload-time = "2025-09-14T22:17:26.042Z" },
    { url = "https://files.pythonhosted.org/packages/3f/06/9ae96a3e5dcfd119377ba33d4c42a7d89da1efabd5cb3e366b156c45ff4d/zstandard-0.25.0-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:a1a4ae2dec3993a32247995bdfe367fc3266da832d82f8438c8570f989753de1", size = 640440, upload-time = "2025-09-14T22:17:27.366Z" },
    { url = "https://files.pythonhosted.org/packages/d9/14/933d27204c2bd404229c69f445862454dcc101cd69ef8c6068f15aaec12c/zstandard-0.25.0-cp313-cp313-manylinux2010_i686.manylinux2014_i686.manylinux_2_12_i686.manylinux_2_17_i686.whl", hash = "sha256:e96594a5537722fdfb79951672a2a63aec5ebfb823e7560586f7484819f2a08f", size = 5343070, upload-time = "2025-09-14T22:17:28.896Z" },
    { url = "https://files.pythonhosted.org/packages/6d/db/ddb11011826ed7db9d0e485d13df79b58586bfdec56e5c84a928a9a78c1c/zstandard-0.25.0-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.whl", hash = "sha256:bfc4e20784722098822e3eee42b8e576b379ed72cca4a7cb856ae733e62192ea", size = 5063001, upload-time = "2025-09-14T22:17:31.044Z" },
    { url = "https://files.pythonhosted.org/packages/db/00/87466ea3f99599d02a5238498b87bf84a6348290c19571051839ca943777/zstandard-0.25.0-cp313-cp313-manylinux2014_ppc64le.manylinux_2_17_ppc64le.whl", hash = "sha256:457ed498fc58cdc12fc48f7950e02740d4f7ae9493dd4ab2168a47c93c31298e", size = 5394120, upload-time = "2025-09-14T22:17:32.711Z" },
    { url = "https://files.pythonhosted.org/packages/2b/95/fc5531d9c618a679a20ff6c29e2b3ef1d1f4ad66c5e161ae6ff847d102a9/zstandard-0.25.0-cp313-cp313-manylinux2014_s390x.manylinux_2_17_s390x.whl", hash = "sha256:fd7a5004eb1980d3cefe26b2685bcb0b17989901a70a1040d1ac86f1d898c551", size = 5451230, upload-time = "2025-09-14T22:17:34.41Z" },
    { url = "https://files.pythonhosted.org/packages/63/4b/e3678b4e776db00f9f7b2fe58e547e8928ef32727d7a1ff01dea010f3f13/zstandard-0.25.0-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:8e735494da3db08694d26480f1493ad2cf86e99bdd53e8e9771b2752a5c0246a", size = 5547173, upload-time = "2025-09-14T22:17:36.084Z" },
    { url = "https://files.pythonhosted.org/packages/4e/d5/ba05ed95c6b8ec30bd468dfeab20589f2cf709b5c940483e31d991f2ca58/zstandard-0.25.0-cp313-cp313-musllinux_1_1_aarch64.whl", hash = "sha256:3a39c94ad7866160a4a46d772e43311a743c316942037671beb264e395bdd611", size = 5046736, upload-time = "2025-09-14T22:17:37.891Z" },
    { url = "https://files.pythonhosted.org/packages/50/d5/870aa06b3a76c73eced65c044b92286a3c4e00554005ff51962deef28e28/zstandard-0.25.0-cp313-cp313-musllinux_1_1_x86_64.whl", hash = "sha256:172de1f06947577d3a3005416977cce6168f2261284c02080e7ad0185faeced3", size = 5576368, upload-time = "2025-09-14T22:17:40.206Z" },
    { url = "https://files.pythonhosted.org/packages/5d/35/398dc2ffc89d304d59bc12f0fdd931b4ce455bddf7038a0a67733a25f550/zstandard-0.25.0-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:3c83b0188c852a47cd13ef3bf9209fb0a77fa5374958b8c53aaa699398c6bd7b", size = 4954022, upload-time = "2025-09-14T22:17:41.879Z" },
    { url = "https://files.pythonhosted.org/packages/9a/5c/36ba1e5507d56d2213202ec2b05e8541734af5f2ce378c5d1ceaf4d88dc4/zstandard-0.25.0-cp313-cp313-musllinux_1_2_i686.whl", hash = "sha256:1673b7199bbe763365b81a4f3252b8e80f44c9e323fc42940dc8843bfeaf9851", size = 5267889, upload-time = "2025-09-14T22:17:43.577Z" },
    { url = "https://files.pythonhosted.org/packages/70/e8/2ec6b6fb7358b2ec0113ae202647ca7c0e9d15b61c005ae5225ad0995df5/zstandard-0.25.0-cp313-cp313-musllinux_1_2_ppc64le.whl", hash = "sha256:0be7622c37c183406f3dbf0cba104118eb16a4ea7359eeb5752f0794882fc250", size = 5433952, upload-time = "2025-09-14T22:17:45.271Z" },
    { url = "https://files.pythonhosted.org/packages/7b/01/b5f4d4dbc59ef193e870495c6f1275f5b2928e01ff5a81fecb22a06e22fb/zstandard-0.25.0-cp313-cp313-musllinux_1_2_s390x.whl", hash = "sha256:5f5e4c2a23ca271c218ac025bd7d635597048b366d6f31f420aaeb715239fc98", size = 5814054, upload-time = "2025-09-14T22:17:47.08Z" },
    { url = "https://files.pythonhosted.org/packages/b2/e5/fbd822d5c6f427cf158316d012c5a12f233473c2f9c5fe5ab1ae5d21f3d8/zstandard-0.25.0-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:4f187a0bb61b35119d1926aee039524d1f93aaf38a9916b8c4b78ac8514a0aaf", size = 5360113, upload-time = "2025-09-14T22:17:48.893Z" },
    { url = "https://files.pythonhosted.org/packages/8e/e0/69a553d2047f9a2c7347caa225bb3a63b6d7704ad74610cb7823baa08ed7/zstandard-0.25.0-cp313-cp313-win32.whl", hash = "sha256:7030defa83eef3e51ff26f0b7bfb229f0204b66fe18e04359ce3474ac33cbc09", size = 436936, upload-time = "2025-09-14T22:17:52.658Z" },
    { url = "https://files.pythonhosted.org/packages/d9/82/b9c06c870f3bd8767c201f1edbdf9e8dc34be5b0fbc5682c4f80fe948475/zstandard-0.25.0-cp313-cp313-win_amd64.whl", hash = "sha256:1f830a0dac88719af0ae43b8b2d6aef487d437036468ef3c2ea59c51f9d55fd5", size = 506232, upload-time = "2025-09-14T22:17:50.402Z" },
    { url = "https://files.pythonhosted.org/packages/d4/57/60c3c01243bb81d381c9916e2a6d9e149ab8627c0c7d7abb2d73384b3c0c/zstandard-0.25.0-cp313-cp313-win_arm64.whl", hash = "sha256:85304a43f4d513f5464ceb938aa02c1e78c2943b29f44a750b48b25ac999a049", size = 462671, upload-time = "2025-09-14T22:17:51.533Z" },
]

ffmpeg
fonts-noto-cjk

"""Hugging Face Spaces entry point."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from real_time_translation.gradio_demo import build_demo

demo = build_demo()
demo.queue()
demo.launch(ssr_mode=False)

audioop-lts>=0.2.1
deepgram-sdk>=5.3.2,<6.0.0
google-genai>=1.58.0
langchain>=1.2.6
langchain-google-genai>=4.2.0
langchain-openai>=0.2.0
numpy>=1.26.0
pillow>=11.0
python-dotenv>=1.0.0
sacrebleu>=2.4.0

---
title: Real-time Translation
emoji: 🎙️
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.25.0
app_file: app.py
pinned: false
---

# Real-time Translation

Zoomミーティングの音声をリアルタイムに文字起こし・翻訳するシステム。
動画ファイルへの日本語字幕追加スクリプト (`add_subtitles.py`) も含む。

## 機能一覧

| 機能 | スクリプト/コマンド | 説明 |
|---|---|---|
| リアルタイム翻訳 (Zoom RTMS) | `uv run real-time-translation` | Zoom音声をリアルタイムで翻訳 |
| リアルタイム翻訳 (Webデモ) | `uv run real-time-translation-demo` | ブラウザマイク入力で翻訳 |
| 動画字幕追加 | `python add_subtitles.py <動画>` | MP4に日本語字幕を焼き込む |

---

## 動画字幕追加スクリプト (`add_subtitles.py`)

動画ファイルから音声を抽出し、Deepgramで文字起こし、Geminiで日本語翻訳して字幕を焼き込みます。

### 処理フロー

```
動画ファイル → ffmpeg（音声抽出）→ Deepgram（文字起こし）→ Gemini（日本語翻訳）→ SRT生成 → ffmpeg（字幕焼き込み）→ 字幕付き動画
```

### 必要な環境変数

`.env` ファイルに以下を設定してください：

```env
DEEPGRAM_API_KEY=your_deepgram_api_key
GOOGLE_API_KEY=your_google_api_key
SOURCE_LANGUAGE=en          # 元言語（省略時: en）
TRANSLATION_DOMAIN=general  # 翻訳ドメイン（実験記録用、省略時: general）
```

### 使い方

```bash
# 動画ファイルを指定して実行
python add_subtitles.py "C:\path\to\video.mp4"

# 引数なしで実行（デフォルトパスを使用）
python add_subtitles.py
```

### 出力ファイル

| ファイル | 説明 |
|---|---|
| `<元ファイル名>_subtitled.mp4` | 字幕焼き込み済み動画 |
| `<元ファイル名>_ja.srt` | SRT字幕ファイル（単体利用可） |

### 自動評価・実験記録

実行後、翻訳品質の自動評価を行い `experiments/` フォルダに記録します：

- **xcomet_score**: Gemini LLM-as-judge による品質スコア（0〜1）
- **chrf_score**: 逆翻訳 + chrF によるスコア（0〜1）

### 依存パッケージ

```bash
pip install python-dotenv deepgram-sdk google-genai sacrebleu
```

ffmpeg が PATH に通っている必要があります。

---

## リアルタイム翻訳システム構成

```
Zoom RTMS → AudioCapture → Deepgram WebSocket → LLM (Gemini/OpenAI) → 翻訳出力
```

## セットアップ

```bash
# 環境変数の設定
cp .env.example .env
# .envファイルを編集してAPIキーを設定
```

## 環境変数

| 変数名                      | 説明                        | 必須         |
| --------------------------- | --------------------------- | ------------ |
| `ZOOM_CLIENT_ID`            | Zoom RTMS Client ID         | 今回は不要   |
| `ZOOM_CLIENT_SECRET`        | Zoom RTMS Client Secret     | 今回は不要   |
| `DEEPGRAM_API_KEY`          | Deepgram APIキー            | ✓            |
| `DEEPGRAM_MODEL`            | Deepgramモデル名            |              |
| `DEEPGRAM_ENDPOINTING`      | 無音検知の確定(ms)          |              |
| `DEEPGRAM_UTTERANCE_END_MS` | 発話終了検知(ms)            |              |
| `DEEPGRAM_INTERIM_RESULTS`  | Interim出力有無             |              |
| `DEEPGRAM_SMART_FORMAT`     | smart_format有無            |              |
| `DEEPGRAM_VAD_EVENTS`       | VADイベント有無             |              |
| `LLM_PROVIDER`              | `gemini` または `openai`    | ✓            |
| `GOOGLE_API_KEY`            | Google AI APIキー           | Gemini使用時 |
| `OPENAI_API_KEY`            | OpenAI APIキー              | OpenAI使用時 |
| `SOURCE_LANGUAGE`           | 元言語コード (例: `en`)     |              |
| `TARGET_LANGUAGE`           | 翻訳先言語コード (例: `ja`) |              |
| `CONTEXT_WINDOW_SIZE`       | 文脈保持の文数              |              |
| `TRANSLATION_QUEUE_SIZE`    | 翻訳キューサイズ            |              |
| `DICTIONARY_PATH`           | 用語辞書CSVパス             |              |

`DEEPGRAM_UTTERANCE_END_MS` を設定すると、UtteranceEndイベントで
直近のinterim結果を確定として扱い、文脈のまとまりを優先できます。

### マイクロサービス用追加環境変数

| 変数名                        | 説明                         | 必須 |
| ----------------------------- | ---------------------------- | ---- |
| `RTMP_URL`                    | NMSのRTMP入力URL             | ✓    |
| `WS_PUBLISH_URL`              | WSサービスへのPublish URL    | ✓    |
| `TRANSLATION_API_URL`         | 翻訳API URL                  | ✓    |
| `DICTIONARY_PATH`             | 用語辞書CSVパス（keyterm用） |      |
| `ZOOM_CAPTION_URL`            | Zoom字幕API URL              |      |
| `ZOOM_CAPTION_LANG`           | Zoom字幕の言語コード         |      |
| `ASR_SEND_INTERIM`            | ASRのinterimをWSへ送信       |      |
| `TRANSLATE_INTERIM`           | interimを翻訳へ送信          |      |
| `ASR_PARTIAL_MIN_INTERVAL_MS` | interim送信間隔(ms)          |      |
| `TRANSLATION_CONCURRENCY`     | 翻訳同時実行数               |      |
| `HTTP_TIMEOUT`                | HTTPタイムアウト(秒)         |      |

`DICTIONARY_PATH`で指定したCSVファイルの`source_term`列がDeepgramの[Keyterm Prompting](https://developers.deepgram.com/docs/keyterm)として渡され、専門用語の認識精度が向上します。

`ZOOM_CAPTION_URL`を設定すると、翻訳結果がZoomミーティングの字幕として表示されます。URLはZoomミーティング内で「字幕を有効化」→「APIトークンをコピー」から取得できます。詳細は[Zoomサポート](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060372)を参照。

## 使い方

```bash
# Zoom RTMS向けCLI
uv run real-time-translation

# Webデモ (Gradio / マイク入力)
uv run real-time-translation-demo

# マイクロサービス単体起動（各サービスのディレクトリで実行）
cd services/ws
uv sync
uv run real-time-translation-ws

cd ../translator
uv sync
uv run real-time-translation-translate

cd ../asr
uv sync
uv run real-time-translation-asr
```

WebデモはZoom認証なしで動作します。`DEEPGRAM_API_KEY` と `LLM_PROVIDER`
に応じたAPIキーのみ設定してください。

## Docker マイクロサービス構成

```bash
# Docker Composeで起動
docker compose up --build
```

各サービスは `services/<name>/pyproject.toml` を持つ独立パッケージです。

### エンドポイント

| サービス            | URL                               |
| ------------------- | --------------------------------- |
| RTMP入力            | `rtmp://localhost:1935/live/zoom` |
| 字幕WebSocket       | `ws://localhost:8001/ws/caption`  |
| NMS管理画面         | `http://localhost:8000/admin`     |
| ngrokダッシュボード | `http://localhost:4040`           |

### 主なサービス

| サービス   | 説明                                     |
| ---------- | ---------------------------------------- |
| `nms`      | Node-Media-Server (RTMP受信)             |
| `ngrok`    | RTMPポートをインターネットに公開         |
| `deepgram` | RTMP → Deepgram ASR、結果をWS/翻訳へ中継 |
| `gemini`   | 翻訳API (FastAPI)                        |
| `ws`       | 字幕配信用WebSocket (FastAPI)            |

### ngrok設定（Zoomカスタムストリーミング用）

Zoomのカスタムストリーミングをローカル環境で受信するには、ngrokでRTMPポートを公開する必要があります。

1. **ngrokアカウント設定**
   - [ngrokダッシュボード](https://dashboard.ngrok.com/get-started/your-authtoken)から認証トークンを取得
   - [設定ページ](https://dashboard.ngrok.com/settings#id-verification)でクレジットカードを登録（TCPトンネル利用に必要、課金なし）

2. **環境変数設定**
   ```bash
   # .envファイルに追加
   NGROK_AUTHTOKEN=your_token_here
   ```

3. **トンネルURLの確認**
   ```bash
   # ngrokダッシュボードでトンネルURLを確認
   curl -s http://localhost:4040/api/tunnels | jq '.tunnels[0].public_url'
   # 例: tcp://0.tcp.jp.ngrok.io:12345
   ```

4. **Zoomでの設定**
   - Streaming URL: `rtmp://0.tcp.jp.ngrok.io:12345/live`
   - Streaming Key: `zoom`

### デバッグモード

WebSocketに流れるメッセージを確認するためのデバッグサービスを起動できます。

```bash
# デバッグモードで起動
docker compose --profile debug up -d

# デバッグログを確認
docker compose logs -f ws-debug

# デバッグモードを含めてすべて停止
docker compose --profile debug down
```

> **Note**:
> `ws-debug`は`profiles: [debug]`で定義されているため、通常の`docker compose down`では停止されません。必ず`--profile debug`を付けて停止してください。

マイクロサービス用の環境変数例は `.env.example` に追加済みです。

Gemini利用時は `google.genai` (google-genai) のContext Cachingで
システムプロンプト/辞書をキャッシュし、LangChainの
`ChatGoogleGenerativeAI(cached_content=...)` 経由で参照します。 Context
Cacheは最小トークン数の制約があるため、プロンプトが小さい場合は 自動的に
`<cache_padding>` を付与してキャッシュを作成します。

翻訳はStructured Outputで `latest_slide`（最新の翻訳）と `kept_terms`
（固有名詞/曖昧語として保持した語）を返し、Webデモでは直近 `CONTEXT_WINDOW_SIZE`
文のスライドウィンド表示を行います。

## 開発

```bash
# テストの実行
uv run pytest

# コードフォーマット
uv run ruff format .

# リント
uv run ruff check .
```

## プロジェクト構造

```
src/real_time_translation/
├── audio/           # 音声取得モジュール
│   ├── __init__.py
│   └── capture.py   # AudioCapture, ZoomRTMSCapture
├── transcription/   # 文字起こしモジュール
│   ├── __init__.py
│   └── deepgram_client.py  # DeepgramTranscriber
├── translation/     # 翻訳モジュール
│   ├── __init__.py
│   └── llm_translator.py   # LLMTranslator (Gemini/OpenAI)
├── __init__.py
├── config.py        # 設定管理
├── gradio_demo.py   # Gradioデモ
├── main.py          # CLIエントリーポイント
└── pipeline.py      # パイプライン統合
services/
├── asr/
│   ├── pyproject.toml
│   └── src/asr_service/      # ASRサービス実装
├── translator/
│   ├── pyproject.toml
│   └── src/translator_service/ # 翻訳サービス実装
└── ws/
    ├── pyproject.toml
    └── src/ws_service/       # WebSocket配信サービス実装
```

# 動画に日本語字幕を追加する方法

このガイドでは、英語の動画ファイルに日本語字幕を自動で追加する手順を説明します。
プログラミングの知識がなくても進められるよう、一つひとつ丁寧に説明します。

---

## 全体の流れ

1. 必要なソフトをインストールする（最初の1回だけ）
2. APIキーを取得して設定する（最初の1回だけ）
3. 字幕を追加したい動画ファイルを指定して実行する

---

## ステップ 1：Python をインストールする

Python（プログラムを動かすソフト）が必要です。

1. [https://www.python.org/downloads/](https://www.python.org/downloads/) を開く
2. 「Download Python」ボタンをクリックしてインストーラーをダウンロード
3. インストーラーを起動し、**「Add Python to PATH」にチェックを入れてから** インストール

> すでに Python がインストール済みの場合はこのステップは不要です。

---

## ステップ 2：ffmpeg をインストールする

動画から音声を取り出すために必要なソフトです。

1. [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/) を開く
2. `ffmpeg-release-essentials.zip` をダウンロード
3. ZIP を解凍して、中の `bin` フォルダのパス（例：`C:\ffmpeg\bin`）をコピーする
4. スタートメニューで「環境変数」と検索 → 「システム環境変数の編集」を開く
5. 「環境変数」→「Path」をダブルクリック → 「新規」→ 上でコピーしたパスを貼り付けて OK

> 設定後、コマンドプロンプトを開き直して `ffmpeg -version` と入力してエラーが出なければ成功です。

---

## ステップ 3：必要なライブラリをインストールする

コマンドプロンプト（黒い画面）を開いて、以下のコマンドをコピー＆ペーストして Enter を押してください。

```
pip install python-dotenv deepgram-sdk google-genai sacrebleu
```

> コマンドプロンプトの開き方：スタートメニューで「cmd」と検索 →「コマンドプロンプト」を開く

---

## ステップ 4：APIキーを取得する

このプログラムは2つの外部サービスを使います。それぞれのサービスに無料登録してAPIキーを取得します。

### Deepgram（音声をテキストに変換するサービス）

1. [https://console.deepgram.com/](https://console.deepgram.com/) にアクセスしてアカウントを作成
2. ログイン後、左メニューの「API Keys」をクリック
3. 「Create a New API Key」→ 名前を適当に入力して作成
4. 表示されたキー（長い文字列）をコピーしてメモ帳などに保存

### Google AI（日本語に翻訳するサービス）

1. [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) にアクセス（Googleアカウントでログイン）
2. 「APIキーを作成」をクリック
3. 表示されたキーをコピーしてメモ帳などに保存

---

## ステップ 5：設定ファイルを作る

このプログラムのフォルダに `.env` というファイルを作って、APIキーを書き込みます。

1. このプログラムのフォルダ（`add_subtitles.py` があるフォルダ）を開く
2. フォルダ内を右クリック →「新規作成」→「テキストドキュメント」
3. ファイル名を `.env` にする（拡張子 `.txt` は削除してください）
4. `.env` ファイルをメモ帳で開き、以下の内容を貼り付ける

```
DEEPGRAM_API_KEY=ここにDeepgramのAPIキーを貼り付け
GOOGLE_API_KEY=ここにGoogleのAPIキーを貼り付け
SOURCE_LANGUAGE=en
TRANSLATION_DOMAIN=general
```

5. 上書き保存する

**設定例：**

```
DEEPGRAM_API_KEY=abc123xyz...（実際のキー）
GOOGLE_API_KEY=AIzaSy...（実際のキー）
SOURCE_LANGUAGE=en
TRANSLATION_DOMAIN=general
```

---

## ステップ 6：字幕を追加する

### 方法A：コマンドプロンプトから実行する

1. コマンドプロンプトを開く
2. このプログラムのフォルダに移動する（フォルダのパスを確認してコピー）

```
cd "C:\Users\（あなたのユーザー名）\（プログラムのフォルダ）"
```

3. 以下のコマンドを入力して Enter を押す（動画のパスは実際のものに変更してください）

```
python add_subtitles.py "C:\Users\（あなたのユーザー名）\Desktop\動画ファイル.mp4"
```

### 方法B：ダブルクリックで実行できるバッチファイルを作る

毎回コマンドプロンプトを開くのが面倒な場合は、以下の手順でダブルクリックだけで動かせるようになります。

1. このプログラムのフォルダに `字幕を追加する.bat` という名前のファイルを新規作成
2. メモ帳で開いて以下の内容を貼り付け、動画のパスを書き換えて保存

```bat
@echo off
cd /d "%~dp0"
python add_subtitles.py "C:\Users\（あなたのユーザー名）\Desktop\動画ファイル.mp4"
pause
```

3. `字幕を追加する.bat` をダブルクリックすると実行されます

---

## 実行中の表示について

実行すると黒い画面に以下のようなメッセージが順番に表示されます。すべて正常な動作です。

```
音声を抽出中: ...        ← 動画から音声を取り出しています
音声抽出完了
Deepgramで文字起こし中...  ← 音声をテキストに変換しています
文字起こし完了: 165 セグメント
Geminiで日本語翻訳中...   ← 日本語に翻訳しています
  翻訳済み: 10/165
  ...
字幕を焼き込み中...       ← 動画に字幕を追加しています
完了!
```

動画の長さによって数分〜十数分かかります。「完了!」と表示されたら終わりです。

---

## 出力されるファイル

元の動画と同じフォルダに以下の2つが作成されます。

| ファイル名 | 説明 |
|---|---|
| `動画名_subtitled.mp4` | 字幕が焼き込まれた動画 |
| `動画名_ja.srt` | 字幕ファイル単体（動画プレイヤーで読み込んで使うこともできます） |

---

## よくあるトラブル

### 「python は内部コマンドではありません」と表示される

→ Python のインストール時に「Add Python to PATH」にチェックを入れ忘れた可能性があります。
　Python を一度アンインストールして、チェックを入れ直してインストールしてください。

### 「ffmpeg は内部コマンドではありません」と表示される

→ ステップ2の環境変数の設定が正しくできていません。コマンドプロンプトを開き直してから再試行してください。

### 「DEEPGRAM_API_KEY が見つかりません」のようなエラーが出る

→ `.env` ファイルの保存場所や内容を確認してください。`add_subtitles.py` と同じフォルダに置かれているか確認してください。

### 処理が途中で止まる・エラーが出る

→ インターネット接続を確認してください。このプログラムはインターネット経由でサービスを利用しています。

---

## 注意事項

- **APIの利用料金**：Deepgram・Google AI ともに一定量まで無料で使えますが、大量に使う場合は料金が発生することがあります。各サービスの料金ページで確認してください。
- **対応している動画形式**：MP4, MOV, AVI など、ffmpeg が対応している形式であれば使えます。
- **翻訳元の言語**：デフォルトでは英語（`SOURCE_LANGUAGE=en`）です。他の言語の動画を翻訳したい場合は `.env` の `SOURCE_LANGUAGE` を変更してください（例：フランス語なら `fr`）。

"""
動画ファイルに日本語字幕を追加するスクリプト。

手順:
1. ffmpegで音声抽出
2. Deepgramで文字起こし（タイムスタンプ付き）
3. Geminiで日本語翻訳
4. SRTファイル生成
5. ffmpegで字幕焼き込み
"""

import asyncio
import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]
GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
SOURCE_LANGUAGE = os.environ.get("SOURCE_LANGUAGE", "en")
TRANSLATION_DOMAIN = os.environ.get("TRANSLATION_DOMAIN", "general")
GEMINI_MODEL = "gemini-2.5-flash"

EXPERIMENTS_DIR = Path(__file__).parent / "experiments"


async def compute_scores(translated: list[dict]) -> tuple[float | None, float | None]:
    """自動評価スコアを計算する。

    xcomet_score: Gemini LLM-as-judge（0〜1）
    chrf_score:   逆翻訳（日→英）後に sacrebleu chrF で計算（0〜1）
    """
    from google import genai

    client = genai.Client(api_key=GOOGLE_API_KEY)
    sample = translated[:20]
    srcs = [s["original"] for s in sample]
    mts = [s["japanese"] for s in sample]

    # --- xcomet_score: LLM-as-judge ---
    print("自動評価（LLM判定）を計算中...")
    judge_prompt = (
        "あなたはプロの翻訳評価者です。以下の英日翻訳ペアをそれぞれ評価し、"
        "翻訳品質を0.00〜1.00のスコアで採点してください。"
        "番号付きリストで数値のみ返してください（例: 1. 0.85）。\n\n"
        + "\n".join(f"{i+1}. EN: {s}\n   JA: {m}" for i, (s, m) in enumerate(zip(srcs, mts)))
    )
    judge_resp = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=judge_prompt,
    )
    xcomet_score: float | None = None
    scores = []
    import re
    for line in (judge_resp.text or "").split("\n"):
        m = re.match(r"\d+\.\s*([\d.]+)", line.strip())
        if m:
            try:
                scores.append(float(m.group(1)))
            except ValueError:
                pass
    if scores:
        xcomet_score = round(sum(scores) / len(scores), 4)
        print(f"  xcomet_score (LLM judge): {xcomet_score}")

    # --- chrf_score: 逆翻訳 + sacrebleu ---
    print("自動評価（逆翻訳 chrF）を計算中...")
    back_prompt = (
        "Translate the following Japanese sentences back to English. "
        "Return only the translations as a numbered list (e.g. 1. text). "
        "Do not include explanations.\n\n"
        + "\n".join(f"{i+1}. {m}" for i, m in enumerate(mts))
    )
    back_resp = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=back_prompt,
    )
    chrf_score: float | None = None
    back_texts: list[str] = []
    for line in (back_resp.text or "").split("\n"):
        line = line.strip()
        if line and line[0].isdigit() and ". " in line:
            back_texts.append(line.split(". ", 1)[1])
        elif line and line[0].isdigit() and "." in line:
            back_texts.append(line.split(".", 1)[1].strip())
    if len(back_texts) >= len(srcs) // 2:
        back_texts = back_texts[: len(srcs)]
        from sacrebleu.metrics import CHRF
        chrf = CHRF()
        raw = chrf.corpus_score(back_texts, [srcs]).score  # 0〜100
        chrf_score = round(raw / 100, 4)
        print(f"  chrf_score (back-translation): {chrf_score}")

    return xcomet_score, chrf_score


def save_experiment_record(
    translated: list[dict],
    video_path: Path,
    xcomet_score: float | None = None,
    chrf_score: float | None = None,
    notes: str = "",
) -> None:
    """実験結果をexperimentsフォルダに保存する。"""
    EXPERIMENTS_DIR.mkdir(exist_ok=True)

    today = date.today().strftime("%Y%m%d")
    model_slug = GEMINI_MODEL.replace("-", "_").replace(".", "")
    json_name = f"{today}_{model_slug}_{TRANSLATION_DOMAIN}.json"
    json_path = EXPERIMENTS_DIR / json_name

    auto_notes = (
        f"{video_path.name} を処理。{len(translated)} セグメント翻訳。"
        + (f" {notes}" if notes else "")
    )

    record = {
        "date": date.today().strftime("%Y-%m-%d"),
        "model": GEMINI_MODEL,
        "domain": TRANSLATION_DOMAIN,
        "xcomet_score": xcomet_score,
        "chrf_score": chrf_score,
        "notes": auto_notes,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"実験記録を保存: {json_path}")

    csv_path = EXPERIMENTS_DIR / "results.csv"
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["date", "model", "domain", "xcomet_score", "chrf_score", "notes"])
        writer.writerow([
            record["date"],
            record["model"],
            record["domain"],
            "" if xcomet_score is None else xcomet_score,
            "" if chrf_score is None else chrf_score,
            record["notes"],
        ])
    print(f"results.csv を更新: {csv_path}")


def extract_audio(video_path: str, audio_path: str) -> None:
    """動画から音声をWAV形式で抽出する。"""
    print(f"音声を抽出中: {video_path}")
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            audio_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg音声抽出に失敗しました:\n{result.stderr}")
    print("音声抽出完了")


def transcribe_audio(audio_path: str) -> list[dict]:
    """Deepgramで音声を文字起こしし、utterancesリストを返す。"""
    from deepgram import DeepgramClient

    print("Deepgramで文字起こし中...")
    client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    response = client.listen.v1.media.transcribe_file(
        request=audio_data,
        model="nova-2-general",
        language=SOURCE_LANGUAGE,
        smart_format=True,
        punctuate=True,
        utterances=True,
        utt_split=0.8,
    )

    utterances = getattr(response.results, "utterances", None) or []

    if not utterances:
        # フォールバック: channelsからwordsを取得してセグメント化
        channels = getattr(response.results, "channels", None) or []
        if not channels:
            raise RuntimeError("文字起こし結果が空です")

        words = channels[0].alternatives[0].words or []
        utterances = group_words_into_segments(
            [{"word": w.word, "start": w.start, "end": w.end} for w in words]
        )
        print(f"文字起こし完了（wordsから生成）: {len(utterances)} セグメント")
        return utterances

    result = [
        {
            "start": u.start,
            "end": u.end,
            "transcript": u.transcript,
        }
        for u in utterances
        if u.transcript
    ]
    print(f"文字起こし完了: {len(result)} セグメント")
    return result


def group_words_into_segments(
    words: list[dict],
    max_words: int = 12,
    max_duration: float = 5.0,
) -> list[dict]:
    """単語リストを字幕セグメントにグループ化する。"""
    if not words:
        return []

    segments = []
    current_words = []
    seg_start = words[0]["start"]

    for idx, word in enumerate(words):
        current_words.append(word)
        duration = word["end"] - seg_start

        if len(current_words) >= max_words or duration >= max_duration:
            text = " ".join(w["word"] for w in current_words)
            segments.append({
                "start": seg_start,
                "end": word["end"],
                "transcript": text,
            })
            current_words = []
            if idx + 1 < len(words):
                seg_start = words[idx + 1]["start"]

    if current_words:
        text = " ".join(w["word"] for w in current_words)
        segments.append({
            "start": seg_start,
            "end": current_words[-1]["end"],
            "transcript": text,
        })

    return segments


async def translate_segments(utterances: list[dict]) -> list[dict]:
    """Geminiで各セグメントを日本語に翻訳する。"""
    from google import genai
    from google.genai import types

    print("Geminiで日本語翻訳中...")
    client = genai.Client(api_key=GOOGLE_API_KEY)

    translated = []
    total = len(utterances)

    batch_size = 10
    for i in range(0, total, batch_size):
        batch = utterances[i : i + batch_size]
        texts = [u["transcript"] for u in batch]

        numbered = "\n".join(f"{j+1}. {t}" for j, t in enumerate(texts))
        prompt = (
            "あなたはプロの翻訳者です。"
            "以下の英語テキストをそれぞれ自然な日本語に翻訳してください。"
            "字幕として表示されるため、簡潔で読みやすい文にしてください。"
            "番号付きリストで返してください（例: 1. 翻訳文）。説明や原文は含めないでください。\n\n"
            f"{numbered}"
        )

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw_text = response.text if response.text else ""
        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]

        ja_texts = []
        for line in lines:
            if line and line[0].isdigit() and ". " in line:
                ja_texts.append(line.split(". ", 1)[1])
            elif line and line[0].isdigit() and "." in line:
                ja_texts.append(line.split(".", 1)[1].strip())
            else:
                ja_texts.append(line)

        # 不足分は原文で補完
        while len(ja_texts) < len(batch):
            ja_texts.append(batch[len(ja_texts)]["transcript"])

        for u, ja in zip(batch, ja_texts):
            translated.append({
                "start": u["start"],
                "end": u["end"],
                "original": u["transcript"],
                "japanese": ja,
            })

        print(f"  翻訳済み: {min(i + batch_size, total)}/{total}")

    print("翻訳完了")
    return translated


def seconds_to_srt_time(seconds: float) -> str:
    """秒数をSRT時間形式（HH:MM:SS,mmm）に変換する。"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def create_srt(translated: list[dict], srt_path: str) -> None:
    """SRT字幕ファイルを生成する。"""
    print(f"SRTファイル生成中: {srt_path}")
    lines = []
    for i, seg in enumerate(translated, 1):
        start = seconds_to_srt_time(seg["start"])
        end = seconds_to_srt_time(seg["end"])
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(seg["japanese"])
        lines.append("")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("SRTファイル生成完了")


def burn_subtitles(video_path: str, srt_path: str, output_path: str) -> None:
    """ffmpegで字幕を動画に焼き込む。"""
    print(f"字幕を焼き込み中 → {output_path}")

    # Windows: パスのコロンをエスケープ（ffmpegのsubstitlesフィルタ用）
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf",
            f"subtitles='{srt_escaped}':force_style='FontName=Arial Unicode MS,FontSize=20,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Alignment=2'",
            "-c:a", "copy",
            output_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"字幕焼き込みに失敗しました:\n{result.stderr}")
    print("字幕焼き込み完了")


async def main(video_path: str) -> None:
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        print(f"エラー: ファイルが見つかりません: {video_path}")
        sys.exit(1)

    output_dir = video_path.parent
    stem = video_path.stem
    srt_path = str(output_dir / f"{stem}_ja.srt")
    output_path = str(output_dir / f"{stem}_subtitled.mp4")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name

    try:
        # 1. 音声抽出
        extract_audio(str(video_path), audio_path)

        # 2. 文字起こし
        utterances = await asyncio.to_thread(transcribe_audio, audio_path)

        if not utterances:
            print("文字起こし結果が空です。動画に音声が含まれているか確認してください。")
            sys.exit(1)

        # 3. 翻訳
        translated = await translate_segments(utterances)

        # 4. SRT生成
        create_srt(translated, srt_path)
        print(f"\nSRTファイル: {srt_path}")

        # プレビュー
        print("\n--- 字幕プレビュー（最初の5件） ---")
        for seg in translated[:5]:
            print(f"[{seconds_to_srt_time(seg['start'])}] {seg['original']}")
            print(f"  → {seg['japanese']}")
        print("---\n")

        # 5. 字幕焼き込み
        burn_subtitles(str(video_path), srt_path, output_path)

        print(f"\n完了!")
        print(f"字幕付き動画: {output_path}")
        print(f"SRTファイル:  {srt_path}")

        # 6. 自動評価スコアを計算して実験記録を保存
        xcomet_score, chrf_score = await compute_scores(translated)
        save_experiment_record(translated, video_path, xcomet_score, chrf_score)

    finally:
        if os.path.exists(audio_path):
            os.unlink(audio_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        video = r"C:\Users\yagua\OneDrive\Desktop\index.mp4"
    else:
        video = sys.argv[1]

    asyncio.run(main(video))

# CLAUDE.md - Claude Code 向け指示書

## 実験記録ルール

**翻訳精度の比較実験を行ったら必ず以下を実行すること：**

1. `/experiments/YYYYMMDD_<実験名>.json` を作成
2. `/experiments/results.csv` に1行追記（なければ新規作成）
3. `git add` してコミット

---

## experiments フォルダ構成

```
/experiments
  20260305_gemini_flash_25_particle.json
  20260305_gemini_flash_30_particle.json
  results.csv
```

---

## JSON フォーマット

```json
{
  "date": "2026-03-05",
  "model": "gemini-flash-2.5",
  "domain": "particle_physics",
  "xcomet_score": 0.87,
  "chrf_score": 0.71,
  "notes": "CKM matrixの訳が不安定。旧モデルのほうが安定していた"
}
```

### フィールド説明

| フィールド | 説明 |
|---|---|
| `date` | 実験日（YYYY-MM-DD） |
| `model` | 使用した翻訳モデル名 |
| `domain` | 翻訳ドメイン（例: particle_physics, general） |
| `xcomet_score` | 自動評価スコア（0〜1、高いほど良い）※任意 |
| `chrf_score` | 自動評価スコア（0〜1、高いほど良い）※任意 |
| `notes` | 観察メモ・問題点・改善案など |

---

## results.csv フォーマット

```csv
date,model,domain,xcomet_score,chrf_score,notes
2026-03-05,gemini-flash-2.5,particle_physics,0.87,0.71,CKM matrixの訳が不安定
```

---

## 自動評価を使わない場合

`xcomet_score` と `chrf_score` は省略可。代わりに `notes` に記述式の評価を詳しく記録すること。

例：
```json
{
  "date": "2026-03-05",
  "model": "gemini-flash-2.5",
  "domain": "particle_physics",
  "xcomet_score": null,
  "chrf_score": null,
  "notes": "専門用語の一貫性が高い。ただし受動態の処理が不自然な箇所あり。前モデルより全体的に自然。"
}
```

source_term,target_term,notes
API,API,そのまま使用
machine learning,機械学習,
deep learning,深層学習,
neural network,ニューラルネットワーク,
transformer,トランスフォーマー,モデルアーキテクチャ
fine-tuning,ファインチューニング,
inference,推論,
latency,レイテンシー,遅延
throughput,スループット,
real-time,リアルタイム,
transcription,文字起こし,
# --- ASR / 音声認識 ---
ASR,ASR,Automatic Speech Recognition
speech recognition,音声認識,
interim result,暫定結果,
is_final,is_final,Deepgramのフラグ
endpointing,エンドポイント検出,発話終了検知
utterance,発話,
diarization,話者分離,
speaker,話者,
word error rate,単語誤り率,
WER,WER,Word Error Rate
VAD,VAD,Voice Activity Detection
noise cancellation,ノイズキャンセリング,
# --- 翻訳 / MT ---
simultaneous interpretation,同時通訳,
simultaneous translation,同時翻訳,
machine translation,機械翻訳,
MT,MT,Machine Translation
NMT,NMT,Neural Machine Translation
post-editing,ポストエディット,翻訳後校正
glossary,用語集,
terminology,用語,
# --- LLM / AI モデル ---
LLM,LLM,Large Language Model
large language model,大規模言語モデル,
GPT,GPT,そのまま使用
ChatGPT,ChatGPT,製品名
Gemini,Gemini,Googleのモデル名
Claude,Claude,Anthropicのモデル名
prompt,プロンプト,
context window,コンテキストウィンドウ,
token,トークン,
hallucination,ハルシネーション,幻覚・誤生成
structured output,構造化出力,
temperature,温度パラメータ,LLMのサンプリングパラメータ
embeddings,埋め込み,
RAG,RAG,Retrieval-Augmented Generation
vector search,ベクター検索,
# --- クラウド / インフラ ---
WebSocket,WebSocket,
REST,REST,
HTTP,HTTP,
SDK,SDK,Software Development Kit
Docker,Docker,
container,コンテナ,
pipeline,パイプライン,
queue,キュー,
async,非同期,
stream,ストリーム,
streaming,ストリーミング,
cache,キャッシュ,
context caching,コンテキストキャッシング,Geminiのキャッシュ機能
# --- Zoom / 会議 ---
Zoom,Zoom,製品名
RTMS,RTMS,Real-Time Media Streams
webinar,ウェビナー,
meeting,ミーティング,
host,ホスト,
attendee,参加者,
caption,字幕,
subtitle,字幕,
breakout room,ブレイクアウトルーム,
# --- ソフトウェア開発 ---
repository,リポジトリ,
pull request,プルリクエスト,
PR,PR,Pull Request
commit,コミット,
branch,ブランチ,
merge,マージ,
deployment,デプロイメント,
CI/CD,CI/CD,
unit test,ユニットテスト,
integration test,統合テスト,
refactoring,リファクタリング,
debugging,デバッグ,
bug,バグ,
feature,フィーチャー,機能
release,リリース,
# --- ビジネス / 会議全般 ---
agenda,アジェンダ,議題
action item,アクションアイテム,
deadline,デッドライン,締め切り
stakeholder,ステークホルダー,
ROI,ROI,Return on Investment
KPI,KPI,Key Performance Indicator
OKR,OKR,Objectives and Key Results
roadmap,ロードマップ,
milestone,マイルストーン,
demo,デモ,
prototype,プロトタイプ,
use case,ユースケース,
feedback,フィードバック,
# --- AI / 生成AI ---
generative AI,生成AI,
foundation model,基盤モデル,
pre-training,事前学習,
instruction tuning,インストラクションチューニング,
RLHF,RLHF,Reinforcement Learning from Human Feedback
alignment,アライメント,AIの価値整合
agent,エージェント,
agentic,エージェンティック,
multi-agent,マルチエージェント,
tool use,ツール使用,LLMがツールを呼び出す機能
function calling,ファンクションコーリング,
system prompt,システムプロンプト,
few-shot,フューショット,
zero-shot,ゼロショット,
chain-of-thought,思考の連鎖,
CoT,CoT,Chain-of-Thought
multimodal,マルチモーダル,
vision,ビジョン,画像認識能力
text-to-image,テキストから画像生成,
image generation,画像生成,
diffusion model,拡散モデル,
GAN,GAN,Generative Adversarial Network
attention mechanism,アテンション機構,
self-attention,自己注意機構,
positional encoding,位置エンコーディング,
softmax,ソフトマックス,
loss function,損失関数,
gradient descent,勾配降下法,
backpropagation,誤差逆伝播,
overfitting,過学習,
underfitting,未学習,
regularization,正則化,
dropout,ドロップアウト,
batch normalization,バッチ正規化,
epoch,エポック,
batch size,バッチサイズ,
learning rate,学習率,
optimizer,オプティマイザ,
Adam,Adam,最適化アルゴリズム
benchmark,ベンチマーク,
evaluation,評価,
accuracy,精度,
precision,適合率,
recall,再現率,
F1 score,F1スコア,
BLEU,BLEU,翻訳評価指標
perplexity,パープレキシティ,
# --- AI インフラ / MLOps ---
MLOps,MLOps,Machine Learning Operations
model serving,モデルサービング,
model registry,モデルレジストリ,
feature store,特徴量ストア,
data pipeline,データパイプライン,
data preprocessing,データ前処理,
dataset,データセット,
annotation,アノテーション,
labeling,ラベリング,
GPU,GPU,Graphics Processing Unit
TPU,TPU,Tensor Processing Unit
VRAM,VRAM,ビデオメモリ
quantization,量子化,モデル軽量化
pruning,プルーニング,モデル枝刈り
distillation,蒸留,知識蒸留
ONNX,ONNX,Open Neural Network Exchange
TensorFlow,TensorFlow,Googleのフレームワーク
PyTorch,PyTorch,Metaのフレームワーク
Hugging Face,Hugging Face,AIモデルプラットフォーム
LangChain,LangChain,LLMフレームワーク
vector database,ベクターデータベース,
Pinecone,Pinecone,ベクターDB製品名
Weaviate,Weaviate,ベクターDB製品名
# --- クラウド / プラットフォーム ---
AWS,AWS,Amazon Web Services
GCP,GCP,Google Cloud Platform
Azure,Azure,Microsoft Azure
Kubernetes,Kubernetes,
k8s,k8s,Kubernetesの略称
serverless,サーバーレス,
microservices,マイクロサービス,
load balancer,ロードバランサー,
auto scaling,オートスケーリング,
CDN,CDN,Content Delivery Network
VPC,VPC,Virtual Private Cloud
IAM,IAM,Identity and Access Management
S3,S3,Amazon S3ストレージ
Cloud Storage,Cloud Storage,GCSストレージ
Pub/Sub,Pub/Sub,メッセージングサービス
Kafka,Kafka,分散メッセージキュー
Redis,Redis,インメモリDB
PostgreSQL,PostgreSQL,
MongoDB,MongoDB,
# --- ネットワーク / セキュリティ ---
TLS,TLS,Transport Layer Security
SSL,SSL,Secure Sockets Layer
OAuth,OAuth,認証プロトコル
JWT,JWT,JSON Web Token
firewall,ファイアウォール,
VPN,VPN,Virtual Private Network
endpoint,エンドポイント,
webhook,ウェブフック,
# --- ソフトウェア開発（追加） ---
open source,オープンソース,
version control,バージョン管理,
Git,Git,バージョン管理ツール
GitHub,GitHub,コードホスティング
monorepo,モノレポ,
microservice,マイクロサービス,
middleware,ミドルウェア,
ORM,ORM,Object-Relational Mapping
GraphQL,GraphQL,クエリ言語
gRPC,gRPC,RPCフレームワーク
observability,オブザーバビリティ,
logging,ロギング,
monitoring,モニタリング,
alerting,アラーティング,
SLA,SLA,Service Level Agreement
SLO,SLO,Service Level Objective
# --- データ分析 ---
data analysis,データ分析,
data science,データサイエンス,
data engineer,データエンジニア,
data analyst,データアナリスト,
exploratory data analysis,探索的データ分析,
EDA,EDA,Exploratory Data Analysis
data cleaning,データクレンジング,
data wrangling,データラングリング,
data transformation,データ変換,
missing value,欠損値,
outlier,外れ値,
normalization,正規化,
standardization,標準化,
feature engineering,特徴量エンジニアリング,
feature selection,特徴量選択,
dimensionality reduction,次元削減,
PCA,PCA,主成分分析
clustering,クラスタリング,
classification,分類,
regression,回帰,
time series,時系列,
forecasting,予測,
anomaly detection,異常検知,
correlation,相関,
causality,因果関係,
statistical significance,統計的有意性,
p-value,p値,
hypothesis testing,仮説検定,
confidence interval,信頼区間,
A/B test,A/Bテスト,
cohort analysis,コホート分析,
funnel analysis,ファネル分析,
retention,リテンション,継続率
churn,チャーン,解約率
conversion rate,コンバージョン率,
# --- データ基盤 ---
data warehouse,データウェアハウス,
data lake,データレイク,
data lakehouse,データレイクハウス,
data mart,データマート,
ETL,ETL,Extract Transform Load
ELT,ELT,Extract Load Transform
batch processing,バッチ処理,
stream processing,ストリーム処理,
real-time analytics,リアルタイム分析,
schema,スキーマ,
partition,パーティション,
index,インデックス,
query,クエリ,
SQL,SQL,
BigQuery,BigQuery,Google BigQuery
Snowflake,Snowflake,データウェアハウス製品名
Redshift,Redshift,Amazon Redshift
dbt,dbt,データ変換ツール
Airflow,Airflow,ワークフロー管理ツール
Spark,Spark,Apache Spark
Pandas,Pandas,Pythonデータ分析ライブラリ
NumPy,NumPy,Python数値計算ライブラリ
Matplotlib,Matplotlib,Python可視化ライブラリ
Jupyter,Jupyter,対話型開発環境
notebook,ノートブック,Jupyter Notebook
# --- 可視化 / BI ---
dashboard,ダッシュボード,
visualization,可視化,
BI,BI,Business Intelligence
Tableau,Tableau,BIツール製品名
Looker,Looker,BIツール製品名
Power BI,Power BI,Microsoft BIツール
chart,チャート,
graph,グラフ,
heatmap,ヒートマップ,
scatter plot,散布図,
histogram,ヒストグラム,
KPI dashboard,KPIダッシュボード,

"""Test translation pipeline with an audio file."""

import asyncio
import os
import subprocess
import sys

from real_time_translation.audio.capture import QueueAudioCapture
from real_time_translation.config import Config
from real_time_translation.pipeline import TranslationPipeline


FFMPEG_FALLBACK = (
    r"C:\Users\yagua\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
)


def _find_ffmpeg() -> str:
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    if os.path.isfile(FFMPEG_FALLBACK):
        return FFMPEG_FALLBACK
    raise FileNotFoundError("ffmpeg not found. Install it or add it to PATH.")


def convert_to_pcm(audio_path: str) -> bytes:
    """Convert any audio file to 16kHz mono PCM using ffmpeg."""
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    print(f"Converting {audio_path} to 16kHz mono PCM...")

    ffmpeg = _find_ffmpeg()
    cmd = [
        ffmpeg,
        "-loglevel", "error",
        "-i", audio_path,
        "-f", "s16le",      # 16-bit signed little-endian PCM
        "-ar", "16000",     # 16kHz sample rate
        "-ac", "1",         # mono
        "-acodec", "pcm_s16le",
        "pipe:1",           # output to stdout
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        print(f"ffmpeg error: {result.stderr.decode()}")
        raise RuntimeError("Failed to convert audio file")

    return result.stdout


def seconds_to_srt(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt(subtitles: list, srt_path: str) -> None:
    """Generate an SRT subtitle file from (start, end, text) list."""
    # Adjust end times: minimum display 1.5s, no overlap with next
    adjusted = []
    for i, (start, end, text) in enumerate(subtitles):
        min_end = start + 1.5
        end = max(end, min_end)
        # Trim if overlapping with next subtitle
        if i + 1 < len(subtitles):
            next_start = subtitles[i + 1][0]
            end = min(end, next_start - 0.05)
            end = max(end, start + 0.5)
        adjusted.append((start, end, text))

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(adjusted, 1):
            f.write(f"{i}\n")
            f.write(f"{seconds_to_srt(start)} --> {seconds_to_srt(end)}\n")
            f.write(f"{text}\n\n")

    print(f"SRTファイル保存: {srt_path}")


def burn_subtitles(input_mp4: str, srt_path: str, output_mp4: str) -> None:
    """Burn SRT subtitles into MP4 using ffmpeg."""
    srt_dir = os.path.dirname(os.path.abspath(srt_path))
    srt_name = os.path.basename(srt_path)

    ffmpeg = _find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-i", input_mp4,
        "-vf", (
            f"subtitles={srt_name}:"
            "force_style='FontName=Meiryo,FontSize=22,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=2,Shadow=1,Alignment=2'"
        ),
        "-c:a", "copy",
        output_mp4,
    ]

    print(f"字幕を動画に焼き込み中...")
    result = subprocess.run(cmd, capture_output=True, check=False, cwd=srt_dir)

    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")
        print(f"ffmpeg error: {err}")
        raise RuntimeError("Failed to burn subtitles into video")

    print(f"字幕付き動画を保存しました: {output_mp4}")


async def test_with_audio_file(audio_path: str) -> None:
    """Test the translation pipeline with an audio file (WAV, FLAC, MP3, MP4, etc.)."""
    config = Config.from_env(require_zoom=False)
    capture = QueueAudioCapture(max_queue_size=500)  # Large queue for file processing
    pipeline = TranslationPipeline(config=config, audio_capture=capture)

    result_count = [0]  # Use list to allow modification in nested function
    all_asr = []  # Final ASR results
    all_translations = []
    all_subtitles = []  # (start_time, end_time, translated_text)
    latest_interim = [""]  # Track latest interim for full ASR capture

    def on_result(result):
        # Track all interim results for full ASR
        if not result.is_final:
            latest_interim[0] = result.original_text
            return

        # Final result
        if result.translated_text:
            result_count[0] += 1
            all_asr.append(result.original_text)
            all_translations.append(result.translated_text)
            all_subtitles.append((result.start_time, result.end_time, result.translated_text))
            print(f"\n[{result_count[0]}] {'='*46}")
            print(f"ASR: {result.original_text}")
            print(f"翻訳: {result.translated_text}")
            if result.kept_terms:
                print(f"保持用語: {', '.join(result.kept_terms)}")
            print(f"{'='*50}\n")
            # Reset interim after final
            latest_interim[0] = ""
        else:
            # Final without translation - just track ASR
            all_asr.append(result.original_text)
            latest_interim[0] = ""

    pipeline.set_callback(on_result)

    print(f"Loading audio file: {audio_path}")

    # Convert to PCM using ffmpeg (supports WAV, FLAC, MP3, MP4, etc.)
    audio_data = convert_to_pcm(audio_path)

    sample_rate = 16000
    duration = len(audio_data) / (sample_rate * 2)  # 2 bytes per sample
    print(f"Duration: {duration:.2f} seconds")

    print("\nStarting pipeline...")
    await pipeline.start()

    try:
        # Send audio in chunks (simulating real-time streaming)
        chunk_size = 16000 * 2  # 1 second of 16kHz 16-bit audio
        total_chunks = len(audio_data) // chunk_size

        print(f"Sending {total_chunks} chunks...")

        for i, offset in enumerate(range(0, len(audio_data), chunk_size)):
            chunk = audio_data[offset : offset + chunk_size]
            capture.push_audio(chunk)
            await asyncio.sleep(1.0)  # Real-time pace for Deepgram

            # Show progress
            if (i + 1) % 10 == 0 or i == total_chunks - 1:
                progress = int((i + 1) / total_chunks * 100)
                print(f"Sending: {progress}% ({i + 1}/{total_chunks}) - ASR: {len(all_asr)}, Trans: {result_count[0]}")

        # Give Deepgram time to process last chunks
        print(f"\nAll audio sent. Waiting 10 seconds for Deepgram to catch up...")
        await asyncio.sleep(10)

        print("Waiting for remaining ASR and translations...")
        last_asr_count = len(all_asr)
        last_trans_count = result_count[0]
        stable_seconds = 0
        max_wait = 180  # Maximum 3 minutes

        for i in range(max_wait):
            await asyncio.sleep(1)
            current_asr = len(all_asr)
            current_trans = result_count[0]

            if current_asr == last_asr_count and current_trans == last_trans_count:
                stable_seconds += 1
            else:
                stable_seconds = 0
                last_asr_count = current_asr
                last_trans_count = current_trans

            if (i + 1) % 10 == 0:
                print(f"  Waiting... {i + 1}s - ASR segments: {len(all_asr)}, Translations: {result_count[0]}")

            # Stop if no new results for 20 seconds
            if stable_seconds >= 20:
                print(f"  No new results for 20 seconds, finishing...")
                break
    finally:
        await pipeline.stop()

    # Print summary
    print(f"\n{'='*60}")
    print(f"完了！合計 {result_count[0]} 件の翻訳を出力しました。")
    print(f"{'='*60}")

    # Print full ASR text (from finals)
    print(f"\n{'='*60}")
    print("【全文 ASR (確定分)】")
    print('='*60)
    full_asr = " ".join(all_asr)
    print(full_asr)

    # If there's remaining interim content, show it
    if latest_interim[0]:
        print(f"\n{'='*60}")
        print("【未確定の中間結果】")
        print('='*60)
        print(latest_interim[0])

    # Print full translation
    print(f"\n{'='*60}")
    print("【全文 翻訳】")
    print('='*60)
    print("".join(all_translations))

    # Generate SRT and burn subtitles into video
    if all_subtitles:
        input_dir = os.path.dirname(os.path.abspath(audio_path))
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        srt_path = os.path.join(input_dir, f"{base_name}_ja.srt")
        output_mp4 = os.path.join(input_dir, f"{base_name}_ja.mp4")

        print(f"\n{'='*60}")
        print("【字幕付き動画を生成中】")
        print('='*60)
        generate_srt(all_subtitles, srt_path)
        burn_subtitles(audio_path, srt_path, output_mp4)
    else:
        print("\n翻訳結果がないため、字幕付き動画は生成されませんでした。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python test_audio_file.py <audio_file>")
        print("\nSupported formats: WAV, FLAC, MP3, MP4, etc. (anything ffmpeg supports)")
        print("\nExample:")
        print("  uv run python test_audio_file.py video.mp4")
        sys.exit(1)

    asyncio.run(test_with_audio_file(sys.argv[1]))

services:
  nms:
    image: illuspas/node-media-server:2.7.5
    ports:
      - "1935:1935"
      - "8000:8000"
      - "8443:8443"

  ngrok:
    image: ngrok/ngrok:latest
    command: tcp nms:1935
    env_file: .env
    environment:
      - NGROK_AUTHTOKEN=${NGROK_AUTHTOKEN}
    ports:
      - "4040:4040"
    depends_on:
      - nms

  ws:
    build: ./services/ws
    ports:
      - "8001:8000"
    env_file: .env

  gemini:
    build: ./services/translator
    env_file: .env
    environment:
      - WS_PUBLISH_URL=http://ws:8000/publish
      - ZOOM_CAPTION_URL=${ZOOM_CAPTION_URL:-}
      - ZOOM_CAPTION_LANG=${ZOOM_CAPTION_LANG:-}
    depends_on:
      - ws

  deepgram:
    build: ./services/asr
    env_file: .env
    environment:
      - RTMP_URL=rtmp://nms:1935/live/zoom
      - WS_PUBLISH_URL=http://ws:8000/publish
      - TRANSLATION_API_URL=http://gemini:8000/translate
      - DICTIONARY_PATH=/app/no_dictionary.csv
    depends_on:
      - nms
      - gemini
      - ws

  ws-debug:
    image: python:3.12-slim
    profiles:
      - debug
    environment:
      - PYTHONUNBUFFERED=1
    volumes:
      - ./scripts:/scripts
    command: sh -c "pip install -q websockets && python /scripts/ws_debug.py"
    depends_on:
      - ws

source_term,target_term,notes
API,API,そのまま使用
machine learning,機械学習,
deep learning,深層学習,
neural network,ニューラルネットワーク,
transformer,トランスフォーマー,モデルアーキテクチャ
fine-tuning,ファインチューニング,
inference,推論,
latency,レイテンシー,遅延
throughput,スループット,
real-time,リアルタイム,
transcription,文字起こし,

"""Test ASR and translation accuracy with a full file (non-streaming)."""

import asyncio
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from deepgram import DeepgramClient
from dotenv import load_dotenv
import os

from real_time_translation.translation.llm_translator import LLMTranslator

logger = logging.getLogger(__name__)


@dataclass
class CombinedResult:
    """Combined translation result from multiple chunks."""
    latest_slide: str
    kept_terms: list


async def test_accuracy(audio_path: str) -> None:
    """Test ASR and translation accuracy with a full audio file."""
    load_dotenv()

    # Get API keys from environment
    deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")
    if not deepgram_api_key:
        print("Error: DEEPGRAM_API_KEY not set in .env")
        return

    llm_provider = os.getenv("LLM_PROVIDER", "gemini")
    if llm_provider == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY")
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        print(f"Error: API key for {llm_provider} not set in .env")
        return

    print(f"Audio file: {audio_path}")
    print(f"LLM Provider: {llm_provider}")
    print(f"Model: {model}")
    print("=" * 60)

    # Step 1: Transcribe with Deepgram Pre-recorded API
    print("\n[1/2] Transcribing with Deepgram...")

    deepgram = DeepgramClient(api_key=deepgram_api_key)

    # Read audio file
    file_path = Path(audio_path)
    with open(audio_path, "rb") as audio_file:
        audio_data = audio_file.read()

    print(f"  File size: {len(audio_data):,} bytes")

    # Detect encoding based on extension
    ext = file_path.suffix.lower()
    encoding_map = {
        ".flac": "flac",
        ".wav": "linear16",
        ".mp3": None,  # Auto-detect
        ".m4a": None,
        ".ogg": "opus",
    }
    encoding = encoding_map.get(ext)
    print(f"  Encoding: {encoding or 'auto-detect'}")

    # Use the new SDK API - transcribe_file with keyword arguments
    # paragraphs=True gives better structure for longer audio
    # keyterm helps with domain-specific vocabulary
    keyterms = [
        "reinforcement learning",
        "offline reinforcement learning",
        "Markov decision process",
        "MDP",
        "five element tuple",
        "tuple",
        "world model",
        "reward model",
        "reward function",
        "transition function",
        "behavior policy",
        "supervised learning",
        "RL",
        "gamma",
        "discounted factor",
        "trajectory dataset",
    ]
    response = deepgram.listen.v1.media.transcribe_file(
        request=audio_data,
        model="nova-3-general",
        language="en",
        smart_format=True,
        punctuate=True,
        paragraphs=True,
        encoding=encoding,
        keyterm=keyterms,
    )

    # Debug info
    metadata = response.metadata
    print(f"  Duration: {metadata.duration:.2f} seconds")
    print(f"  Channels: {metadata.channels}")

    # Extract transcript
    channel = response.results.channels[0]
    alternative = channel.alternatives[0]
    transcript = alternative.transcript
    confidence = alternative.confidence

    print(f"  Confidence: {confidence:.2%}")
    print(f"  Words detected: {len(alternative.words)}")

    print("\n" + "=" * 60)
    print("【ASR結果 (Deepgram)】")
    print("=" * 60)
    print(transcript)

    # Step 2: Translate with LLM
    print("\n" + "=" * 60)
    print("[2/2] Translating with LLM...")
    print("=" * 60)

    logger.debug("Transcript length: %d chars, %d words", len(transcript), len(transcript.split()))

    translator = LLMTranslator(
        provider=llm_provider,
        api_key=api_key,
        model=model,
        source_language="English",
        target_language="Japanese",
    )

    await translator.prepare()

    # Split long text into sentences and translate in chunks
    # This prevents truncation issues with long texts
    sentences = re.split(r'(?<=[.!?])\s+', transcript)
    logger.debug("Split into %d sentences", len(sentences))

    all_translations = []
    all_kept_terms = []
    chunk_size = 3  # Translate 3 sentences at a time

    for i in range(0, len(sentences), chunk_size):
        chunk = " ".join(sentences[i:i + chunk_size])
        chunk_num = i // chunk_size + 1
        total_chunks = (len(sentences) + chunk_size - 1) // chunk_size
        logger.debug("Translating chunk %d/%d (%d chars)", chunk_num, total_chunks, len(chunk))

        try:
            chunk_result = await asyncio.wait_for(translator.translate(chunk), timeout=60.0)
            all_translations.append(chunk_result.latest_slide)
            all_kept_terms.extend(chunk_result.kept_terms)
        except asyncio.TimeoutError:
            logger.error("Chunk %d timed out!", chunk_num)
            all_translations.append(f"[翻訳タイムアウト: {chunk[:50]}...]")

    # Combine results
    result = CombinedResult(
        latest_slide="\n".join(all_translations),
        kept_terms=list(set(all_kept_terms))
    )

    print("\n" + "=" * 60)
    print("【翻訳結果】")
    print("=" * 60)
    print(result.latest_slide)

    if result.kept_terms:
        print(f"\n保持用語: {', '.join(result.kept_terms)}")

    print("\n" + "=" * 60)
    print("完了!")
    print("=" * 60)

    # Save results to file
    output_file = Path(audio_path).stem + "_results.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"Audio file: {audio_path}\n")
        f.write(f"Duration: {metadata.duration:.2f} seconds\n")
        f.write(f"Confidence: {confidence:.2%}\n")
        f.write(f"Words detected: {len(alternative.words)}\n")
        f.write("\n" + "=" * 60 + "\n")
        f.write("【ASR結果 (Deepgram)】\n")
        f.write("=" * 60 + "\n")
        f.write(transcript + "\n")
        f.write("\n" + "=" * 60 + "\n")
        f.write("【翻訳結果】\n")
        f.write("=" * 60 + "\n")
        f.write(result.latest_slide + "\n")
        if result.kept_terms:
            f.write(f"\n保持用語: {', '.join(result.kept_terms)}\n")
    print(f"\n結果を保存しました: {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python test_asr_accuracy.py <audio_file>")
        print("\nSupported formats: WAV, FLAC, MP3, etc.")
        print("\nExample:")
        print("  uv run python test_asr_accuracy.py clip_386-464.flac")
        sys.exit(1)

    asyncio.run(test_accuracy(sys.argv[1]))

# Real-time Translation Environment Variables

# Zoom RTMS Credentials (required)
ZOOM_CLIENT_ID=your_zoom_client_id
ZOOM_CLIENT_SECRET=your_zoom_client_secret
ZOOM_WEBHOOK_PORT=8080
ZOOM_WEBHOOK_PATH=/webhook

# Deepgram API Key (required)
DEEPGRAM_API_KEY=your_deepgram_api_key
DEEPGRAM_MODEL=nova-3-general
DEEPGRAM_ENDPOINTING=500
DEEPGRAM_UTTERANCE_END_MS=1000
DEEPGRAM_INTERIM_RESULTS=true
DEEPGRAM_SMART_FORMAT=true
# DEEPGRAM_VAD_EVENTS=false

# LLM Provider: "gemini" or "openai"
LLM_PROVIDER=gemini

# Google AI API Key (required if LLM_PROVIDER=gemini)
GOOGLE_API_KEY=your_google_api_key

# OpenAI API Key (required if LLM_PROVIDER=openai)
# OPENAI_API_KEY=your_openai_api_key

# Model settings (optional)
GEMINI_MODEL=gemini-3-flash-preview
OPENAI_MODEL=gpt-4o-mini

# Translation settings
SOURCE_LANGUAGE=en
TARGET_LANGUAGE=ja
CONTEXT_WINDOW_SIZE=3
TRANSLATION_QUEUE_SIZE=10

# Dictionary (optional) - CSV file with domain-specific terminology
# Format: source_term,target_term,notes
DICTIONARY_PATH=dictionary.csv

# RTMP / ffmpeg settings (microservices)
RTMP_URL=rtmp://nms:1935/live/zoom
FFMPEG_CHUNK_MS=20
FFMPEG_SAMPLE_RATE=16000
FFMPEG_CHANNELS=1

# WebSocket + translation service settings (microservices)
WS_PUBLISH_URL=http://ws:8000/publish
TRANSLATION_API_URL=http://gemini:8000/translate
ASR_SEND_INTERIM=true
TRANSLATE_INTERIM=false
ASR_PARTIAL_MIN_INTERVAL_MS=200
TRANSLATION_CONCURRENCY=2
HTTP_TIMEOUT=10

# Ngrok authentication token - get it from https://dashboard.ngrok.com/get-started/your-authtoken
NGROK_AUTHTOKEN=your_ngrok_authtoken_here

# Zoom Closed Caption (optional) - Get the caption URL from Zoom meeting
# See: https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060372
# ZOOM_CAPTION_URL=https://wmcc.zoom.us/closedcaption?id=...
# ZOOM_CAPTION_LANG=ja
# Python-generated files
__pycache__/
*.py[oc]
build/
dist/
wheels/
*.egg-info

# Virtual environments
.venv

# IDE
.idea/
.vscode/
*.swp
*.swo

# Test and coverage
.pytest_cache/
.coverage
htmlcov/

# uv
uv.lock

# Environment
.env

3.13

# AGENTS.md

このプロジェクトはuvを使用したPythonプロジェクト管理を行っています。

## プロジェクト構造

```
real_time_translation/
├── src/real_time_translation/   # メインパッケージ
│   ├── audio/                   # 音声取得モジュール
│   ├── transcription/           # Deepgram文字起こし
│   ├── translation/             # LangChain翻訳
│   ├── config.py                # 設定管理
│   ├── pipeline.py              # パイプライン統合
│   └── main.py                  # CLIエントリーポイント
├── tests/                       # テストファイル
├── pyproject.toml               # プロジェクト設定
└── .env.example                 # 環境変数テンプレート
```

## パッケージマネージャ: uv

```bash
# 依存関係のインストール
uv sync --extra dev

# 依存関係の追加
uv add <package-name>
uv add --dev <package-name>

# スクリプトの実行
uv run real-time-translation
uv run pytest
uv run ruff check .
```

## 主要コンポーネント

| モジュール                         | 役割                             |
| ---------------------------------- | -------------------------------- |
| `audio/capture.py`                 | Zoom RTMS SDKからの音声取得      |
| `transcription/deepgram_client.py` | Deepgram WebSocket文字起こし     |
| `translation/llm_translator.py`    | LangChain + Gemini/OpenAI翻訳    |
| `pipeline.py`                      | 音声→文字起こし→翻訳のフロー制御 |
| `config.py`                        | 環境変数からの設定読み込み       |

## コーディング規約

- **フォーマッター**: Ruff (line-length: 88)
- **リンター**: Ruff (E, F, I, UP, B, SIM)
- **型ヒント**: 必須
- **非同期**: asyncio使用

## 注意事項

- `uv.lock`は自動生成、手動編集不可
- 依存関係は`uv add`コマンドで追加
- APIキーは`.env`ファイルで管理（gitignored）

# リアルタイム同時翻訳システム アーキテクチャ設計書

## 1. 概要

本システムは、Zoom RTMSもしくはWebマイク入力をリアルタイムに文字起こしし、
文脈を加味して翻訳し、低遅延で表示するSimulSTパイプラインである。Deepgramによる
低レイテンシASRと、Gemini 3.0 Flash/OpenAIによる文脈指向翻訳を組み合わせる。

## 2. 設計目標

1. **Low Latency:** 非同期パイプラインでブロッキングを排除し、遅延を最小化する。
2. **Context Awareness:** 直近の会話履歴を参照し、断片入力でも高精度に翻訳する。
3. **Operational Simplicity:** 起動時のキャッシュ生成と明確な再生成トリガーで運用を安定化。

## 3. システム構成図 (Data Flow)

```mermaid
graph LR
    A[Audio Input<br/>Zoom RTMS / Web Mic] -->|Stream| B(Deepgram ASR)

    subgraph "Producer"
        B -->|is_final| C{Filter + Mask}
        C -->|Enqueue| D[Transcription Queue]
    end

    subgraph "Consumer"
        D -->|Dequeue| E[Prompt Builder]
        E -->|Request| F[Gemini / OpenAI]
    end

    F -->|Translation| G[UI / Frontend]
```

## 4. コンポーネント詳細設計

### 4.1 Audio Input

- **Zoom RTMS:** SDKからPCMフレームを取得し、Deepgram WebSocketへ送信。
- **Web Demo:** Gradioのマイク入力を`QueueAudioCapture`へ流し込み、同一パイプラインで処理。

### 4.2 ASR: Deepgram Settings

- **Model:** `nova-2-general` (推奨)
- **Key Parameters:**
  - `smart_format=true`: 句読点・数値整形を有効化し、翻訳精度を向上。
  - `endpointing=500`: 発話終了後500msの無音検知で `is_final` を発行。
  - `utterance_end_ms`: 意味的な発話区切り検知。UtteranceEnd受信時に直近interimを確定。
  - `interim_results=true`: UI向けの体感速度改善に利用するが、翻訳トリガーには使わない。

### 4.3 MT Strategy: Contextual Sliding Window

- **Trigger:** `is_final: true` のみを翻訳対象とする。
- **Prompt Structure:** `<context>` と `<target>` を分離し、文脈と翻訳対象を明示。
- **Sliding Window:**
  - 直近 `N` 文（デフォルト3）をFIFOバッファで保持。
  - 翻訳後にバッファへ現在文を追加する（自己参照を回避）。
- **曖昧語/固有名詞:**
  - 人名・組織名・製品名・地名・略語・コード識別子、または曖昧/未知語は「そのまま残す」。

### 4.4 MT Engine: Gemini 3.0 Flash / OpenAI

- **Gemini (Context Caching必須):**
  - システムプロンプト + 辞書をContext Cacheへ登録。
  - 翻訳リクエストはキャッシュ参照 + `<context>` `<target>` を送信。
  - 辞書更新時はキャッシュを破棄・再生成。
- **Structured Output:**
  - LangChainのStructured Outputで `latest_slide`（最新の翻訳結果）と `kept_terms`
    （固有名詞/曖昧語として保持した語）を返す。
- **OpenAI:**
  - LangChain経由でシステムプロンプトを送信（キャッシュは不要）。

### 4.5 キュー/バックプレッシャー

- 翻訳処理はASR受信ループから独立したConsumerタスクで実行。
- `translation_queue_size` を超過した場合は古い文を破棄し、最新文優先。

## 5. 実装ロジック (Python Asyncio)

```python
async def start():
    await translator.prepare()  # Gemini cache作成
    await transcriber.connect()
    await audio_capture.start()
    tasks = [
        asyncio.create_task(audio_to_transcription()),
        asyncio.create_task(collect_transcriptions()),
        asyncio.create_task(translation_worker()),
    ]

async def collect_transcriptions():
    async for result in transcriber.results():
        if not result.is_final:
            continue
        text = result.text.strip()
        if not text:
            continue
        masked = f"[uncertain: {text}]" if result.is_low_confidence else text
        if queue.full():
            queue.get_nowait()  # drop oldest
        queue.put_nowait((result, masked))

async def translation_worker():
    while True:
        result, masked = await queue.get()
        output = await translator.translate(masked)  # structured output
        emit(result.text, output.latest_slide, output.kept_terms, output.slide_window)
```

## 6. Webデモ (Gradio)

- **入力:** ブラウザのマイク音声（ストリーミング）
- **処理:** `QueueAudioCapture` → `TranslationPipeline`
- **出力:** スライドウィンド（直近N文）の文字起こし/翻訳をリアルタイム表示
- **起動:** `uv run real-time-translation-demo`

## 7. エッジケースと対策

| 事象 | 対策 |
| --- | --- |
| 無音過多 | `endpointing`が効かない場合はタイムアウト監視で手動確定。 |
| 翻訳遅延 | キュー溢れ時は古い文を破棄し、最新を優先する。 |
| 幻覚 | `<context>` `<target>` タグで文脈と翻訳対象を分離する。 |
| 辞書更新 | Context Cacheの再生成を実施し、IDを差し替える。 |

## 8. 今後の拡張性

- **RAG:** 専門用語辞書や会議録のVector検索を導入し、動的に用語注入。
- **Speaker Diarization:** 発話者情報を文脈に含め、口調の一貫性を向上。
- **代替ASR:** Aqua Voice / AssemblyAIの評価・切替を可能にする抽象化。

---

# Zoom → ASR → 翻訳 → WebSocket 字幕 配信構成まとめ

## 目的

Zoom 会議音声をリアルタイムで文字起こしし、翻訳結果を WebSocket 経由で即時配信する。
遅延最小化を最優先。

## 全体アーキテクチャ

```
Zoom
↓ RTMP
Node-Media-Server
↓ PCM (16kHz, mono)
DeepGram ASR (Python)
├─ WebSocket（ASR即時字幕）
└─ HTTP（非同期）
↓
Gemini 翻訳 (Python)
↓
WebSocket（翻訳字幕更新）
```

## コンテナ構成（docker-compose）

- nms  
  RTMP 受信専用。中継のみ。
- deepgram  
  音声を ASR。interim 結果を即時配信。
- gemini  
  翻訳専用。ステートレス API。
- ws  
  字幕配信用。FastAPI + WebSocket。

## docker-compose.yml（最終形）

```yaml
version: "3.9"

services:
  nms:
    image: illuspas/node-media-server:2.7.5
    ports:
      - "1935:1935"
      - "8000:8000"
      - "8443:8443"

  ws:
    build: ./services/ws
    ports:
      - "8000:8000"
    env_file: .env

  gemini:
    build: ./services/translator
    env_file: .env
    environment:
      - WS_PUBLISH_URL=http://ws:8000/publish
    depends_on:
      - ws

  deepgram:
    build: ./services/asr
    env_file: .env
    environment:
      - RTMP_URL=rtmp://nms:1935/live/zoom
      - WS_PUBLISH_URL=http://ws:8000/publish
      - TRANSLATION_API_URL=http://gemini:8000/translate
    depends_on:
      - nms
      - gemini
      - ws
```

## DeepGram ASR（要点）

- ffmpeg 設定
  - low delay
  - 16kHz / linear16 / mono
  - 20–40ms chunk

```bash
ffmpeg -fflags nobuffer -flags low_delay \
 -i rtmp://nms:1935/live/zoom \
 -f s16le -ar 16000 -ac 1 -
```

- DeepGram オプション
  - interim_results = true
  - endpointing = 50ms
  - vad_events = false

## Gemini 翻訳

- FastAPI HTTP API
- ASR と完全並列
- partial 文を短文で翻訳
- 翻訳完了後に字幕を更新送信

## WebSocket 字幕配信

### エンドポイント

```
ws://<host>:8000/ws/caption
```

### メッセージ形式

```json
{
  "type": "asr_partial",
  "text": "こんにちは",
  "ts": 123456
}
```

```json
{
  "type": "translation",
  "src": "こんにちは",
  "translated": "Hello"
}
```

## 遅延最小化の原則

- ASR → 翻訳を直列にしない
- interim 結果を即配信
- 翻訳は後追い更新
- WebSocket は 1 hop
- RTMP バッファを切る

## レイテンシ目安

| 区間          | 遅延        |
| ----------- | --------- |
| RTMP → PCM  | 20–40ms   |
| ASR interim | 80–150ms  |
| WebSocket   | <10ms     |
| 翻訳          | 200–400ms |

## 今後の拡張候補

- WebRTC 化（RTMP 廃止）
- Redis / Kafka による多会議スケール
- 話者分離（diarization）
- Gemini による要約・議事録生成
- 字幕 Web UI（React / Svelte）
