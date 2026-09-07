"""Tests for translation.dictionary."""

from real_time_translation.translation.dictionary import TermDictionary


def test_keep_as_is_terms_filters_to_same_source_and_target() -> None:
    d = TermDictionary()
    d.add_entry("T5", "T5")
    d.add_entry("federal funds rate", "フェデラルファンドレート")
    d.add_entry("PaLM", "PaLM")

    assert set(d.keep_as_is_terms()) == {"T5", "PaLM"}


def test_keep_as_is_terms_excludes_non_ascii_terms() -> None:
    d = TermDictionary()
    d.add_entry("東京", "東京")
    d.add_entry("AWS", "AWS")

    assert d.keep_as_is_terms() == ["AWS"]


def test_as_asr_keywords_appends_boost_to_keep_as_is_terms() -> None:
    d = TermDictionary()
    d.add_entry("T5", "T5")
    d.add_entry("federal funds rate", "フェデラルファンドレート")

    assert d.as_asr_keywords(boost=3.0) == ["T5:3.0"]
