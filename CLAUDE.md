# CLAUDE.md - Claude Code 向け指示書

## 実験記録ルール

**翻訳精度の比較実験を行ったら必ず以下を実行すること：**

1. `experiments/YYYYMMDD_<実験名>.json` を作成
2. `experiments/results.csv` に1行追記（なければ新規作成）
3. `git add` してコミット

`add_subtitles.py` は 1 と 2 を自動で行うので、実行後はコミットだけでよい。

---

## experiments フォルダ構成

```text
experiments/
  20260312_gemini_25_flash_general.json
  20260312_gemini_flash_25_economics.json
  results.csv
  segments/      # add_subtitles.py が保存する原文・訳文・タイムスタンプの生データ
```

---

## JSON フォーマット

```json
{
  "date": "2026-03-05",
  "model": "gemini-2.5-flash",
  "domain": "particle_physics",
  "llm_judge": 0.97,
  "chrf_score": 0.71,
  "comet_score": 0.86,
  "cometkiwi_score": 0.82,
  "notes": "CKM matrixの訳が不安定。旧モデルのほうが安定していた"
}
```

### フィールド説明

| フィールド | 説明 |
|---|---|
| `date` | 実験日（YYYY-MM-DD） |
| `model` | 使用した翻訳モデル名 |
| `domain` | 翻訳ドメイン（例: particle_physics, general） |
| `llm_judge` | Gemini による LLM-as-judge スコア（0〜1）※任意。0.98〜1.0 に張り付きやすく差の検出力が低い |
| `chrf_score` | 文字 n-gram 一致の chrF（0〜1、高いほど良い）※任意 |
| `comet_score` | COMET-22（wmt22-comet-da、参照訳あり、0〜1）※任意 |
| `cometkiwi_score` | CometKiwi-22（wmt22-cometkiwi-da、参照訳なし QE、0〜1）※任意 |
| `notes` | 観察メモ・問題点・改善案など |

スコアを測らない場合は、スコアの項目を省略または `null` にして、代わりに `notes` に記述式の評価を詳しく書くこと。

> **注意（2026-09-29 改名）:** `llm_judge` は以前 `xcomet_score` という名前だったが、
> 中身は最初から本物の xCOMET ではなく Gemini の LLM 判定だった。過去の JSON・CSV も
> 一括で `llm_judge` に改名済み（notes 本文中の「xCOMET」表記は当時の記録のまま）。
> 本物の学習済み指標は `evaluation/neural_metrics.py`（COMET-22 / CometKiwi-22）で計算する。
> `unbabel-comet` は Python 3.13 に入らないため、Python 3.12 の使い捨て uv 環境で
> subprocess 実行している。CometKiwi は HuggingFace の gated モデルなので、
> ライセンス同意と `HF_TOKEN` 設定が済むまでは空欄になる。

---

## results.csv フォーマット

```csv
date,model,domain,llm_judge,chrf_score,notes,comet_score,cometkiwi_score
2026-03-05,gemini-2.5-flash,particle_physics,0.97,0.71,CKM matrixの訳が不安定,0.86,0.82
```

`comet_score` と `cometkiwi_score` は後方互換のため `notes` の後ろの列にある。6列だけの行も有効。

---

## アドホック実験 vs ベンチマーク実験（重要）

動画やセグメント数が毎回違う実験では、スコアの変化がパイプラインの変更によるものか、
動画が訳しやすかっただけなのかを区別できない。比較実験は次の2種類を使い分けること。

### ① アドホック実験

新しい動画・新しいドメインで**探索的に**問題を見つけるための実験。
`add_subtitles.py <video>` を実行する。原文・訳文・タイムスタンプの生データは
`experiments/segments/YYYYMMDD_<動画名>.json` に自動保存され、ベンチマーク作成の材料になる。

### ② ベンチマーク実験（before/after比較をしたいとき）

**同じ入力データ**に対してパイプライン変更の効果だけを測るための回帰テスト。

1. `evaluation/benchmarks/*.json` に、固定の入力（`raw_utterances`）と
   人手レビュー済みの正解訳（`reference_ja`）を用意する
   （`experiments/segments/*.json` から代表的なセグメントを選ぶとよい）
2. `python evaluation/run_benchmark.py evaluation/benchmarks/<name>.json` を実行
   （`--thinking-budget` / `--context-window-size` で変更したいパラメータだけ渡す）
3. 結果は `experiments/results.csv` に `[benchmark=<name>]` タグ付きで記録される
   （逆翻訳ではなく正解訳と直接比較するため、アドホック実験の chrF より信頼度が高い）

マイクのリアルタイム翻訳と動画/CLI は同じアルゴリズム
（`merge_incomplete_utterances` / `StreamingUtteranceMerger`、`LLMTranslator`）を
使うため、ベンチマークの結果は両方に適用できる。ただし `thinking_budget` の既定は
マイクが 0（低遅延優先）、動画/CLI が 1024（精度優先）で異なる。マイク相当の設定は
`--thinking-budget 0` で検証できる。

### ベンチマークの正解訳（reference_ja）について

`evaluation/benchmarks/` の14件はすべて `reference_status: "human_reviewed"`
（確定時の方針は各ファイルの `reference_note`、元の草案は `reference_ja_draft`）。

- 参照訳を変更したら、`python evaluation/rescore_neural.py experiments/<...>_model_comparison.json`
  で chrF・COMET ともに再採点すること（`chrf_score_mean` は実行時点の参照訳に対する値のため）。
- 新しいベンチマークの正解訳は、訳語を `dictionary.csv` に合わせ、同じ英文が既存の
  ベンチマークにあれば訳を揃えること。
- 人手レビュー前の草案は `reference_status: "draft_needs_human_review"` とし、スコアの
  絶対値ではなく同じベンチマークでの実行間の相対的な変化の参考としてのみ使うこと。

---

## ドキュメントの置き場所

- 利用者向けの説明は `README.md`（画面）と `USE.md`（CLI）に書く
- 開発上の変更内容・検証結果は `CHANGELOG.md` の先頭に追記する
- コード内の「README更新履歴参照」は `CHANGELOG.md` のことを指す
