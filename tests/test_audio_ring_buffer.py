"""Tests for pipeline._AudioRingBuffer (Whisper再検証用の音声バッファ)."""

from real_time_translation.pipeline import _AudioRingBuffer

_SAMPLE_RATE = 16000
_BYTES_PER_SECOND = _SAMPLE_RATE * 2  # 16-bit mono


def _silence_chunk(seconds: float) -> bytes:
    return b"\x00\x00" * int(_SAMPLE_RATE * seconds)


def test_slice_returns_expected_byte_length() -> None:
    buf = _AudioRingBuffer(sample_rate=_SAMPLE_RATE, max_seconds=10.0)
    for _ in range(5):
        buf.append(_silence_chunk(0.2))  # 5 * 0.2s = 1.0s total

    sliced = buf.slice(0.2, 0.6, pad=0.0)
    assert sliced is not None
    assert len(sliced) == int(0.4 * _BYTES_PER_SECOND)


def test_slice_returns_none_outside_buffered_range() -> None:
    buf = _AudioRingBuffer(sample_rate=_SAMPLE_RATE, max_seconds=10.0)
    buf.append(_silence_chunk(0.5))

    assert buf.slice(5.0, 6.0, pad=0.0) is None


def test_old_chunks_are_evicted_beyond_max_seconds() -> None:
    buf = _AudioRingBuffer(sample_rate=_SAMPLE_RATE, max_seconds=1.0)
    for _ in range(20):
        buf.append(_silence_chunk(0.2))  # 4.0s total sent, only last ~1.0s kept

    # 最初の方の区間はもう破棄されているはず
    assert buf.slice(0.0, 0.1, pad=0.0) is None
    # 直近の区間は残っている
    assert buf.slice(3.8, 3.9, pad=0.0) is not None
