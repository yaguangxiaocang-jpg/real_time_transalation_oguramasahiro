# CLAUDE.md - Claude Code 向け指示書

## 実験記録ルール

**翻訳精度の比較実験を行ったら必ず以下を実行すること：**

1. `/experiments/YYYYMMDD_<実験名>.json` を作成
2. `/experiments/results.csv` に1行追記（なければ新規作成）
3. `git add` してコミット

---

## experiments フォルダ構成

```
/experiments
  20260305_gemini_flash_25_particle.json
  20260305_gemini_flash_30_particle.json
  results.csv
```

---

## JSON フォーマット

```json
{
  "date": "2026-03-05",
  "model": "gemini-flash-2.5",
  "domain": "particle_physics",
  "xcomet_score": 0.87,
  "chrf_score": 0.71,
  "notes": "CKM matrixの訳が不安定。旧モデルのほうが安定していた"
}
```

### フィールド説明

| フィールド | 説明 |
|---|---|
| `date` | 実験日（YYYY-MM-DD） |
| `model` | 使用した翻訳モデル名 |
| `domain` | 翻訳ドメイン（例: particle_physics, general） |
| `xcomet_score` | 自動評価スコア（0〜1、高いほど良い）※任意 |
| `chrf_score` | 自動評価スコア（0〜1、高いほど良い）※任意 |
| `notes` | 観察メモ・問題点・改善案など |

---

## results.csv フォーマット

```csv
date,model,domain,xcomet_score,chrf_score,notes
2026-03-05,gemini-flash-2.5,particle_physics,0.87,0.71,CKM matrixの訳が不安定
```

---

## 自動評価を使わない場合

`xcomet_score` と `chrf_score` は省略可。代わりに `notes` に記述式の評価を詳しく記録すること。

例：
```json
{
  "date": "2026-03-05",
  "model": "gemini-flash-2.5",
  "domain": "particle_physics",
  "xcomet_score": null,
  "chrf_score": null,
  "notes": "専門用語の一貫性が高い。ただし受動態の処理が不自然な箇所あり。前モデルより全体的に自然。"
}
```

---

## アドホック実験 vs ベンチマーク実験（重要）

`experiments/*.json` に残っている実験履歴を見るとわかるが、これまでの実験は
**毎回違う動画・違うセグメント数**で行われてきた（index.mp4 → short_test.mp4 →
short_test_llm.mp4 → short_test_llm8.mp4 …）。この方式には限界がある：
スコアが変化しても、それがパイプラインの変更（thinking_budget・
context_window_size・utterance結合パラメータ・プロンプトなど）による効果なのか、
単に今回の動画が訳しやすかっただけなのか区別できない。

このため、比較実験には2種類ある。使い分けること。

### ① アドホック実験（従来通り）

新しい動画・新しいドメインで**探索的に**問題を見つけるための実験。
`add_subtitles.py <video>` を実行し、上記のルール通り `experiments/` に記録する。
`add_subtitles.py` は実行のたびに `experiments/segments/YYYYMMDD_<動画名>.json` に
原文・訳文・タイムスタンプの生データも自動保存する（後述のベンチマーク作成の
材料になる）。

### ② ベンチマーク実験（before/after比較をしたいとき）

**同じ入力データ**に対してパイプライン変更の効果だけを測るための回帰テスト。

1. `evaluation/benchmarks/*.json` に、固定の入力（`raw_utterances`）と
   人手レビュー済みの正解訳（`reference_ja`）を用意する
   （`add_subtitles.py` が生成する `experiments/segments/*.json` の中から、
   代表的なセグメントを選んで作るとよい）
2. `python evaluation/run_benchmark.py evaluation/benchmarks/<name>.json` を実行
   （`--thinking-budget` / `--context-window-size` で変更したいパラメータだけ渡す）
3. 結果は `experiments/results.csv` に `[benchmark=<name>]` タグ付きで記録される
   （reference-based chrF。逆翻訳ではなく正解訳と直接比較するため、
   アドホック実験のchrFより信頼度が高い）

**マイクのリアルタイム翻訳とアドホック実験（動画/CLI）は同じアルゴリズム**
（`merge_incomplete_utterances` / `StreamingUtteranceMerger`、
`LLMTranslator`）を使っているため、ベンチマーク実験の結果は両方の経路に
適用できると考えてよい。ただし `thinking_budget` はマイク側が既定0
（低遅延優先）、動画/CLI側が既定1024（精度優先）で異なる点に注意
（`evaluation/run_benchmark.py` の `--thinking-budget 0` でマイク側相当の
設定も検証できる）。

### ベンチマークの正解訳（reference_ja）について

`reference_status: "draft_needs_human_review"` のベンチマークは、まだ人手
レビューが済んでいない草案。スコアの絶対値ではなく、同じベンチマークに対する
実行間の相対的な変化（改善/悪化）の参考としてのみ使うこと。本格的に運用する
前に、ドメイン知識のある人が正解訳を確認・修正すること。
