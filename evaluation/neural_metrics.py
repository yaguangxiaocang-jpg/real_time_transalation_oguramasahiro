"""学習済みニューラル翻訳評価指標（COMET-22 / CometKiwi-22）。

2026-09-29追加。それまで results.csv の `xcomet_score` 列は名前に反して本物の
xCOMET ではなく Gemini の LLM-as-judge で、0.98〜1.0 に張り付く天井効果により
モデル間の差を検出できていなかった（flash-lite比較で p=0.40）。列を `llm_judge`
に改名し、本物の学習済み指標を別列で追加した。

- `comet_score`:     COMET-22（Unbabel/wmt22-comet-da）。参照訳あり。WMT22標準。
- `cometkiwi_score`: CometKiwi-22（Unbabel/wmt22-cometkiwi-da）。参照訳なしQE。
  参照訳の品質（人手レビュー未了のdraft）に左右されない。HuggingFaceの gated
  モデルなので、HFでライセンスに同意し `HF_TOKEN` を設定するまでは None になる。

xCOMET-XL/XXL は 3.5B/10.7B パラメータで、GPUの無い開発機（RAM 15GB）では
実用的に動かないため採用していない。

`unbabel-comet` は Python 3.13 にインストールできないため、計算は
`evaluation/comet_worker.py` を Python 3.12 の使い捨て uv 環境で subprocess
実行して行う（初回は依存とモデル約2.3GB/件のダウンロードで数分かかる）。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

WORKER = Path(__file__).parent / "comet_worker.py"
UV_CMD = [
    "uv", "run", "--no-project", "--python", "3.12",
    "--with", "unbabel-comet==2.2.7", "--with", "setuptools<81",
    "python", str(WORKER),
]


def score_neural(
    srcs: list[str],
    hyps: list[str],
    refs: list[str] | None = None,
    metrics: tuple[str, ...] = ("comet22", "cometkiwi"),
) -> dict:
    """COMET-22（refsがあるとき）とCometKiwi-22でセグメント単位・システム単位のスコアを返す。

    Returns:
        {"comet_score": float|None, "cometkiwi_score": float|None,
         "comet_segments": [...]|None, "cometkiwi_segments": [...]|None,
         "errors": {metric: message}}
        いずれかの指標が使えなくても例外は投げず None を返す（評価の本体を止めない）。
    """
    wanted = [m for m in metrics if m != "comet22" or refs]
    result: dict = {
        "comet_score": None,
        "cometkiwi_score": None,
        "comet_segments": None,
        "cometkiwi_segments": None,
        "errors": {},
    }
    if not wanted:
        return result

    with tempfile.TemporaryDirectory() as tmp:
        in_path, out_path = Path(tmp) / "in.json", Path(tmp) / "out.json"
        in_path.write_text(
            json.dumps(
                {"src": srcs, "mt": hyps, "ref": refs, "metrics": wanted},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        try:
            proc = subprocess.run(
                [*UV_CMD, str(in_path), str(out_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            result["errors"] = {m: f"{type(e).__name__}: {e}" for m in wanted}
            return result
        if not out_path.exists():
            tail = (proc.stderr or "").strip().splitlines()[-3:]
            result["errors"] = {m: " / ".join(tail) for m in wanted}
            return result
        out = json.loads(out_path.read_text(encoding="utf-8"))

    for name, prefix in (("comet22", "comet"), ("cometkiwi", "cometkiwi")):
        r = out.get(name)
        if not r:
            continue
        if "error" in r:
            result["errors"][name] = r["error"]
        else:
            result[f"{prefix}_score"] = r["system"]
            result[f"{prefix}_segments"] = r["segments"]
    for name, msg in result["errors"].items():
        print(f"  {name}: スキップ（{msg[:160]}）")
    if result["comet_score"] is not None:
        print(f"  comet_score (COMET-22): {result['comet_score']}")
    if result["cometkiwi_score"] is not None:
        print(f"  cometkiwi_score (CometKiwi-22 QE): {result['cometkiwi_score']}")
    return result


def score_neural_batch(
    items: list[tuple[list[str], list[str], list[str] | None]],
) -> list[dict]:
    """複数の (srcs, hyps, refs) をワーカー1回（モデル読み込み1回）でまとめて採点する。

    `score_neural` を実行ごとに呼ぶと毎回 uv 環境の起動とモデル読み込み（約25秒）が
    かかるため、model_comparison のような多数実行の採点はこちらを使う。
    refs が None または hyps と件数が合わない項目は CometKiwi のみ計算する。
    各項目の system スコアはセグメントスコアの平均（COMETの system_score と同じ定義）。
    """
    with_ref = [i for i, (_, h, r) in enumerate(items) if r and len(r) == len(h)]
    flat_src = [src for srcs, _, _ in items for src in srcs]
    flat_hyp = [hyp for _, hyps, _ in items for hyp in hyps]
    spans, pos = [], 0
    for _, hs, _ in items:
        spans.append((pos, pos + len(hs)))
        pos += len(hs)

    kiwi = score_neural(flat_src, flat_hyp, None, metrics=("cometkiwi",))
    ref_src = [s for i in with_ref for s in items[i][0]]
    ref_hyp = [h for i in with_ref for h in items[i][1]]
    ref_ref = [r for i in with_ref for r in items[i][2]]
    comet = score_neural(ref_src, ref_hyp, ref_ref, metrics=("comet22",)) if with_ref else None

    comet_seg_by_item: dict[int, list[float]] = {}
    if comet and comet["comet_segments"]:
        p = 0
        for i in with_ref:
            n = len(items[i][1])
            comet_seg_by_item[i] = comet["comet_segments"][p : p + n]
            p += n

    def mean(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 4)

    out = []
    for i, (a, b) in enumerate(spans):
        kseg = kiwi["cometkiwi_segments"][a:b] if kiwi["cometkiwi_segments"] else None
        cseg = comet_seg_by_item.get(i)
        out.append(
            {
                "comet_score": mean(cseg) if cseg else None,
                "cometkiwi_score": mean(kseg) if kseg else None,
                "comet_segments": cseg,
                "cometkiwi_segments": kseg,
                "errors": {**kiwi["errors"], **((comet or {}).get("errors") or {})},
            }
        )
    return out
