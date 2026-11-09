"""辞書（dictionary.csv）作成のアシスト機能。

Gradio の「📖 辞書」タブから使う、UI に依存しないロジックをまとめる。

- 辞書CSVを表として読み書きする（`# ---` で始まるコメント行・並び順を保持）
- 文字起こし・講義資料のテキストから、辞書未登録の固有名詞・頭字語を候補として抽出する
- PDF / テキストファイルからテキストを取り出す
- Gemini に専門用語の抽出・訳語の提案をさせる（任意。APIキーがあるときだけ）
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from real_time_translation.translation.dictionary import TermDictionary
from real_time_translation.translation.terminology_check import check_terminology

# 表の列: 原語, 訳語, メモ
DictionaryRow = list[str]

# 候補表の列（UIの gr.Dataframe と同じ順序）
CANDIDATE_HEADERS = ["追加", "原語", "訳語（提案）", "出現回数", "種類", "文脈"]


# ---------------------------------------------------------------------------
# 辞書CSVの読み書き
# ---------------------------------------------------------------------------


def _is_comment_row(row: DictionaryRow) -> bool:
    return bool(row) and row[0].lstrip().startswith("#")


def read_dictionary_rows(path: Path | str) -> list[DictionaryRow]:
    """辞書CSVを [原語, 訳語, メモ] の行リストとして読む（ヘッダー行は除く）。

    `# --- ASR / 音声認識 ---` のようなコメント行は、原語の列に行全体を入れた
    行として残す。表で編集して保存してもコメント・並び順が崩れないようにするため。
    存在しないファイルは空の辞書として扱う。
    """
    path = Path(path)
    if not path.exists():
        return []

    rows: list[DictionaryRow] = []
    with path.open(encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f):
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            if line.lstrip().startswith("#"):
                rows.append([line, "", ""])
                continue
            parsed = next(csv.reader([line]), [])
            if (
                line_no == 0
                and parsed
                and parsed[0].strip().lower()
                in (
                    "source",
                    "source_term",
                    "原語",
                )
            ):
                continue
            cells = [c.strip() for c in parsed[:3]]
            rows.append(cells + [""] * (3 - len(cells)))
    return rows


@dataclass
class SaveReport:
    """辞書保存の結果。"""

    saved: int
    skipped_incomplete: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    backup_path: Path | None = None


def normalize_rows(rows: list[list[Any]]) -> list[DictionaryRow]:
    """UIの表から来た値（None・数値・余分な列を含みうる）を文字列3列に揃える。"""
    normalized: list[DictionaryRow] = []
    for row in rows:
        cells = ["" if c is None else str(c).strip() for c in list(row)[:3]]
        cells += [""] * (3 - len(cells))
        if not any(cells):
            continue
        normalized.append(cells)
    return normalized


def write_dictionary_rows(path: Path | str, rows: list[list[Any]]) -> SaveReport:
    """表の行を辞書CSVとして保存する。

    - 原語・訳語のどちらかが空の行は保存しない（`TermDictionary` が読み飛ばすため）
    - 原語の重複（大文字小文字を区別しない）は保存するが報告する。
      `TermDictionary` では後の行が優先される
    - 上書き前の内容を `<name>.bak` に退避する
    """
    path = Path(path)
    report = SaveReport(saved=0)
    seen: set[str] = set()

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["source_term", "target_term", "notes"])
    for row in normalize_rows(rows):
        if _is_comment_row(row):
            buf.write(row[0] + "\n")
            continue
        source, target, notes = row
        if not source or not target:
            report.skipped_incomplete.append(source or target)
            continue
        key = source.lower()
        if key in seen:
            report.duplicates.append(source)
        seen.add(key)
        writer.writerow([source, target, notes])
        report.saved += 1

    if path.exists():
        backup = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup)
        report.backup_path = backup
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buf.getvalue(), encoding="utf-8", newline="")
    return report


def rows_to_dictionary(rows: list[list[Any]]) -> TermDictionary:
    """表の行から `TermDictionary` を作る（未保存の編集内容でも照合できるように）。"""
    dictionary = TermDictionary()
    for source, target, notes in normalize_rows(rows):
        if source.lstrip().startswith("#") or not source or not target:
            continue
        dictionary.add_entry(source, target, notes)
    return dictionary


def merge_candidates_into_rows(
    rows: list[list[Any]], candidates: list[list[Any]]
) -> tuple[list[DictionaryRow], list[str], list[str]]:
    """候補表で「追加」にチェックが入った行を辞書の行の末尾に足す。

    Returns:
        (新しい辞書の行, 追加した原語, 訳語が空で追加できなかった原語)
    """
    merged = normalize_rows(rows)
    existing = {r[0].lower() for r in merged if not _is_comment_row(r)}
    added: list[str] = []
    missing_target: list[str] = []
    for cand in candidates:
        if len(cand) < 3 or not _truthy(cand[0]):
            continue
        source = str(cand[1] or "").strip()
        target = str(cand[2] or "").strip()
        if not source or source.lower() in existing:
            continue
        if not target:
            missing_target.append(source)
            continue
        kind = str(cand[4] or "").strip() if len(cand) > 4 else ""
        merged.append([source, target, f"辞書アシストで追加（{kind}）" if kind else ""])
        existing.add(source.lower())
        added.append(source)
    return merged, added, missing_target


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "✓", "x")
    return bool(value)


# ---------------------------------------------------------------------------
# 候補抽出（ルールベース）
# ---------------------------------------------------------------------------

# 頭字語・モデル名: 大文字が2文字以上、または大文字+数字を含む語（GPT-3, T5, BERT,
# PaLM, MoE, LLaMA, ChatGPT, GPT-4o など）。ハイフン・ドットでつながった部分も含める。
_ACRONYM_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?=[A-Za-z0-9.\-]*[A-Z][A-Za-z0-9.\-]*[A-Z0-9])"
    r"[A-Za-z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*"
    r"(?![A-Za-z0-9])"
)
# 大文字で始まる語の連続（"Federal Reserve", "Mixture of Experts" など）。
# 間に of / the / and / for / de を1語だけ挟んでもよい。
_CAPITALIZED_PHRASE_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"[A-Z][a-z][A-Za-z\-]*"
    r"(?:\s+(?:(?:of|the|and|for|de)\s+)?[A-Z][a-z][A-Za-z\-]*)*"
)
_DOTTED_ABBREV_RE = re.compile(r"(?:[A-Za-z]\.)+[A-Za-z]?")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")

# 文頭などで大文字になるだけの一般語。単独の大文字語・フレーズの先頭から除外する。
_STOPWORDS = frozenset(
    """
    a an and are as at be but by can could did do does for from had has have he her
    here him his how i if in into is it its just let like maybe me my no not now of
    off ok okay on one or our out over really right she so some than that the their
    them then there these they this those to too two up us very was we well were
    what when where which while who why will with would yeah yes you your also all
    any because both each even every first last many most much next only other same
    second since still such third through today tomorrow yesterday mr mrs ms dr
    thank thanks hello hi good great sure actually basically again another before
    after between during about above below under three four five six seven eight
    nine ten monday tuesday wednesday thursday friday saturday sunday january
    february march april may june july august september october november december
    """.split()  # noqa: SIM905
)
# 頭字語の形をしていても辞書に入れる意味がほぼないもの
_ACRONYM_STOPWORDS = frozenset({"OK", "AM", "PM", "TV", "ID", "OH", "UM", "UH"})


@dataclass
class TermCandidate:
    """辞書に未登録の用語候補。"""

    term: str
    count: int
    kind: str  # "頭字語・モデル名" / "固有名詞" / "専門用語（Gemini）"
    context: str
    suggested_target: str = ""

    def to_row(self, checked: bool = False) -> list[Any]:
        return [
            checked,
            self.term,
            self.suggested_target,
            self.count,
            self.kind,
            self.context,
        ]


def _registered_keys(dictionary: TermDictionary) -> set[str]:
    keys: set[str] = set()
    for entry in dictionary.entries():
        keys.add(entry.source_term.strip().lower())
        keys.add(entry.target_term.strip().lower())
    return keys


def _context_snippet(sentence: str, term: str, width: int = 80) -> str:
    sentence = " ".join(sentence.split())
    idx = sentence.find(term)
    if idx < 0 or len(sentence) <= width:
        return sentence[:width]
    start = max(0, idx - (width - len(term)) // 2)
    snippet = sentence[start : start + width]
    return (
        ("…" if start > 0 else "")
        + snippet
        + ("…" if start + width < len(sentence) else "")
    )


def _strip_stopwords(words: list[str]) -> list[str]:
    while words and words[0].lower() in _STOPWORDS:
        words = words[1:]
    while words and words[-1].lower() in _STOPWORDS:
        words = words[:-1]
    return words


def extract_term_candidates(
    text: str,
    dictionary: TermDictionary,
    min_count: int = 2,
    max_candidates: int = 200,
) -> list[TermCandidate]:
    """テキストから辞書未登録の頭字語・モデル名・固有名詞を抽出する。

    - 頭字語・モデル名（GPT-3, T5, PaLM など）は1回でも出れば候補にする。
      訳語は原語のまま（「そのまま使う」用語）を提案する
    - 大文字で始まる語・フレーズ（Federal Reserve, Deepgram など）は文頭を除いて
      `min_count` 回以上出たものだけを候補にする（スライドの見出しのように
      全単語が大文字始まりの文で候補が大量に出るのを抑えるため）
    - 小文字だけの専門用語（memory wall 等）はルールでは拾えないので
      `llm_extract_terms` を使う
    """
    registered = _registered_keys(dictionary)
    counts: Counter[str] = Counter()
    kinds: dict[str, str] = {}
    contexts: dict[str, str] = {}
    display: dict[str, str] = {}

    def add(term: str, kind: str, sentence: str) -> None:
        key = term.lower()
        if key in registered:
            return
        counts[key] += 1
        if key not in display:
            display[key] = term
            kinds[key] = kind
            contexts[key] = _context_snippet(sentence, term)
        elif kind == "頭字語・モデル名":
            kinds[key] = kind

    for sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        acronym_spans: list[tuple[int, int]] = []
        for m in _ACRONYM_RE.finditer(sentence):
            term = m.group(0).rstrip(".-")
            if len(term) < 2 or term.upper() in _ACRONYM_STOPWORDS:
                continue
            if term.isupper() and term.lower() in _STOPWORDS:  # "I", "A", "IT" 等
                continue
            if _DOTTED_ABBREV_RE.fullmatch(term):  # "U.S", "e.g" 等の略記
                continue
            acronym_spans.append(m.span())
            add(term, "頭字語・モデル名", sentence)

        for m in _CAPITALIZED_PHRASE_RE.finditer(sentence):
            phrase = m.group(0)
            # 頭字語として拾った部分（"Then DeepSeek-V3" の "DeepSeek-V3" 等）より前だけを使う
            for s, e in acronym_spans:
                if s < m.end() and e > m.start():
                    phrase = sentence[m.start() : max(s, m.start())]
                    break
            words = phrase.split()
            at_sentence_start = sentence[: m.start()].strip(" \"'([-") == ""
            if at_sentence_start:
                words = words[1:] if len(words) == 1 else _strip_stopwords(words)
            else:
                words = _strip_stopwords(words)
            if not words:
                continue
            term = " ".join(words)
            if len(term) < 3:
                continue
            add(term, "固有名詞", sentence)

    candidates = [
        TermCandidate(
            term=display[key],
            count=count,
            kind=kinds[key],
            context=contexts[key],
            suggested_target=display[key] if kinds[key] == "頭字語・モデル名" else "",
        )
        for key, count in counts.items()
        if kinds[key] == "頭字語・モデル名" or count >= min_count
    ]
    candidates.sort(key=lambda c: (-c.count, c.term.lower()))
    return candidates[:max_candidates]


# ---------------------------------------------------------------------------
# 翻訳結果の振り返り（用語漏れ + 未登録用語）
# ---------------------------------------------------------------------------


@dataclass
class TranslationReview:
    """直近の翻訳結果から見た辞書の改善点。"""

    misses: list[list[str]]  # [原語, 辞書の訳語, 実際の訳文の例]
    candidates: list[TermCandidate]


def review_translation_pairs(
    pairs: list[tuple[str, str]],
    dictionary: TermDictionary,
    min_count: int = 2,
) -> TranslationReview:
    """原文・訳文ペアから、守られなかった辞書の用語と、未登録の用語候補を出す。"""
    misses: list[list[str]] = []
    for miss in check_terminology(pairs, dictionary).misses:
        example = ""
        needle = miss.source_term.lower()
        for src, tgt in pairs:
            if needle in src.lower():
                example = f"{src} → {tgt}"
                break
        misses.append([miss.source_term, miss.target_term, example])

    source_text = "\n".join(src for src, _ in pairs)
    candidates = extract_term_candidates(source_text, dictionary, min_count=min_count)
    for cand in candidates:
        for src, tgt in pairs:
            if cand.term in src:
                cand.context = f"{_context_snippet(src, cand.term)} → {tgt[:60]}"
                break
    return TranslationReview(misses=misses, candidates=candidates)


# ---------------------------------------------------------------------------
# ファイルからのテキスト抽出
# ---------------------------------------------------------------------------

TEXT_SUFFIXES = (".txt", ".md", ".srt", ".vtt", ".csv", ".json")


def extract_text_from_file(path: Path | str) -> str:
    """PDF / テキスト（.txt .md .srt .vtt など）から本文テキストを取り出す。"""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if suffix in (".srt", ".vtt"):
        return _subtitle_text(path.read_text(encoding="utf-8-sig", errors="replace"))
    return path.read_text(encoding="utf-8-sig", errors="replace")


_SRT_TIMING_RE = re.compile(r"\d{1,2}:\d{2}:\d{2}[.,]\d{3}\s*-->")


def _subtitle_text(raw: str) -> str:
    """SRT/VTT から番号・タイムコード行を除いた字幕本文を取り出す。"""
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.isdigit() or stripped == "WEBVTT":
            continue
        if _SRT_TIMING_RE.search(stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gemini による抽出・訳語提案（任意）
# ---------------------------------------------------------------------------

_LLM_TEXT_LIMIT = 30000  # プロンプトに入れる本文の上限（文字数）

_EXTRACT_PROMPT = """\
You are building a terminology dictionary for translating {domain} lectures \
from {source} into {target}.
From the text below, list technical terms, proper nouns, model/product names and \
acronyms that a translator must render consistently. Skip common everyday words and \
terms already in the dictionary.
For each term give the {target} translation used by experts in this field. \
If the term should be kept as-is (acronyms, model names, product names), \
give the original term as the translation.

