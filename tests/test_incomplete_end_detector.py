"""Tests for incomplete_end_detector and its integration into utterance_merge.

Gemini呼び出しをモックし、(a) 成功時にLLM判定が使われること、
(b) API失敗/タイムアウト時に正規表現へフォールバックすることを確認する。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from real_time_translation.config import Config
from real_time_translation.transcription import incomplete_end_detector as detector_module
from real_time_translation.transcription.utterance_merge import (
    merge_incomplete_utterances,
    merge_incomplete_utterances_with_detector,
)


@dataclass
class _FakeResponse:
    text: str
    usage_metadata: Any = None


def _make_config(**overrides: Any) -> Config:
    base = dict(
        deepgram_api_key="dg-key",
        llm_provider="gemini",
        zoom_client_id="",
        zoom_client_secret="",
        google_api_key="google-key",
        gemini_model="gemini-2.5-flash",
    )
    base.update(overrides)
    return Config(**base)


async def test_detect_incomplete_ends_batch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call_gemini(prompt: str, api_key: str, model: str) -> _FakeResponse:
        return _FakeResponse(text='{"r":[{"i":0,"x":true},{"i":1,"x":false}]}')

    monkeypatch.setattr(detector_module, "_call_gemini", fake_call_gemini)

    result = await detector_module.detect_incomplete_ends_batch(
        ["fragment that", "a complete sentence."], "key", "model"
    )

    assert result == [True, False]


async def test_detect_incomplete_ends_batch_gives_up_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_call(prompt: str, api_key: str, model: str) -> _FakeResponse:
        raise RuntimeError("API down")

    monkeypatch.setattr(detector_module, "_call_gemini", failing_call)

    result = await detector_module.detect_incomplete_ends_batch(
        ["a", "b"], "key", "model", max_retries=1
    )

    assert result == [None, None]


async def test_detect_incomplete_end_one_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow_call(prompt: str, api_key: str, model: str) -> _FakeResponse:
        await asyncio.sleep(0.3)
        return _FakeResponse(text='{"r":[{"i":0,"x":true}]}')

    monkeypatch.setattr(detector_module, "_call_gemini", slow_call)

    result = await detector_module.detect_incomplete_end_one(
        "some text", "key", "model", timeout=0.05
    )

    assert result is None  # タイムアウト時は None（呼び出し側は正規表現へフォールバック）


async def test_merge_with_detector_uses_llm_flags_over_regex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正規表現なら「完全」と判定される文でも、LLMが不完全と言えばマージされる。"""

    async def fake_batch(texts, api_key, model, usage_sink=None):
        # 全て「不完全」と判定 → 最後まで結合され続ける
        return [True] * len(texts)

    monkeypatch.setattr(detector_module, "detect_incomplete_ends_batch", fake_batch)

    utterances = [
        {"start": 0.0, "end": 1.0, "transcript": "This looks complete."},
        {"start": 1.0, "end": 2.0, "transcript": "But actually continues."},
        {"start": 2.0, "end": 3.0, "transcript": "and even further."},
    ]

    config = _make_config(utterance_merge_max_duration=20.0, utterance_merge_max_words=60)
    merged = await merge_incomplete_utterances_with_detector(utterances, config)

    assert len(merged) == 1
    assert merged[0]["transcript"] == (
        "This looks complete. But actually continues. and even further."
    )


async def test_merge_with_detector_falls_back_to_regex_on_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM判定が失敗（None）した場合、正規表現の結果と一致する。"""

    async def failing_batch(texts, api_key, model, usage_sink=None):
        return [None] * len(texts)

    monkeypatch.setattr(detector_module, "detect_incomplete_ends_batch", failing_batch)

    utterances = [
        {"start": 0.0, "end": 1.0, "transcript": "Hello world."},
        {"start": 1.0, "end": 2.0, "transcript": "This is a fragment"},
        {"start": 2.0, "end": 3.5, "transcript": "that continues."},
        {"start": 3.5, "end": 5.0, "transcript": "New sentence."},
    ]

    config = _make_config(utterance_merge_max_duration=20.0, utterance_merge_max_words=60)
    merged_with_detector = await merge_incomplete_utterances_with_detector(utterances, config)
    merged_regex_only = merge_incomplete_utterances(utterances)

    assert merged_with_detector == merged_regex_only
