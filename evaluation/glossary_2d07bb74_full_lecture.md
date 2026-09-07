# 専門用語一覧 — LLM第8回講義動画（2d07bb74、全編通し）

出典: `experiments/segments/20260728_2d07bb74c1f408e21e4e4ec7e3dbdb02 (1).json`
（105セグメント、講演者 Yanqi Zhou / Google DeepMind、「LLM scaling: dense modelの
power lawからMOE・continual learning・modularity(MOA)まで」の講演全編）。
`evaluation/benchmarks/technology_moe_2d07bb74_clip1〜5` はこの講演の一部区間の
抜粋であり、これまでの誤認識調査（report.txt）もclip2/3に限定されていたため、
今回は全編を通して専門用語を洗い出した。

## 1. dictionary.csv に追加済み（このセッションで反映）

### ASR誤認識の補正（新規パターン、置換の確度が高いもの）

| ASR出力 | 正しい語 | 根拠 |
|---|---|---|
| `TIFI` | T5 | 「TIFI originally reaches 11 billion parameters」＝T5-XXL(11B)の話。既存の`TIFINE`とは別の綴り |
| `GPG3` | GPT-3 | 「the GPG3 at 175 billion parameters」＝GPT-3(175B)の話。既存の`g p g three`とは別の綴り（スペース無し数字表記） |
| `PARAM two` | PaLM 2 | 既存の`PARM two`とA1文字違いの別変種 |

### 用語カバレッジ不足（ASRは概ね正しいが辞書未登録だった）

BERT, GLUE, masked language modeling, text-to-text, encoder-decoder, decoder-only,
in-context learning, prefix LM, GLaM, sparsely-gated, top-2 gating,
feed-forward network, continual learning, catastrophic forgetting,
domain adaptation, LWF / learning without forgetting, memory replay,
L2 regularization, mixture of adapters, MMLU, memory offloading,
power law, Moore's law, dense model, sparsity, modularity

特に **GLaM** は要注意: `keep_as_is_terms()`（Deepgramキーワードブースト対象）にも
含まれるが、辞書登録前は翻訳時にただの英単語 "glam"（「華やかな」）と誤訳される
リスクがあった（実際にこの講演では固有名詞のGoogleのMOEモデル名として使われている）。

## 2. 要確認（確度が低いため dictionary.csv には追加していない）

past incidentのMOA/MOE取り違え（report.txt参照）の教訓通り、根拠の弱い置換を
そのまま登録するのはリスクがあるため、以下は「音声を聞いて確認してから登録」を
推奨する候補として記録するに留めた。

| ASR出力 | 該当箇所 | 推定 | 確度 |
|---|---|---|---|
| `Annotify introduced a major conceptual simplification. It covered every single problem from translation to question answering into a text to text format.` | セグメント20-21 | 文脈から「**And T5** introduced...」の誤認識と推測（T5のtext-to-text統一を説明する文脈と一致） | 中（語形が大きく違うため要聴取確認） |
| `the g sharp top two routing function` / `the g sharp top two gating function` | セグメント36, 41 | MOEのtop-2ルーティングの文脈から **GShard top-2**（Lepikhin et al. 2020のtop-2 gating手法）の誤認識と推測 | 中 |
| `our target QA` / `q Quizlet` | セグメント85 | ドメイン適応評価に使ったデータセット名と思われるが特定できず | 低 |

## 3. 既に十分カバーされている主要用語（参考、dictionary.csv内で確認済み）

T5, GPT-3, PaLM, PaLM 2, MOE (Mixture of Experts), MOA (Mixture of Adapters),
FLOPS, memory wall, fine-tuning, few-shot, regularization, perplexity, latency,
ASR / speech recognition 系一式

## 4. 講演の技術的な流れ（メモ）

Moore's law・power lawの限界 → BERT(encoder-only, MLM) / T5(text-to-text,
encoder-decoder) → GPT-3(decoder-only, in-context learning) / PaLM・PaLM 2
(prefix LM) → dense modelの限界 → GLaM(MOE, top-2 gating, sparsely-gated) →
continual learning(catastrophic forgettingの回避: expansion + regularization,
LWF) → modularity / MOA(frozen backbone + task-specific adapters, プライバシー
分離, MMLU改善) という一本の筋になっている。dictionary.csvへの追加もこの流れを
踏まえて拾った。
