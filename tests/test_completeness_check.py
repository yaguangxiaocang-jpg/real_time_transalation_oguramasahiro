"""Tests for translation.completeness_check."""

from real_time_translation.translation.completeness_check import CompletenessTracker


def test_no_flag_during_warmup() -> None:
    tracker = CompletenessTracker(min_history_for_judgement=5)

    # 極端に短い訳文でも、履歴が min_history_for_judgement 件たまるまでは判定しない
    for _ in range(4):
        flag = tracker.check(
            "This is a reasonably long source sentence for testing purposes.",
            "短い",
        )
        assert flag is None


def test_no_flag_for_normal_ratio() -> None:
    tracker = CompletenessTracker(min_history_for_judgement=3)

    source = "This is a reasonably long source sentence for testing purposes here."
    translated = "これはテスト目的のための、それなりに長い原文の文です。"

    for _ in range(10):
        flag = tracker.check(source, translated)
        assert flag is None


def test_flags_sudden_short_translation() -> None:
    tracker = CompletenessTracker(min_history_for_judgement=3, ratio_threshold=0.5)

    source = "This is a reasonably long source sentence for testing purposes here."
    translated = "これはテスト目的のための、それなりに長い原文の文です。"

    for _ in range(5):
        assert tracker.check(source, translated) is None

    # 急に短い訳文（中央値の半分未満）が来たらフラグが立つ
    flag = tracker.check(source, "短い。")
    assert flag is not None
    assert flag.flag == "possible_undertranslation"


def test_flags_empty_translation() -> None:
    tracker = CompletenessTracker()

    flag = tracker.check(
        "This is a reasonably long source sentence for testing purposes.", ""
    )
    assert flag is not None
    assert flag.flag == "empty_translation"


def test_short_source_is_never_flagged() -> None:
    tracker = CompletenessTracker(min_source_chars=15)

    flag = tracker.check("Hi.", "")
    assert flag is None
