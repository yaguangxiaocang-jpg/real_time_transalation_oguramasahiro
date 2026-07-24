"""Tests for utterance-merge logic shared by add_subtitles.py and pipeline.py."""

from real_time_translation.transcription.utterance_merge import (
    StreamingUtteranceMerger,
    merge_incomplete_utterances,
)


def test_merge_incomplete_utterances_joins_mid_sentence_split() -> None:
    utterances = [
        {"start": 0.0, "end": 1.0, "transcript": "Hello world."},
        {"start": 1.0, "end": 2.0, "transcript": "This is a fragment"},
        {"start": 2.0, "end": 3.5, "transcript": "that continues."},
        {"start": 3.5, "end": 5.0, "transcript": "New sentence."},
    ]

    merged = merge_incomplete_utterances(utterances)

    assert len(merged) == 3
    assert merged[0]["transcript"] == "Hello world."
    assert merged[1]["transcript"] == "This is a fragment that continues."
    assert merged[1]["start"] == 1.0
    assert merged[1]["end"] == 3.5
    assert merged[2]["transcript"] == "New sentence."


def test_merge_incomplete_utterances_respects_max_words() -> None:
    utterances = [
        {"start": 0.0, "end": 1.0, "transcript": "word " * 10},
        {"start": 1.0, "end": 2.0, "transcript": "word " * 10},
        {"start": 2.0, "end": 3.0, "transcript": "word " * 5},
    ]

    merged = merge_incomplete_utterances(utterances, max_words=15)

    # 1回目の結合で20語（上限15語）を超えるため、2回目の結合は打ち切られる
    assert len(merged) == 2
    assert len(merged[0]["transcript"].split()) == 20
    assert len(merged[1]["transcript"].split()) == 5


def test_streaming_merger_buffers_until_sentence_end() -> None:
    merger = StreamingUtteranceMerger(max_duration=8.0, max_words=30)

    result = merger.feed("in The United States. It's called the federal", 0.0, 2.0, 0.95)
    assert result is None  # まだ文の途中 → 翻訳キューへは積まない

    result = merger.feed("funds rate,", 2.0, 3.5, 0.9)
    assert result is None

    result = merger.feed("which is set by the Fed.", 3.5, 5.0, 0.88)
    assert result is not None
    assert result.text == (
        "in The United States. It's called the federal funds rate, which is set by the Fed."
    )
    assert result.start_time == 0.0
    assert result.end_time == 5.0
    assert result.confidence == 0.88  # min confidence across merged pieces


def test_streaming_merger_flushes_on_max_duration() -> None:
    merger = StreamingUtteranceMerger(max_duration=2.0, max_words=30)

    result = merger.feed("this sentence never ends", 0.0, 3.0, 0.9)

    assert result is not None  # 秒数上限を超えたら文末でなくても結合を打ち切る


def test_streaming_merger_flush_returns_pending_buffer() -> None:
    merger = StreamingUtteranceMerger()

    assert merger.feed("mid sentence without punctuation", 0.0, 1.0, 0.9) is None
    remaining = merger.flush()

    assert remaining is not None
    assert remaining.text == "mid sentence without punctuation"
    assert merger.flush() is None  # バッファは空になっている
