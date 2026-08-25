"""`unnaturalness_check_enabled`（不自然度スコアによるチャンク動的延長）の
before/after検証。

`config.py`のコメントに明記されている通り、この機能は「未検証の新機能の
ためデフォルトOFF。有効化する前に`evaluation/run_benchmark.py`でbefore/after
比較を行うこと」という運用ルールがある。ただしこの機能はマイクの
ストリーミング経路（`pipeline.py`の`StreamingUtteranceMerger` +
`naturalness_detector.score_unnaturalness_with_timeout`）専用で、
`run_benchmark.py`が使うバッチ版`merge_incomplete_utterances`（正規表現のみ）
には配線されていない。そのため本スクリプトでは、`pipeline.py`と同じ経路
（`StreamingUtteranceMerger.feed(force_incomplete=...)`）を、Deepgramの
生発話を1件ずつ流し込む形でオフライン再現し、OFF/ON双方の結合結果と
翻訳品質を比較する。

対象データについての注意:
    `naturalness_detector`が狙う失敗パターンは「文法的には句読点で終わって
    いるが、文脈上はまだ話が続いている」ケース（代名詞の指示先未定、話題の
    継続、リスト/比較の未完了など）であり、これまでのチャンク長検証
    （`chunk_length_sweep.py`）で使った「句読点が無いまま分断された」ケース
    （`SENTENCE_END_RE`で既に検出できる）とは異なる失敗モードを狙っている。
    そのため同じ生データでも、この機能が実際に発火する（＝正規表現とは
    異なる判定を下す）とは限らない。発火しなかった場合はその旨も含めて
    正直に報告する（「効果なし」も検証結果として意味がある）。

使い方:
    python evaluation/naturalness_check_ab_test.py experiments/segments/20260824_2d07bb74_v2_clip1_raw_unmerged.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
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

from run_benchmark import GEMINI_MODEL, GOOGLE_API_KEY, score_with_llm_judge  # noqa: E402

UNNATURALNESS_THRESHOLD = 0.6  # config.py unnaturalness_threshold の既定値と同じ
UNNATURALNESS_CONTEXT_SIZE = 3  # config.py unnaturalness_context_size の既定値と同じ
CONTEXT_WINDOW_SIZE = 5  # config.py context_window_size（翻訳側の文脈窓）の既定値と同じ


async def run_streaming_merge(
    raw_utterances: list[dict],
    *,
    use_unnaturalness_check: bool,
) -> list[dict]:
    """`pipeline.py._collect_transcriptions`と同じ経路をオフラインで再現する。

    Deepgramの生発話を1件ずつ`StreamingUtteranceMerger.feed()`に投入し、
    `use_unnaturalness_check=True`なら実際にGeminiで不自然度スコアを計算して
    `force_incomplete`に反映する（`pipeline.py`と同一の`naturalness_detector`
    を使用）。
    """
    merger = StreamingUtteranceMerger(max_duration=8.0, max_words=30)  # マイク既定値
    tgt_context: list[str] = []  # 未使用（不自然度チェックは原文側のみ参照）
    src_context_for_check: list[str] = []
    merged_out: list[dict] = []
    fired_log: list[dict] = []

    for u in raw_utterances:
        force_incomplete = False
        score = None
        if use_unnaturalness_check:
            candidate = merger.peek_combined_text(u["transcript"])
            score = await score_unnaturalness(
                candidate,
                src_context_for_check[-UNNATURALNESS_CONTEXT_SIZE:],
                GOOGLE_API_KEY,
                GEMINI_MODEL,
            )
            if score is not None and score >= UNNATURALNESS_THRESHOLD:
                force_incomplete = True

        merged = merger.feed(
            u["transcript"],
            u["start"],
            u["end"],
            confidence=1.0,
            force_incomplete=force_incomplete,
        )
        if merged is not None:
            merged_out.append(
                {"start": merged.start_time, "end": merged.end_time, "transcript": merged.text}
            )
            src_context_for_check.append(merged.text)
            if force_incomplete:
                fired_log.append(
                    {"candidate": candidate, "score": score, "note": "確定直前に発火(最終的にflush)"}
                )
        elif force_incomplete:
            fired_log.append({"candidate": candidate, "score": score, "note": "結合継続を強制"})

    remaining = merger.flush()
    if remaining is not None:
        merged_out.append(
            {"start": remaining.start_time, "end": remaining.end_time, "transcript": remaining.text}
        )

    return merged_out, fired_log


async def translate_sequential(merged: list[dict], domain: str) -> list[str]:
    """pipeline.pyのSharedTranslationContextを簡略化した、順次翻訳（文脈引き継ぎあり）。"""
    translator = LLMTranslator(
        provider="gemini",
        api_key=GOOGLE_API_KEY,
        model=GEMINI_MODEL,
        source_language="English",
        target_language="Japanese",
        domain=domain,
        context_window_size=CONTEXT_WINDOW_SIZE,
        thinking_budget=0,  # マイク側の既定（低遅延優先）に合わせる
    )
    src_ctx: list[str] = []
    tgt_ctx: list[str] = []
    outputs = []
    for seg in merged:
        result = await translator.translate(
            seg["transcript"], src_context=src_ctx, tgt_context=tgt_ctx, update_context=False
        )
        outputs.append(result.latest_slide)
        src_ctx.append(seg["transcript"])
        tgt_ctx.append(result.latest_slide)
        if len(src_ctx) > CONTEXT_WINDOW_SIZE:
            src_ctx.pop(0)
            tgt_ctx.pop(0)
    return outputs


async def main(raw_path: Path) -> None:
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    raw = data["raw_utterances"]
    print(f"生発話数: {len(raw)}\n")

    print("=== OFF（既定、正規表現のみ） ===")
    merged_off, _ = await run_streaming_merge(raw, use_unnaturalness_check=False)
    for m in merged_off:
        print(f"  [{m['start']:.1f}-{m['end']:.1f}s] {m['transcript']}")
    print(f"セグメント数: {len(merged_off)}\n")

    print("=== ON（unnaturalness_check_enabled、実際にGeminiで採点） ===")
    merged_on, fired = await run_streaming_merge(raw, use_unnaturalness_check=True)
    for m in merged_on:
        print(f"  [{m['start']:.1f}-{m['end']:.1f}s] {m['transcript']}")
    print(f"セグメント数: {len(merged_on)}\n")

    if fired:
        print(f"--- 不自然度チェックが閾値({UNNATURALNESS_THRESHOLD})以上で発火した箇所（{len(fired)}件） ---")
        for f in fired:
            print(f"  score={f['score']:.2f} [{f['note']}] candidate: {f['candidate']!r}")
    else:
        print("--- 不自然度チェックは一度も閾値を超えませんでした（OFFと同じ結合結果） ---")

    if merged_off == merged_on:
        print("\n結合結果はOFF/ONで完全に同一でした。この検証データでは効果を確認できませんでした。")
        return

    print("\n=== 翻訳して品質を比較 ===")
    domain = "technology"
    hyps_off = await translate_sequential(merged_off, domain)
    hyps_on = await translate_sequential(merged_on, domain)

    srcs_off = [m["transcript"] for m in merged_off]
    srcs_on = [m["transcript"] for m in merged_on]

    judge_off = await score_with_llm_judge(srcs_off, hyps_off)
    judge_on = await score_with_llm_judge(srcs_on, hyps_on)

    print(f"\nOFF: segments={len(merged_off)}, LLM-judge score={judge_off}")
    print(f"ON : segments={len(merged_on)}, LLM-judge score={judge_on}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="unnaturalness_check_enabledのbefore/after検証（マイク経路のストリーミング結合を再現）"
    )
    parser.add_argument("raw_json", type=Path, help="生発話JSON（raw_utterancesキーを含む）")
    args = parser.parse_args()

    if not args.raw_json.exists():
        print(f"エラー: ファイルが見つかりません: {args.raw_json}")
        sys.exit(1)
    if not GOOGLE_API_KEY:
        print("エラー: GOOGLE_API_KEY が設定されていません。")
        sys.exit(1)

    asyncio.run(main(args.raw_json))
