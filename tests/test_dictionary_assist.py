"""Tests for translation.dictionary_assist."""

from pathlib import Path

from real_time_translation.translation.dictionary import TermDictionary
from real_time_translation.translation.dictionary_assist import (
    extract_term_candidates,
    extract_text_from_file,
    merge_candidates_into_rows,
    parse_llm_terms,
    read_dictionary_rows,
    review_translation_pairs,
    rows_to_dictionary,
    write_dictionary_rows,
)

_CSV = """source_term,target_term,notes
API,API,そのまま使用
# --- ASR / 音声認識 ---
machine learning,機械学習,
TIFINE,T5,"誤認識, 補正用"
"""


def _terms(candidates) -> list[str]:
    return [c.term for c in candidates]


def test_read_keeps_comment_rows_and_skips_header(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    path.write_text(_CSV, encoding="utf-8")

    rows = read_dictionary_rows(path)

    assert rows == [
        ["API", "API", "そのまま使用"],
        ["# --- ASR / 音声認識 ---", "", ""],
        ["machine learning", "機械学習", ""],
        ["TIFINE", "T5", "誤認識, 補正用"],
    ]


def test_read_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_dictionary_rows(tmp_path / "none.csv") == []


def test_write_round_trip_preserves_entries_comments_and_backup(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    path.write_text(_CSV, encoding="utf-8")

    report = write_dictionary_rows(path, read_dictionary_rows(path))

    assert report.saved == 3
    assert path.read_text(encoding="utf-8") == _CSV
    assert report.backup_path is not None and report.backup_path.exists()
    d = TermDictionary()
    assert d.load_csv(path) == 3
    assert d.get("tifine").notes == "誤認識, 補正用"


def test_write_skips_incomplete_rows_and_reports_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    rows = [
        ["GPT-3", "GPT-3", None],
        ["memory wall", "", ""],
        ["gpt-3", "GPT-3", "dup"],
        [None, None, None],
    ]

    report = write_dictionary_rows(path, rows)

    assert report.saved == 2
    assert report.skipped_incomplete == ["memory wall"]
    assert report.duplicates == ["gpt-3"]


def test_extract_acronyms_and_repeated_proper_nouns() -> None:
    text = (
        "Today we talk about GPT-3 and PaLM. The Switch Transformer from Google Brain "
        "is sparse.\nThe Switch Transformer uses routing. Google Brain proposed GLaM. "
        "I think it is OK. Then DeepSeek-V3 came, e.g. in the U.S."
    )

    terms = _terms(extract_term_candidates(text, TermDictionary(), min_count=2))

    for expected in [
        "GPT-3",
        "PaLM",
        "GLaM",
        "DeepSeek-V3",
        "Switch Transformer",
        "Google Brain",
    ]:
        assert expected in terms
    for noise in ["I", "OK", "Today", "Then", "The", "U.S", "DeepSeek-V"]:
        assert noise not in terms


def test_extract_suggests_keep_as_is_for_acronyms_only() -> None:
    text = "We use BERT here. Then Google Brain again. Also Google Brain."

    by_term = {c.term: c for c in extract_term_candidates(text, TermDictionary())}

    assert by_term["BERT"].suggested_target == "BERT"
    assert by_term["Google Brain"].suggested_target == ""
    assert by_term["Google Brain"].count == 2


def test_extract_excludes_registered_terms_case_insensitively() -> None:
    d = TermDictionary()
    d.add_entry("MoE", "MoE")
    d.add_entry("TIFINE", "T5")

    terms = _terms(extract_term_candidates("MOE and T5 and TIFINE and BERT.", d))

    assert terms == ["BERT"]


def test_single_capitalized_word_needs_min_count() -> None:
    text = "We called Deepgram. Then we called Deepgram again."

    assert "Deepgram" in _terms(
        extract_term_candidates(text, TermDictionary(), min_count=2)
    )
    assert "Deepgram" not in _terms(
        extract_term_candidates(text, TermDictionary(), min_count=3)
    )


def test_merge_candidates_adds_only_checked_rows_with_target() -> None:
    rows = [["API", "API", ""]]
    candidates = [
        [True, "BERT", "BERT", 2, "頭字語・モデル名", ""],
        [True, "memory wall", "", 1, "専門用語（Gemini）", ""],
        [False, "PaLM", "PaLM", 1, "頭字語・モデル名", ""],
        ["true", "api", "API", 1, "頭字語・モデル名", ""],  # 登録済み
    ]

    merged, added, missing = merge_candidates_into_rows(rows, candidates)

    assert added == ["BERT"]
    assert missing == ["memory wall"]
    assert merged[-1][:2] == ["BERT", "BERT"]
    assert len(merged) == 2


def test_review_reports_misses_with_example_and_unregistered_terms() -> None:
    d = rows_to_dictionary([["memory wall", "メモリウォール", ""], ["# c", "", ""]])
    pairs = [
        ("We hit the memory wall with GPT-4.", "GPT-4でメモリーの壁に当たる。"),
        ("That is all.", "以上です。"),
    ]

    review = review_translation_pairs(pairs, d)

    assert review.misses == [
        [
            "memory wall",
            "メモリウォール",
            "We hit the memory wall with GPT-4. → GPT-4でメモリーの壁に当たる。",
        ]
    ]
    assert _terms(review.candidates) == ["GPT-4"]
    assert "→" in review.candidates[0].context


def test_parse_llm_terms_handles_fences_and_garbage() -> None:
    content = '```json\n{"terms": [{"source": "memory wall", "target": "メモリウォール"}, {"x": 1}]}\n```'

    assert parse_llm_terms(content) == [
        {"source": "memory wall", "target": "メモリウォール", "note": ""}
    ]
    assert parse_llm_terms("not json") == []
    assert parse_llm_terms('{"terms": "oops"}') == []


def test_extract_text_from_srt_drops_numbers_and_timings(tmp_path: Path) -> None:
    path = tmp_path / "a.srt"
    path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello GPT-3\n\n2\n00:00:03,000 --> 00:00:04,000\nBye\n",
        encoding="utf-8",
    )

    assert extract_text_from_file(path) == "Hello GPT-3\nBye"
