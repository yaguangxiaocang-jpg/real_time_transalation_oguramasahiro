"""翻訳の「訳し漏れ」を検出する完全性チェック。

`lecture_subtitle_translator`（TypeScript版）の `coverageValidator.ts` は、
同一言語内（日本語原文 vs 日本語字幕）でLCS（最長共通部分列）による文字列
一致率を見ている。本アプリは英語→日本語のように言語をまたぐ翻訳のため、
原文と訳文の文字列を直接比較しても意味がない。

代わりに「原文の文字数に対する訳文の文字数比」に着目する。同じ話者・同じ
ドメインの発話であれば、この比率はセグメントごとにある程度安定するため、
直近の比率の中央値から大きく外れて低い（＝訳が短すぎる＝内容が欠落している
疑いがある）セグメントを、API呼び出し不要の統計的ヒューリスティックとして
検出する。
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Literal

CompletenessFlagKind = Literal["possible_undertranslation", "empty_translation"]

DEFAULT_HISTORY_SIZE = 20
DEFAULT_MIN_HISTORY_FOR_JUDGEMENT = 5
DEFAULT_RATIO_THRESHOLD = 0.5
DEFAULT_MIN_SOURCE_CHARS = 15


@dataclass(frozen=True)
class CompletenessFlag:
    """要確認フラグ。"""

    flag: CompletenessFlagKind
    ratio: float
    median_ratio: float | None


class CompletenessTracker:
    """翻訳ペアを1件ずつ受け取り、訳し漏れの疑いがあるものにフラグを立てる。"""

    def __init__(
        self,
        *,
        history_size: int = DEFAULT_HISTORY_SIZE,
        min_history_for_judgement: int = DEFAULT_MIN_HISTORY_FOR_JUDGEMENT,
        ratio_threshold: float = DEFAULT_RATIO_THRESHOLD,
        min_source_chars: int = DEFAULT_MIN_SOURCE_CHARS,
    ) -> None:
        self._history_size = history_size
        self._min_history_for_judgement = min_history_for_judgement
        self._ratio_threshold = ratio_threshold
        self._min_source_chars = min_source_chars
        self._ratio_history: list[float] = []

    def check(self, source_text: str, translated_text: str) -> CompletenessFlag | None:
        """原文・訳文のペアを1件チェックする。

        フラグを立てた/立てなかったに関わらず、判定対象になったセグメントの
        比率は履歴に積む（フラグが立ったセグメント自体も次以降の中央値計算に
        混ざるが、極端な外れ値1件が中央値を大きく動かすことはない）。
        """
        source = source_text.strip()
        translated = translated_text.strip()

        if len(source) < self._min_source_chars:
            return None  # 短すぎる原文は誤検知が多いため対象外

        if not translated:
            return CompletenessFlag(
                flag="empty_translation", ratio=0.0, median_ratio=self._median()
            )

        ratio = len(translated) / len(source)

        flag: CompletenessFlag | None = None
        if len(self._ratio_history) >= self._min_history_for_judgement:
            median_ratio = self._median()
            is_below_threshold = (
                median_ratio is not None
                and ratio < median_ratio * self._ratio_threshold
            )
            if is_below_threshold:
                flag = CompletenessFlag(
                    flag="possible_undertranslation",
                    ratio=round(ratio, 3),
                    median_ratio=round(median_ratio, 3),
                )

        self._ratio_history.append(ratio)
        if len(self._ratio_history) > self._history_size:
            self._ratio_history.pop(0)

        return flag

    def _median(self) -> float | None:
        if not self._ratio_history:
            return None
        return statistics.median(self._ratio_history)
