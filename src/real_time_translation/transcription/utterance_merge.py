"""文末で終わっていないutteranceを結合するロジック（バッチ／ストリーミング共通）。

Deepgramのutterance分割は無音区間（endpointing）の長さで決まるため、1文が
息継ぎ位置で複数utteranceに分断されることがある（例:
"in The United States. It's called the federal" / "funds rate,"）。
各utteranceを独立に翻訳するとこうした断片が文法的に不自然な訳になるため、
文末punctuationが来るまで次のutteranceと結合してから翻訳に渡す。

このモジュールは動画字幕（add_subtitles.py、バッチ処理）とマイクの
リアルタイム翻訳（pipeline.py、ストリーミング処理）の両方から使われる。
アルゴリズムを共有することで、2経路の翻訳精度を同じ条件で比較できる。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from real_time_translation.config import Config
    from real_time_translation.translation.usage_tracking import UsageSink

SENTENCE_END_RE = re.compile(r"[.!?][\"'”\)\]]*$")

DEFAULT_MAX_DURATION = 20.0
DEFAULT_MAX_WORDS = 60


def _merge_with_predicate(
    utterances: list[dict],
    max_duration: float,
    max_words: int,
    is_incomplete: Callable[[int, str], bool],
) -> list[dict]:
    """「このutteranceの末尾は不完全か」を判定する関数 `is_incomplete(index, text)`
    を受け取り、不完全な間は次のutteranceと結合し続ける共通ループ。

    `index` には「現在のバッファに最後に merge された元のutteranceのインデックス」
    を渡す（バッファの先頭インデックスではない）。正規表現版は末尾の文字列しか
    見ないため、これはバッファ全体の文字列を都度チェックするのと同じ結果になる。
    LLM版は元のutterance単位で事前にバッチ判定した結果を使うため、
    「直近マージされた元utteranceの判定」を引き継ぐ必要がある。

    `merge_incomplete_utterances`（正規表現版）と
    `merge_incomplete_utterances_with_detector`（LLM版）の両方から使われる。
    """
    if not utterances:
        return utterances

    merged: list[dict] = []
    buf = dict(utterances[0])
    last_idx = 0

    for nxt_idx, nxt in enumerate(utterances[1:], start=1):
        text = buf["transcript"].strip()
        duration = buf["end"] - buf["start"]
        word_count = len(text.split())

        should_merge = (
            is_incomplete(last_idx, text)
            and duration < max_duration
            and word_count < max_words
        )
        if should_merge:
            buf["transcript"] = f"{text} {nxt['transcript'].strip()}"
            buf["end"] = nxt["end"]
            last_idx = nxt_idx
        else:
            merged.append(buf)
            buf = dict(nxt)
            last_idx = nxt_idx

    merged.append(buf)
    return merged


def merge_incomplete_utterances(
    utterances: list[dict],
    max_duration: float = DEFAULT_MAX_DURATION,
    max_words: int = DEFAULT_MAX_WORDS,
) -> list[dict]:
    """文末の句読点で終わっていないutteranceを次のutteranceと結合する（正規表現版）。

    動画字幕生成（add_subtitles.py）で、Deepgramのバッチ文字起こし結果
    （全utteranceが揃っている状態）に対して使う。
    """
    return _merge_with_predicate(
        utterances,
        max_duration,
        max_words,
        is_incomplete=lambda _idx, text: not SENTENCE_END_RE.search(text),
    )


async def merge_incomplete_utterances_with_detector(
    utterances: list[dict],
    config: Config,
    usage_sink: UsageSink | None = None,
) -> list[dict]:
    """LLM分類器（`incomplete_end_detector`）で文末の完全性を判定してから結合する。

    バッチ判定に失敗した項目（`None`）は正規表現にフォールバックする。
    LLM判定自体を無効化したい場合は呼び出し側で `merge_incomplete_utterances`
    をそのまま使うこと。
    """
    if not utterances:
        return utterances

    from real_time_translation.transcription.incomplete_end_detector import (
        detect_incomplete_ends_batch,
    )

    texts = [u["transcript"].strip() for u in utterances]
    api_key = config.google_api_key or ""
    model = config.incomplete_end_detection_model or config.gemini_model
    flags = await detect_incomplete_ends_batch(texts, api_key, model, usage_sink)

    def is_incomplete(idx: int, text: str) -> bool:
        flag = flags[idx] if idx < len(flags) else None
        if flag is not None:
            return flag
        return not SENTENCE_END_RE.search(text)

    return _merge_with_predicate(
        utterances,
        config.utterance_merge_max_duration,
        config.utterance_merge_max_words,
        is_incomplete=is_incomplete,
    )


@dataclass
class MergedUtterance:
    """結合済みutterance（ストリーミング版の出力単位）。"""

    text: str
    start_time: float
    end_time: float
    confidence: float

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < 0.7


class StreamingUtteranceMerger:
    """リアルタイム文字起こし向けのutterance結合バッファ。

    マイクのリアルタイム翻訳（pipeline.py）は、Deepgramのstreaming APIから
    `is_final=True` の結果を1つずつ受け取る。この結果が文末で終わっていない
    場合、`feed()` は None を返して次の final を待つ（＝字幕確定を少し遅らせる）。
    文末punctuationに達するか、上限（秒数・語数）を超えたら結合済みutteranceを返す。
    """

    def __init__(
        self,
        max_duration: float = 8.0,
        max_words: int = 30,
    ) -> None:
        self._max_duration = max_duration
        self._max_words = max_words
        self._buf: MergedUtterance | None = None

    def feed(
        self,
        text: str,
        start_time: float,
        end_time: float,
        confidence: float,
        is_incomplete_override: bool | None = None,
    ) -> MergedUtterance | None:
        """final文字起こし結果を1件投入する。

        結合完了なら `MergedUtterance` を返す。まだ文の途中なら None を返し、
        内部バッファに保持したまま次の `feed()` 呼び出しを待つ。

        Args:
            is_incomplete_override: 今回投入した `text` の末尾が不完全かどうかの
                外部判定結果（LLM分類器など）。`None`（既定）なら従来通り
                正規表現（`SENTENCE_END_RE`）で判定する。
        """
        text = text.strip()
        if not text:
            return None

        if self._buf is None:
            self._buf = MergedUtterance(
                text=text, start_time=start_time, end_time=end_time, confidence=confidence
            )
        else:
            self._buf = MergedUtterance(
                text=f"{self._buf.text} {text}",
                start_time=self._buf.start_time,
                end_time=end_time,
                confidence=min(self._buf.confidence, confidence),
            )

        duration = self._buf.end_time - self._buf.start_time
        word_count = len(self._buf.text.split())

        if is_incomplete_override is None:
            is_complete = bool(SENTENCE_END_RE.search(self._buf.text))
        else:
            is_complete = not is_incomplete_override

        should_flush = (
            is_complete
            or duration >= self._max_duration
            or word_count >= self._max_words
        )
        if should_flush:
            result = self._buf
            self._buf = None
            return result
        return None

    def flush(self) -> MergedUtterance | None:
        """バッファに残っている未確定の断片を強制的に取り出す（パイプライン停止時用）。"""
        result = self._buf
        self._buf = None
        return result
