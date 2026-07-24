"""Tests for translation.terminology_check."""

from real_time_translation.translation.dictionary import TermDictionary
from real_time_translation.translation.terminology_check import (
    check_terminology,
    format_terminology_misses,
)


def _dictionary(*entries: tuple[str, str]) -> TermDictionary:
    d = TermDictionary()
    for source, target in entries:
        d.add_entry(source, target)
    return d


def test_ok_when_dictionary_empty() -> None:
    result = check_terminology([("hello world", "こんにちは世界")], TermDictionary())
    assert result.ok is True
    assert result.misses == []


def test_ok_when_term_not_in_source() -> None:
    dictionary = _dictionary(("federal funds rate", "フェデラルファンドレート"))
    pairs = [("hello world", "こんにちは世界")]

    result = check_terminology(pairs, dictionary)
    assert result.ok is True  # 原文に用語がそもそも出てきていないので対象外


def test_ok_when_term_translated_correctly() -> None:
    dictionary = _dictionary(("federal funds rate", "フェデラルファンドレート"))
    pairs = [
        ("The Federal Funds Rate is set by the Fed.", "フェデラルファンドレートはFRBが設定する。"),
    ]

    result = check_terminology(pairs, dictionary)
    assert result.ok is True
    assert result.misses == []


def test_detects_missing_target_term() -> None:
    dictionary = _dictionary(("federal funds rate", "フェデラルファンドレート"))
    pairs = [
        ("The federal funds rate is important.", "その金利は重要です。"),
    ]

    result = check_terminology(pairs, dictionary)
    assert result.ok is False
    assert len(result.misses) == 1
    assert result.misses[0].source_term == "federal funds rate"
    assert result.misses[0].target_term == "フェデラルファンドレート"


def test_case_insensitive_source_matching() -> None:
    dictionary = _dictionary(("GDP", "国内総生産"))
    pairs = [("The gdp grew by 2%.", "国内総生産は2%成長した。")]

    result = check_terminology(pairs, dictionary)
    assert result.ok is True


def test_format_terminology_misses_empty() -> None:
    assert "なし" in format_terminology_misses([])


def test_format_terminology_misses_nonempty() -> None:
    dictionary = _dictionary(("federal funds rate", "フェデラルファンドレート"))
    pairs = [("The federal funds rate is important.", "その金利は重要です。")]
    result = check_terminology(pairs, dictionary)

    text = format_terminology_misses(result.misses)
    assert "federal funds rate" in text
    assert "フェデラルファンドレート" in text
