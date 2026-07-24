"""Tests for translation.usage_tracking."""

from real_time_translation.translation.usage_tracking import LlmUsageRecord, UsageSink


def test_push_ignores_zero_token_records() -> None:
    sink = UsageSink()
    sink.push(LlmUsageRecord(model="gemini-2.5-flash", node="translate"))

    assert sink.records() == []


def test_push_and_records() -> None:
    sink = UsageSink()
    sink.push(
        LlmUsageRecord(
            model="gemini-2.5-flash", node="translate", prompt_tokens=10, completion_tokens=5
        )
    )

    records = sink.records()
    assert len(records) == 1
    assert records[0].prompt_tokens == 10
    assert records[0].completion_tokens == 5


def test_aggregate_by_model() -> None:
    sink = UsageSink()
    sink.push(
        LlmUsageRecord(model="a", node="translate", prompt_tokens=10, completion_tokens=5)
    )
    sink.push(
        LlmUsageRecord(model="a", node="translate", prompt_tokens=20, completion_tokens=10)
    )
    sink.push(
        LlmUsageRecord(model="b", node="detect_incomplete_ends", prompt_tokens=1, completion_tokens=1)
    )

    aggs = sink.aggregate_by_model()
    assert len(aggs) == 2
    by_model = {a.model: a for a in aggs}
    assert by_model["a"].calls == 2
    assert by_model["a"].prompt_tokens == 30
    assert by_model["a"].completion_tokens == 15
    assert by_model["b"].calls == 1


def test_calls_in_last_seconds() -> None:
    sink = UsageSink()
    now = 1000.0
    sink.push(LlmUsageRecord(model="a", node="translate", prompt_tokens=1, at=now - 5))
    sink.push(LlmUsageRecord(model="a", node="translate", prompt_tokens=1, at=now - 90))

    assert sink.calls_in_last_seconds(60, now=now) == 1
    assert sink.calls_in_last_seconds(120, now=now) == 2


def test_rate_limit_status_near_limit() -> None:
    sink = UsageSink()
    now = 1000.0
    for i in range(12):
        sink.push(LlmUsageRecord(model="a", node="translate", prompt_tokens=1, at=now - i))

    status = sink.rate_limit_status(limit=15, window_seconds=60, now=now)
    assert status.calls_last_60s == 12
    assert status.near_limit is True  # 12 >= 15 * 0.8


def test_rate_limit_status_not_near_limit() -> None:
    sink = UsageSink()
    status = sink.rate_limit_status(limit=15, window_seconds=60)
    assert status.calls_last_60s == 0
    assert status.near_limit is False


def test_summary_text_empty() -> None:
    sink = UsageSink()
    assert "記録なし" in sink.summary_text()


def test_summary_text_with_records() -> None:
    sink = UsageSink()
    sink.push(
        LlmUsageRecord(model="a", node="translate", prompt_tokens=100, completion_tokens=50)
    )
    text = sink.summary_text()
    assert "1回呼び出し" in text
    assert "100" in text
    assert "50" in text
