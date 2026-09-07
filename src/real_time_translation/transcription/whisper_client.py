"""faster-whisperを使ったオフライン文字起こし（バッチ処理専用）。

Deepgramのようなストリーミング WebSocket API を持たないため、マイクの
リアルタイム翻訳（`pipeline.py`）には未対応。動画字幕生成（`add_subtitles.py`）や
Gradio動画タブのような、音声ファイル全体をまとめて処理するオフライン経路でのみ使う
（`DESIGN_DOC.md` の「代替ASR」拡張候補に対応）。

2026-08-11の調査で、DeepgramがGoogleの大規模言語モデル名（T5・PaLM・GPT-3等）を
誤認識するケース（例: "T5"→"TIFINE"）が確認された一方、同じ音声をfaster-whisperで
文字起こしするとほとんどのケースで正しく認識できることを確認した
（`README.md` 更新履歴 2026-08-11 参照）。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=2)
def _get_model(model_size: str) -> Any:
    """モデルをロードしてキャッシュする（同一プロセス内での再ロードを避ける）。"""
    from faster_whisper import WhisperModel

    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe_with_whisper(
    audio_path: str,
    model_size: str = "small.en",
    language: str = "en",
) -> list[dict]:
    """音声ファイルをfaster-whisperで文字起こしする。

    Deepgramの`transcribe_audio()`と同じ形式（`{"start", "end", "transcript"}`の
    リスト）を返すため、呼び出し側（`add_subtitles.py`/`gradio_demo.py`）は
    ASRプロバイダを差し替えるだけでそのまま動く。

    Args:
        audio_path: 音声ファイルパス（wav推奨）
        model_size: faster-whisperのモデルサイズ（例: "small.en", "medium"）
        language: 言語コード（"en"等）。"auto"を渡すと自動検出に任せる

    Returns:
        {"start": float, "end": float, "transcript": str} のリスト
    """
    model = _get_model(model_size)
    whisper_language = None if language == "auto" else language.split("-")[0]

    segments, _info = model.transcribe(
        audio_path,
        beam_size=5,
        language=whisper_language,
        word_timestamps=False,
    )

    result: list[dict] = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        result.append({"start": seg.start, "end": seg.end, "transcript": text})
    return result


def transcribe_pcm_with_whisper(
    pcm_audio: bytes,
    model_size: str = "small.en",
    language: str = "en",
) -> tuple[str, list[tuple[str, float]]]:
    """生PCM音声（16bit / 16kHz / mono）をfaster-whisperで文字起こしする。

    `whisper_reverify.reverify_terms` から、Deepgramの確定文と同じ音声区間を
    再文字起こしして照合するために使う（ファイル経由の`transcribe_with_whisper`
    と異なり、リアルタイム経路の音声バッファをそのまま渡せる）。

    Args:
        pcm_audio: 16bit PCM（リトルエンディアン、16kHz、mono）の生バイト列
        model_size: faster-whisperのモデルサイズ
        language: 言語コード（"en"等）。"auto"を渡すと自動検出に任せる

    Returns:
        (文字起こしされたテキスト（セグメントを結合したもの）,
         単語ごとの(単語, confidence)のリスト)。
        confidenceは`word.probability`（faster-whisperの単語レベル信頼度、
        0.0〜1.0）。`whisper_reverify.apply_term_corrections`の信頼度ガードに使う
        （2026-09-07追加、MOA/MOE誤補正対策の一環）。単語検出のため
        `word_timestamps=True`にしている点が変更前との違い。
    """
    import numpy as np

    model = _get_model(model_size)
    whisper_language = None if language == "auto" else language.split("-")[0]
    audio_array = np.frombuffer(pcm_audio, dtype=np.int16).astype(np.float32) / 32768.0

    segments, _info = model.transcribe(
        audio_array,
        beam_size=5,
        language=whisper_language,
        word_timestamps=True,
    )

    texts: list[str] = []
    words: list[tuple[str, float]] = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            texts.append(text)
        for w in seg.words or []:
            word_text = w.word.strip()
            if word_text:
                words.append((word_text, float(w.probability)))

    return " ".join(texts), words
