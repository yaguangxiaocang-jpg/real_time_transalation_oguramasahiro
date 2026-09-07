"""どのGeminiモデルがリアルタイム翻訳に向いているかの比較調査。

これまでの実験（`experiments/results.csv`）はすべて`gemini-2.5-flash`固定で
行われており、他モデルとの比較が一度もなかった（2026-08-26時点で判明）。

2026-08-27に実際にAPIを叩いて確認したところ、当初の比較候補
（`gemini-2.5-flash-lite`, `gemini-2.0-flash`）はいずれも
`404 NOT_FOUND`（提供終了。エラーメッセージが後継モデルとして
`gemini-3.5-flash-lite` / `gemini-3.6-flash` を案内していた）で使えなくなっており、
代わりに`gemini-3.5-flash-lite`, `gemini-3.6-flash`, `gemini-3.1-pro-preview`が
利用可能だった。`gemini-3.5-flash-lite`が2ベンチマークとも最速・最高chrFという
結果だったが、「2ベンチマーク・各1回の実行のみの予備調査」という限界があった
（README更新履歴 2026/08/27参照）。

また、**gemini-3.x世代は`thinking_budget=0`（Thinking無効化）を受け付けない**
（`400 INVALID_ARGUMENT: "This model only works in thinking mode."`、
`gemini-3.1-pro-preview`で実機確認）ことが判明した。マイクのリアルタイム翻訳経路
（`pipeline.py`）は低遅延優先で`thinking_budget=0`を既定にしているため、これが
使えないモデルは少なくとも現行の実装のままではマイク経路に採用できない
（Thinkingを完全に切れないと、その分レイテンシが必ず上乗せされる）。
そのため、`gemini-2.5-flash`のみ本番と同じ`thinking_budget=0`、他モデルは
受理される最小値（128、実機確認済み）で代用して比較する
（完全に公平な比較ではない点に注意）。

**2026-09-07の追加検証**（report.txtの優先課題(1)対応）:
前回の予備調査で明確に劣っていた`gemini-3.6-flash`・`gemini-3.1-pro-preview`は
除外し、有力候補の`gemini-3.5-flash-lite`と現行本番の`gemini-2.5-flash`の
2モデルに絞って、(a) 全ベンチマーク（`evaluation/benchmarks/*.json`、10件）に
対象を拡大、(b) 各ベンチマークにつき`REPEATS`回実行してばらつきを確認、
(c) 本番と同じ`dictionary_path`を配線（前回は未配線だった）、の3点を追加した。

固定ベンチマークに対して、モデルごとに全セグメント翻訳の合計所要時間
（wall-clock、1セグメントあたり平均に換算）と、reference-based chrF /
LLM-as-judgeスコアを計測する。

使い方:
    python evaluation/model_comparison.py
"""

from __future__ import annotations

import asyncio
import csv
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

from run_benchmark import (  # noqa: E402
    GOOGLE_API_KEY,
    load_benchmark,
    merge_raw_utterances,
    score_against_reference,
    score_with_llm_judge,
    translate_merged,
)

REPO_ROOT = Path(__file__).parent.parent
EXPERIMENTS_DIR = REPO_ROOT / "experiments"
DICTIONARY_PATH = REPO_ROOT / "dictionary.csv"

BENCHMARK_PATHS = sorted((REPO_ROOT / "evaluation/benchmarks").glob("*.json"))

REPEATS = 2

# (モデル名, thinking_budget, 備考)。
# thinking_budgetの非対称性についてはモジュールdocstring参照。
# 2026-09-07: gemini-3.6-flash/gemini-3.1-pro-previewは前回予備調査で明確に
# 劣っていた（README 2026/08/27参照）ため、追加ベンチマークの対象からは外し、
# gemini-3.5-flash-lite（有力候補）とgemini-2.5-flash（現行本番）に絞って
# ベンチマーク数・実行回数を増やす方に予算を割く。
CANDIDATES: list[tuple[str, int, str]] = [
    ("gemini-2.5-flash", 0, "現行の本番既定モデル（マイクと同じthinking_budget=0）"),
    ("gemini-3.5-flash-lite", 128, "軽量モデル候補（thinking_budget=0は拒否されたため128で代用）"),
]


async def run_candidate(benchmark: dict, model: str, thinking_budget: int) -> dict:
    merged = merge_raw_utterances(benchmark)
    refs = benchmark["reference_ja"]

    t0 = time.perf_counter()
    hyps = await translate_merged(
        merged,
        benchmark["domain"],
        context_window_size=5,
        thinking_budget=thinking_budget,
        model=model,
        dictionary_path=DICTIONARY_PATH,
    )
    elapsed = time.perf_counter() - t0

    # このベンチマーク集合には、reference_jaがraw_utterances単位ではなく
    # 全文連結でしか比較できないもの（v2_clip1_scaling_intro等）も含むため、
    # chunk_length_sweep.pyと同じdocument-level chrFで統一する。
    chrf = score_against_reference([" ".join(hyps)], [" ".join(refs)])
    judge = await score_with_llm_judge([s["transcript"] for s in merged], hyps)

    return {
        "model": model,
        "thinking_budget": thinking_budget,
        "segment_count": len(merged),
        "elapsed_seconds": round(elapsed, 2),
        "avg_seconds_per_segment": round(elapsed / len(merged), 2),
        "chrf_score": chrf,
        "xcomet_score": judge,
        "hyps": hyps,
    }


