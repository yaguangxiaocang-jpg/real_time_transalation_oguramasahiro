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
   （`min_confidence`）。`whisper_client.transcribe_pcm_with_whisper`が
   返す`faster-whisper`の単語ごとの`probability`を使い、確信度の低い聞き取りを
   採用しない。

**2026-09-07のmin_confidenceチューニング**（`whisper_reverify_confidence_sweep.py`、
report.txtの優先課題(2)対応）: 上記ガード追加直後の値（0.6）で
`technology_moe_2d07bb74_clip{1..5}`を再検証したところ、既知の誤補正
MOA→MOE（confidence 0.616、ガード1で常にブロックされるため閾値と無関係）は
引き続き防げていたが、正しい補正TIFINE→T5（confidence 0.5997）が0.6の
すぐ下で弾かれ、取りこぼしていたことが判明した（faster-whisperはCPU推論の
スレッド間非決定性で同一音声でもconfidenceが実行ごとに微妙にブレるため、
0.6という値はこの1件に対して実質コイントスに近い）。ガード1が既知の
誤補正パターン（MOA/MOE）を信頼度と無関係に独立して防いでいるため、
閾値を下げてもこのパターンが再発するリスクは無い。この観測に基づき既定値を
0.6→0.5に緩和した（0.5997との間に0.1のマージンを持たせる）。

**2026-09-08のハイフン分割トークン化バグ修正**（同じくreport.txtの優先課題(2)
残課題）: 正しい補正のうち「G p t three」→GPT-3だけは、min_confidenceの値に
関わらず一度も発火しなかった。原因はfaster-whisperが`"GPT-3,"`を単語レベル
タイムスタンプ上で`"GPT"`と`"-3,"`という2つの単語トークンに分割して返すことが
あり、空白区切りで結合すると`"gpt -3"`になって辞書の`"gpt-3"`と一致しなかった
ため。信頼度チェック以前にトークン化の時点で候補として成立していなかった
（閾値の問題ではなかった）。空白を除いた結合形（`"gpt-3"`）でも一致を試すよう
修正し、一致した場合はWhisperの生の分割表記ではなく辞書の正式表記
（`"GPT-3"`）を置換文字列として使うようにした。

**2026-09-21の confidence-weighted ROVER 化**（絶対閾値min_confidenceの限界
への対応）: これまでの`min_confidence`は「3件の既知の実例（TIFINE→T5,
G p t three→GPT-3, MOA→MOE誤補正）に対してコイントスにならない値」を
手動で探すチューニングだった（0.6→0.5、`whisper_reverify_confidence_sweep.py`
参照）。faster-whisperの信頼度自体がCPU推論の非決定性でブレるため、
この方式は未知のパターンに対して頑健とは言えない。ROVER（Recognizer Output
Voting Error Reduction, NIST）の系譜にある confidence-weighted ASR
combination（"Automatic Quality Estimation for ASR System Combination",
arXiv:1706.07238 など）は、単一システムの絶対閾値ではなく複数システムの
信頼度を相対比較して採否を決める。これに倣い、Deepgram側の単語レベル信頼度
（`deepgram_word_confidences`、`DeepgramTranscriber`が新たに`words[].confidence`
から取得）を導入した。

ただし実装当初、`replace`区間（原文側にも比較対象の単語がある差分）を
「絶対閾値の代わりに相対比較（Whisper信頼度 > Deepgram信頼度）のみで判定する」
方式にしたところ、実音声（`technology_moe_2d07bb74_clip3`）での検証で既知の
正しい補正TIFINE→T5が退行することが判明した。原因はDeepgramが「t five」という
頻出語列に対して0.83という高い信頼度を報告する一方、Whisperの「T5」は0.82と
わずかに下回っていたこと。**技術用語のASR誤認識は「間違っている側のシステムの
方がむしろ自信満々」というケースが珍しくなく**、これは"Driving ROVER with
Segment-based ASR Quality Estimation"が指摘する「生の信頼度スコアの単純な
比較は頑健ではない」という限界そのものだった。

