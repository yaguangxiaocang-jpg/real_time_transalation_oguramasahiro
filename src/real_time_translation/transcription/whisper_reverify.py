"""Whisperによる確定文の再検証（ハイブリッドASR構成）。

`whisper_client.py`のdocstringにある通り、2026-08-11の調査でDeepgramが
"T5"→"TIFINE"のような固有名詞・モデル名を誤認識するケースが確認された一方、
faster-whisperは同じ音声を正しく認識できることが多い。

このモジュールは、Deepgramのis_final確定文に対して同じ音声区間を
faster-whisperで再文字起こしし、辞書の「そのまま使う」用語
（`TermDictionary.keep_as_is_terms()`）がDeepgram側で誤認識されていないかを
照合する。乖離が見つかった箇所だけをWhisper側の認識結果へ差し替える
（全文をWhisperの結果で置き換えるとWhisperの幻覚リスクを引き継ぐため、
既知の用語に一致した差分だけを狙い撃ちで補正する）。

`incomplete_end_detector`/`naturalness_detector`と同じ設計方針: 呼び出し側
（`pipeline.py`）がタイムアウト付きで呼び、失敗時は元のDeepgram結果へ
フォールバックする（リアルタイム性を壊さない安全弁）。

2026-08-26のbefore/after検証（README更新履歴・report.txt参照）で、Deepgramが
「MOA」（正しい）と認識した箇所をWhisperが「MOE」と聞き間違え、それを誤って
「補正」として採用してしまう事例（false positive）が実測で見つかった。
これを受けて2026-09-07に2つのガードを追加した:

1. **原文側が既に別の登録済み用語である場合は補正しない**
   （`_is_ambiguous_original`）。Deepgram側の単語自体が`keep_terms`に含まれる
   別の正当な用語（例: MOA）である場合、Whisper側の異なる用語（例: MOE）で
   単純に上書きすると、どちらのASRが正しいか判別できないまま誤った側を
   信じてしまうリスクがある。「原文が未登録語・脱落・崩れた表記のときだけ
   補正する」という元の設計意図に立ち返り、原文自体が有効な用語のときは
   常にスキップする。
2. **Whisper側の単語レベル信頼度が閾値未満なら補正しない**
   （`min_confidence`、既定0.6）。`whisper_client.transcribe_pcm_with_whisper`が
   返す`faster-whisper`の単語ごとの`probability`を使い、確信度の低い聞き取りを
   採用しない。
"""

from __future__ import annotations

import difflib
import re

from real_time_translation.transcription.whisper_client import (
    transcribe_pcm_with_whisper,
)

_WORD_RE = re.compile(r"\S+")
_PUNCT_STRIP = ".,!?;:\"'、。"

DEFAULT_MIN_CONFIDENCE = 0.6


def _normalize(word: str) -> str:
    return word.strip(_PUNCT_STRIP).lower()


def apply_term_corrections(
    text: str,
    whisper_text: str,
    keep_terms: list[str],
    *,
    whisper_word_confidences: list[tuple[str, float]] | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> tuple[str, list[str]]:
    """`text`（Deepgram側）と`whisper_text`（Whisper側）を単語単位で比較し、

    `keep_terms`（辞書の「そのまま使う」用語）に一致する差分だけをWhisper側の
    表記へ差し替える。純粋関数（音声I/Oなし）なのでユニットテストしやすい。

    Args:
        whisper_word_confidences: Whisper側の(単語, confidence)のリスト
            （`transcribe_pcm_with_whisper`が返す単語レベル信頼度、単語の並びが
            `whisper_text`をトークナイズした結果と一致している前提）。`None`なら
            信頼度チェックはスキップする（後方互換・テスト用）。
        min_confidence: `whisper_word_confidences`使用時、この値未満の単語を
            含む置換候補は採用しない。

    Returns:
        (補正後テキスト, 実際に補正した用語のリスト)
    """
    if not keep_terms or not whisper_text.strip():
        return text, []

    keep_terms_lower = {t.lower() for t in keep_terms}
    orig_words = _WORD_RE.findall(text)

    if whisper_word_confidences is not None:
        whisper_words = [w for w, _ in whisper_word_confidences]
        confidences = [c for _, c in whisper_word_confidences]
    else:
        whisper_words = _WORD_RE.findall(whisper_text)
        confidences = None

    if not orig_words or not whisper_words:
        return text, []

    orig_norm = [_normalize(w) for w in orig_words]
    whisper_norm = [_normalize(w) for w in whisper_words]

    matcher = difflib.SequenceMatcher(a=orig_norm, b=whisper_norm, autojunk=False)

    # (i1, i2, replacement) を先に集めてから、末尾側から適用する。
    # 先頭側から適用すると、リストの長さが変わって後続のインデックスがずれるため。
    ops: list[tuple[int, int, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag not in ("replace", "insert"):
            continue
        candidate_norm = " ".join(whisper_norm[j1:j2])
        if candidate_norm not in keep_terms_lower:
            continue
        if candidate_norm in orig_norm[i1:i2]:
            continue  # 既に一致している
        # ガード1: 原文側が既に別の登録済み用語（例: MOA）なら、Whisper側の
        # 異なる用語（例: MOE）で上書きしない（2026-09-07、MOA/MOE誤補正対策）。
        original_span = " ".join(orig_norm[i1:i2])
        if original_span in keep_terms_lower:
            continue
        # ガード2: Whisper側の信頼度が低ければ採用しない。
        if confidences is not None:
            span_confidences = confidences[j1:j2]
            if not span_confidences or min(span_confidences) < min_confidence:
                continue
        ops.append((i1, i2, " ".join(whisper_words[j1:j2])))

    if not ops:
        return text, []

    corrected_words = list(orig_words)
    fixed_terms: list[str] = []
    for i1, i2, replacement in sorted(ops, key=lambda op: op[0], reverse=True):
        corrected_words[i1:i2] = [replacement]
        fixed_terms.append(replacement)

    return " ".join(corrected_words), list(reversed(fixed_terms))


def reverify_terms(
    text: str,
    pcm_audio: bytes,
    keep_terms: list[str],
    *,
    model_size: str = "small.en",
    language: str = "en",
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> tuple[str, list[str]]:
    """Deepgramの確定文をWhisperで再検証し、既知用語の誤認識のみ補正する。

    ブロッキング呼び出し（faster-whisperのCPU推論）なので、呼び出し側で
    `asyncio.to_thread` + `asyncio.wait_for` によるタイムアウト保護をかけること。

    Returns:
        (補正後テキスト, 補正した用語のリスト)
    """
    if not keep_terms or not pcm_audio:
        return text, []

    whisper_text, word_confidences = transcribe_pcm_with_whisper(
        pcm_audio, model_size=model_size, language=language
    )
    return apply_term_corrections(
        text,
        whisper_text,
        keep_terms,
        whisper_word_confidences=word_confidences,
        min_confidence=min_confidence,
    )
