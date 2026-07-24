"""utterance が文末で終わっているかをLLMで判定する（句読点ヒューリスティックの補強）。

`utterance_merge.py` は今まで正規表現（`SENTENCE_END_RE`：`. ! ?` などで終わって
いるか）だけで「結合すべきか」を判断していた。これは高速・無料だが、
Deepgramが句読点を付け損なうケースや、疑問形・省略形など正規表現でカバーし
きれないパターンを取りこぼす。

ここでは `lecture_subtitle_translator`（TypeScript版）の
`detectIncompleteEnds.ts` と同じ発想で、軽量LLMに「文末が不完全か」をバッチで
判定させる。判定に失敗した項目は `None` を返し、呼び出し側で正規表現に
フォールバックする（LLMが使えない・落ちていても機能は止まらない）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from real_time_translation.translation.usage_tracking import LlmUsageRecord, UsageSink

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a fast subtitle-fragment classifier. "
    "For each input item, decide if it ENDS MID-SENTENCE "
    "(i.e., it is grammatically incomplete and continues into the next utterance). "
    "Examples that end MID-SENTENCE (incomplete=true): trails off without "
    "sentence-final punctuation, ends with a conjunction/preposition, or ends "
    "with a comma before a connective like \"and\"/\"but\"/\"because\". "
    "Examples that DO NOT end mid-sentence (incomplete=false): ends with . ! ? "
    "or any clear sentence-final form. Be fast and approximate. "
    'Respond only with JSON: {"r":[{"i":<id>,"x":<true|false>}, ...]} '
    "where x=true means INCOMPLETE."
)

_DEFAULT_MAX_RETRIES = 1


def _extract_json_object(content: str) -> dict[str, Any] | None:
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _parse_batch_response(content: str, expected_count: int) -> list[bool | None]:
    """レスポンスをパースし、`expected_count` の長さの `bool | None` 配列を返す。"""
    result: list[bool | None] = [None] * expected_count
    parsed = _extract_json_object(content)
    if parsed is None:
        return result

    raw = parsed.get("r") or parsed.get("results")
    if not isinstance(raw, list):
        return result

    for entry in raw:
        if not isinstance(entry, dict):
            continue
        idx_raw = entry.get("i", entry.get("id"))
        try:
            idx = int(idx_raw)
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < expected_count):
            continue
        x = entry.get("x", entry.get("incomplete"))
        result[idx] = bool(x) if isinstance(x, bool) else str(x).lower() == "true"

    return result


async def _call_gemini(prompt: str, api_key: str, model: str) -> Any:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_PROMPT,
        temperature=0.0,
    )
    return await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=prompt,
        config=config,
    )


def _record_usage(
    usage_sink: UsageSink | None,
    model: str,
    node: str,
    response: Any,
    duration_ms: float,
) -> None:
    if usage_sink is None:
        return
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return
    usage_sink.push(
        LlmUsageRecord(
            model=model,
            node=node,
            prompt_tokens=getattr(usage, "prompt_token_count", None) or 0,
            completion_tokens=getattr(usage, "candidates_token_count", None) or 0,
            thinking_tokens=getattr(usage, "thoughts_token_count", None) or 0,
            duration_ms=duration_ms,
        )
    )


async def detect_incomplete_ends_batch(
    texts: list[str],
    api_key: str,
    model: str,
    usage_sink: UsageSink | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> list[bool | None]:
    """複数のutteranceについて、文末が不完全かをまとめてLLMに判定させる。

    1回のプロンプトで全件をバッチ判定する（呼び出し回数を抑えるため）。
    失敗時は `max_retries` 回までリトライし、それでも失敗したら全件 `None`
    （呼び出し側は正規表現へフォールバックする）。
    """
    if not texts:
        return []

    items = [{"i": i, "t": t} for i, t in enumerate(texts)]
    prompt = json.dumps(items, ensure_ascii=False)

    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            start = time.monotonic()
            response = await _call_gemini(prompt, api_key, model)
            duration_ms = (time.monotonic() - start) * 1000
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "incomplete-end detection failed (attempt %d/%d): %s",
                attempt + 1,
                attempts,
                exc,
            )
            continue

        _record_usage(
            usage_sink, model, "detect_incomplete_ends", response, duration_ms
        )
        content = (getattr(response, "text", None) or "").strip()
        if not content:
            continue

        parsed = _parse_batch_response(content, len(texts))
        if any(v is not None for v in parsed):
            return parsed

    return [None] * len(texts)


async def detect_incomplete_end_one(
    text: str,
    api_key: str,
    model: str,
    timeout: float,
    usage_sink: UsageSink | None = None,
) -> bool | None:
    """リアルタイム経路向けの単発版。タイムアウトを厳守し、超えたら `None` を返す。

    マイクのストリーミング処理は1件ずつ同期的に流れるため、LLM判定を待つ間に
    遅延が積み上がらないよう、必ずタイムアウトで打ち切る。
    """
    try:
        result = await asyncio.wait_for(
            detect_incomplete_ends_batch(
                [text], api_key, model, usage_sink, max_retries=0
            ),
            timeout=timeout,
        )
    except TimeoutError:
        logger.debug("incomplete-end detection timed out (%.2fs)", timeout)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("incomplete-end detection error: %s", exc)
        return None

    return result[0] if result else None
