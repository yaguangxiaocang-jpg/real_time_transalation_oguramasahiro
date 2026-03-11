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
