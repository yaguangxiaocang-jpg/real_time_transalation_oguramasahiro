"""Tests for latency."""

import csv
import io

import pytest

from real_time_translation.latency import (
    BYTES_PER_SECOND,
    AudioClock,
    LatencyTracker,
    SegmentTiming,
    StepTimer,
    percentile,
)


def _clock_with_chunks(chunk_seconds: float, sent_times: list[float]) -> AudioClock:
    clock = AudioClock()
    for sent in sent_times:
        clock.record(int(chunk_seconds * BYTES_PER_SECOND), sent)
    return clock


def test_audio_clock_realtime_chunks_maps_inside_chunk() -> None:
    # 0.5秒ずつリアルタイムに送信: 0〜0.5秒の音声は 100.5 に送信、0.5〜1.0秒は 101.0 …
    clock = _clock_with_chunks(0.5, [100.5, 101.0, 101.5])

    # 0.8秒地点の音声は2つ目のチャンク（末尾1.0秒、送信101.0）の0.2秒前に話された
    assert clock.to_wall(0.8) == pytest.approx(100.8)
    assert clock.to_wall(1.5) == pytest.approx(101.5)


def test_audio_clock_faster_than_realtime_does_not_go_before_previous_send() -> None:
    # 1秒ぶんを0.5秒ごとに送る（音声ファイル処理）
    clock = _clock_with_chunks(1.0, [10.0, 10.5, 11.0])

    # 1.1秒地点: チャンク末尾まで0.9秒あるが、前の送信(10.0)より前にはしない
    assert clock.to_wall(1.1) == pytest.approx(10.0)
    assert clock.to_wall(2.0) == pytest.approx(10.5)


def test_audio_clock_returns_none_outside_sent_audio() -> None:
    clock = _clock_with_chunks(0.5, [1.0])

    assert clock.to_wall(0.7) is None
    assert AudioClock().to_wall(0.0) is None


def test_audio_clock_drops_old_marks() -> None:
    clock = AudioClock(max_marks=2)
    for sent in [1.0, 2.0, 3.0]:
        clock.record(BYTES_PER_SECOND, sent)

    assert clock.to_wall(0.5) is None  # 捨てた範囲の音声は不明
    assert clock.to_wall(1.5) == pytest.approx(1.5)
    assert clock.to_wall(3.0) == pytest.approx(3.0)


def _timing(**kw) -> SegmentTiming:
    base = dict(
        text="Hello.",
        speech_end=10.0,
        first_asr_final=10.2,
        asr_final=10.6,
        endpoint_done=10.7,
        queued=10.7,
        translate_start=11.0,
        translate_end=12.0,
        displayed=12.4,
    )
    base.update(kw)
    return SegmentTiming(**base)


def test_segment_timing_stages_and_total() -> None:
    t = _timing()

    assert t.stages() == pytest.approx(
        {
            "asr": 0.6,
            "endpoint": 0.1,
            "reverify": 0.0,
            "queue": 0.3,
            "llm": 1.0,
            "display": 0.4,
        }
    )
    assert t.total == pytest.approx(2.4)
    assert t.merge_wait == pytest.approx(0.4)
    assert sum(t.stages().values()) == pytest.approx(t.total)


def test_segment_timing_missing_points_are_none() -> None:
    t = _timing(speech_end=None, displayed=None)

    assert t.stages()["asr"] is None
    assert t.stages()["display"] is None
    assert t.total is None


def test_percentile_interpolates() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]

    assert percentile(values, 50) == 3.0
    assert percentile(values, 95) == pytest.approx(4.8)
    assert percentile([7.0], 95) == 7.0
    with pytest.raises(ValueError):
        percentile([], 50)


def test_tracker_summary_and_csv() -> None:
    tracker = LatencyTracker()
    tracker.add(_timing())
    tracker.add(_timing(text="Second, with comma.", displayed=13.4))
    tracker.add(_timing(speech_end=None))  # 話し終わり不明 → 合計からは除外

    summary = {s.label: s for s in tracker.summary()}
    total = summary["合計（話し終わり→表示）"]
    assert total.count == 2
    assert total.median == pytest.approx(2.9)
    assert summary["音声認識"].count == 2
    assert summary["翻訳API"].count == 3
    assert tracker.latest_total() == pytest.approx(3.4)

    rows = list(csv.reader(io.StringIO(tracker.to_csv())))
    assert rows[0][:3] == ["no", "recorded_at", "text"]
    assert len(rows) == 4
    assert rows[2][2] == "Second, with comma."
    assert rows[1][-2] == "2.400"
    assert rows[3][-2] == ""

    assert "| 合計（話し終わり→表示） | 2.90秒" in tracker.summary_markdown()


def test_tracker_empty() -> None:
    tracker = LatencyTracker()

    assert tracker.summary() == []
    assert tracker.summary_markdown() == ""
    assert tracker.latest_total() is None


def test_step_timer_summary() -> None:
    now = [0.0]
    timer = StepTimer(clock=lambda: now[0])
    timer.start("音声抽出")
    now[0] = 2.0
    assert timer.stop() == pytest.approx(2.0)
    timer.start("翻訳")
    now[0] = 10.0
    timer.stop()

    lines = timer.summary_lines(media_seconds=20.0)

    assert "  - 音声抽出: 2.0秒（20%）" in lines
    assert "  - 翻訳: 8.0秒（80%）" in lines
    assert "  - 合計: 10.0秒" in lines
    assert lines[-1] == "  - 動画 20.0秒 に対して 0.50倍の時間"
