"""マイク入力の「話し終わり → 訳文表示」遅延を、実音声と実 API で計測する。

動画（音声）ファイルを 0.5 秒ずつ実時間のペースで `gradio_demo.handle_audio` に流し、
ブラウザのマイク入力（Gradio の stream_every=0.5 秒）と同じ経路で翻訳させる。
区間ごとの計測（`real_time_translation.latency`）を CSV に保存し、集計表を表示する。

設定は `.env` をそのまま使う（画面の Start と同じ）。ブラウザ → サーバーの転送時間は
含まれないので、実際のマイクよりわずかに短く出る。

使い方:
    python evaluation/latency_mic_sim.py clips/2d07bb74_clip1.mp4
    python evaluation/latency_mic_sim.py clips/2d07bb74_clip1.mp4 --seconds 60 \\
        --out experiments/20261029_latency_mic_sim_clip1.csv
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

load_dotenv(ROOT / ".env")

from real_time_translation import gradio_demo  # noqa: E402

CHUNK_SECONDS = 0.5
TAIL_SILENCE_SECONDS = 8.0  # 最後の文を確定・翻訳させるための無音


async def run(media: str, seconds: float | None, out: Path | None) -> None:
    pcm = gradio_demo._convert_file_to_pcm(media)
    if seconds:
        pcm = pcm[: int(seconds * 16000) * 2]
    state, status, _, _ = await gradio_demo.start_session(None)
    if state is None:
        raise SystemExit(status)

    chunk_bytes = int(16000 * CHUNK_SECONDS) * 2
    silence = np.zeros(chunk_bytes // 2, dtype=np.int16)
    chunks = [
        np.frombuffer(pcm[off : off + chunk_bytes], dtype=np.int16)
        for off in range(0, len(pcm), chunk_bytes)
    ]
    chunks += [silence] * int(TAIL_SILENCE_SECONDS / CHUNK_SECONDS)

    print(f"{len(pcm) / 32000:.1f}秒の音声を実時間で流します...")
    t0 = time.monotonic()
    for i, samples in enumerate(chunks):
        await gradio_demo.handle_audio((16000, samples), state)
        target = t0 + (i + 1) * CHUNK_SECONDS
        await asyncio.sleep(max(0.0, target - time.monotonic()))

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(state.latency.to_csv(), encoding="utf-8-sig")
        print(f"CSV: {out}")
    _, _, summary = await gradio_demo.stop_session(state, {})
    print(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("media", help="音声または動画ファイル")
    parser.add_argument("--seconds", type=float, default=None, help="先頭から何秒使うか")
    parser.add_argument("--out", type=Path, default=None, help="計測結果のCSV")
    args = parser.parse_args()
    asyncio.run(run(args.media, args.seconds, args.out))


if __name__ == "__main__":
    main()
