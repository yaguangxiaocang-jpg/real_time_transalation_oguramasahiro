"""whisper_reverify.pyのmin_confidence閾値の適合率-再現率(PR)曲線を求める。

report.txtの優先課題(2)（min_confidenceを0.6にすると既知の誤補正MOA->MOEは
解消できるが、正しい補正2件(T5・GPT-3)も一緒に抑制されてしまう適合率/再現率の
トレードオフ）への対応。単一の閾値を勘で探すのではなく、既知の正例(true
positive)/負例(false positive)ラベルに対してPR曲線・AUC-PR・最適F1点を機械的に
計算し、「そもそも単一の絶対閾値だけで両方を満たせるのか」を定量的に判定する。

`evaluation/whisper_reverify_confidence_sweep.py`が保存したJSON
（`experiments/YYYYMMDD_whisper_reverify_confidence_sweep.json`）の
`candidates`（find_candidatesが返す生候補、閾値・ambiguousガード適用前）を
入力にする。生候補には「原文スパン→候補用語」の組ごとに既知の正誤ラベルが
`whisper_reverify_confidence_sweep.py`のdocstringに記載されているので、それを
そのままground truthとして使う。ラベルが未知の組み合わせ（新しいクリップなどで
初めて観測されたもの）は集計から除外し、警告を表示する（＝このスクリプトは
既知の少数事例に対する再現性チェックであり、未知の誤り一般を検出するものでは
ない点に注意）。

Note: この分析はguard1（ambiguous_original、既知の紛らわしい用語ペアを常時
ブロックする別ガード）を無視し、min_confidenceの閾値だけで判定した場合の
理論的なPR曲線を出す。実運用ではguard1が先にMOAを弾くため、実際に発火する
補正はguard1適用後の`sweep`フィールドの方に一致する。

使い方:
    python evaluation/whisper_reverify_pr_curve.py \
        experiments/20260912_whisper_reverify_confidence_sweep.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

# report.txt・whisper_reverify_confidence_sweep.pyのdocstringに記載された、
# 実データ(technology_moe_2d07bb74_clip1〜5)で観測済みの既知の正誤ラベル。
# キーは (original_span, candidate) の正規化済み小文字ペア。
KNOWN_LABELS: dict[tuple[str, str], str] = {
    ("tifine", "t5"): "TP",
    ("tfi", "t5"): "TP",
    ("tifi", "t5"): "TP",
    ("t five", "t5"): "TP",
    ("parm", "palm"): "TP",
    ("parm two", "palm2"): "TP",
    ("parm two", "palm 2"): "TP",
    ("g p three", "gpt-3"): "TP",
    ("g p g three", "gpt-3"): "TP",
    ("g p t three", "gpt-3"): "TP",
    ("memory war", "memory wall"): "TP",
    ("moa", "moe"): "FP",
}


def label_candidate(candidate: dict) -> str | None:
    key = (candidate["original_span"].lower(), candidate["candidate"].lower())
    return KNOWN_LABELS.get(key)


def build_pr_curve(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """既知ラベル付き候補を信頼度降順に並べ、各閾値での適合率/再現率を計算する。

    Returns:
        (labeled_candidates, curve) のタプル。curveの各要素は
        {"threshold", "tp", "fp", "precision", "recall", "f1"}。
    """
    labeled = []
    unknown = []
    for c in candidates:
        label = label_candidate(c)
        if label is None:
            unknown.append(c)
            continue
        labeled.append({**c, "label": label})

    if unknown:
        print(f"警告: 既知ラベルに一致しない候補を{len(unknown)}件除外しました:")
        for c in unknown:
            print(f"  [{c['clip_id']}] {c['original_span']!r} -> {c['candidate']!r} (ラベル不明)")

    total_tp = sum(1 for c in labeled if c["label"] == "TP")
    if total_tp == 0:
        raise ValueError("既知の正例(TP)が1件もありません。KNOWN_LABELSを確認してください。")

    # 各候補自身のmin_span_confidenceを閾値候補にする（PR曲線はこれらの点でしか
    # 変化しないため、これで十分に完全な階段関数が描ける）。閾値=その値ちょうど
    # を含む(>=)ことを明示するため、値そのものと「わずかに下」を両方使う。
    thresholds = sorted({c["min_span_confidence"] for c in labeled}, reverse=True)

    curve = []
    for th in thresholds:
        fired = [c for c in labeled if c["min_span_confidence"] >= th]
        tp = sum(1 for c in fired if c["label"] == "TP")
        fp = sum(1 for c in fired if c["label"] == "FP")
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / total_tp
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        curve.append(
            {
                "threshold": th,
                "tp": tp,
                "fp": fp,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
            }
        )

    # 閾値0（全件発火）の点も末尾に追加し、recall=1.0地点を明示する。
    if thresholds[-1] > 0.0:
        fired = labeled
        tp = sum(1 for c in fired if c["label"] == "TP")
        fp = sum(1 for c in fired if c["label"] == "FP")
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / total_tp
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        curve.append(
            {"threshold": 0.0, "tp": tp, "fp": fp, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}
        )

    return labeled, curve


def auc_pr(curve: list[dict]) -> float:
    """recall昇順に並べ替えて台形則でAUC-PRを積分する（純Python実装）。"""
    points = sorted({(c["recall"], c["precision"]) for c in curve})
    area = 0.0
    for (r0, p0), (r1, p1) in zip(points, points[1:]):
        area += (r1 - r0) * (p0 + p1) / 2
    return round(area, 4)


def find_best_threshold(curve: list[dict]) -> dict:
    return max(curve, key=lambda c: (c["f1"], c["threshold"]))


def find_perfect_threshold(curve: list[dict]) -> dict | None:
    perfect = [c for c in curve if c["precision"] == 1.0 and c["recall"] == 1.0]
    return perfect[0] if perfect else None


def load_latest_sweep_json() -> Path:
    candidates = sorted(EXPERIMENTS_DIR.glob("*_whisper_reverify_confidence_sweep.json"))
    if not candidates:
        print("エラー: experiments/*_whisper_reverify_confidence_sweep.json が見つかりません")
        sys.exit(1)
    return candidates[-1]


def save_results(source_json: Path, labeled: list[dict], curve: list[dict], auc: float, best: dict, perfect: dict | None) -> None:
    EXPERIMENTS_DIR.mkdir(exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    json_path = EXPERIMENTS_DIR / f"{today}_whisper_reverify_pr_curve.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": date.today().strftime("%Y-%m-%d"),
                "source": str(source_json),
                "method": "precision-recall curve over min_span_confidence (guard1/ambiguous_original excluded)",
                "labeled_candidates": labeled,
                "curve": curve,
                "auc_pr": auc,
                "best_f1_point": best,
                "perfect_point": perfect,
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
        if perfect:
            verdict = f"perfect_threshold={perfect['threshold']}で精度・再現率とも1.0達成可能"
        else:
            verdict = (
                f"単一閾値では精度1.0と再現率1.0を同時に満たせない"
                f"(best_f1={best['f1']}@threshold={best['threshold']}, precision={best['precision']}, recall={best['recall']})"
            )
        notes = (
            f"[whisper_reverify_pr_curve][source={source_json.name}] "
            f"AUC-PR={auc}, {verdict}"
        )
        writer.writerow([date.today().strftime("%Y-%m-%d"), "whisper_reverify", "technology", "", "", notes])
    print(f"results.csv を更新: {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="whisper_reverify min_confidenceのPR曲線を計算する")
    parser.add_argument(
        "sweep_json",
        type=Path,
        nargs="?",
        default=None,
        help="whisper_reverify_confidence_sweep.pyが出力したJSON（省略時は最新のものを自動選択）",
    )
    args = parser.parse_args()

    source_json = args.sweep_json or load_latest_sweep_json()
    if not source_json.exists():
        print(f"エラー: {source_json} が見つかりません")
        sys.exit(1)

    with open(source_json, encoding="utf-8") as f:
        data = json.load(f)

    labeled, curve = build_pr_curve(data["candidates"])
    auc = auc_pr(curve)
    best = find_best_threshold(curve)
    perfect = find_perfect_threshold(curve)

    print(f"\n=== PR曲線 (source={source_json.name}) ===")
    print(f"{'threshold':>10} {'TP':>3} {'FP':>3} {'precision':>10} {'recall':>8} {'F1':>6}")
    for c in curve:
        print(f"{c['threshold']:>10} {c['tp']:>3} {c['fp']:>3} {c['precision']:>10} {c['recall']:>8} {c['f1']:>6}")

    print(f"\nAUC-PR: {auc}")
    print(f"最良F1点: threshold={best['threshold']}, precision={best['precision']}, recall={best['recall']}, F1={best['f1']}")
    if perfect:
        print(f"=> precision=1.0かつrecall=1.0を同時に満たす閾値が存在します: threshold={perfect['threshold']}")
    else:
        print(
            "=> どの単一閾値でもprecision=1.0とrecall=1.0を同時には満たせません。"
            "min_confidenceだけのチューニングでは限界があり、"
            "guard1（既知の紛らわしい用語ペアを個別にブロックする仕組み）のような"
            "用語ペア単位のルールが引き続き必要と言えます。"
        )

    save_results(source_json, labeled, curve, auc, best, perfect)


if __name__ == "__main__":
    main()
