"""LLM呼び出しのトークン使用量トラッキング。

Gemini無料枠は1分あたりの呼び出し回数に上限があり（README参照）、ユーザーは
エラーが出て初めて制限に気づく状態だった。ここでは呼び出しごとの使用量を
記録し、モデル別の集計とレート制限への近さを可視化するための最小限の仕組みを
提供する。

`lecture_subtitle_translator`（TypeScript版）の `llmUsageSink.ts` と同じ発想
（呼び出し点ごとに push、後でまとめて集計）だが、あちらはデスクトップアプリ
（同時実行は常に1つ）を前提にモジュールレベルのグローバルsinkを使っている。
本アプリはGradio（複数セッションが同時に動きうる）なので、
`TranslationPipeline` インスタンス・動画処理ジョブごとに専用のインスタンスを
持たせて使う（グローバル共有はしない）。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LlmUsageRecord:
    """1回のLLM呼び出しの使用量。"""

    model: str
    node: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thinking_tokens: int = 0
    duration_ms: float = 0.0
    at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class AggregatedUsage:
    """モデル単位で集計した使用量。"""

    model: str
    calls: int
    prompt_tokens: int
    completion_tokens: int
    thinking_tokens: int
    duration_ms: float


@dataclass(frozen=True)
class RateLimitStatus:
    """レート制限への近さ。UI表示専用（自動スロットリングはしない）。"""

    calls_last_60s: int
    limit: int
    near_limit: bool


class UsageSink:
    """LLM使用量レコードを集約する箱。1パイプライン実行・1動画処理ジョブにつき1個。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[LlmUsageRecord] = []

    def push(self, record: LlmUsageRecord) -> None:
        """使用量レコードを1件追加する。

        トークン数が全て0の場合は記録しない（API失敗でusageが取得できなかった
        呼び出しなど）。
        """
        if (
            record.prompt_tokens <= 0
            and record.completion_tokens <= 0
            and record.thinking_tokens <= 0
        ):
            return
        with self._lock:
            self._records.append(record)

    def records(self) -> list[LlmUsageRecord]:
        with self._lock:
            return list(self._records)

    def aggregate_by_model(self) -> list[AggregatedUsage]:
        """モデルID単位で集計する。呼び出し回数が多い順に返す。"""
        totals: dict[str, dict[str, float]] = {}
        for r in self.records():
            bucket = totals.setdefault(
                r.model,
                {
                    "calls": 0,
                    "prompt": 0,
                    "completion": 0,
                    "thinking": 0,
                    "duration": 0.0,
                },
            )
            bucket["calls"] += 1
            bucket["prompt"] += r.prompt_tokens
            bucket["completion"] += r.completion_tokens
            bucket["thinking"] += r.thinking_tokens
            bucket["duration"] += r.duration_ms

        result = [
            AggregatedUsage(
                model=model,
                calls=int(v["calls"]),
                prompt_tokens=int(v["prompt"]),
                completion_tokens=int(v["completion"]),
                thinking_tokens=int(v["thinking"]),
                duration_ms=v["duration"],
            )
            for model, v in totals.items()
        ]
        result.sort(key=lambda a: a.prompt_tokens + a.completion_tokens, reverse=True)
        return result

    def calls_in_last_seconds(self, seconds: float, *, now: float | None = None) -> int:
        """直近N秒以内に記録された呼び出し件数。"""
        cutoff = (now if now is not None else time.time()) - seconds
        return sum(1 for r in self.records() if r.at >= cutoff)

    def rate_limit_status(
        self, limit: int, *, window_seconds: float = 60.0, now: float | None = None
    ) -> RateLimitStatus:
        """直近1分あたりの呼び出し件数を、指定した上限（Gemini無料枠のRPM目安等）と比較する。"""
        calls = self.calls_in_last_seconds(window_seconds, now=now)
        near_limit = limit > 0 and calls >= int(limit * 0.8)
        return RateLimitStatus(calls_last_60s=calls, limit=limit, near_limit=near_limit)

    def summary_text(self) -> str:
        """UI/ログ表示用の1行サマリ。"""
        aggs = self.aggregate_by_model()
        if not aggs:
            return "LLM使用量: 記録なし"
        total_calls = sum(a.calls for a in aggs)
        total_prompt = sum(a.prompt_tokens for a in aggs)
        total_completion = sum(a.completion_tokens for a in aggs)
        return (
            f"LLM使用量: {total_calls}回呼び出し / "
            f"入力{total_prompt:,}トークン / 出力{total_completion:,}トークン"
        )
