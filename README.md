---
title: Real-time Translation
emoji: 🎙️
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.25.0
app_file: app.py
pinned: false
---

# 動画字幕生成・リアルタイム翻訳ツール

動画ファイルに日本語字幕を自動生成したり、マイクの音声をリアルタイムで翻訳するツールです。

---

## このツールでできること

| 機能 | 説明 |
|---|---|
| **動画に字幕を付ける** | 英語の動画を自動で文字起こし・翻訳し、日本語字幕付き動画を生成します |
| **マイクをリアルタイム翻訳** | マイクに向かって話すと、リアルタイムで文字起こし・翻訳されます |
| **音声ファイルを翻訳** | WAV・MP3 などの音声ファイルをアップロードして翻訳できます |

### 実績

- 90分の講義動画への字幕生成に対応
- 翻訳品質スコア xCOMET: **0.9925**（人間翻訳に近い水準）
- SRT 字幕ファイルの出力にも対応（YouTube などへの字幕アップロードに使用可）

---

## 必要なもの

### APIキー（2つ）

このツールは外部の AI サービスを使っています。利用には各サービスの API キーが必要です。
どちらも**無料枠**で始められます。
#支払方法の設定を絶対に忘れない
#従量課金しないと止まる
#### 1. Deepgram（音声を文字にするサービス）
1. [https://console.deepgram.com/](https://console.deepgram.com/) にアクセス
2. アカウントを作成してログイン
3. ダッシュボードの「API Keys」から新しいキーを作成
4. 表示された文字列をコピーして保管

#### 2. Google AI（Gemini）（文字を翻訳するサービス）
1. [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey) にアクセス
2. Google アカウントでログイン
3. 「APIキーを作成」をクリック
4. 表示された文字列をコピーして保管


> **無料枠の制限について**
> Gemini 無料枠では 1 分あたり約 10〜15 回の API 呼び出しが上限です。
> 90 分の動画の字幕生成には 90 分程度かかります。

---

## セットアップ（最初だけ）

### 前提条件

- Windows 10 / 11
- インターネット接続

### 手順

1. このフォルダ内の **`launch.bat`** をダブルクリックして起動します
2. 初回起動時は自動でブラウザが開きます
   - 開かない場合は [http://localhost:7861](http://localhost:7861) をブラウザで開いてください
3. 画面上部の「API Keys」欄に Deepgram と Google AI のキーを入力します

> タスクトレイ（画面右下）にアイコンが表示されます。右クリックして「終了」を選ぶとアプリが終了します。

---

## 使い方

### 動画に字幕を付ける（主な用途）

1. アプリを起動してブラウザを開く
2. **「🎬 動画字幕」タブ**をクリック
3. 「動画ファイル」欄に動画をドラッグ＆ドロップ（または「Upload」をクリック）
4. 「ドメイン」で動画の専門分野を選択（迷ったら `general`）
5. **「🎬 字幕を生成する」**ボタンをクリック
6. 処理が終わったら「字幕付き動画」と「SRT ファイル」をダウンロード

**処理の流れ（ログで確認できます）：**

```
🎵 音声を抽出中...
📝 文字起こし中（Deepgram）...
🌐 日本語に翻訳中（Gemini）...
🎬 字幕を動画に焼き込み中...
🎉 完了！
```

> **所要時間の目安**
> 動画の長さとほぼ同じ時間がかかります（90分動画 → 約90分）

---

### マイクをリアルタイム翻訳する

1. **「🎤 Microphone」タブ**をクリック
2. **「Start」**ボタンをクリック
3. マイクに向かって話す（英語など）
4. 画面下部に文字起こしと翻訳が表示される
5. 終了するときは**「Stop」**をクリック

---

### 出力ファイルについて

| ファイル | 説明 | 使い方 |
|---|---|---|
| 字幕付き動画（MP4） | 日本語字幕が焼き込まれた動画 | そのまま共有・配信に使用 |
| SRT ファイル | 字幕データのみ（動画なし） | YouTube などへの字幕追加に使用 |

#### SRT ファイルを YouTube に使う場合
1. YouTube Studio で動画をアップロード
2. 「字幕」タブ → 「ファイルをアップロード」
3. ダウンロードした `.srt` ファイルを選択

---

## 更新履歴

### 2026/09/08 (続き)

#### 変更内容

**Whisper再検証: ハイフン分割トークン化バグの修正**（前日「未検証」に残していた
「G p t three」→GPT-3が拾えない問題への対応、report.txtの優先課題(2)残課題）

原因はfaster-whisperが`"GPT-3,"`を単語レベルタイムスタンプ上で`"GPT"`と`"-3,"`の
2トークンに分割して返すことがあり、`whisper_reverify.py`の候補マッチング
（`" ".join(whisper_norm[j1:j2])`）は空白区切りで結合するため`"gpt -3"`になって
辞書の`"gpt-3"`と一致しなかった——信頼度チェック以前にトークン化の時点で候補
自体が成立していなかった（min_confidenceの問題ではなかった）。空白を除いた
結合形（`"gpt-3"`）でも一致を試すよう`apply_term_corrections()`を修正し、
一致した場合はWhisperの生の分割表記ではなく辞書の正式表記
（`TermDictionary`の元の大文字小文字）を置換文字列として使うようにした。
回帰テスト1件追加（`tests/test_whisper_reverify.py`、計11件）。

`clips/2d07bb74_clip3.mp4`の実音声で`reverify_terms()`を直接呼んで確認した結果、
`"G p t three and the parm two architectures..."` → `"GPT-3 and the parm two
architectures..."`と、想定通り補正が発火した。`evaluation/
whisper_reverify_confidence_sweep.py`（分析用に同じマッチングロジックを
複製していたスクリプト）にも同じフォールバックを追加し、production側の
挙動と乖離しないようにした。

実験記録: `experiments/20260908_whisper_reverify_confidence_sweep.json`。

---

### 2026/09/07 18:00

#### 変更内容

report.txtで優先度が高いとされた3項目（①gemini-3.5-flash-liteの追加ベンチマーク、
②Whisper再検証・不自然度チェックの誤判定を減らすガード追加、③チャンク長スイープ用
ベンチマークの拡充）を実装し、実際にAPIキーで実行して検証した
（前回2026-09-06時点では`.env`が未設定で実行できなかったが、今回は設定済みだった）。

**① gemini-3.5-flash-liteの追加ベンチマーク**

2026-08-27の予備調査（2ベンチマーク・辞書なし・各1回のみ）を拡張し、
`evaluation/model_comparison.py`を全10ベンチマーク・各2回実行・本番同様に
`dictionary_path`配線ありに変更（明確に劣っていた`gemini-3.6-flash`・
`gemini-3.1-pro-preview`は対象から外し、有力候補に絞って予算を割いた）。

- **速度**: gemini-3.5-flash-liteが10/10ベンチマークで一貫して高速
  （0.89〜1.23s/seg vs gemini-2.5-flashの1.27〜2.50s/seg）。前回の結論を再確認。
- **chrF**: 辞書を配線すると10/10ベンチマークでgemini-2.5-flashが逆転して優位に
  （前回は辞書なしで2/2ともflash-liteが優位だった）。切り分け実験の結果、原因は
  document-level chrF化ではなく**辞書の有無そのもの**: 辞書を渡すとgemini-2.5-flashは
  chrFが上がる一方、flash-liteは下がる（例: economics dict無=0.6131→dict有=0.4751）。
  ただし出力を目視確認すると、flash-liteの訳は意味的には妥当で正解訳と言い回しが
  違うだけに見え、LLM-as-judgeスコアは辞書ありでも両モデルとも0.93〜1.0で同水準
  だった。reference_jaが人手レビュー未了（draft）のため、この時点で
  「flash-liteは辞書と相性が悪い」と断定するのは尚早と判断した。
- **結論**: 速度面ではgemini-3.5-flash-liteは依然有力だが、辞書運用時のchrF低下は
  本採用前に人手レビュー済みreferenceでの再確認が必要。

実験記録: `experiments/20260907_model_comparison.json`、`experiments/results.csv`
（`[model_comparison]`タグ）。

**② Whisper再検証・不自然度チェックの誤判定を減らすガード追加**

*Whisper再検証（`whisper_reverify.py`）*: 2026-08-26に見つかったMOA/MOEの誤補正
（false positive）を防ぐため、2つのガードを追加した。(1) 原文側が既に別の登録済み
用語（例: MOA）の場合は補正しない、(2) Whisperの単語レベル信頼度
（`whisper_client.transcribe_pcm_with_whisper`が返す`probability`、既定閾値0.6）が
低い候補は採用しない。`clip2〜5`で再検証した結果、**clip5のMOA→MOE誤補正は0件に
解消**したが、clip3の正しい補正2件（T5×1、GPT-3×1）も一緒に発火しなくなり、
適合率(precision)と再現率(recall)のトレードオフとして残った
（`min_confidence`のチューニングが次の課題）。単体テスト4件追加
（`tests/test_whisper_reverify.py`）。

*不自然度チェック（`naturalness_detector.py`）*: スコアだけでなく理由ラベル
（`"complete"`/`"dangling_clause"`/`"unresolved_reference"`/
`"unfinished_list_or_comparison"`/`"trailing_conjunction"`/`"other"`）もLLMに
返させ、`reason=="complete"`（モデル自身が「実は完結している」と判断）の場合は
スコアが閾値以上でも強制継続させないガードを追加した。2026-08-25と同一データで
再検証したところ、結合結果・発火数（14/26）は前回と完全に一致し、reasonの内訳に
`"complete"`は1件もなかった——つまり今回のデータでは、既知の誤検知ケース
（句点で終わった完結文がdangling_clauseと判定されて発火）をこのガードは
防げなかった。回帰は無いが、天井効果・過剰発火の根本解決には至っておらず、
reference-basedな評価による閾値・プロンプトの見直しが引き続き必要
（report.txtの元の結論通り）。

実験記録: `experiments/20260907_gemini_25_flash_whisper_reverify_ab_test.json`、
`experiments/20260907_gemini_25_flash_unnaturalness_check_ab_test_2d07bb74_v2_clip1_reason_gate.json`、
`experiments/results.csv`。

**③ チャンク長スイープ用ベンチマークの拡充**

既存の断片化ベンチマーク4件（生発話2〜4件、非単調な揺れが大きく最適値を特定
できなかった）に対し、`experiments/segments/20260824_2d07bb74_v2_clip1_raw_unmerged.json`
（未結合の生発話26件、既存より大幅に長い）から新規ベンチマーク
`evaluation/benchmarks/technology_fragment_2d07bb74_v2_clip1_scaling_intro.json`を
作成（reference_jaはclaude-opus-5が英文から独立に作成、draft_needs_human_review）。

`chunk_length_sweep.py`で6段階スイープした結果、比較的単調な右肩上がりの傾向:
1.0s(seg25)=0.5511 → 2.0s(seg20)=0.5665 → 3.0s(seg18)=0.5447(小さな谷) →
4.0s(seg15)=0.6348 → 8.0s(seg13,マイク既定)=0.6147 → 20.0s(seg11,動画既定)=0.6607
（最良）。3.0sの小さな谷を除けば「長く結合するほど自然になる」という元の仮説と
整合的で、データを長く・多くするほどchrFのノイズが減り傾向が見えやすくなることを
示唆する。依然として一意の「最適値」の断定には至らないが、断片化ベンチマークを
拡充する方向性自体がノイズ低減に有効という手応えが得られた。

実験記録: `experiments/20260907_gemini_25_flash_chunk_length_sweep_technology_fragment_2d07bb74_v2_clip1_scaling_intro.json`、
`experiments/results.csv`。

#### 未検証

- 不自然度チェックのreasonガードは、モデル自身が完結文を「まだ続く」と誤判定する
  ケースには無力なため、reference-basedな評価（正解の結合境界セットに対する
  precision/recall）でプロンプト・閾値そのものの見直しが必要。
- gemini-3.5-flash-liteの辞書配線時chrF低下は、人手レビュー済みreferenceでの
  再確認が必要（現状のdraft referenceでは言い回しの違いと実質的な劣化を
  区別できない）。

---

### 2026/09/07 19:10

#### 変更内容

**Whisper再検証`min_confidence`のチューニング**（上記「未検証」に挙げていた項目の対応）

新規スクリプト`evaluation/whisper_reverify_confidence_sweep.py`を追加。
`technology_moe_2d07bb74_clip{1..5}`の全結合セグメントに対してfaster-whisperの
再文字起こしを1回だけ実行し（faster-whisperはCPU推論のスレッド間非決定性で
同一音声でもconfidenceが実行ごとに微妙にブレるため、閾値ごとに再実行すると
このブレと閾値の効果を混同してしまう）、同じ文字起こし結果に対して
`min_confidence`候補（0.0〜0.8）だけを変えて発火状況を比較した（Gemini API
呼び出し無し、ローカル推論のみで完結）。

- 既知の誤補正MOA→MOE（confidence 0.616）は、確認した全ての閾値候補で
  発火しなかった。ガード1（原文が既に別の登録済み用語なら補正しない）が
  信頼度と無関係に常時ブロックしているためで、**min_confidenceを下げても
  この誤補正が再発するリスクは無い**ことを確認できた。
- 正しい補正TIFINE→T5のconfidenceは0.5997と、既定値0.6のすぐ下だった。
  この1件に関しては0.6は実質コイントスに近い閾値だったことになる。
- 上記2点から、既定値を0.6→**0.5**に変更（`whisper_reverify.py`の
  `DEFAULT_MIN_CONFIDENCE`、`config.py`の`whisper_reverify_min_confidence`、
  `WHISPER_REVERIFY_MIN_CONFIDENCE`環境変数の既定値）。
  `evaluation/whisper_reverify_ab_test.py`を全5クリップで再実行して確認した
  結果、TIFINE→T5の補正が想定通り復活した（clip3の発火数が1→2件に）。

**未解決のまま残った別件**: 正しい補正の3件目「G p t three」→GPT-3は、
min_confidenceの値によらず今回も一度も発火しなかった。原因を調べたところ
`min_confidence`とは無関係の別バグで、faster-whisperが`"GPT-3,"`を
`"GPT"`と`"-3,"`という2つの単語トークンに分割して返すことがあり、
現行のマッチング処理は候補スパンを空白区切りで結合する
（`" ".join(whisper_norm[j1:j2])`）ため`"gpt -3"`となってしまい、辞書の
`"gpt-3"`と一致しない。信頼度チェック以前にトークン化の時点で候補として
成立しないため、閾値をどう調整しても回収できない。ハイフン区切り複合語の
再結合ロジックが必要（次の課題として残す）。

実験記録: `experiments/20260907_whisper_reverify_confidence_sweep.json`、
`experiments/20260907_gemini_25_flash_whisper_reverify_ab_test.json`（上書き、
min_confidence=0.5版）、`experiments/results.csv`。

#### 未検証

- 「G p t three」→GPT-3のハイフン分割トークン化問題（上記）は2026/09/08に修正
  （下記「2026/09/08 (続き)」参照）。
- 不自然度チェック・gemini-3.5-flash-lite辞書配線chrFの2件は上と同じ
  （未解決のまま）。

---

### 2026/09/08

#### 変更内容

**Deepgramキーワードブーストを動画字幕パス（`add_subtitles.py`）にも配線**

`deepgram_keyword_boost_enabled`（辞書の「そのまま使う」用語をDeepgramへ渡して
ASR誤認識自体を減らす根本対策）は`pipeline.py`（マイクのリアルタイム翻訳）には
配線済みだったが、`add_subtitles.py`の`transcribe_audio()`（`client.listen.v1.media.
transcribe_file()`を直接呼ぶ動画字幕パス）には配線されていなかった
（実装漏れ）。`TermDictionary.as_asr_keywords()`を使って`keywords`パラメータを
渡すよう追加し、`DEEPGRAM_KEYWORD_BOOST_ENABLED`/`DEEPGRAM_KEYWORD_BOOST_VALUE`
環境変数（`config.py`と共通の名前）で制御できるようにした。

`clips/2d07bb74_clip3.mp4`の冒頭10秒（`technology_moe_2d07bb74_clip3`ベンチマークの
既知の誤認識区間）で実際にDeepgram APIを呼んで確認したところ、これまで
"G p t three and the parm two architectures" と誤認識されていた箇所が
"GPT three and the PaLM two architectures" に改善した（PaLMは完全一致、GPTは
"GPT-3"ではなく"GPT three"ではあるが、辞書によるASR誤認識補正パターン
`g p three,GPT-3`との組み合わせで翻訳段階ではこれまで通り拾える）。

なお、Whisper再検証（`whisper_reverify_enabled`）・不自然度チェック
（`unnaturalness_check_enabled`）は`pipeline.py`専用として設計されており
（`whisper_reverify_ab_test.py`のdocstring参照）、動画字幕パスには意図的に
未配線のまま——今回の対象はキーワードブーストのみ。

**Gradio動画字幕タブ（本番エントリーポイント、`gradio_demo.py`）にも同じ抜けを発見・修正**

`gradio_demo.py`の`_video_transcribe()`（`process_video`が呼ぶ、Gradio UIの
「動画に字幕を付ける」タブ用の文字起こし関数）も`add_subtitles.py`と全く同じ
`transcribe_file()`直呼びのコードで、キーワードブーストが未配線だった。
`add_subtitles.py`は実験用CLIだが、こちらは`launch.bat`で起動する実際の
本番UIパスのため、影響範囲はこちらの方が大きい。`VIDEO_DICTIONARY_PATH`と
同じ命名規則で`VIDEO_DEEPGRAM_KEYWORD_BOOST_ENABLED`/`_VALUE`を追加し、
`_video_load_deepgram_keywords()`を新設して配線した。同じ
`clips/2d07bb74_clip3.mp4`の10秒区間で実際にDeepgram APIを呼んで確認し、
`add_subtitles.py`と同じ改善（"parm two"→"PaLM two"）を確認した。

---

### 2026/09/06 21:20

#### 変更内容

**講義動画（2d07bb74）の全編通し文字起こしから専門用語一覧を作成し、`dictionary.csv`に反映**

これまでのASR誤認識調査（2026-08-11）は`evaluation/benchmarks/technology_moe_2d07bb74_clip2〜5`
（抜粋4クリップ、計38セグメント）に限定されていた。`experiments/segments/`に
残っていた同講義の全編通し文字起こし（105セグメント、`20260728_...json`）を
読み直し、未発見だった専門用語・誤認識パターンを洗い出した
（詳細: `evaluation/glossary_2d07bb74_full_lecture.md`）。

- **新規ASR誤認識パターン3件を追加**: `TIFI`→T5（既存`TIFINE`の別変種）、
  `GPG3`→GPT-3（既存`g p g three`の別表記）、`PARAM two`→PaLM 2（既存
  `PARM two`のA1文字違い）。
- **未登録だった専門用語27件を追加**: BERT, GLUE, GLaM, masked language
  modeling, text-to-text, encoder-decoder, decoder-only, in-context learning,
  prefix LM, continual learning, catastrophic forgetting, domain adaptation,
  LWF, memory replay, mixture of adapters, MMLU など。特に**GLaM**は登録前は
  ただの英単語"glam"（華やかな）と誤訳されるリスクがあった。
- 確度の低い推測（例: `Annotify`→"And T5"、`g sharp top two`→"GShard top-2"）は
  過去のMOA/MOE誤補正の教訓（2026-08-26参照）を踏まえ、誤登録リスクを避けて
  辞書には追加せず「要確認」として`evaluation/glossary_2d07bb74_full_lecture.md`
  に記録するに留めた。

**不自然度チェック（`naturalness_detector.py`）にバイリンガル文脈を追加**

2026-08-25のAB testで「LLM自己採点のスコアが0.80〜0.90に偏り判別力が乏しい」
という課題が見つかっていた。これまで判定プロンプトの`<context>`には英語原文
しか渡していなかった（`pipeline.py`側で`SharedTranslationContext`の訳文側
`_tgt_ctx`を取得しつつ未使用のまま捨てていた）のを、既に確定済みの日本語訳も
ペアで渡すように変更した。

- `naturalness_detector.py`: `_build_prompt`/`score_unnaturalness`/
  `score_unnaturalness_with_timeout`の`context`引数を`list[str]`から
  `(英語原文, 日本語訳)`のペアのリストに変更。システムプロンプトも、日本語側の
  手がかり（「そして、」で終わる等の宙に浮いた接続表現）を参照するよう明記。
- `pipeline.py`: `_collect_transcriptions`で`src_ctx`・`tgt_ctx`の両方から
  直近`unnaturalness_context_size`件をペアにして渡すよう修正。
- `evaluation/naturalness_check_ab_test.py`: 判定と同じタイミングで逐次翻訳し、
  その訳文を次の判定のコンテキストに使うよう`run_streaming_merge`を書き換え
  （マイクの実経路を忠実に再現するため）。品質評価もこの時に得た訳文をそのまま
  使うようにし、判定時に見せた訳文と評価対象がずれないようにした。

`.venv`のpytest全56件はパス。ただし`.env`にAPIキーが未設定のため、
実際のGemini呼び出しを伴う効果検証（このAB testの再実行、および
`deepgram_keyword_boost_enabled`有効化後のASR精度再比較）はこの環境では
未実施。

#### 未検証

- キーワードブースト（`deepgram_keyword_boost_enabled=True`、既定で有効）が
  実際のDeepgram認識精度をどれだけ改善するか。2026-08-26時点の「faster-whisperが
  既知誤認識9箇所中8箇所で優位」という比較はこの機能が入る前のデータの可能性が
  高く、ブースト適用後の再比較が必要。
- 上記のバイリンガル文脈化で、不自然度スコアの天井効果・粒度の粗さが実際に
  改善するかどうか（実APIキーでの再AB testが必要）。

---

### 2026/08/27

#### 変更内容

**`run_benchmark.py` に `dictionary_path` を配線（辞書の効果が初めてベンチマークスコアに反映）**

2026/08/11時点で「未実施」としていた、用語辞書の効果をベンチマークスコアに反映
させる対応を行った。`evaluation/run_benchmark.py`（および内部で使う
`translate_merged`/`save_result`）に`--dictionary-path`と`--model`を追加し、
`LLMTranslator`へそのまま渡すようにした（`model`は次項のモデル比較用）。

`technology_moe_2d07bb74_clip3`ベンチマーク（T5→TFI等の既知の誤認識を含む）で
辞書あり/なしを比較したところ、**chrF 0.4753 → 0.5765、LLM-as-judge 0.9909 → 1.0**
と、辞書の効果が初めて数値で確認できた（これまでは`dictionary_path`が未配線
だったため、ベンチマークスコアには一切反映されていなかった）。

**「どのモデルがリアルタイム翻訳に向いているか」の比較調査を実施**

`experiments/results.csv`を確認したところ、これまでの実験は全て`gemini-2.5-flash`
固定で行われており、他モデルとの比較が一度もなかった。新規スクリプト
`evaluation/model_comparison.py`で、`economics_federal_funds_rate`・
`technology_moe_2d07bb74_clip3`の2ベンチマークに対し、モデルごとの翻訳速度
（1セグメントあたりの平均秒数）とchrF/LLM-as-judgeスコアを計測した。

- **候補モデルの選定過程で分かったこと**: 当初候補にしていた
  `gemini-2.5-flash-lite`・`gemini-2.0-flash`は、2026-08-27時点で実際にAPIを
  叩いたところ両方とも`404 NOT_FOUND`（提供終了）だった。エラーメッセージが
  案内する後継モデル`gemini-3.5-flash-lite`・`gemini-3.6-flash`と、
  `gemini-3.1-pro-preview`を代わりに使用した。
- **重要な制約**: `gemini-3.x`世代は`thinking_budget=0`（Thinking無効化）を
  受け付けない（`400 INVALID_ARGUMENT: "This model only works in thinking
  mode."`、`gemini-3.1-pro-preview`で実機確認）。マイクのリアルタイム翻訳
  （`pipeline.py`）は低遅延優先で`thinking_budget=0`が既定のため、この制約は
  今後の3.x系モデル採用検討における無視できない足かせになる。今回は
  `gemini-2.5-flash`のみ`thinking_budget=0`、他モデルは受理される最小値
  （128）で代用して比較した（完全に公平な比較ではない点に注意）。
- **結果**（詳細は`experiments/20260827_model_comparison.json`）:

  | モデル | thinking_budget | 平均秒/セグメント（economics/technology） | chrF（同） | judge（同） |
  |---|---|---|---|---|
  | gemini-2.5-flash（現行本番） | 0 | 3.37s / 1.15s | 0.4313 / 0.4845 | 0.98 / 1.0 |
  | gemini-3.5-flash-lite | 128 | **1.01s / 0.87s** | **0.6131 / 0.5496** | 1.0 / 0.9955 |
  | gemini-3.6-flash | 128 | 1.51s / 1.39s | 0.5131 / 0.5335 | 0.99 / 0.9927 |
  | gemini-3.1-pro-preview | 128 | 9.40s / 6.44s | 0.2466 / 0.4438 | 1.0 / 0.9909 |

  `gemini-3.5-flash-lite`が両ベンチマークで最速かつ最高chrFだった（Thinking
  強制の不利を負っているにもかかわらず現行の`gemini-2.5-flash`より高速）。
  一方`gemini-3.1-pro-preview`は「Pro」の名に反して両ベンチマークで最も低い
  chrFだった（例: "Federal Reserve"を訳さず英語のまま残す等、固有名詞を
  過度に温存する傾向がありそうだと目視でも確認した）。LLM-as-judgeスコアは
  全モデルで0.98〜1.0に張り付いており、天井効果でモデル間の差を判別できて
  いない点は2026-08-25の不自然度チェック検証と同じ注意が必要。

**結論**: `gemini-3.5-flash-lite`は速度・chrFともに現行の`gemini-2.5-flash`を
上回っており、次に検証すべき最有力候補。ただし2ベンチマーク・各1回の実行のみの
予備調査であり、`thinking_budget`非対称という比較条件の制約もあるため、本番採用を
判断する前に追加のベンチマーク・複数回実行によるばらつきの確認が必要。

実験記録: `experiments/20260827_model_comparison.json`、
`experiments/results.csv`（`[model_comparison]`タグ）。

---

### 2026/08/26

#### 変更内容

**`WHISPER_REVERIFY_ENABLED` のbefore/after検証を実施（有効化は非推奨と判断）**

2026/08/20時点で「未検証」としていた、`WHISPER_REVERIFY_ENABLED=true`にする前に
before/after比較を行うという`config.py`記載のルールに従い、`evaluation/whisper_reverify_ab_test.py`（新規）で検証した。

`run_benchmark.py`はテキストのみのベンチマークを扱うため、音声区間の再文字起こしを
必要とする`whisper_reverify`をそのまま配線できない（`naturalness_check_ab_test.py`と
同じ制約）。そのため、既知のASR誤認識（T5→TFI/TIFINE等）を含む実データである
`evaluation/benchmarks/technology_moe_2d07bb74_clip2〜5`（計38セグメント）について、
対応する音声（`clips/2d07bb74_clipN.mp4`）から`pipeline.py`と同じ処理順序（utterance
結合 → 結合後セグメント区間をffmpegで切り出し → 既知用語の差分のみ補正）をオフラインで
再現した。

- **結果**: 4箇所で補正が発生（clip3で`T5`×2・`GPT-3,`×1、clip5で`MOA→MOE`が1件）。
  clip3では`parm two`/`PARM two`/`g p three`/`g p g three`/`Parm`の5箇所は未補正の
  まま残った（faster-whisper自身もこれらを正しい表記では書き起こせなかったため、
  差分が辞書の用語と一致しなかった）。
- **誤補正（false positive）を1件確認**: clip5の`MOA→MOE`は、Deepgramの認識
  （`MOA`）が正しく、Whisper側が`MOE`と聞き間違えたケースだった。`MOA`
  （Mixture of Adapters）と`MOE`（Mixture of Experts）は講義内で意味の異なる別概念
  であり、`keep_as_is_terms`との完全一致だけで「どちらのASRが正しいか」を判定しない
  現行ロジックでは、正しい認識の方を誤って書き換えてしまうリスクがあることが実測で
  判明した。
- **doc_chrf（document-level、`chunk_length_sweep.py`と同じ手法）**:
  clip2 -0.0163、clip3 -0.0003、clip4 +0.0375、clip5 -0.0211。補正が0件だった
  clip2/clip4でも同程度に変動しており、`thinking_budget=0`での翻訳の非決定性ノイズ
  と同程度の振れ幅のため、この規模のスコア差だけでは補正の効果・悪影響を主張できない。

**結論**: 実際に効くケースはあるが的中率が低く（既知エラー8箇所中3箇所）、かつ
音響的に紛らわしいacronym同士（`MOA`/`MOE`等）では誤って正しい認識を書き換える
リスクが確認された。現状の実装（`keep_as_is_terms`との完全一致のみで採否を決め、
Whisper側の確信度やDeepgramとの一致度を考慮しない）のままでは
`WHISPER_REVERIFY_ENABLED=true`への変更は推奨しない。改善案として、
①音響的に紛らわしい語同士をkeep_as_is_termsから除外する、②Whisperの確信度
スコアを考慮する、③Deepgram/Whisper双方が一致した場合のみ採用する、といった
追加ガードが今後の課題として残る。

実験記録: `experiments/20260826_gemini_25_flash_whisper_reverify_ab_test.json`、
`experiments/results.csv`（`[whisper_reverify_ab_test]`タグ）。

---

### 2026/08/20

#### 変更内容

**マイクのリアルタイム翻訳に「Whisper再検証」を実装（ハイブリッドASR構成、既定OFF）**

2026/08/11 の調査で、Deepgramが専門用語・モデル名（T5→「TIFINE」、PaLM→「Parm」等）を
誤認識する一方、faster-whisperは同じ音声を正しく認識できるケースが多いことが分かって
いた。この時点ではfaster-whisperはストリーミングAPIを持たないためマイクのリアルタイム
翻訳には未対応で、動画字幕生成（オフライン一括処理）のみを対象に代替ASRとしての導入を
開始していた。

今回、マイクの低遅延表示はDeepgramのまま維持しつつ、**確定した文（`is_final`）だけを
裏でfaster-whisperに再文字起こしさせ、辞書の「そのまま使う」用語
（`dictionary.csv`のsource=targetエントリ、例: T5/PaLM/MOE/AWS）に一致する差分だけを
Whisper側の表記へ差し替える**ハイブリッド構成を実装した。全文をWhisperの結果で
置き換えるとWhisper自身の幻覚リスクを引き継ぐため、既知用語に一致した箇所だけを
狙い撃ちで補正する設計にしている。

- `transcription/whisper_reverify.py`（新規）: `apply_term_corrections()`が
  Deepgram確定文とWhisper再文字起こし結果を単語単位で比較（`difflib`）し、
  辞書用語に一致する差分だけを補正する純粋関数。`reverify_terms()`が実際の
  Whisper呼び出しと繋ぐ。
- `transcription/whisper_client.py`: 生PCM音声を直接渡せる
  `transcribe_pcm_with_whisper()`を追加（既存はファイル経由のみだった）。
- `translation/dictionary.py`: `keep_as_is_terms()`を追加。Deepgramの
  キーワードブースト（`as_asr_keywords()`）とWhisper再検証で同じ用語リストを共有。
- `pipeline.py`: マイク音声チャンクを送信バイト数ベースの経過秒数でバッファする
  `_AudioRingBuffer`を追加し、Deepgramの`is_final`確定文と同じ音声区間を
  切り出せるようにした。確定文を翻訳キューに積む直前にWhisper再検証を呼び、
  `asyncio.wait_for`でタイムアウト保護する（`incomplete_end_detector`/
  `naturalness_detector`と同じ安全弁設計。タイムアウト・エラー時は元の
  Deepgram結果へフォールバックし、リアルタイム性を壊さない）。

**設定項目を追加**（`config.py` / `.env`）

| 環境変数 | デフォルト | 説明 |
|---|---|---|
| `WHISPER_REVERIFY_ENABLED` | `false` | Whisper再検証のON/OFF |
| `WHISPER_REVERIFY_TIMEOUT` | `1.5`（秒） | 再検証のタイムアウト。超えたら元のDeepgram結果を使う |
| `WHISPER_REVERIFY_MODEL_SIZE` | `small.en` | 再検証に使うfaster-whisperのモデルサイズ |

**テスト追加**

`tests/test_whisper_reverify.py`（用語補正ロジック）、`tests/test_dictionary.py`
（`keep_as_is_terms`）、`tests/test_audio_ring_buffer.py`（音声バッファの切り出し）を
追加（全56件パス確認済み）。実装中に`_AudioRingBuffer.slice()`で浮動小数点誤差
（例: `0.6 - 0.4 == 0.19999999999999998`）によりチャンク境界が1サンプル欠落する
バグを発見し、`int()`切り捨てから`round()`に変更して修正した。

#### 未検証

- CPU推論（`small.en`）のため、確定ごとに数百ms〜数秒の追加レイテンシが乗る見込みだが
  実測はまだ。GPUなし環境でのリアルタイム性への影響は未計測。
- ~~`CLAUDE.md`の実験記録ルールに従い、`WHISPER_REVERIFY_ENABLED=true`にする前に
  `evaluation/run_benchmark.py`でbefore/after比較を行う予定（未実施のため既定OFF）。~~
  → 2026/08/26に実施済み。誤補正（false positive）が確認されたため既定OFFを維持
  （詳細は「2026/08/26」を参照）。
- 動画字幕生成・Gradio動画タブ（オフライン一括処理経路）には未適用。今回はマイクの
  リアルタイム翻訳のみが対象。

---

### 2026/08/11

#### 変更内容

**専門用語の失敗調査、および用語辞書カバレッジ検査のバグ修正**

「専門用語に弱い」という課題について、`evaluation/benchmarks/technology_moe_2d07bb74_clip2〜5.json`
（LLM第8回講義動画の実データ）を使い、失敗した専門用語10件について
「音声認識(Deepgram)の誤りか、翻訳(Gemini)の誤りか」を切り分けた。

- **ASR（Deepgram）側の誤り**: T5→「TIFINE」「TFI」、PaLM→「Parm」、
  PaLM 2→「PARM two」、GPT-3→「g p three」/「g p g three」（スペルアウト）、
  memory wall→「memory war」（1文字違いで意味が変わる）。いずれも音声認識の
  誤変換で、翻訳(`LLMTranslator`)はそれをそのまま受け取っているだけだった。
  ただし後述の通り、Geminiが文脈（例: 「5000億パラメータ」）から自力で
  「Parm」→「PaLM」のように復元できるケースもあった。
- **辞書カバレッジ不足**: `MOE`（Mixture of Experts、この講義の中心用語）
  および`MOA`（Mixture of Adapters）、`FLOPS`が`dictionary.csv`に
  未登録だった（ASR自体は正しく認識できていた）。
- **用語チェックツール自体の誤検知（バグ）**: `results.csv`に頻出していた
  「用語漏れ: WER→WER, PR→PR, BI→BI, ORM→ORM, SLA→SLA, RAG→RAG」は、
  実際の翻訳漏れではなく`terminology_check.py`のバグだった。単純な部分
  文字列一致で判定していたため、"PR"が"process"に、"BI"が"bidirectional"に、
  "ORM"が"normalization"に、のように無関係な単語に偶然含まれて誤検知していた。

**「完璧な資料（辞書）があればどこまで対応できるか」の実測テスト**

`LLMTranslator`に実際に`gemini-2.5-flash`（thinking_budget=1024、本番と同一設定）で
辞書あり/なしを比較した。「TIFINE→T5」「TFI→T5」のように観測済みの誤認識
文字列を辞書に事前登録しておくと、辞書なしでは直らなかった「TFI」「TIFINE」が
辞書ありでは確実に「T5」に修正されることを確認した。ただしこれはモグラ叩き的な
対策であり、①既に観測したパターンにしか効かない（次に別の形で誤認識されたら
再発する）、②ASRの誤り自体（英語側のログ等）は直らない、という限界がある。
なお、現行の`evaluation/run_benchmark.py`は`dictionary_path`を渡していないため、
これまでのベンチマークスコアは辞書の効果を反映していなかった点も判明した
（次回、`run_benchmark.py`に`dictionary_path`を配線する予定）。

**今回実施した修正**

1. **`terminology_check.py`のバグ修正**（`_contains_term()`を追加）。
   ASCII英数字の用語（頭字語・モデル名）は、前後がASCII英数字でないことを
   条件に一致判定するようにした。Pythonの正規表現`\b`はUnicode対応で
   日本語の文字も「単語文字」とみなすため使えず（「のPRを」のように
   分かち書きされない日本語字幕では境界と判定されず見逃しが起きる）、
   独自のlookaround（`(?<![A-Za-z0-9])...(?![A-Za-z0-9])`）で実装した。
   日本語の訳語（例: 「フェデラルファンドレート」）は対象外とし、従来通り
   部分文字列一致のまま。`tests/test_terminology_check.py`に回帰テストを
   3件追加（全43件パス確認済み）。
2. **`dictionary.csv`に実証済みの補正エントリを追加**。
   - モデル名: `GPT-3`, `T5`, `PaLM`, `PaLM 2`
   - 講義の中心語彙: `mixture of experts`/`MOE`, `MOA`, `FLOPS`, `memory wall`
   - ASR誤認識の既知パターン補正: `TIFINE→T5`, `TFI→T5`, `Parm→PaLM`,
     `PARM two→PaLM 2`, `g p three→GPT-3`, `g p g three→GPT-3`,
     `memory war→メモリウォール`（新しい動画で別の誤変換パターンが
     見つかったら随時追記する運用とする）

#### 未検証

- `evaluation/run_benchmark.py`への`dictionary_path`配線（辞書の効果を
  ベンチマークスコアに反映させる対応）はまだ未実施。
- Deepgram側のキーワードブースト機能（ASRの誤認識自体を減らす根本対策）は
  未調査・未実装。現状は翻訳段階での事後補正のみ。

---

**複数音声認識サービスの比較、およびfaster-whisper導入（作業途中）**

上記の専門用語調査を受け、「Deepgram以外のASRなら誤認識を防げるか」「複数ASRの
結果をLLMに突き合わせさせて正しい方を選ばせられるか」を検証した。

- **ASR比較（Deepgram vs. faster-whisper small.en）**: 同じ音声
  （`clips/2d07bb74_clip2.mp4`, `clip3.mp4`）をfaster-whisper（ローカル実行、
  APIキー不要）で文字起こしし、Deepgramが誤認識した9箇所と比較した。
  T5/PaLM/PaLM 2/GPT-3/memory wallの誤認識8/9箇所でfaster-whisperの方が
  正確だった。唯一"BERT and T5"の"T5"（Deepgramでは"TFI"）だけは
  faster-whisperも同じく誤認識しており、この箇所は音響的に聞き取りづらい
  可能性がある。
- **複数ASR結果をLLMに渡す照合テスト**: Deepgram単独／faster-whisper単独／
  両方を提示して照合、の3条件でGeminiに翻訳させ比較した。3条件とも8/8で
  正しい用語に訳せたが、これは「複数ASRを渡したこと」自体の効果ではなく、
  検証に使ったプロンプトが「誤認識と判断したら一般知識で補正してよい」と
  明示的に許可していたためと判明した（本番の`LLMTranslator`のプロンプトは
  逆に「固有名詞は原文のまま保持し、曖昧なら推測しない」という保守的な
  指示のため、同じ強さの自己修正は起きない）。この方式はGemini自身が
  訓練データで知っている有名なモデル名だから機能しており、話者固有の
  人名・社内製品名のような未知の固有名詞に対しては、複数ASRを見せても
  補正できない、あるいは誤ったもっともらしい単語を生成するリスクがある
  点に注意が必要（詳細は上記チャットのやり取り、または
  `evaluation/`配下に今後追加予定のベンチマークを参照）。

上記の検証結果を受け、動画字幕生成・Gradio動画タブ（オフライン一括処理の経路のみ。
マイクのリアルタイム翻訳はfaster-whisperがストリーミングAPIを持たないため対象外）に
faster-whisperを代替ASRとして選択できるよう実装を開始した。

- `faster-whisper>=1.2.1`を依存関係に追加（`uv add faster-whisper`で
  `pyproject.toml`/`uv.lock`/`requirements.txt`に反映済み）。
- `src/real_time_translation/transcription/whisper_client.py`を新規作成。
  `transcribe_with_whisper()`がDeepgramの`transcribe_audio()`と同じ
  `{"start", "end", "transcript"}`形式のリストを返すため、呼び出し側は
  ASRプロバイダを差し替えるだけで動く設計。
- `add_subtitles.py`に`TRANSCRIPTION_PROVIDER`（`deepgram`/`whisper`）・
  `WHISPER_MODEL_SIZE`環境変数を追加。

**未完了（次回に持ち越し）**

- `add_subtitles.py`の`main()`から実際に`TRANSCRIPTION_PROVIDER`で
  Deepgram/whisperを切り替える配線（`transcribe_audio_with_provider()`相当の
  ディスパッチ関数）はまだ未反映。
- `gradio_demo.py`の動画タブ（`_video_transcribe`/`process_video`）への
  同様の配線は未着手。
- `.env.example`・READMEの環境変数一覧表への`TRANSCRIPTION_PROVIDER`/
  `WHISPER_MODEL_SIZE`の記載、および`whisper_client.py`の単体テストも未着手。

### 2026/07/23

#### 変更内容

**翻訳品質チェック4点を追加し、マイクのリアルタイム翻訳・動画字幕生成の両方に適用**

これまで自動評価（xCOMET/chrF）はあったが、「今まさに訳し漏れが起きていないか」
「用語辞書が実際に守られているか」「LLM呼び出しが無料枠の上限に近づいていない
か」をその場で検知する仕組みがなかった。今回、以下の4つを追加した
（マイクのリアルタイム翻訳 `pipeline.py` と動画字幕生成の両方に適用）。

1. **翻訳完全性チェック（要確認フラグ）** — `translation/completeness_check.py`。
   原文の文字数に対する訳文の文字数比を直近セグメントの中央値と比較し、
   極端に低い（＝訳が短すぎる＝訳し漏れの疑いがある）セグメントに
   `⚠️ 要確認` フラグを立てる。API呼び出し不要の統計的ヒューリスティック。
2. **LLM使用量トラッキング／レート制限警告** — `translation/usage_tracking.py`。
   呼び出しごとのトークン数を記録し、モデル別に集計。Gemini無料枠の目安
   （既定15回/分、`GEMINI_FREE_TIER_RPM`）に近づくとUIに警告を表示する。
   「翻訳が途中で止まった」（下記FAQ）に事前に気づけるようにする狙い。
3. **utterance分断検出のLLM分類器化** — `transcription/incomplete_end_detector.py`。
   これまで「文末が `. ! ? ` で終わっているか」という正規表現だけで
   utterance結合の要否を判定していたが、句読点が付かない/正規表現でカバーし
   きれないケースを取りこぼしていた。軽量LLMによるバッチ判定を追加し、
   判定に失敗した場合は正規表現へ自動フォールバックする。マイク（ストリーミング）
   側は `INCOMPLETE_END_DETECTION_TIMEOUT`（既定0.6秒）でタイムアウトし、
   リアルタイム性を壊さないようにしている。
4. **用語辞書カバレッジ検査** — `translation/terminology_check.py`。
   `LLMTranslator` は用語辞書をプロンプトに埋め込むだけで、実際に使われたかは
   検証していなかった。「原文にその用語が出たのに訳文に期待訳語が出ていない」
   ケース（用語漏れ）を検出するようにした。

**実装の過程で見つかった既存の不整合を合わせて修正**

- **動画字幕タブ（`gradio_demo.py::process_video`、= `app.py`/`launch.bat` が
  使う本番エントリーポイント）に utterance 結合が一切適用されていなかった。**
  `add_subtitles.py`（実験用CLIスクリプト）だけが結合していたため、
  CLAUDE.md が前提とする「マイクと動画/CLIは同じアルゴリズムを共有」は
  実際のGradio動画タブには当てはまっていなかった。今回、動画タブにも
  同じutterance結合処理を追加した。
- **動画字幕パス（`add_subtitles.py` / `gradio_demo.py` の動画タブ）は
  `LLMTranslator` に用語辞書（`DICTIONARY_PATH`）を渡していなかった。**
  マイクのリアルタイム翻訳にしか辞書が効いていなかったため、両経路に配線した。

**設定項目を追加**（`config.py` / `.env`）

| 環境変数 | デフォルト | 説明 |
|---|---|---|
| `INCOMPLETE_END_DETECTION_ENABLED` | `true` | utterance分断検出のLLM分類器を使うか（動画/CLI側） |
| `INCOMPLETE_END_DETECTION_ENABLED_REALTIME` | `true` | 同上（マイク側。タイムアウトあり） |
| `INCOMPLETE_END_DETECTION_TIMEOUT` | `0.6`（秒） | マイク側のLLM判定タイムアウト。超えたら正規表現にフォールバック |
| `INCOMPLETE_END_DETECTION_MODEL` | 空（`GEMINI_MODEL`を流用） | 分類専用に別モデルを使いたい場合に指定 |
| `COMPLETENESS_CHECK_ENABLED` | `true` | 翻訳完全性チェックのON/OFF |
| `COMPLETENESS_RATIO_THRESHOLD` | `0.5` | 直近中央値の何倍を下回ったら要確認フラグを立てるか |
| `GEMINI_FREE_TIER_RPM` | `15` | Gemini無料枠のレート制限目安（UI警告表示にのみ使用） |

#### 未検証

- 実APIキーを使ったエンドツーエンドの動作確認（マイク・動画タブとも）は
  未実施。ロジックはユニットテスト（モック）で担保している。
- utterance分断検出のLLM分類器化による翻訳精度への効果（xCOMET/chrFの変化）は
  未計測。次回、`evaluation/run_benchmark.py` で before/after 比較を行う予定。

---

**LLM第8回講義動画（継続学習・MOEがテーマ、`2d07bb74`）からベンチマーク5件を追加し、
reference-based chrFで精度評価**

これまでの `experiments/*.json` は逆翻訳ベースのchrF（英→日→英に戻して原文と比較）
または LLM-as-judge のxCOMETのみで、「人間が作った正解訳とどれだけ一致するか」を
直接測るベンチマークは `evaluation/benchmarks/economics_federal_funds_rate.json`
の1件（1セグメントのみ）しかなかった。

今回、既存の切り出し済みクリップ5本（`clips/2d07bb74_clip1〜5.mp4`、
`experiments/segments/` に文字起こし結果が残っていたためDeepgram再実行なし）を使い、
各クリップの英語原文（合計47セグメント、technology ドメイン）を claude-sonnet-5 が
独立に和訳し、`evaluation/benchmarks/technology_moe_2d07bb74_clip{1-5}.json` として
登録した（`reference_status: draft_needs_human_review`）。この正解訳に対して現行の
`LLMTranslator`（gemini-2.5-flash, thinking_budget=1024）の出力を
`evaluation/run_benchmark.py` で評価した。

| クリップ | セグメント数 | chrF（reference-based） |
|---|---|---|
| clip1 | 9 | 0.588 |
| clip2 | 9 | 0.686 |
| clip3 | 11 | 0.607 |
| clip4 | 9 | 0.565 |
| clip5 | 9 | 0.572 |
| **平均** | 47 | **0.603** |

全セグメントを目視確認したが、意味の取り違えや訳抜けは無く、chrFが1.0にならない
主な要因は言い回しの違い（接続詞の有無・語順・同義語選択）だった。一方で2点、
改善余地を確認した。

- Deepgramが "T5" → "TIFINE"、"PaLM" → "Parm" のように誤認識した箇所を、
  翻訳もそのまま誤認識のまま出力していた（辞書に無い固有名詞のASR誤りは
  補正されない）。`dictionary.csv` に補正用エントリを足すことで改善できる見込み。
- clip3の1セグメントで、1文の訳が3行に不自然に改行されて出力された（原因未調査）。

生の翻訳結果は `experiments/20260723_gemini_25_flash_benchmark_technology_moe_2d07bb74_clip{1-5}.json`
に保存済み。正解訳は人手レビュー未了のため、本格運用前に専門家の確認が必要。

### 2026/07/11

#### 変更内容

**英日併記SRTファイルの出力（`add_subtitles.py`）**

これまで `translated_script/` フォルダに保存されるSRTファイルは日本語訳のみでした。
今回、認識した英語原文と日本語訳を1つの字幕ブロックに2行で並記して出力するように
変更しました（`create_bilingual_srt()`）。

```
1
00:00:00,240 --> 00:00:04,319
Base as it prioritize the new specific domain.
新しいドメインを優先することが弊害となっています。
```

動画への字幕焼き込み（`burn_subtitles`）は従来通り日本語のみです。焼き込み用の
SRTは処理中だけ使う一時ファイルに分離し（永続化せず処理後に削除）、
`translated_script/*_ja.srt` は英日併記版のみが残るようにしました。

---

### 2026/07/08

#### 変更内容

**マイクのリアルタイム翻訳にも文分断対策を実装**

2026/07/02〜07/04 の実験で見つかった「Deepgramのutterance分割が文の途中で
発生し、断片が不自然な訳になる」問題（`merge_incomplete_utterances`）は、
これまで `add_subtitles.py`（動画字幕・CLI経路）にのみ実装されており、
マイクのリアルタイム翻訳パイプライン（`pipeline.py`）には未反映でした。

今回、結合ロジックを `src/real_time_translation/transcription/utterance_merge.py`
に切り出し、以下の2つの実装で共有するようにしました。

- `merge_incomplete_utterances()`：バッチ版（`add_subtitles.py` が使用）
- `StreamingUtteranceMerger`：ストリーミング版（`pipeline.py` が使用）。
  Deepgramの `is_final=True` 結果を1件ずつ受け取り、文末の句読点
  （`. ! ?`）で終わっていなければ内部バッファに保持し、次のfinal結果が
  来るまで翻訳キューに積まない（＝**字幕の確定表示を少し遅らせてから
  結合する**）。文末に達するか、上限（デフォルト: 8秒 or 30語）を超えたら
  結合を確定し、翻訳キューに送る。

これにより「in The United States. It's called the federal」/「funds rate,」
のような分断も、マイク経由のリアルタイム翻訳で同様に解消されます。

**設定項目を追加**（`config.py` / `.env`）

| 環境変数 | デフォルト | 説明 |
|---|---|---|
| `MERGE_UTTERANCES` | `true` | utterance結合のON/OFF |
| `UTTERANCE_MERGE_MAX_DURATION` | `8.0`（秒） | 結合を打ち切るまでの最大長さ |
| `UTTERANCE_MERGE_MAX_WORDS` | `30`（語） | 結合を打ち切るまでの最大語数 |

動画/CLI側（`add_subtitles.py`）はオフライン処理のため従来通り
`max_duration=20.0秒 / max_words=60語` と長めの上限のまま。マイク側は
リアルタイム性を優先し、字幕確定の遅延が大きくなりすぎないよう
短めの上限（8秒 / 30語）をデフォルトにしています。

**パイプライン停止時のバッファ処理**

`TranslationPipeline.stop()` で、結合待ちのまま残っていた未確定の断片は
`flush()` で強制的に翻訳キューへ送るようにし、末尾の発話が失われないように
しました。`clear_context()`（文脈クリア操作）でも結合バッファをリセットします。

**テスト追加**

`tests/test_utterance_merge.py` にバッチ版・ストリーミング版それぞれの
結合ロジック（文末判定・秒数上限・語数上限・flush）のユニットテストを追加。

#### 未検証

- 実際のマイク入力（ライブ音声）でのA/B比較実験はまだ実施していません
  （ユニットテストでロジックの正しさのみ確認済み）。次回、動画と同様に
  xCOMET/chrFで実地検証する予定です。
- リアルタイム性への影響（字幕確定までの体感遅延）も未計測です。

---

**固定ベンチマークデータセットの導入（`evaluation/`）**

`experiments/results.csv` を見直したところ、これまでの比較実験は
毎回違う動画（index.mp4 → short_test.mp4 → short_test_llm.mp4 →
short_test_llm8.mp4 …）・違うセグメント数で行われており、スコアの変化が
「パイプラインの変更によるもの」か「その回だけたまたま訳しやすい動画
だったから」なのかを区別できないという問題がありました。また、
`experiments/*.json` には集計スコアと所感（notes）しか残しておらず、
原文・訳文そのものはどこにも保存されていなかったため、後から
ベンチマークデータを作ろうにも材料がない状態でした。

対策として以下を追加しました。

1. **`add_subtitles.py` に生データ保存機能を追加**：実行のたびに
   `experiments/segments/YYYYMMDD_<動画名>.json` へ、全セグメントの
   原文・訳文・タイムスタンプを自動保存するようにしました。
   今後の実験から、ベンチマーク候補データが自然に蓄積されます。
2. **`evaluation/` フォルダを新設**：固定入力データ（`raw_utterances`）と
   人手レビュー済み正解訳（`reference_ja`）をセットにした
   ベンチマークファイル（`evaluation/benchmarks/*.json`）と、それを
   実行して reference-based chrF を計測する
   `evaluation/run_benchmark.py` を追加しました。
   `--thinking-budget` / `--context-window-size` で設定を変えながら、
   同じデータに対して before/after を比較できます。
3. **seedベンチマークを1件追加**：2026-07-02の実験で見つかった
   「federal funds rate」の文分断の実例（`experiments/20260702_...json`の
   notesから復元）を `evaluation/benchmarks/economics_federal_funds_rate.json`
   として登録しました。正解訳はClaudeが作成した草案のため
   `reference_status: "draft_needs_human_review"` としており、本格運用前に
   人手レビューが必要です。
4. **`CLAUDE.md` に運用ルールを追記**：「アドホック実験」（探索的、動画は
   毎回変えてよい）と「ベンチマーク実験」（回帰テスト、入力データは固定）を
   使い分けるルールを明文化しました。

これにより、今後 utterance結合のパラメータやプロンプトを調整する際は、
`evaluation/run_benchmark.py` で固定データに対する before/after を
直接比較できるようになります（動画を選び直す手間や、目視での
字幕プレビュー確認への依存を減らせます）。

### 2026/07/06

#### 変更内容

**短い英語音声動画での翻訳精度定量測定**

`add_subtitles.py` の自動評価パイプライン（xCOMET・chrF）を使い、東大松尾研の
公開LLM講義動画（`LLM2025応用編_第8回前半`）から、話者が英語で自己紹介している
90秒区間を切り出して（`short_test_llm.mp4`）、`technology` ドメインでの翻訳精度を
測定しました（`experiments/20260706_gemini_25_flash_technology_shortclip_llm2025.json`）。

| 指標 | 結果 |
|------|------|
| xCOMET（LLM判定） | **0.9971** |
| chrF（逆翻訳ベース） | 0.5378 |

Deepgramの文字起こしは27セグメント、utterance結合後は7セグメントとなり、
字幕プレビューを確認したところ「suspension agent」（本来は human-in-the-loop 的な
表現の誤認識と思われる固有名詞）以外は文法・専門用語ともに自然な訳文でした。
なお同じ動画の冒頭5分（司会者による日本語イントロ部分）は `language=en` 強制設定の
影響でDeepgramが空の文字起こし結果を返したため、英語音声区間（10分地点）から
切り出す必要がありました。

**② 別動画（LLM第8回）でも同様に測定**

`add_subtitles.py` の出力先を `translated_script/` フォルダに変更した上で（後述）、
別のLLM講義動画（`LLM第8回`、継続学習・破滅的忘却がテーマ）からも英語音声区間
（10分地点）の90秒クリップを切り出し、同じ `technology` ドメインで測定しました
（`experiments/20260706_gemini_25_flash_technology_shortclip_llm8.json`）。

| 指標 | 結果 |
|------|------|
| xCOMET（LLM判定） | **1.0** |
| chrF（逆翻訳ベース） | **0.7038** |

Deepgramの文字起こしは26セグメント、utterance結合後は8セグメント。「壊滅的忘却」
「継続学習技術」など専門用語の訳も正確で、chrFは前回のクリップ（0.5378）より
大きく改善しました。

**③ SRT出力先を `translated_script/` フォルダに変更**

`add_subtitles.py` が生成するSRTファイルを、動画と同じ場所ではなく専用の
`translated_script/` フォルダにまとめて出力するよう変更しました（動画本体・
焼き込み済み動画は従来通り入力動画と同じ場所に出力）。生成物のため
`.gitignore` に追加済みです。

### 2026/07/02

#### 変更内容

**① `add_subtitles.py`（CLI版の動画字幕生成スクリプト）も統一**

2026/06/30 の統一作業では Gradio アプリ内の動画字幕タブ（`gradio_demo.py`）のみが
`LLMTranslator` に統一されており、実験用の独立 CLI スクリプト `add_subtitles.py` は
旧来の Gemini 直接バッチ翻訳のままでした。今回 `add_subtitles.py` の `translate_segments()`
を書き換え、マイク・動画と同じ `LLMTranslator`（`context_window_size=5`, `thinking_budget=1024`）
を使うよう統一しました。これにより3経路（マイク・動画字幕タブ・CLIスクリプト）すべてが
同じ翻訳エンジンで検証できるようになりました。

**② 統一後 初の翻訳精度実験を実施**

`short_test.mp4`（90秒の経済学講義動画）で統一後の翻訳精度を検証しました
（`experiments/20260702_gemini_25_flash_economics.json`）。

| 指標 | 結果 |
|------|------|
| xCOMET（LLM判定） | 1.0 |
| chrF（逆翻訳ベース） | 0.4337 |

自動評価スコアは良好でしたが、手動で字幕プレビューを確認したところ、Deepgramの
utterance（発話単位）分割が1文の途中で発生するケースを発見しました。

```
[00:00:16,045] in The United States. It's called the federal
  → 米国では。フェデラルと呼ばれています。
```

`LLMTranslator` は各utteranceを独立に（前方向の文脈のみを見て）翻訳するため、
文が複数utteranceに跨ると、後続の文脈が見えず文法的に不自然な訳になることが
分かりました。これは元々ユーザーから指摘のあった「マイクのリアルタイム翻訳が
シンプル過ぎる」という課題を裏付ける具体例です。

### 2026/07/04

#### 変更内容

**utterance結合による文分断対策（`add_subtitles.py`）**

2026/07/02 で見つかった「Deepgramのutterance分割が1文の途中で発生し、断片が
不自然に翻訳される」問題への対策として、`merge_incomplete_utterances()` を
追加しました。文末の句読点（`. ! ?`）で終わっていないutteranceを、上限
（語数・秒数）まで次のutteranceと結合してから `LLMTranslator` に渡します。

`short_test.mp4` で2パターン比較しました。

| 設定 | セグメント数 | xCOMET | chrF |
|------|------|--------|------|
| 結合なし（baseline, 2026-07-02） | 25 | 1.0 | 0.4337 |
| 結合あり（max_words=40, max_duration=12s） | 12 | 0.9783 | **0.5433** |
| 結合あり（max_words=60, max_duration=20s） | 11 | **1.0** | 0.4994 |

以前不自然だった「in The United States. It's called the federal」/「funds rate,」の
分断は両設定で解消され、「これは米国における最短期間の金利です。フェデラル
ファンドレートと呼ばれ、オーバーナイトレートです。」のような自然な訳になりました。
ただし`max_words=40`では結合が打ち切られて新たに文末で終わらないセグメントが
発生する副作用があったため、`max_words=60 / max_duration=20s` を採用し、
`MERGE_UTTERANCES` のデフォルトを `true` に変更しました。

#### 次の試行（進行中）

- 未来方向（次のutterance）を先読みして文脈に含める方式の検証
- 経済学以外のドメイン（`general` など）でも同様の分断対策の効果を確認
- より長い動画・別の話者での再現性確認

### 2026/06/30

#### 変更内容

**① 動画字幕とマイク翻訳のアルゴリズムを統一**

これまで動画字幕とマイクのリアルタイム翻訳は、内部で全く別々の翻訳エンジンを使っていました。
今回の変更で、動画字幕もマイクと同じ `LLMTranslator` エンジンを使うよう統一しました。

**② 翻訳エンジンの品質向上**

| 項目 | 変更前 | 変更後 |
|------|--------|--------|
| 文脈の記憶（コンテキスト窓） | 直前 3 文 | 直前 5 文 |
| ドメイン（専門分野）指示 | なし | あり（6 種類） |
| 動画の翻訳精度設定 | 思考なし | 思考あり（1024 tokens）|
| UI のドメイン選択 | 動画タブのみ | マイク・音声・動画で共通 |

**③ 並列翻訳の文脈一貫性を改善（SharedTranslationContext）**

マイクのリアルタイム翻訳では速度向上のために 3 つのワーカーが並列で翻訳していましたが、
それぞれが独立した文脈を持つため、同じ単語でも訳がばらつく問題がありました。

今回、全ワーカーが共通の文脈（`SharedTranslationContext`）を参照・更新する仕組みを導入しました。
並列処理の速度は維持しつつ、翻訳の一貫性を大幅に改善しています。

#### 期待できる効果

- **動画とマイクを同じ条件で比較・検証できる**（アルゴリズム統一）
- **用語の表記ゆれが減る**（共有コンテキストにより、同じ単語が一貫して訳される）
- **専門分野の翻訳精度が上がる**（ドメイン指示により、素粒子物理・医療・法律などの用語を正確に処理）
- **動画字幕の品質が上がる**（思考モード有効化により、より自然で正確な翻訳）

---

## よくある質問

**Q. 動画をアップロードできない**
アプリを再起動してください（`launch.bat` をダブルクリック）。
それでも解決しない場合、ブラウザのキャッシュをクリアするか、別のブラウザを試してください。

**Q. 「APIキーが未設定です」と表示される**
画面上部の「API Keys」欄に Deepgram と Google AI のキーが入力されているか確認してください。

**Q. 翻訳が途中で止まった**
Gemini の無料枠のレート制限（1分あたりの上限）に達した可能性があります。
エラーが出た場合はしばらく待ってから再試行してください。アプリは自動でリトライします。

**Q. 字幕の日本語が文字化けしている**
Windows の場合は自動で日本語対応フォント（Yu Gothic）が使われます。
正しく表示されない場合はお知らせください。

**Q. 処理をキャンセルしたい**
動画字幕タブの「🎬 字幕を生成する」ボタン付近に処理中の進捗が表示されます。
音声ファイルタブには「Cancel」ボタンがあります。

---

## 翻訳品質について

| スコア | 意味 | 今回の結果 |
|---|---|---|
| xCOMET | AI が採点した翻訳の意味的な正確さ（0〜1、高いほど良い） | **0.9925**（非常に高品質） |
| chrF | 逆翻訳による文字一致率（英日間では 0.37〜0.45 が目安） | **0.3745**（標準的） |

xCOMET の 0.99 は人間の翻訳者に近い水準です。

---

## サポート・お問い合わせ

問題が解決しない場合は、以下の情報を添えてご連絡ください。

- 発生した操作の手順
- エラーメッセージ（あれば）
- `launcher_error.log` ファイルの内容（プロジェクトフォルダ内）
