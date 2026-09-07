"""Tests for transcription.whisper_reverify (pure term-correction logic)."""

from real_time_translation.transcription.whisper_reverify import (
    apply_term_corrections,
)


def test_no_correction_when_no_keep_terms() -> None:
    text, fixed = apply_term_corrections(
        "The TIFINE model is great.", "The T5 model is great.", []
    )
    assert text == "The TIFINE model is great."
    assert fixed == []


def test_no_correction_when_whisper_text_empty() -> None:
    text, fixed = apply_term_corrections("The TIFINE model is great.", "", ["T5"])
    assert text == "The TIFINE model is great."
    assert fixed == []


def test_corrects_known_term_misrecognition() -> None:
    text, fixed = apply_term_corrections(
        "The TIFINE model is great.",
        "The T5 model is great.",
        ["T5", "PaLM"],
    )
    assert text == "The T5 model is great."
    assert fixed == ["T5"]


def test_no_correction_when_terms_already_match() -> None:
    text, fixed = apply_term_corrections(
        "The T5 model is great.",
        "The T5 model is great.",
        ["T5"],
    )
    assert text == "The T5 model is great."
    assert fixed == []


def test_no_correction_when_replacement_is_not_a_known_term() -> None:
    # Deepgram/Whisperで語尾が違うだけ（辞書用語に無関係）なら補正しない。
    text, fixed = apply_term_corrections(
        "The model runs fast.",
        "The model runs faster.",
        ["T5"],
    )
    assert text == "The model runs fast."
    assert fixed == []


def test_corrects_dropped_term_via_insert() -> None:
    # DeepgramがT5を丸ごと脱落させ、Whisper側にだけ現れているケース。
    text, fixed = apply_term_corrections(
        "The model is great.",
        "The T5 model is great.",
        ["T5"],
    )
    assert "T5" in text
    assert fixed == ["T5"]


def test_multiple_terms_corrected_independently() -> None:
    text, fixed = apply_term_corrections(
        "TIFINE and POM were compared.",
        "T5 and PaLM were compared.",
        ["T5", "PaLM"],
    )
    assert text == "T5 and PaLM were compared."
    assert set(fixed) == {"T5", "PaLM"}


def test_no_correction_when_original_is_already_a_different_known_term() -> None:
    # 2026-09-07追加: 2026-08-26のbefore/after検証で見つかったMOA/MOE誤補正
    # (false positive)の再発防止ガード。DeepgramがMOA（正しい）と認識し、
    # Whisperが別の登録済み用語MOEと聞き間違えた場合、原文側が既に有効な
    # 用語であるため上書きしない。
    text, fixed = apply_term_corrections(
        "We use a MOA architecture here.",
        "We use a MOE architecture here.",
        ["MOA", "MOE"],
    )
    assert text == "We use a MOA architecture here."
    assert fixed == []


def test_confidence_guard_blocks_low_confidence_replacement() -> None:
    # Whisper側の単語信頼度が閾値未満なら採用しない。
    whisper_text = "The T5 model is great."
    confidences = [
        ("The", 0.99),
        ("T5", 0.4),  # 閾値(既定0.6)未満
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    text, fixed = apply_term_corrections(
        "The TIFINE model is great.",
        whisper_text,
        ["T5"],
        whisper_word_confidences=confidences,
    )
    assert text == "The TIFINE model is great."
    assert fixed == []


def test_confidence_guard_allows_high_confidence_replacement() -> None:
    whisper_text = "The T5 model is great."
    confidences = [
        ("The", 0.99),
        ("T5", 0.95),
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    text, fixed = apply_term_corrections(
        "The TIFINE model is great.",
        whisper_text,
        ["T5"],
        whisper_word_confidences=confidences,
    )
    assert text == "The T5 model is great."
    assert fixed == ["T5"]
