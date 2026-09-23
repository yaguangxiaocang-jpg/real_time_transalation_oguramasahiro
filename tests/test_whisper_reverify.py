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


def test_deepgram_relative_confidence_allows_low_whisper_confidence() -> None:
    # 2026-09-21追加: confidence-weighted ROVER方式。Deepgram側の元の単語
    # ("TIFINE")の信頼度が非常に低く(0.2)、Whisper側の信頼度(0.3)が絶対閾値
    # (既定0.5)未満でも、Deepgramよりは自信があるなら採用する。
    whisper_text = "The T5 model is great."
    whisper_confidences = [
        ("The", 0.99),
        ("T5", 0.3),
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    deepgram_confidences = [
        ("The", 0.99),
        ("TIFINE", 0.2),
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    text, fixed = apply_term_corrections(
        "The TIFINE model is great.",
        whisper_text,
        ["T5"],
        whisper_word_confidences=whisper_confidences,
        deepgram_word_confidences=deepgram_confidences,
    )
    assert text == "The T5 model is great."
    assert fixed == ["T5"]


def test_deepgram_relative_confidence_does_not_override_absolute_pass() -> None:
    # 2026-09-21の実音声検証（technology_moe_2d07bb74_clip3、README参照）で、
    # 相対比較を絶対閾値の「代わり」に使うと、Deepgram側が誤認識に対して
    # 高い信頼度(0.83)を報告するケース（"t five"）でWhisper側の正しい信頼度
    # (0.82)が僅差で負けて、既知の正しい補正TIFINE→T5が退行することが判明した。
    # そのため相対比較は絶対閾値を満たさない場合の「追加救済」としてのみ働き、
    # 絶対閾値を満たしていればDeepgram側がどれだけ自信を持っていても採用する。
    whisper_text = "The T5 model is great."
    whisper_confidences = [
        ("The", 0.99),
        ("T5", 0.9),  # 絶対閾値(既定0.5)は超えている
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    deepgram_confidences = [
        ("The", 0.99),
        ("TIFINE", 0.95),  # Whisperよりも高い
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    text, fixed = apply_term_corrections(
        "The TIFINE model is great.",
        whisper_text,
        ["T5"],
        whisper_word_confidences=whisper_confidences,
        deepgram_word_confidences=deepgram_confidences,
    )
    assert text == "The T5 model is great."
    assert fixed == ["T5"]


def test_deepgram_relative_confidence_blocks_when_both_absolute_and_relative_fail() -> None:
    # 絶対閾値未満(0.3<0.5)かつDeepgram側の方が自信を持っている(0.6>0.3)場合は
    # 救済されず不採用のまま。
    whisper_text = "The T5 model is great."
    whisper_confidences = [
        ("The", 0.99),
        ("T5", 0.3),
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    deepgram_confidences = [
        ("The", 0.99),
        ("TIFINE", 0.6),
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    text, fixed = apply_term_corrections(
        "The TIFINE model is great.",
        whisper_text,
        ["T5"],
        whisper_word_confidences=whisper_confidences,
        deepgram_word_confidences=deepgram_confidences,
    )
    assert text == "The TIFINE model is great."
    assert fixed == []


def test_deepgram_confidences_misaligned_length_falls_back_to_absolute_threshold() -> None:
    # deepgram_word_confidencesの語数がtextとズレている場合（結合処理での
    # 空白挿入などを想定）は、相対比較を諦めて従来通りの絶対閾値を使う。
    whisper_text = "The T5 model is great."
    whisper_confidences = [
        ("The", 0.99),
        ("T5", 0.95),
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    mismatched_deepgram_confidences = [("The", 0.99), ("TIFINE", 0.99)]
    text, fixed = apply_term_corrections(
        "The TIFINE model is great.",
        whisper_text,
        ["T5"],
        whisper_word_confidences=whisper_confidences,
        deepgram_word_confidences=mismatched_deepgram_confidences,
    )
    assert text == "The T5 model is great."
    assert fixed == ["T5"]


def test_deepgram_confidences_not_used_for_insert_ops() -> None:
    # Deepgramが用語を丸ごと脱落させたケース(insert)は原文側に比較対象の単語が
    # ないため、deepgram_word_confidencesを渡していても絶対閾値にフォールバックする。
    whisper_text = "The T5 model is great."
    whisper_confidences = [
        ("The", 0.99),
        ("T5", 0.3),  # 絶対閾値(既定0.5)未満
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    deepgram_confidences = [
        ("The", 0.99),
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    text, fixed = apply_term_corrections(
        "The model is great.",
        whisper_text,
        ["T5"],
        whisper_word_confidences=whisper_confidences,
        deepgram_word_confidences=deepgram_confidences,
    )
    assert text == "The model is great."
    assert fixed == []


def test_corrects_hyphenated_term_split_across_whisper_word_tokens() -> None:
    # 2026-09-08発見: faster-whisperが"GPT-3,"を単語レベルタイムスタンプ上で
    # "GPT"+"-3,"の2トークンに分割することがあり、空白区切りで結合すると
    # "gpt -3"になって辞書の"GPT-3"と一致しなくなっていた（report.txtの
    # 優先課題(2)残課題）。空白を除いた結合形でも一致を試し、一致すれば
    # 辞書の正式表記（Whisperの生の分割表記ではなく）を使う。
    whisper_text = "The GPT-3, model is great."
    confidences = [
        ("The", 0.99),
        ("GPT", 0.9),
        ("-3,", 0.9),
        ("model", 0.99),
        ("is", 0.99),
        ("great.", 0.99),
    ]
    text, fixed = apply_term_corrections(
        "The g p t three model is great.",
        whisper_text,
        ["GPT-3"],
        whisper_word_confidences=confidences,
    )
    assert text == "The GPT-3 model is great."
    assert fixed == ["GPT-3"]
