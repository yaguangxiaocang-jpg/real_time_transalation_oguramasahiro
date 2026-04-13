"""
Real-time Translation App Launcher
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
