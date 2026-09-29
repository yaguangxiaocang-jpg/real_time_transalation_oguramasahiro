"""COMET-22 / CometKiwi-22 を計算するワーカー（隔離環境で実行される）。

`unbabel-comet` は numpy<2 に固定されており、本プロジェクトの Python 3.13 では
wheel が無くインストールできない（2026-09-29確認）。そのためプロジェクトの venv
には入れず、`evaluation/neural_metrics.py` が以下のように Python 3.12 の使い捨て
環境で本スクリプトを subprocess 実行する:

    uv run --no-project --python 3.12 --with unbabel-comet --with "setuptools<81" \
        python evaluation/comet_worker.py in.json out.json

入力JSON: {"src": [...], "mt": [...], "ref": [...] or null, "metrics": ["comet22", "cometkiwi"]}
出力JSON: {"comet22": {"system": float, "segments": [...]} | {"error": str}, ...}

モデルは HuggingFace のシンボリックリンク方式キャッシュを使わず（Windowsの
一般ユーザー権限では WinError 1314 で失敗する）、`COMET_MODELS_DIR`（既定
`~/.cache/comet_models`）配下に実体ファイルとして保存する。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MODELS = {
    "comet22": "Unbabel/wmt22-comet-da",
    "cometkiwi": "Unbabel/wmt22-cometkiwi-da",  # gated: HFでライセンス同意+トークンが必要
}

MODELS_DIR = Path(
    os.environ.get("COMET_MODELS_DIR", Path.home() / ".cache" / "comet_models")
)


def _load(repo_id: str):
    from comet import load_from_checkpoint
    from huggingface_hub import snapshot_download

    local_dir = MODELS_DIR / repo_id.split("/")[-1]
    ckpt = local_dir / "checkpoints" / "model.ckpt"
    if not ckpt.exists():
        snapshot_download(repo_id, local_dir=str(local_dir))
    return load_from_checkpoint(str(ckpt))


def main(in_path: str, out_path: str) -> None:
    req = json.loads(Path(in_path).read_text(encoding="utf-8"))
    srcs, mts, refs = req["src"], req["mt"], req.get("ref")
    out: dict = {}
    for name in req.get("metrics", list(MODELS)):
        if name == "comet22" and not refs:
            out[name] = {"error": "reference required"}
            continue
        try:
            model = _load(MODELS[name])
            data = [
                {"src": s, "mt": m, **({"ref": refs[i]} if name == "comet22" else {})}
                for i, (s, m) in enumerate(zip(srcs, mts))
            ]
            pred = model.predict(data, batch_size=8, gpus=0, progress_bar=False)
            out[name] = {
                "system": round(float(pred.system_score), 4),
                "segments": [round(float(x), 4) for x in pred.scores],
            }
        except Exception as e:  # gated repo・ネットワーク失敗などは呼び出し側でスキップ扱い
            out[name] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
