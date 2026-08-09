"""Tests for translation.llm_translator._strip_prompt_delimiters."""

from real_time_translation.translation.llm_translator import _strip_prompt_delimiters


def test_no_delimiters_leaves_text_unchanged() -> None:
    text = "このアプローチは、正則化を使ってモデルが新しいデータに過学習するのを防ぎます。"
    assert _strip_prompt_delimiters(text) == text


def test_strips_leaked_closing_target_tag() -> None:
    # 短いチャンクの翻訳でモデルが </target> を出力に混入させた実例
    text = "このアプローチは、正則化を使ってモデルが\n</target>\n新しいデータに過学習するのを防ぎます。"
    result = _strip_prompt_delimiters(text)
    assert "</target>" not in result
    assert "このアプローチは、正則化を使ってモデルが" in result
    assert "新しいデータに過学習するのを防ぎます。" in result


def test_strips_opening_target_and_context_tags() -> None:
    text = "<target>こんにちは</context>"
    result = _strip_prompt_delimiters(text)
    assert "<target>" not in result
    assert "</context>" not in result
    assert result == "こんにちは"


def test_strips_cache_padding_tags_case_insensitive() -> None:
    text = "こんにちは<CACHE_PADDING>世界</Cache_Padding>"
    result = _strip_prompt_delimiters(text)
    assert "cache_padding" not in result.lower()
    assert "こんにちは" in result and "世界" in result


def test_collapses_blank_lines_left_by_stripped_tag() -> None:
    text = "一行目\n\n\n二行目"
    result = _strip_prompt_delimiters(text)
    assert "\n\n" not in result
