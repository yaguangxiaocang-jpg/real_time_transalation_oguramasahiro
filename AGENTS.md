# AGENTS.md

uv で管理する Python 3.13 のプロジェクトです。翻訳精度の実験を記録するときのルールは `CLAUDE.md` を、設計は `DESIGN_DOC.md` を参照してください。

## プロジェクト構造

```text
├── src/real_time_translation/   # メインパッケージ
│   ├── audio/                   # 音声取得
│   ├── transcription/           # 文字起こし（Deepgram / Whisper）と発話の結合
│   ├── translation/             # 翻訳、用語辞書、品質チェック
│   ├── config.py                # 設定管理
│   ├── gradio_demo.py           # Web UI
│   ├── pipeline.py              # パイプライン統合
│   └── main.py                  # CLI エントリーポイント
├── services/                    # マイクロサービス（asr / translator / ws）
├── evaluation/                  # 翻訳品質の評価とベンチマーク
├── experiments/                 # 実験記録
├── tests/                       # テスト
├── add_subtitles.py             # 動画字幕の生成スクリプト
├── pyproject.toml               # プロジェクト設定
└── .env.example                 # 環境変数テンプレート
```

## コマンド

```bash
# 依存関係のインストール（必要に応じて --extra zoom / --extra microphone を追加）
uv sync --extra dev

# 依存関係の追加
uv add <package-name>
uv add --dev <package-name>

# 実行
uv run real-time-translation       # Zoom RTMS 向け CLI（--extra zoom が必要）
uv run real-time-translation-demo  # Web UI

# テストとリント
uv run pytest
uv run ruff check .
uv run ruff format .
```

## 主要コンポーネント

| モジュール | 役割 |
|---|---|
| `audio/capture.py` | Zoom RTMS とキュー経由の音声取得 |
| `transcription/deepgram_client.py` | Deepgram WebSocket の文字起こし |
| `transcription/utterance_merge.py` | 分断された発話の結合 |
| `translation/llm_translator.py` | Gemini / OpenAI の翻訳 |
| `translation/dictionary.py` | 用語辞書 |
| `pipeline.py` | 音声 → 文字起こし → 翻訳のフロー制御 |
| `config.py` | 環境変数からの設定読み込み |

## コーディング規約

- **フォーマッター:** Ruff（line-length: 88）
- **リンター:** Ruff（E, F, I, UP, B, SIM）
- **型ヒント:** 必須
- **非同期:** asyncio を使う

## 注意事項

- 依存関係は `uv add` で追加します。
- `uv.lock` は自動生成されるファイルで、Git の管理対象外です。手動で編集しないでください。
- API キーは `.env` で管理します（Git の管理対象外）。