async def run_benchmark_across_models(benchmark_path: Path) -> list[dict]:
    benchmark = load_benchmark(benchmark_path)
    print(f"\n=== {benchmark['benchmark_id']} ===")
    results = []
    for model, thinking_budget, note in CANDIDATES:
        runs = []
        for rep in range(REPEATS):
            try:
                r = await run_candidate(benchmark, model, thinking_budget)
            except Exception as exc:  # noqa: BLE001
                print(f"  {model} (tb={thinking_budget}) rep{rep}: FAIL -> {exc}")
                results.append(
                    {
                        "model": model,
                        "thinking_budget": thinking_budget,
                        "benchmark_id": benchmark["benchmark_id"],
                        "error": str(exc),
                    }
                )
                continue
            runs.append(r)
        if not runs:
            continue

        chrf_scores = [r["chrf_score"] for r in runs]
        judge_scores = [r["xcomet_score"] for r in runs if r["xcomet_score"] is not None]
        avg_seconds = [r["avg_seconds_per_segment"] for r in runs]

        agg = {
            "model": model,
            "thinking_budget": thinking_budget,
            "benchmark_id": benchmark["benchmark_id"],
            "note": note,
            "repeats": len(runs),
            "segment_count": runs[0]["segment_count"],
            "avg_seconds_per_segment_mean": round(statistics.mean(avg_seconds), 2),
            "avg_seconds_per_segment_range": [round(min(avg_seconds), 2), round(max(avg_seconds), 2)],
            "chrf_score_mean": round(statistics.mean(chrf_scores), 4),
            "chrf_score_range": [round(min(chrf_scores), 4), round(max(chrf_scores), 4)],
            "xcomet_score_mean": round(statistics.mean(judge_scores), 4) if judge_scores else None,
            "xcomet_score_range": (
                [round(min(judge_scores), 4), round(max(judge_scores), 4)] if judge_scores else None
            ),
            "runs": runs,
        }
        results.append(agg)
        print(
            f"  {model:<24} tb={thinking_budget:>3} | "
            f"avg={agg['avg_seconds_per_segment_mean']:>5.2f}s/seg {agg['avg_seconds_per_segment_range']} | "
            f"chrF={agg['chrf_score_mean']} {agg['chrf_score_range']} | "
            f"judge={agg['xcomet_score_mean']} | n={agg['repeats']} | {note}"
        )
    return results


def save_results(all_results: list[dict]) -> None:
    EXPERIMENTS_DIR.mkdir(exist_ok=True)
    today = date.today().strftime("%Y%m%d")

    json_path = EXPERIMENTS_DIR / f"{today}_model_comparison.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {"date": date.today().strftime("%Y-%m-%d"), "results": all_results},
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
        for r in all_results:
            if "error" in r:
                notes = (
                    f"[benchmark={r.get('benchmark_id', '?')}][model_comparison] "
                    f"thinking_budget={r['thinking_budget']} -> エラー: {r['error'][:200]}"
                )
                writer.writerow(
                    [date.today().strftime("%Y-%m-%d"), r["model"], "", "", "", notes]
                )
                continue
            notes = (
                f"[benchmark={r['benchmark_id']}][model_comparison][n={r['repeats']}] "
                f"thinking_budget={r['thinking_budget']}, dictionary=有 -> "
                f"avg={r['avg_seconds_per_segment_mean']}s/segment "
                f"(range={r['avg_seconds_per_segment_range']}, segments={r['segment_count']}), "
                f"chrF={r['chrf_score_mean']} (range={r['chrf_score_range']}), "
                f"judge={r['xcomet_score_mean']} (range={r['xcomet_score_range']}), "
                f"{r['note']}"
            )
            writer.writerow(
                [
                    date.today().strftime("%Y-%m-%d"),
                    r["model"],
                    "",
                    r["xcomet_score_mean"],
                    r["chrf_score_mean"],
                    notes,
                ]
            )
    print(f"results.csv を更新: {csv_path}")


async def main() -> None:
    all_results: list[dict] = []
    for benchmark_path in BENCHMARK_PATHS:
        all_results.extend(await run_benchmark_across_models(benchmark_path))

    print("\n=== まとめ ===")
    for r in all_results:
        if "error" in r:
            print(f"{r['model']} / {r.get('benchmark_id', '?')}: エラー")
            continue
        print(
            f"{r['benchmark_id']:<45} {r['model']:<24} tb={r['thinking_budget']:>3} | "
            f"avg={r['avg_seconds_per_segment_mean']:>5.2f}s/seg | "
            f"chrF={r['chrf_score_mean']} | judge={r['xcomet_score_mean']}"
        )

    save_results(all_results)


if __name__ == "__main__":
    if not GOOGLE_API_KEY:
        print("エラー: GOOGLE_API_KEY が設定されていません。")
        sys.exit(1)
    asyncio.run(main())
