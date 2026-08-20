"""チャンク長（utterance結合の`max_duration`/`max_words`）のトレードオフ検証。

課題: チャンク（1回の翻訳単位）を長く結合するほど文法的に自然な訳になりやすい
一方、字幕が確定して表示されるまでの待ち時間（体感速度）は伸びる。この
トレードオフを、固定ベンチマークデータに対して段階的にチャンク長を変えながら
実測する。

`evaluation/run_benchmark.py`の通常経路（1ベンチマーク=1セグメント数固定）とは
異なり、ここでは同じ生データ（`raw_utterances`）に対して結合パラメータだけを
変え、結合後のセグメント数が変わる（＝正解訳とのペアリングが崩れる）ことを
前提にしている。そのため、セグメント単位ではなく**全文を連結したdocument-level
chrF**で評価する（セグメント数が変わっても比較可能にするため）。

使い方:
    python evaluation/chunk_length_sweep.py evaluation/benchmarks/economics_federal_funds_rate.json

対象データについての注意:
    現行の`evaluation/benchmarks/*.json`のうち、technology_moe系5件は
    Deepgramの生発話（`raw_utterances`）が既にすべて文末の句読点で終わっており、
    `max_duration`/`max_words`をどれだけ変えても結合結果が一切変化しない
    （＝チャンク長設定の効果を測れない）。この検証で意味のある変化が出るのは
    `economics_federal_funds_rate`（2026-07-02に発見された文分断の実例）のみ。
    より一般的な結論を得るには、生の（未結合の）Deepgram発話が文中で分断される
    実例を追加でベンチマーク化する必要がある（今回は未実施、詳細は結果末尾の
    注記を参照）。
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

from run_benchmark import (  # noqa: E402
    GEMINI_MODEL,
    GOOGLE_API_KEY,
    load_benchmark,
    merge_raw_utterances,
    score_against_reference,
    translate_merged,
)

EXPERIMENTS_DIR = Path(__file__).parent.parent / "experiments"

# (max_duration_sec, max_words) の候補。economics_federal_funds_rate（3発話、
# 未結合なら3セグメント、完全結合なら1セグメント）で3通りの結合状態
# （未結合/部分結合/完全結合）を横断できるよう選定した
# （事前調査: `merge_incomplete_utterances`の挙動を秒数だけ変えて確認済み）。
DEFAULT_SWEEP_POINTS: list[tuple[float, int]] = [
    (1.0, 5),
    (2.0, 8),
    (3.0, 10),
    (4.0, 15),
    (8.0, 30),  # マイクの既定値
    (20.0, 60),  # 動画/CLIの既定値
]


async def run_sweep_point(
    benchmark: dict,
    max_duration: float,
    max_words: int,
    *,
    context_window_size: int = 5,
    thinking_budget: int = 1024,
) -> dict:
    merged = merge_raw_utterances(
        benchmark, max_duration=max_duration, max_words=max_words
    )
    refs = benchmark["reference_ja"]

    hyps = await translate_merged(
        merged,
        benchmark["domain"],
        context_window_size=context_window_size,
        thinking_budget=thinking_budget,
    )

    # セグメント数が結合パラメータで変わるため、文書全体を連結してスコアリングする
    # （セグメント単位のreference-based chrFは、正解訳が完全結合前提のため使えない）。
    doc_chrf = score_against_reference([" ".join(hyps)], [" ".join(refs)])

    durations = [seg["end"] - seg["start"] for seg in merged]

    return {
        "max_duration": max_duration,
        "max_words": max_words,
        "segment_count": len(merged),
        "avg_chunk_seconds": round(sum(durations) / len(durations), 2),
        "max_chunk_seconds": round(max(durations), 2),
        "first_chunk_seconds": round(durations[0], 2),
        "doc_chrf": doc_chrf,
        "merged_texts": [seg["transcript"] for seg in merged],
        "translated_texts": hyps,
    }


def save_sweep_results(benchmark_id: str, points: list[dict]) -> None:
    """CLAUDE.mdの実験記録ルールに沿って、各スイープ点をJSON保存 + results.csvへ追記する。"""
    EXPERIMENTS_DIR.mkdir(exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    model_slug = GEMINI_MODEL.replace("-", "_").replace(".", "")

    json_path = (
        EXPERIMENTS_DIR / f"{today}_{model_slug}_chunk_length_sweep_{benchmark_id}.json"
    )
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": date.today().strftime("%Y-%m-%d"),
                "model": GEMINI_MODEL,
                "benchmark_id": benchmark_id,
                "sweep": points,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n結果を保存: {json_path}")

    csv_path = EXPERIMENTS_DIR / "results.csv"
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(
                ["date", "model", "domain", "xcomet_score", "chrf_score", "notes"]
            )
        for p in points:
            notes = (
                f"[benchmark={benchmark_id}][chunk_length_sweep] "
                f"max_duration={p['max_duration']}s, max_words={p['max_words']} -> "
                f"segments={p['segment_count']}, "
                f"avg_chunk={p['avg_chunk_seconds']}s, "
                f"first_chunk={p['first_chunk_seconds']}s, "
                f"doc_chrf(reference-based, document-level)={p['doc_chrf']}"
            )
            writer.writerow(
                [
                    date.today().strftime("%Y-%m-%d"),
                    GEMINI_MODEL,
                    "economics",
                    "",
                    p["doc_chrf"],
                    notes,
                ]
            )
    print(f"results.csv を更新: {csv_path}")


async def main(benchmark_path: Path, sweep_points: list[tuple[float, int]]) -> None:
    benchmark = load_benchmark(benchmark_path)
    print(
        f"チャンク長スイープ実行: {benchmark['benchmark_id']} "
        f"(raw_utterances={len(benchmark['raw_utterances'])})\n"
    )

    results = []
    for max_duration, max_words in sweep_points:
        point = await run_sweep_point(benchmark, max_duration, max_words)
        results.append(point)
        print(
            f"max_duration={max_duration:>5}s max_words={max_words:>3} | "
            f"segments={point['segment_count']} | "
            f"avg_chunk={point['avg_chunk_seconds']:>5}s | "
            f"first_chunk={point['first_chunk_seconds']:>5}s | "
            f"doc_chrf={point['doc_chrf']}"
        )

    print("\n--- セグメント分割の内訳（設定ごと） ---")
    for point in results:
        print(f"\n[max_duration={point['max_duration']}s max_words={point['max_words']}]")
        for text in point["merged_texts"]:
            print(f"  - {text}")

    save_sweep_results(benchmark["benchmark_id"], results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="チャンク長（utterance結合パラメータ）のトレードオフを固定ベンチマークで検証する"
    )
    parser.add_argument("benchmark", type=Path, help="evaluation/benchmarks/*.json へのパス")
    args = parser.parse_args()

    if not args.benchmark.exists():
        print(f"エラー: ベンチマークファイルが見つかりません: {args.benchmark}")
        sys.exit(1)
    if not GOOGLE_API_KEY:
        print("エラー: GOOGLE_API_KEY が設定されていません。")
        sys.exit(1)

    asyncio.run(main(args.benchmark, DEFAULT_SWEEP_POINTS))