Already in the dictionary (do not repeat):
{existing}

Return only JSON: {{"terms": [{{"source": "...", "target": "...", "note": "short reason"}}]}}
At most {max_terms} terms, most important first.

Text:
\"\"\"
{text}
\"\"\"
"""

_SUGGEST_PROMPT = """\
Translate each {source} term into {target} as used by experts in {domain}. \
Keep acronyms, model names and product names as-is.
Return only JSON: {{"terms": [{{"source": "...", "target": "..."}}]}}

Terms:
{terms}
"""


def build_extract_prompt(
    text: str,
    dictionary: TermDictionary,
    source_language: str = "English",
    target_language: str = "Japanese",
    domain: str = "general",
    max_terms: int = 60,
) -> str:
    existing = ", ".join(sorted({e.source_term for e in dictionary.entries()}))
    return _EXTRACT_PROMPT.format(
        domain=domain,
        source=source_language,
        target=target_language,
        existing=existing or "(none)",
        max_terms=max_terms,
        text=text[:_LLM_TEXT_LIMIT],
    )


def build_suggest_prompt(
    terms: list[str],
    source_language: str = "English",
    target_language: str = "Japanese",
    domain: str = "general",
) -> str:
    return _SUGGEST_PROMPT.format(
        source=source_language,
        target=target_language,
        domain=domain,
        terms="\n".join(f"- {t}" for t in terms),
    )


def parse_llm_terms(content: str) -> list[dict[str, str]]:
    """LLM応答（```json フェンス付きでもよい）から用語リストを取り出す。"""
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    terms = data.get("terms") if isinstance(data, dict) else None
    if not isinstance(terms, list):
        return []
    result: list[dict[str, str]] = []
    for item in terms:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        if not source:
            continue
        result.append(
            {
                "source": source,
                "target": str(item.get("target") or "").strip(),
                "note": str(item.get("note") or "").strip(),
            }
        )
    return result


async def _call_gemini_json(prompt: str, api_key: str, model: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
    )
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=prompt,
        config=config,
    )
    return response.text or ""


async def llm_extract_terms(
    text: str,
    dictionary: TermDictionary,
    api_key: str,
    model: str,
    source_language: str = "English",
    target_language: str = "Japanese",
    domain: str = "general",
) -> list[TermCandidate]:
    """Gemini に専門用語を抽出させ、訳語の提案つきの候補にする。

    ルールベースでは拾えない小文字の専門用語（memory wall, mixture of experts 等）
    を拾うためのもの。辞書登録済みの用語は除外する。
    """
    prompt = build_extract_prompt(
        text, dictionary, source_language, target_language, domain
    )
    items = parse_llm_terms(await _call_gemini_json(prompt, api_key, model))
    registered = _registered_keys(dictionary)
    lowered_text = text.lower()
    candidates: list[TermCandidate] = []
    seen: set[str] = set()
    for item in items:
        key = item["source"].lower()
        if key in registered or key in seen:
            continue
        seen.add(key)
        count = lowered_text.count(key)
        context = ""
        for sentence in _SENTENCE_SPLIT_RE.split(text):
            if key in sentence.lower():
                idx = sentence.lower().find(key)
                context = _context_snippet(sentence, sentence[idx : idx + len(key)])
                break
        if not context and item["note"]:
            context = item["note"]
        candidates.append(
            TermCandidate(
                term=item["source"],
                count=count,
                kind="専門用語（Gemini）",
                context=context,
                suggested_target=item["target"],
            )
        )
    return candidates


async def llm_suggest_targets(
    terms: list[str],
    api_key: str,
    model: str,
    source_language: str = "English",
    target_language: str = "Japanese",
    domain: str = "general",
) -> dict[str, str]:
    """原語のリストに対し Gemini に訳語を提案させる（原語の小文字 → 訳語）。"""
    if not terms:
        return {}
    prompt = build_suggest_prompt(terms, source_language, target_language, domain)
    items = parse_llm_terms(await _call_gemini_json(prompt, api_key, model))
    return {i["source"].lower(): i["target"] for i in items if i["target"]}
