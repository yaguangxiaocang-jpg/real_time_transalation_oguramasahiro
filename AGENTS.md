# AGENTS.md

このプロジェクトはuvを使用したPythonプロジェクト管理を行っています。

## プロジェクト構造

```
real_time_translation/
├── src/real_time_translation/   # メインパッケージ
│   ├── audio/                   # 音声取得モジュール
│   ├── transcription/           # 文字起こし・発話結合・Whisper再検証
│   ├── translation/             # 翻訳・辞書・品質チェック
│   ├── config.py                # 設定管理
│   ├── pipeline.py              # パイプライン統合
│   ├── latency.py               # 遅延計測
│   ├── gradio_demo.py           # Web UI
│   ├── dictionary_tab.py        # Web UI の辞書タブ
│   └── main.py                  # CLIエントリーポイント
├── add_subtitles.py             # 動画字幕のCLI
├── launcher.py                  # launch.bat から起動するデスクトップ用ランチャー
├── app.py                       # Hugging Face Spaces 用エントリーポイント
├── evaluation/                  # ベンチマーク・評価スクリプト
├── experiments/                 # 実験記録（CLAUDE.md 参照）
├── services/                    # Zoom 配信構成の Docker サービス
├── tests/                       # テストファイル
├── pyproject.toml               # プロジェクト設定
└── .env.example                 # 環境変数テンプレート
```

## パッケージマネージャ: uv

```bash
# 依存関係のインストール
uv sync --extra dev

# 依存関係の追加
uv add <package-name>
uv add --dev <package-name>

# スクリプトの実行
uv run real-time-translation
uv run pytest
uv run ruff check .
```

## 主要コンポーネント

| モジュール                         | 役割                             |
| ---------------------------------- | -------------------------------- |
| `audio/capture.py`                 | マイク・Zoom RTMSからの音声取得  |
| `transcription/deepgram_client.py` | Deepgram WebSocket文字起こし     |
| `translation/llm_translator.py`    | Gemini/OpenAI翻訳                |
| `pipeline.py`                      | 音声→文字起こし→翻訳のフロー制御 |
| `config.py`                        | 環境変数からの設定読み込み       |

## コーディング規約

- **フォーマッター**: Ruff (line-length: 88)
- **リンター**: Ruff (E, F, I, UP, B, SIM)
- **型ヒント**: 必須
- **非同期**: asyncio使用

## 注意事項

- `uv.lock`は自動生成、手動編集不可
- 依存関係は`uv add`コマンドで追加
- APIキーは`.env`ファイルで管理（gitignored）