この実測を踏まえ、相対比較は絶対閾値の**代わり**ではなく**追加の救済経路**
として使う設計に修正した: まず従来通り絶対閾値`min_confidence`で判定し、
それを満たせば採用する（相対比較でDeepgram側がどれだけ自信を持っていても、
既存の正しい補正が失われることはない）。絶対閾値を満たさない場合のみ、
`replace`区間かつDeepgram側信頼度が入手できる場合に限り、「Whisper信頼度 >
その区間のDeepgram信頼度」の相対比較で追加救済を試みる（＝相対比較は基準を
厳しくする方向にではなく、緩める方向にのみ働く）。`insert`区間（脱落語の
補完）や、`deepgram_word_confidences`が渡されない・語数がずれて`text`と
アラインしない場合は、絶対閾値のみで判定する（従来と同じ挙動）。
"""

from __future__ import annotations

import difflib
import re

from real_time_translation.transcription.whisper_client import (
    transcribe_pcm_with_whisper,
)

_WORD_RE = re.compile(r"\S+")
_PUNCT_STRIP = ".,!?;:\"'、。"

DEFAULT_MIN_CONFIDENCE = 0.5


def _normalize(word: str) -> str:
    return word.strip(_PUNCT_STRIP).lower()


def apply_term_corrections(
    text: str,
    whisper_text: str,
    keep_terms: list[str],
    *,
    whisper_word_confidences: list[tuple[str, float]] | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    deepgram_word_confidences: list[tuple[str, float]] | None = None,
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
            含む置換候補は原則採用しない絶対閾値（セーフティネット）。
        deepgram_word_confidences: Deepgram側の(単語, confidence)のリスト
            （`text`をトークナイズした結果と語数が一致している前提）。絶対閾値
            `min_confidence`を満たさなかった`replace`区間（原文側にも比較対象
            の単語がある差分）だけを対象に、「Whisper信頼度 > その区間の
            Deepgram信頼度」の相対比較で追加救済する（confidence-weighted
            ROVER方式）。絶対閾値を満たしている区間は、Deepgram側がどれだけ
            自信を持っていても採用を取り消さない（2026-09-21の実音声検証で、
            相対比較を絶対閾値の代わりに使うと既知の正しい補正TIFINE→T5が
            退行することが判明したため。モジュールdocstring参照）。`None`
            または語数が`text`と合わない場合はこの救済を行わない。

    Returns:
        (補正後テキスト, 実際に補正した用語のリスト)
    """
    if not keep_terms or not whisper_text.strip():
        return text, []

    keep_terms_lower = {t.lower() for t in keep_terms}
    # 小文字形から辞書の正式表記への逆引き（2026-09-08追加、ハイフン分割
    # トークン化対策。同じ小文字形が複数あれば最初の1件を使う）。
    keep_terms_canonical: dict[str, str] = {}
    for t in keep_terms:
        keep_terms_canonical.setdefault(t.lower(), t)
    orig_words = _WORD_RE.findall(text)

    if whisper_word_confidences is not None:
        whisper_words = [w for w, _ in whisper_word_confidences]
        confidences = [c for _, c in whisper_word_confidences]
    else:
        whisper_words = _WORD_RE.findall(whisper_text)
        confidences = None

    if not orig_words or not whisper_words:
        return text, []

    # Deepgram側の単語レベル信頼度が`text`と語数レベルでアラインしている場合のみ
    # 相対比較に使う。ズレている場合（マージ処理の空白挿入など）は安全側に倒し、
    # 絶対閾値へフォールバックする。
    deepgram_confidences: list[float] | None = None
    if deepgram_word_confidences is not None and len(deepgram_word_confidences) == len(
        orig_words
    ):
        deepgram_confidences = [c for _, c in deepgram_word_confidences]

    orig_norm = [_normalize(w) for w in orig_words]
    whisper_norm = [_normalize(w) for w in whisper_words]

    matcher = difflib.SequenceMatcher(a=orig_norm, b=whisper_norm, autojunk=False)

    # (i1, i2, replacement) を先に集めてから、末尾側から適用する。
    # 先頭側から適用すると、リストの長さが変わって後続のインデックスがずれるため。
    ops: list[tuple[int, int, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag not in ("replace", "insert"):
            continue
        candidate_words = whisper_norm[j1:j2]
        candidate_norm = " ".join(candidate_words)
        replacement_text = " ".join(whisper_words[j1:j2])
        if candidate_norm not in keep_terms_lower:
            # faster-whisperがハイフン区切り複合語（例: "GPT-3,"）を
            # "GPT" + "-3," のように複数の単語トークンへ分割して返すことがあり、
            # 空白区切りで結合すると"gpt -3"のようになって辞書の"gpt-3"と
            # 一致しなくなる（2026-09-08発見、report.txtの優先課題(2)残課題）。
            # 空白を除いた結合形でも試し、一致すれば辞書の正式表記
            # （whisperの生の分割表記ではなく）を置換文字列として使う。
            candidate_compact = "".join(candidate_words)
            if candidate_compact not in keep_terms_lower:
                continue
            candidate_norm = candidate_compact
            replacement_text = keep_terms_canonical[candidate_compact]
        if candidate_norm in orig_norm[i1:i2]:
            continue  # 既に一致している
        # ガード1: 原文側が既に別の登録済み用語（例: MOA）なら、Whisper側の
        # 異なる用語（例: MOE）で上書きしない（2026-09-07、MOA/MOE誤補正対策）。
        original_span = " ".join(orig_norm[i1:i2])
        if original_span in keep_terms_lower:
            continue
        # ガード2: Whisper側の信頼度で採否を決める。
        if confidences is not None:
            span_confidences = confidences[j1:j2]
            if not span_confidences:
                continue
            whisper_conf = min(span_confidences)
            passes_absolute = whisper_conf >= min_confidence
            # `replace`区間（原文側にも比較対象の単語がある）でDeepgram側の
            # 信頼度が入手できる場合、相対比較（confidence-weighted ROVER方式。
            # arXiv:1706.07238等）を絶対閾値の「追加の採用経路」として使う。
            # 2026-09-21の実音声検証で、相対比較を絶対閾値の**代わり**に使うと
            # 既知の正しい補正（TIFINE→T5）を退行させることが判明した
            # （原因: Deepgramが"t five"という一般語列に対して0.83という高い
            # 信頼度を報告する一方、Whisperの"T5"は0.82とわずかに下回っており、
            # 相対比較だけでは弾かれてしまう。技術用語のASR誤認識は「間違った側
            # (Deepgram)がむしろ自信満々」というケースが珍しくないため、
            # "Driving ROVER with Segment-based ASR Quality Estimation"が指摘する
            # 通り生の信頼度スコアの相対比較だけでは頑健にならない）。
            # そのため絶対閾値はセーフティネットとして残し、相対比較は絶対閾値
            # 未満で不採用になったケースを追加で救済する用途にのみ使う
            # （＝relative比較は基準を厳しくする方向にではなく、緩める方向にのみ働く）。
            passes_relative = False
            if not passes_absolute and deepgram_confidences is not None and tag == "replace":
                deepgram_conf = min(deepgram_confidences[i1:i2])
                passes_relative = whisper_conf > deepgram_conf
            if not (passes_absolute or passes_relative):
                continue
        ops.append((i1, i2, replacement_text))

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
    deepgram_word_confidences: list[tuple[str, float]] | None = None,
) -> tuple[str, list[str]]:
    """Deepgramの確定文をWhisperで再検証し、既知用語の誤認識のみ補正する。

    ブロッキング呼び出し（faster-whisperのCPU推論）なので、呼び出し側で
    `asyncio.to_thread` + `asyncio.wait_for` によるタイムアウト保護をかけること。

    Args:
        deepgram_word_confidences: Deepgram側の(単語, confidence)のリスト。
            `apply_term_corrections`の同名引数を参照
            （confidence-weighted ROVER方式の相対比較に使う）。

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
        deepgram_word_confidences=deepgram_word_confidences,
    )
