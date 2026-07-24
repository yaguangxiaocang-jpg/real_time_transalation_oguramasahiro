"""用語辞書が実際に守られたかを検証する。

`LLMTranslator` は用語辞書をシステムプロンプトに埋め込んで指示するだけで、
LLMが指示通りに用語を使ったかどうかは検証していない。ここでは
「原文にその用語が出現したのに、訳文に期待する訳語が出ていない」ケースを
検出する。`lecture_subtitle_translator`（TypeScript版）の `terminologyCheck.ts`
と同じロジック。
"""

from __future__ import annotations

from dataclasses import dataclass

from real_time_translation.translation.dictionary import TermDictionary


@dataclass(frozen=True)
class TerminologyMiss:
    """用語漏れ1件。"""

    source_term: str
    target_term: str


@dataclass(frozen=True)
class TerminologyCheckResult:
    """用語辞書カバレッジ検査の結果。"""

    ok: bool
    misses: list[TerminologyMiss]


def check_terminology(
    pairs: list[tuple[str, str]],
    dictionary: TermDictionary,
) -> TerminologyCheckResult:
    """原文・訳文ペアの集合に対し、辞書の用語が守られているか検査する。

    Args:
        pairs: (原文, 訳文) のペアのリスト（セッション/ジョブ全体で蓄積したもの）
        dictionary: 参照する用語辞書

    Returns:
        ok=Trueなら漏れなし。misses に漏れた用語の一覧。
    """
    if not dictionary:
        return TerminologyCheckResult(ok=True, misses=[])

    all_source = " ".join(src for src, _ in pairs).lower()
    all_target = " ".join(tgt for _, tgt in pairs)

    misses: list[TerminologyMiss] = []
    for entry in dictionary.entries():
        source_term = entry.source_term.strip()
        target_term = entry.target_term.strip()
        if not source_term or not target_term:
            continue

        if source_term.lower() not in all_source:
            continue  # そもそも原文に出てきていない用語は対象外

        if target_term not in all_target:
            misses.append(
                TerminologyMiss(source_term=source_term, target_term=target_term)
            )

    return TerminologyCheckResult(ok=len(misses) == 0, misses=misses)


def format_terminology_misses(misses: list[TerminologyMiss]) -> str:
    """人間向けの1行サマリを生成する。"""
    if not misses:
        return "用語漏れ: なし"
    joined = ", ".join(f"{m.source_term}→{m.target_term}" for m in misses)
    return f"⚠️ 用語漏れ {len(misses)}件: {joined}"
