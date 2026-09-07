"""次に翻訳するチャンクが、直前の字幕を踏まえたときにどれだけ唐突/不自然かをLLMで判定する。

`incomplete_end_detector.py` は「このutteranceの末尾が文法的に不完全か」だけを見るため、
文法的には完結していても、直前の文脈から見て今訳すと唐突・尻切れに見える候補
（代名詞の指示先が定まらない、話題が明らかに続く、リストや比較の途中、等）は
検出できない。

このモジュールは直前の字幕（`<context>`、原文と、既に確定済みの訳文がある場合は
その訳文も併記したペア）を踏まえ、候補チャンク（`<candidate>`）を「今このまま訳して
字幕として出したときの不自然さ」を0.0〜1.0でLLMに採点させる。スコアが閾値以上なら
チャンクを確定させず、次のutteranceと結合を続ける（`transcription/utterance_merge.py` の
`StreamingUtteranceMerger.feed(force_incomplete=True)`）。

原文だけでなく訳文（JA側）も参考情報として渡しているのは、話題の継続や指示語の
未解決といった「不自然さ」の手がかりが、英語原文よりも実際に出力される日本語側
（「そして、」で終わる、助詞が宙に浮く、など）の方が判定しやすいことがあるため
（2026-09-06、実運用でのAB test結果を受けた改善。当初は原文側のみを参照していたが、
スコアが0.80〜0.90に偏り判別力が乏しい問題があった）。訳文がまだ無い行（オフライン
再現などで翻訳を省略する場合）は空文字列を渡してよく、その場合は原文のみが
コンテキストとして使われる。

マイクのリアルタイム翻訳（`pipeline.py`）専用。動画/CLIのバッチ経路は元々
`context_window_size=5`・`thinking_budget=1024`・長めのutterance結合上限
（20秒/60語）で精度を優先しており、対象外とする。

判定に失敗・タイムアウトした場合は `None` を返す。呼び出し側はNone時は
不自然度チェックをスキップすること（＝これまで通りの完全性判定のみに従う、
リアルタイム性を壊さない安全弁）。

2026-08-25のAB testで「既に句点で終わった完結文を、無関係な次発話と過剰結合
してしまう事例」と「LLM自己採点がOFF/ONとも0.98以上に偏り判別力が乏しい」
という2つの問題が見つかっていた（`evaluation/naturalness_check_ab_test.py`・
README更新履歴参照）。単一のスコアだけを閾値判定に使うと、モデルが
「なんとなく高いスコア」を返しただけの誤検知と、実際に継続の手がかりがある
ケースを区別できない。2026-09-07、スコアに加えて**理由ラベル**
（`NaturalnessResult.reason`）も返させ、"complete"（＝実は完結している）の
場合は明示的にスコアだけでは強制継続させないガードを追加した
（`pipeline.py`側で`reason != "complete"`も条件に加える）。理由ラベルという
離散カテゴリを併用することで、スコアの粒度の粗さを補い、モデル自身に
「なぜそのスコアなのか」を一言で説明させることで根拠のない高スコアを
減らす狙い。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from real_time_translation.translation.usage_tracking import LlmUsageRecord, UsageSink

logger = logging.getLogger(__name__)

_VALID_REASONS = frozenset(
    {
        "complete",
        "dangling_clause",
        "unresolved_reference",
        "unfinished_list_or_comparison",
        "trailing_conjunction",
        "other",
    }
)

_SYSTEM_PROMPT = (
    "You are a real-time subtitle-chunking assistant for simultaneous interpretation. "
    "You are given <context> (already-finalized preceding subtitle lines, oldest "
    "first, may be empty, each shown as its English source and, when already "
    "translated, the Japanese subtitle actually shown to viewers) and a <candidate> "
    "fragment being considered as the NEXT subtitle chunk. "
    "Use the Japanese lines when present — cues like a dangling connective ending "
    "(e.g. a line ending in \"そして、\" or a bare particle) or an unresolved "
    "reference are often easier to see there than in the English source. "
    "Judge how unnatural or abrupt it would look if <candidate> were translated and "
    "shown as a subtitle RIGHT NOW, on its own, without waiting for more speech. "
    "Score 0.0 if translating it now would read naturally and completely. "
    "Score close to 1.0 if it clearly continues (dangling clause, unresolved "
    "pronoun/reference, an obvious setup like a list or comparison that isn't "
    "finished, a trailing conjunction). Be fast and approximate; when unsure, "
    "prefer a LOW score (translating now is usually fine — only flag clear cases). "
    "Also pick the single best-matching reason code for your score: "
    '"complete" (it already reads fine on its own — use this even if you gave a '
    'nonzero score out of caution), "dangling_clause", "unresolved_reference", '
    '"unfinished_list_or_comparison", "trailing_conjunction", or "other". '
    "Only a reason other than \"complete\" should ever be treated as a real "
    "continuation signal, so pick \"complete\" whenever you are not sure there is "
    "a concrete continuation cue. "
    'Respond only with JSON: {"score": <0.0-1.0>, "reason": <reason code>}'
)

_DEFAULT_MAX_RETRIES = 1


@dataclass(frozen=True)
class NaturalnessResult:
    """`score_unnaturalness`の判定結果。

    `reason`が`"complete"`の場合、モデル自身が「実際には完結している」と
    判断している。スコアだけを見て高いからと強制継続させるのではなく、
    `reason != "complete"`も合わせて確認すること（2026-09-07のガード追加、
    モジュールdocstring参照）。
    """

    score: float
    reason: str


def _extract_result(content: str) -> NaturalnessResult | None:
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            return None

    if not isinstance(parsed, dict):
        return None
    score = parsed.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    score = max(0.0, min(1.0, float(score)))

    reason = parsed.get("reason")
    if not isinstance(reason, str) or reason not in _VALID_REASONS:
        # モデルがreasonを返さなかった/未知の値を返した場合は"other"として扱う
        # （＝スコアのみで判定する旧来の挙動にフォールバック。呼び出し側の
        # ガードは`reason != "complete"`なので、これは安全側に倒れる）。
        reason = "other"
    return NaturalnessResult(score=score, reason=reason)


def _build_prompt(candidate: str, context: list[tuple[str, str]]) -> str:
    """`context` は (英語原文, 既に確定した日本語訳) のペアのリスト（古い順）。

    訳文がまだ無い場合は2要素目を空文字列にしてよい（EN行のみ出力する）。
    """
    if not context:
        context_block = "(no prior context)"
    else:
        lines = []
        for src, tgt in context:
            lines.append(f"EN: {src}" + (f"\nJA: {tgt}" if tgt else ""))
        context_block = "\n\n".join(lines)
    return f"<context>\n{context_block}\n</context>\n<candidate>\n{candidate}\n</candidate>"


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
    usage_sink: UsageSink | None, model: str, response: Any, duration_ms: float
) -> None:
    if usage_sink is None:
        return
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return
    usage_sink.push(
        LlmUsageRecord(
            model=model,
            node="score_unnaturalness",
            prompt_tokens=getattr(usage, "prompt_token_count", None) or 0,
            completion_tokens=getattr(usage, "candidates_token_count", None) or 0,
            thinking_tokens=getattr(usage, "thoughts_token_count", None) or 0,
            duration_ms=duration_ms,
        )
    )


async def score_unnaturalness(
    candidate: str,
    context: list[tuple[str, str]],
    api_key: str,
    model: str,
    usage_sink: UsageSink | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> NaturalnessResult | None:
    """`candidate` を直前の `context` を踏まえて今訳した場合の不自然さを判定する。

    失敗時は `None`（呼び出し側は不自然度チェックをスキップしてよい）。
    """
    if not candidate.strip():
        return None

    prompt = _build_prompt(candidate, context)
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            start = time.monotonic()
            response = await _call_gemini(prompt, api_key, model)
            duration_ms = (time.monotonic() - start) * 1000
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "unnaturalness scoring failed (attempt %d/%d): %s",
                attempt + 1,
                attempts,
                exc,
            )
            continue

        _record_usage(usage_sink, model, response, duration_ms)
        content = (getattr(response, "text", None) or "").strip()
        if not content:
            continue

        result = _extract_result(content)
        if result is not None:
            return result

    return None


async def score_unnaturalness_with_timeout(
    candidate: str,
    context: list[tuple[str, str]],
    api_key: str,
    model: str,
    timeout: float,
    usage_sink: UsageSink | None = None,
) -> NaturalnessResult | None:
    """リアルタイム経路向けの単発版。タイムアウトを厳守し、超えたら `None` を返す。

    マイクのストリーミング処理は1件ずつ同期的に流れるため、LLM判定を待つ間に
    遅延が積み上がらないよう、必ずタイムアウトで打ち切る
    （`incomplete_end_detector.detect_incomplete_end_one` と同じ設計）。
    """
    try:
        return await asyncio.wait_for(
            score_unnaturalness(
                candidate, context, api_key, model, usage_sink, max_retries=0
            ),
            timeout=timeout,
        )
    except TimeoutError:
        logger.debug("unnaturalness scoring timed out (%.2fs)", timeout)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("unnaturalness scoring error: %s", exc)
        return None
