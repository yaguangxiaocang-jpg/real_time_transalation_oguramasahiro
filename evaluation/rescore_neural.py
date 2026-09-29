"""保存済みの model_comparison 結果を、現在の参照訳で COMET-22 / CometKiwi-22 再採点する。

`experiments/*_model_comparison.json` は全実行の訳文（runs[].hyps）を保存しているので、
翻訳APIを叩き直さずに、参照訳の人手レビュー後の reference_ja と学習済み指標で
スコアを付け直せる。結果は各集計に `comet_score_mean` / `cometkiwi_score_mean` を
追加した新しいJSON（`<元ファイル名>_rescored_<今日>.json`）として保存し、
`significance.py --metric comet_score_mean` でそのまま有意差検定できる。

参照訳と訳文のセグメント数が合わないベンチマーク（結合結果が参照訳の粒度と
異なるもの）は COMET-22 を計算せず CometKiwi のみとする。

使い方:
    python evaluation/rescore_neural.py experiments/20260907_model_comparison.json
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from neural_metrics import score_neural_batch  # noqa: E402
from run_benchmark import merge_raw_utterances  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
BENCHMARKS_DIR = REPO_ROOT / "evaluation" / "benchmarks"
EXPERIMENTS_DIR = REPO_ROOT / "experiments"


def main(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    aggs = [r for r in data["results"] if "runs" in r]

    benchmarks: dict[str, dict] = {}
    items, index = [], []
    for ai, agg in enumerate(aggs):
        bid = agg["benchmark_id"]
        if bid not in benchmarks:
            benchmarks[bid] = json.loads(
                (BENCHMARKS_DIR / f"{bid}.json").read_text(encoding="utf-8")
            )
        bench = benchmarks[bid]
        srcs = [s["transcript"] for s in merge_raw_utterances(bench)]
        for ri, run in enumerate(agg["runs"]):
            items.append((srcs, run["hyps"], bench["reference_ja"]))
            index.append((ai, ri))

    print(f"{len(items)}実行・{sum(len(h) for _, h, _ in items)}セグメントを採点中...")
    scores = score_neural_batch(items)

    for (ai, ri), sc in zip(index, scores):
        aggs[ai]["runs"][ri].update(
            {k: sc[k] for k in ("comet_score", "cometkiwi_score", "comet_segments", "cometkiwi_segments")}
        )
    for agg in aggs:
        for key in ("comet_score", "cometkiwi_score"):
            vals = [r[key] for r in agg["runs"] if r.get(key) is not None]
            agg[f"{key}_mean"] = round(statistics.mean(vals), 4) if vals else None
        bench = benchmarks[agg["benchmark_id"]]
        agg["reference_status"] = bench.get("reference_status")

    today = date.today()
    data["rescored"] = {
        "date": today.isoformat(),
        "source": path.name,
        "metrics": ["Unbabel/wmt22-comet-da", "Unbabel/wmt22-cometkiwi-da"],
        "errors": scores[0]["errors"] if scores else {},
    }
    out_path = EXPERIMENTS_DIR / f"{path.stem}_rescored_{today:%Y%m%d}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    with open(EXPERIMENTS_DIR / "results.csv", "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        for agg in aggs:
            notes = (
                f"[benchmark={agg['benchmark_id']}][rescore_neural][source={path.name}] "
                f"保存済み訳文(n={len(agg['runs'])})を再採点。"
                f"reference_status={agg['reference_status']}"
            )
            w.writerow(
                [today.isoformat(), agg["model"], "", agg.get("llm_judge_mean", ""),
                 agg.get("chrf_score_mean", ""), notes,
                 "" if agg["comet_score_mean"] is None else agg["comet_score_mean"],
                 "" if agg["cometkiwi_score_mean"] is None else agg["cometkiwi_score_mean"]]
            )

    print(f"\n結果を保存: {out_path}")
    for agg in aggs:
        print(
            f"{agg['benchmark_id']:<52} {agg['model']:<24} "
            f"chrF={agg.get('chrf_score_mean')} COMET={agg['comet_score_mean']} "
            f"Kiwi={agg['cometkiwi_score_mean']}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    main(parser.parse_args().path)
