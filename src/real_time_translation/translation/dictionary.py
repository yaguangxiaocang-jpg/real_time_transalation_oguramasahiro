"""Dictionary management for domain-specific terminology."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

# ASR（Deepgram）のキーワードブースト対象として妥当な用語かの判定用。
# 英数字・スペース・ハイフンのみで構成される表記（頭字語・モデル名など）を想定。
_ASCII_TERM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-\.]*$")


@dataclass
class DictionaryEntry:
    """A single dictionary entry."""

    source_term: str
    target_term: str
    notes: str = ""


class TermDictionary:
    """Dictionary for domain-specific terminology.

    Manages terminology mappings loaded from CSV files.
    CSV format: source_term,target_term,notes (optional)
    """

    def __init__(self) -> None:
        """Initialize empty dictionary."""
        self._entries: dict[str, DictionaryEntry] = {}

    def load_csv(self, path: Path | str) -> int:
        """Load dictionary entries from CSV file.

        Args:
            path: Path to CSV file

        Returns:
            Number of entries loaded
        """
        path = Path(path)
        count = 0

        with path.open(encoding="utf-8") as f:
            reader = csv.reader(f)

            # Skip header if present
            first_row = next(reader, None)
            header_values = ("source", "source_term", "原語")
            if first_row and first_row[0].lower() not in header_values:
                # Not a header, process as data
                self._add_row(first_row)
                count += 1

            for row in reader:
                if self._add_row(row):
                    count += 1

        return count

    def _add_row(self, row: list[str]) -> bool:
        """Add a row from CSV.

        Args:
            row: CSV row data

        Returns:
            True if entry was added
        """
        if len(row) < 2:
            return False

        source_term = row[0].strip()
        target_term = row[1].strip()
        notes = row[2].strip() if len(row) > 2 else ""

        if not source_term or not target_term:
            return False

        self._entries[source_term.lower()] = DictionaryEntry(
            source_term=source_term,
            target_term=target_term,
            notes=notes,
        )
        return True

    def add_entry(self, source_term: str, target_term: str, notes: str = "") -> None:
        """Add a dictionary entry.

        Args:
            source_term: Term in source language
            target_term: Term in target language
            notes: Optional notes about the term
        """
        self._entries[source_term.lower()] = DictionaryEntry(
            source_term=source_term,
            target_term=target_term,
            notes=notes,
        )

    def get(self, term: str) -> DictionaryEntry | None:
        """Look up a term.

        Args:
            term: Term to look up

        Returns:
            Dictionary entry or None if not found
        """
        return self._entries.get(term.lower())

    def entries(self) -> list[DictionaryEntry]:
        """Return all dictionary entries.

        Returns:
            List of all entries (order not guaranteed)
        """
        return list(self._entries.values())

    def format_for_prompt(self) -> str:
        """Format dictionary for inclusion in LLM prompt.

        Returns:
            Formatted dictionary string
        """
        if not self._entries:
            return ""

        lines = ["[Terminology Dictionary - Use these exact translations:]"]
        for entry in self._entries.values():
            line = f"- {entry.source_term} → {entry.target_term}"
            if entry.notes:
                line += f" ({entry.notes})"
            lines.append(line)

        return "\n".join(lines)

    def keep_as_is_terms(self) -> list[str]:
        """翻訳時に変換されず「そのまま使う」用語だけを抽出する（重複除去）。

        source_term と target_term が一致するエントリ（例: `T5,T5`, `PaLM,PaLM`,
        `MOE,MOE`, `AWS,AWS`）は、翻訳時に変換されない固有名詞・頭字語・モデル名
        であり、かつASR誤認識対策として `dictionary.csv` に事前登録されている
        用語群と重なる（2026-08-11の調査参照）。source != target のエントリ
        （通常の訳語ペアや、`TIFINE,T5,...` のようなASR誤認識パターン補正用の
        エントリ）は対象外とする——後者を含めるとDeepgramに誤認識形そのもの
        （"TIFINE"等）を強化してしまい逆効果になるため。

        `as_asr_keywords`（Deepgramブースト用）と
        `whisper_reverify.reverify_terms`（Whisper再検証用）の両方から使われる。

        Returns:
            用語文字列のリスト（元の表記のまま、boost値等の付加情報なし）。
        """
        keywords: list[str] = []
        seen: set[str] = set()
        for entry in self._entries.values():
            term = entry.source_term.strip()
            if term.lower() != entry.target_term.strip().lower():
                continue
            if not _ASCII_TERM_RE.match(term):
                continue
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            keywords.append(term)
        return keywords

    def as_asr_keywords(self, boost: float = 2.0) -> list[str]:
        """Deepgramのキーワードブースト用に「そのまま使う」用語だけを抽出する。

        Returns:
            "term:boost" 形式の文字列リスト（Deepgram `keywords` パラメータ用）。
        """
        return [f"{term}:{boost}" for term in self.keep_as_is_terms()]

    def __len__(self) -> int:
        """Return number of entries."""
        return len(self._entries)

    def __bool__(self) -> bool:
        """Return True if dictionary has entries."""
        return bool(self._entries)
