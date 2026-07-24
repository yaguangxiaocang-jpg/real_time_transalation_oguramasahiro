"""固定ベンチマークデータセットに対して翻訳エンジンを評価するスクリプト。

`experiments/` 配下のアドホックな実験（動画ごとに毎回違うデータ・セグメント数で
実施される）とは異なり、このスクリプトは `evaluation/benchmarks/*.json` に
凍結された同一の入力データに対して毎回評価を行う。

これにより、パイプラインの変更（プロンプト・thinking_budget・context_window_size・
utterance結合パラメータなど）の効果を、他の変数（今回はどの動画を使ったか、
セグメント数がいくつだったか）に惑わされずに比較できる。

- マイク・動画字幕・CLIスクリプトすべてで共有される `merge_incomplete_utterances`
  （transcription/utterance_merge.py）と `LLMTranslator`
  （translation/llm_translator.py）をそのまま使う。
- 評価は逆翻訳ではなく、ベンチマークに同梱された人手レビュー済み正解訳
  （reference_ja）に対する chrF（reference-based）で行う。

使い方:
    python evaluation/run_benchmark.py evaluation/benchmarks/economics_federal_funds_rate.json
    python evaluation/run_benchmark.py evaluation/benchmarks/economics_federal_funds_rate.json --thinking-budget 0
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

EXPERIMENTS_DIR = Path(__file__).parent.parent / "experiments"


def load_benchmark(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        benchmark = json.load(f)

    if benchmark.get("reference_status") == "draft_needs_human_review":
        print(
            "警告: このベンチマークの正解訳（reference_ja）はまだ人手レビュー未了です"
            "（reference_status=draft_needs_human_review）。"
            "スコアの絶対値ではなく相対的な変化（前回との差分）の参考にとどめてください。\n"
        )
    return benchmark


def merge_raw_utterances(benchmark: dict) -> list[dict]:
    """動画字幕・マイクと同じ結合アルゴリズムを適用する。"""
    from real_time_translation.transcription.utterance_merge import (
        merge_incomplete_utterances,
    )

    merged = merge_incomplete_utterances(benchmark["raw_utterances"])

    expected = benchmark.get("expected_merged_count")
    if expected is not None and len(merged) != expected:
        print(
            f"注意: 結合後のセグメント数が想定と異なります"
            f"（期待={expected}, 実際={len(merged)}）。"
            "結合ロジックの変更でセグメント分割が変わった可能性があります。"
        )

    return merged


async def translate_merged(
    merged: list[dict],
    domain: str,
    *,
    context_window_size: int = 5,
    thinking_budget: int = 1024,
) -> list[str]:
    """動画字幕（add_subtitles.py）と同じ LLMTranslator で各セグメントを翻訳する。"""
    from real_time_translation.translation.llm_translator import LLMTranslator

    translator = LLMTranslator(
        provider="gemini",
        api_key=GOOGLE_API_KEY,
        model=GEMINI_MODEL,
        source_language="English",
        target_language="Japanese",
        domain=domain,
        context_window_size=context_window_size,
        thinking_budget=thinking_budget,
    )

    outputs = []
    for seg in merged:
        result = await translator.translate(seg["transcript"])
        outputs.append(result.latest_slide)
    return outputs


def score_against_reference(hyps: list[str], refs: list[str]) -> float:
    """人手レビュー済み正解訳に対するchrF（reference-based、0〜1）。"""
    from sacrebleu.metrics import CHRF

    chrf = CHRF()
    raw = chrf.corpus_score(hyps, [refs]).score  # 0〜100
    return round(raw / 100, 4)


async def score_with_llm_judge(srcs: list[str], hyps: list[str]) -> float | None:
    """Gemini LLM-as-judgeによる翻訳品質スコア（0〜1）。

    add_subtitles.py の compute_scores と同じ方式（EN原文とJA訳をペアで
    Geminiに採点させる）で計算し、results.csv 上でアドホック実験とスコアの
    意味を揃える。
    """
    from google import genai

    client = genai.Client(api_key=GOOGLE_API_KEY)
    judge_prompt = (
        "あなたはプロの翻訳評価者です。以下の英日翻訳ペアをそれぞれ評価し、"
        "翻訳品質を0.00〜1.00のスコアで採点してください。"
        "番号付きリストで数値のみ返してください（例: 1. 0.85）。\n\n"
        + "\n".join(
            f"{i+1}. EN: {s}\n   JA: {h}" for i, (s, h) in enumerate(zip(srcs, hyps))
        )
    )
    judge_resp = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=judge_prompt,
    )
    scores = []
    for line in (judge_resp.text or "").split("\n"):
        m = re.match(r"\d+\.\s*([\d.]+)", line.strip())
        if m:
            try:
                scores.append(float(m.group(1)))
            except ValueError:
                pass
    if not scores:
        return None
    score = round(sum(scores) / len(scores), 4)
    print(f"  xcomet_score (LLM judge): {score}")
    return score


def save_result(
    benchmark_id: str,
    domain: str,
    hyps: list[str],
    refs: list[str],
    xcomet_score: float | None,
    chrf_score: float,
    thinking_budget: int,
    context_window_size: int,
) -> None:
    EXPERIMENTS_DIR.mkdir(exist_ok=True)

    today = date.today().strftime("%Y%m%d")
    model_slug = GEMINI_MODEL.replace("-", "_").replace(".", "")
    json_path = (
        EXPERIMENTS_DIR / f"{today}_{model_slug}_benchmark_{benchmark_id}.json"
    )

    notes = (
        f"[benchmark={benchmark_id}] 固定データセット（{len(refs)}セグメント）に対する"
        f"reference-based chrF評価 + LLM-as-judge xCOMETスコア。"
        f"thinking_budget={thinking_budget}, "
        f"context_window_size={context_window_size}。"
    )

    record = {
        "date": date.today().strftime("%Y-%m-%d"),
        "model": GEMINI_MODEL,
        "domain": domain,
        "benchmark_id": benchmark_id,
        "xcomet_score": xcomet_score,
        "chrf_score": chrf_score,
        "notes": notes,
        "segments": [
            {"reference_ja": r, "mt_ja": h} for r, h in zip(refs, hyps)
        ],
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"\n結果を保存: {json_path}")

    csv_path = EXPERIMENTS_DIR / "results.csv"
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(
                ["date", "model", "domain", "xcomet_score", "chrf_score", "notes"]
            )
        writer.writerow(
            [
                record["date"],
                record["model"],
                record["domain"],
                "" if xcomet_score is None else xcomet_score,
                chrf_score,
                notes,
            ]
        )
    print(f"results.csv を更新: {csv_path}")


async def main(
    benchmark_path: Path, thinking_budget: int, context_window_size: int
) -> None:
    benchmark = load_benchmark(benchmark_path)
    print(
        f"ベンチマーク実行: {benchmark['benchmark_id']} "
        f"(domain={benchmark['domain']}, raw_utterances={len(benchmark['raw_utterances'])})"
    )

    merged = merge_raw_utterances(benchmark)
    refs = benchmark["reference_ja"]

    if len(merged) != len(refs):
        print(
            f"エラー: 結合後のセグメント数（{len(merged)}）と正解訳の数（{len(refs)}）が"
            "一致しません。ベンチマークデータまたは結合ロジックを確認してください。"
        )
        sys.exit(1)

    hyps = await translate_merged(
        merged,
        benchmark["domain"],
        context_window_size=context_window_size,
        thinking_budget=thinking_budget,
    )

    chrf_score = score_against_reference(hyps, refs)

    print(f"\nchrF（reference-based）: {chrf_score}")
    print("\n--- 差分プレビュー ---")
    for seg, ref, hyp in zip(merged, refs, hyps):
        marker = "OK" if hyp.strip() == ref.strip() else "!!"
        print(f"[{marker}] {seg['transcript']}")
        print(f"  正解: {ref}")
        print(f"  MT  : {hyp}")

    srcs = [seg["transcript"] for seg in merged]
    xcomet_score = await score_with_llm_judge(srcs, hyps)

    save_result(
        benchmark["benchmark_id"],
        benchmark["domain"],
        hyps,
        refs,
        xcomet_score,
        chrf_score,
        thinking_budget,
        context_window_size,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="固定ベンチマークデータセットで翻訳エンジンを評価する"
    )
    parser.add_argument("benchmark", type=Path, help="evaluation/benchmarks/*.json へのパス")
    parser.add_argument(
        "--thinking-budget",
        type=int,
        default=1024,
        help="Geminiのthinking_budget（既定: 1024、動画/CLIパスと同じ）",
    )
    parser.add_argument(
        "--context-window-size",
        type=int,
        default=5,
        help="翻訳コンテキスト窓のサイズ（既定: 5）",
    )
    args = parser.parse_args()

    if not args.benchmark.exists():
        print(f"エラー: ベンチマークファイルが見つかりません: {args.benchmark}")
        sys.exit(1)

    asyncio.run(
        main(args.benchmark, args.thinking_budget, args.context_window_size)
    )
