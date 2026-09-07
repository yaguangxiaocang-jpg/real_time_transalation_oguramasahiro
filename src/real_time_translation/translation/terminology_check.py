"""用語辞書が実際に守られたかを検証する。

`LLMTranslator` は用語辞書をシステムプロンプトに埋め込んで指示するだけで、
LLMが指示通りに用語を使ったかどうかは検証していない。ここでは
「原文にその用語が出現したのに、訳文に期待する訳語が出ていない」ケースを
検出する。`lecture_subtitle_translator`（TypeScript版）の `terminologyCheck.ts`
と同じロジック。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from real_time_translation.translation.dictionary import TermDictionary

# ASCII英数字（頭字語・モデル名等、空白を含んでもよい）のみで構成された用語かどうか。
_ASCII_TERM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-_./]*$")


def _contains_term(haystack: str, term: str) -> bool:
    """termがhaystack中に「単語として」出現するか判定する。

    "PR"や"BI"のような短いASCII頭字語は、単純な部分文字列一致だと
    "process"や"bidirectional"のような無関係な単語の中に偶然含まれてしまい、
    誤検知（実際には登場していないのに用語漏れと判定される）を起こす。
    このためASCII英数字の用語だけは、前後がASCII英数字でないことを条件に
    判定する（例: "process"内の"PR"は前後がASCII文字なので不一致、
    "のPRを"内の"PR"は前後が日本語で挟まれているので一致）。

    正規表現の `\\b` は使わない。Pythonの`\\b`はUnicode対応で日本語の文字も
    「単語文字」とみなすため、"のPRを"のように英字アクロニムが日本語に
    直接隣接する（分かち書きされない）実際の字幕では境界とみなされず、
    今度は逆に見逃し（本当は出現しているのに漏れ扱いになる）を起こす。

    日本語の訳語（例: "フェデラルファンドレート"）はこの前後判定の対象外とし、
    従来通り部分文字列一致で判定する。
    """
    if _ASCII_TERM_RE.match(term):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
        return re.search(pattern, haystack) is not None
    return term in haystack


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

        if not _contains_term(all_source, source_term.lower()):
            continue  # そもそも原文に出てきていない用語は対象外

        if not _contains_term(all_target, target_term):
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
