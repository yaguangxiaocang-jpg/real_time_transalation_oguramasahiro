"""evaluation/diarization_check.py の話者切り替わり位置の補正（API呼び出しなし）のテスト。

例文は harari_utada 全編（2026-10-19 のDeepgram出力）で実際に起きた誤りから取っている。
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evaluation"))

# diarization_check が import する add_subtitles は読み込み時にAPIキーを要求する
os.environ.setdefault("DEEPGRAM_API_KEY", "test")
os.environ.setdefault("GOOGLE_API_KEY", "test")

from diarization_check import split_by_word_speaker  # noqa: E402


def _utt(*spans: tuple[int, str]) -> dict:
    """(話者番号, "単語 単語 ...") の並びから、単語単位の話者番号付きutteranceを作る。"""
    words, t = [], 0.0
    for speaker, text in spans:
        for w in text.split():
            words.append({"word": w, "start": t, "end": t + 0.3, "speaker": speaker})
            t += 0.35
    return {
        "start": 0.0, "end": t, "speaker": spans[0][0], "transcript": "", "words": words
    }


def _texts(segments: list[dict]) -> list[tuple[int, str]]:
    return [(s["speaker"], s["transcript"]) for s in segments]


def test_moves_sentence_head_to_next_speaker():
    # 「Yes. To | talk about art」: "To" は次の話者の文の頭
    utt = _utt((0, "Yes. To"), (1, "talk about art."))
    segments, snapped = split_by_word_speaker([utt])
    assert snapped == 1
    assert _texts(segments) == [(0, "Yes."), (1, "To talk about art.")]


def test_moves_sentence_tail_to_previous_speaker():
    # 「... appreciate that | or not.」: "or not." は前の話者の文の尻尾
    utt = _utt(
        (0, "But whether people will appreciate that"), (1, "or not."), (0, "Right?")
    )
    segments, snapped = split_by_word_speaker([utt])
    assert snapped == 1
    assert _texts(segments) == [
        (0, "But whether people will appreciate that or not."),
        (0, "Right?"),
    ]


def test_keeps_backchannel_inside_sentence():
    # 相手のあいづち "Mhmm." を話し手の文に吸収しない（初版の誤り）
    utt = _utt((0, "the response time"), (1, "Mhmm."), (0, "matters a lot."))
    segments, snapped = split_by_word_speaker([utt])
    assert snapped == 0
    assert _texts(segments) == [
        (0, "the response time"),
        (1, "Mhmm."),
        (0, "matters a lot."),
    ]


def test_keeps_backchannel_before_continuation():
    # 「perfect place | Yes. | To talk」: "Yes." は話者Aのまま、"To" だけ話者Bへ
    utt = _utt(
        (1, "I think it's the perfect place"), (0, "Yes. To"), (1, "talk about art.")
    )
    segments, snapped = split_by_word_speaker([utt])
    assert snapped == 1
    assert _texts(segments) == [
        (1, "I think it's the perfect place"),
        (0, "Yes."),
        (1, "To talk about art."),
    ]


def test_does_not_move_more_than_two_words():
    # 3語以上の食い違いは本当の割り込みかもしれないのでDeepgramの判定を優先する
    utt = _utt((0, "We were talking about the"), (1, "very long interruption here."))
    segments, snapped = split_by_word_speaker([utt])
    assert snapped == 0
    assert len(segments) == 2


def test_does_not_move_across_long_pause():
    a = _utt((0, "And"))
    b = _utt((1, "it's going to be a ride."))
    for w in b["words"]:
        w["start"] += 5.0
        w["end"] += 5.0
    segments, snapped = split_by_word_speaker([a, b])
    assert snapped == 0
    assert _texts(segments) == [(0, "And"), (1, "it's going to be a ride.")]


def test_snap_disabled():
    utt = _utt((0, "Yes. To"), (1, "talk about art."))
    segments, snapped = split_by_word_speaker([utt], snap=False)
    assert snapped == 0
    assert _texts(segments) == [(0, "Yes. To"), (1, "talk about art.")]
