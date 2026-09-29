"""比較実験のスコア差が偶然のばらつきか統計的に有意かを判定するツール。

report.txtの優先課題(1)（gemini-3.5-flash-liteのchrF回帰が実際の品質劣化か
chrF指標のノイズかを切り分けられない）への対応。Koehn (2004) "Statistical
Significance Tests for Machine Translation Evaluation" (EMNLP) のペアード
ブートストラップ・リサンプリング法を実装する：観測データからブートストラップ
（復元抽出）でリサンプルを多数回作り、スコア差の分布を経験的に推定することで、
1回の実行結果だけでは判断できない「差が有意かどうか」を数値化する。

2種類の粒度に対応する:
    bootstrap_paired_diff   : 任意のペアードスカラー値（例: ベンチマークごとの
        平均chrF）に対する汎用版。`evaluation/model_comparison.py`が出力する
        JSONのように、ベンチマーク単位でしかペアが取れない場合に使う。
    bootstrap_segment_chrf  : セグメント単位のhyp/refペアが両方揃っている場合
        （`evaluation/run_benchmark.py`が出力するJSONの`segments`）に使う、
        より粒度の細かいオリジナルのKoehn (2004)方式。

CLI（model_comparison.py の出力に対して使う場合）:
    python evaluation/significance.py experiments/20260907_model_comparison.json \
        gemini-2.5-flash gemini-3.5-flash-lite --metric chrf_score_mean
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

DEFAULT_N_RESAMPLES = 10000
DEFAULT_SEED = 42


def _summarize_resamples(observed_diff: float, resample_diffs: list[float]) -> dict:
    resample_diffs = sorted(resample_diffs)
    n = len(resample_diffs)
    ci_lo = resample_diffs[int(0.025 * n)]
    ci_hi = resample_diffs[min(int(0.975 * n), n - 1)]
    # Koehn (2004)の近似p値: 観測した差と符号が逆（=0を跨いで反対側）になった
    # リサンプルの割合。小さいほど「B>Aは偶然ではなさそうだ」と言える。
    if observed_diff >= 0:
        p_value = sum(1 for d in resample_diffs if d <= 0) / n
    else:
        p_value = sum(1 for d in resample_diffs if d >= 0) / n
    b_wins = sum(1 for d in resample_diffs if d > 0) / n
    return {
        "observed_diff": round(observed_diff, 4),
        "ci95_diff": [round(ci_lo, 4), round(ci_hi, 4)],
        "p_value_approx": round(p_value, 4),
        "win_prob_b_gt_a": round(b_wins, 4),
        "n_resamples": n,
    }


def bootstrap_paired_diff(
    scores_a: list[float],
    scores_b: list[float],
    *,
    n_resamples: int = DEFAULT_N_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> dict:
    """ペアードスカラー値（例: ベンチマークごとの平均chrF）に対する汎用ブートストラップ検定。

    `scores_a[i]`と`scores_b[i]`は同じ単位（同じベンチマークなど）に対する
    2つの条件（モデルA/モデルBなど）のスコアであること。
    """
    if len(scores_a) != len(scores_b):
        raise ValueError("scores_a と scores_b の長さが一致しません")
    n = len(scores_a)
    if n < 2:
        raise ValueError("ブートストラップには最低2ペアの単位（ベンチマーク等）が必要です")

    rng = random.Random(seed)
    paired_diffs = [b - a for a, b in zip(scores_a, scores_b)]
    observed_diff = sum(paired_diffs) / n

    resample_diffs = []
    for _ in range(n_resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        sample = [paired_diffs[i] for i in idx]
        resample_diffs.append(sum(sample) / n)

    result = _summarize_resamples(observed_diff, resample_diffs)
    result.update({"n_units": n, "mean_a": round(sum(scores_a) / n, 4), "mean_b": round(sum(scores_b) / n, 4)})
    return result


def bootstrap_segment_chrf(
    hyps_a: list[str],
    hyps_b: list[str],
    refs: list[str],
    *,
    n_resamples: int = DEFAULT_N_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Koehn (2004)方式のセグメント単位ペアードブートストラップ（コーパスレベルchrF）。

    `hyps_a[i]` / `hyps_b[i]` / `refs[i]`が同じセグメントに対応している前提
    （`run_benchmark.py`が保存する`segments`フィールドなど）。
    """
    from sacrebleu.metrics import CHRF

    if not (len(hyps_a) == len(hyps_b) == len(refs)):
        raise ValueError("hyps_a / hyps_b / refs の長さが一致しません")
    n = len(refs)
    if n < 2:
        raise ValueError("ブートストラップには最低2セグメントが必要です")

    chrf = CHRF()
    rng = random.Random(seed)

    def corpus_chrf(hyps: list[str], rs: list[str]) -> float:
        return chrf.corpus_score(hyps, [rs]).score / 100

    observed_a = corpus_chrf(hyps_a, refs)
    observed_b = corpus_chrf(hyps_b, refs)
    observed_diff = observed_b - observed_a

    resample_diffs = []
    for _ in range(n_resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        ra = [hyps_a[i] for i in idx]
        rb = [hyps_b[i] for i in idx]
        rr = [refs[i] for i in idx]
        resample_diffs.append(corpus_chrf(rb, rr) - corpus_chrf(ra, rr))

    result = _summarize_resamples(observed_diff, resample_diffs)
    result.update({"n_segments": n, "chrf_a": round(observed_a, 4), "chrf_b": round(observed_b, 4)})
    return result


def _load_model_comparison_pairs(
    json_path: Path, model_a: str, model_b: str, metric: str
) -> tuple[list[float], list[float], list[str]]:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    by_benchmark: dict[str, dict[str, dict]] = {}
    for r in data["results"]:
        if "error" in r:
            continue
        by_benchmark.setdefault(r["benchmark_id"], {})[r["model"]] = r

    scores_a, scores_b, benchmark_ids = [], [], []
    skipped = []
    for benchmark_id, by_model in by_benchmark.items():
        if model_a not in by_model or model_b not in by_model:
            skipped.append(benchmark_id)
            continue
        val_a, val_b = by_model[model_a].get(metric), by_model[model_b].get(metric)
        if val_a is None or val_b is None:
            skipped.append(benchmark_id)
            continue
        scores_a.append(val_a)
        scores_b.append(val_b)
        benchmark_ids.append(benchmark_id)

    if skipped:
        print(f"警告: 両モデルの{metric}が揃わなかったため除外したベンチマーク: {skipped}")

    return scores_a, scores_b, benchmark_ids


def save_result(model_a: str, model_b: str, metric: str, result: dict, benchmark_ids: list[str]) -> None:
    EXPERIMENTS_DIR.mkdir(exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    json_path = EXPERIMENTS_DIR / f"{today}_significance_{model_a}_vs_{model_b}_{metric}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": date.today().strftime("%Y-%m-%d"),
                "method": "paired bootstrap resampling (Koehn 2004)",
                "model_a": model_a,
                "model_b": model_b,
                "metric": metric,
                "benchmark_ids": benchmark_ids,
                "result": result,
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
            writer.writerow(["date", "model", "domain", "llm_judge", "chrf_score", "notes"])
        notes = (
            f"[significance_test][paired bootstrap, Koehn 2004, n_units={result['n_units']}, "
            f"n_resamples={result['n_resamples']}] {model_a}(mean={result['mean_a']}) vs "
            f"{model_b}(mean={result['mean_b']}) on {metric}: "
            f"diff={result['observed_diff']} (95%CI={result['ci95_diff']}), "
            f"p_value_approx={result['p_value_approx']}, "
            f"win_prob({model_b}>{model_a})={result['win_prob_b_gt_a']}"
        )
        writer.writerow([date.today().strftime("%Y-%m-%d"), f"{model_a} vs {model_b}", "", "", "", notes])
    print(f"results.csv を更新: {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "model_comparison.py が出力したJSONから2モデルのスコア差を取り出し、"
            "ペアードブートストラップ検定（Koehn 2004）で有意性を判定する"
        )
    )
    parser.add_argument("model_comparison_json", type=Path)
    parser.add_argument("model_a")
    parser.add_argument("model_b")
    parser.add_argument(
        "--metric",
        default="chrf_score_mean",
        choices=["chrf_score_mean", "llm_judge_mean", "comet_score_mean", "cometkiwi_score_mean"],
        help="比較する指標（既定: chrf_score_mean）",
    )
    parser.add_argument("--n-resamples", type=int, default=DEFAULT_N_RESAMPLES)
    args = parser.parse_args()

    if not args.model_comparison_json.exists():
        print(f"エラー: {args.model_comparison_json} が見つかりません")
        sys.exit(1)

    scores_a, scores_b, benchmark_ids = _load_model_comparison_pairs(
        args.model_comparison_json, args.model_a, args.model_b, args.metric
    )
    if len(scores_a) < 2:
        print("エラー: 両モデルが揃うベンチマークが2件未満のため検定できません")
        sys.exit(1)

    result = bootstrap_paired_diff(scores_a, scores_b, n_resamples=args.n_resamples)

    print(f"\n=== {args.model_a} vs {args.model_b} ({args.metric}, n={len(benchmark_ids)}ベンチマーク) ===")
    print(f"平均: {args.model_a}={result['mean_a']}  {args.model_b}={result['mean_b']}")
    print(f"観測差 ({args.model_b} - {args.model_a}): {result['observed_diff']}")
    print(f"95%信頼区間: {result['ci95_diff']}")
    print(f"近似p値: {result['p_value_approx']}")
    print(f"{args.model_b}が{args.model_a}を上回る確率(ブートストラップ内): {result['win_prob_b_gt_a']}")

    if result["p_value_approx"] < 0.05:
        direction = "上回る" if result["observed_diff"] > 0 else "下回る"
        print(f"\n=> 有意水準0.05で統計的に有意: {args.model_b}は{args.model_a}を一貫して{direction}と言える。")
    else:
        print("\n=> 有意水準0.05では統計的に有意と言えない(観測されたベンチマーク数の中では偶然の範囲)。")

    save_result(args.model_a, args.model_b, args.metric, result, benchmark_ids)


if __name__ == "__main__":
    main()
