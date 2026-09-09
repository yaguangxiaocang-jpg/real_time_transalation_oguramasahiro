"""naturalness_detectorのスコア分布を確認する(粒度改善のbefore/after比較用)。

`evaluation/naturalness_check_ab_test.py`は「閾値(0.6)以上で発火したケース」しか
ログに残さないため、report.txtで指摘された「スコアが0.80〜0.90に偏り粒度が粗い」
という問題(発火した14/26件のスコア分布)を追跡するには不十分。本スクリプトは
`naturalness_check_ab_test.py`と同じ経路(`StreamingUtteranceMerger` +
`score_unnaturalness`、bilingual context)で**全発話**のスコアを記録し、
分布(平均・標準偏差・0.1刻みのヒストグラム)を出力する。

2026-09-09、`naturalness_detector._SYSTEM_PROMPT`にスコア帯ごとの具体例付き
ルーブリックを追加した(0.8〜0.90への偏りを緩和する狙い)。本スクリプトを
変更前後で実行し、分布がどう変わったかを比較する。

使い方:
    python evaluation/naturalness_score_distribution.py experiments/segments/20260824_2d07bb74_v2_clip1_raw_unmerged.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

from real_time_translation.transcription.naturalness_detector import (  # noqa: E402
    score_unnaturalness,
)
from real_time_translation.transcription.utterance_merge import (  # noqa: E402
    StreamingUtteranceMerger,
)
from real_time_translation.translation.llm_translator import LLMTranslator  # noqa: E402

from run_benchmark import GEMINI_MODEL, GOOGLE_API_KEY  # noqa: E402

UNNATURALNESS_CONTEXT_SIZE = 3  # config.py unnaturalness_context_size の既定値と同じ
CONTEXT_WINDOW_SIZE = 5  # config.py context_window_size（翻訳側の文脈窓）の既定値と同じ


async def main(raw_path: Path) -> None:
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    raw = data["raw_utterances"]
    print(f"生発話数: {len(raw)}\n")

    translator = LLMTranslator(
        provider="gemini",
        api_key=GOOGLE_API_KEY,
        model=GEMINI_MODEL,
        source_language="English",
        target_language="Japanese",
        domain="technology",
        context_window_size=CONTEXT_WINDOW_SIZE,
        thinking_budget=0,
    )

    merger = StreamingUtteranceMerger(max_duration=8.0, max_words=30)
    src_context: list[str] = []
    tgt_context: list[str] = []
    records: list[dict] = []

    for u in raw:
        candidate = merger.peek_combined_text(u["transcript"])
        n = UNNATURALNESS_CONTEXT_SIZE
        context_pairs = list(zip(src_context[-n:], tgt_context[-n:]))
        result = await score_unnaturalness(
            candidate, context_pairs, GOOGLE_API_KEY, GEMINI_MODEL
        )
        if result is not None:
            records.append(
                {"candidate": candidate, "score": result.score, "reason": result.reason}
            )
            print(f"  score={result.score:.2f} reason={result.reason:28s} {candidate!r}")
        else:
            print(f"  score=None(判定失敗)                              {candidate!r}")

        # 実際の結合判断は既存の閾値(0.6)+reasonガードで行う(このスクリプトの
        # 目的はスコア分布の観測なので、ここではforce_incompleteの計算は
        # naturalness_check_ab_test.pyと揃えず、素朴にmerger既定の完全性判定のみ使う)
        merged = merger.feed(u["transcript"], u["start"], u["end"], confidence=1.0)
        if merged is not None:
            if translator is not None:
                mt = await translator.translate(
                    merged.text,
                    src_context=src_context,
                    tgt_context=tgt_context,
                    update_context=False,
                )
                tgt_context.append(mt.latest_slide)
            src_context.append(merged.text)

    scores = [r["score"] for r in records]
    print(f"\n判定件数: {len(scores)}")
    if scores:
        print(f"平均: {statistics.mean(scores):.3f}  標準偏差: {statistics.pstdev(scores):.3f}")
        print(f"最小: {min(scores):.2f}  最大: {max(scores):.2f}")
        print("\nヒストグラム(0.1刻み):")
        buckets = [0] * 10
        for s in scores:
            idx = min(int(s * 10), 9)
            buckets[idx] += 1
        for i, count in enumerate(buckets):
            lo = i / 10
            hi = (i + 1) / 10
            bar = "#" * count
            print(f"  {lo:.1f}-{hi:.1f}: {count:2d} {bar}")

        fired = [r for r in records if r["score"] >= 0.6]
        print(f"\n閾値0.6以上: {len(fired)}件")
        if fired:
            fired_scores = [r["score"] for r in fired]
            print(
                f"  平均: {statistics.mean(fired_scores):.3f}  "
                f"標準偏差: {statistics.pstdev(fired_scores):.3f}  "
                f"範囲: {min(fired_scores):.2f}-{max(fired_scores):.2f}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="naturalness_detectorのスコア分布を確認する")
    parser.add_argument("raw_json", type=Path)
    args = parser.parse_args()

    if not args.raw_json.exists():
        print(f"エラー: ファイルが見つかりません: {args.raw_json}")
        sys.exit(1)
    if not GOOGLE_API_KEY:
        print("エラー: GOOGLE_API_KEY が設定されていません。")
        sys.exit(1)

    asyncio.run(main(args.raw_json))
