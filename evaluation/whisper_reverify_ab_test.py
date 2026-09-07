"""`WHISPER_REVERIFY_ENABLED`（Deepgram確定文をfaster-whisperで再検証するハイブリッド
ASR補正）のbefore/after検証。

`config.py`のコメントに「有効化する前に`evaluation/run_benchmark.py`でbefore/after
比較を行うこと」という運用ルールがある。ただし`whisper_reverify`はマイクの
ストリーミング経路（`pipeline.py`）専用で、utterance結合後の確定発話と同じ音声区間を
生PCMでfaster-whisperに再文字起こしさせ、辞書の「そのまま使う」用語
（`TermDictionary.keep_as_is_terms()`）と照合する仕組みのため、`run_benchmark.py`が
使うテキストのみのベンチマーク（`raw_utterances`）にそのまま配線することはできない
（`naturalness_check_ab_test.py`と同じ制約）。

そのため、実際にDeepgramの誤認識（T5→TFI/TIFINE、PaLM→Parm等、2026-08-11の調査で
確認済み）が記録されている`technology_moe_2d07bb74_clip{1..5}`ベンチマークについて、
対応する音声（`clips/2d07bb74_clipN.mp4`）から`pipeline.py`と同じ処理順序
（`_reverify_merged`: utterance結合 → 結合後セグメントの`[start, end]`区間を
再文字起こし → 既知用語の差分だけ補正）をffmpegでの音声切り出しで再現する。
結合・翻訳のパラメータはマイクの既定値（`max_duration=8.0s`, `max_words=30`,
`context_window_size=5`, `thinking_budget=0`）に合わせる
（`whisper_reverify`は動画/CLI経路には未適用のため）。

セグメント数が結合パラメータやWhisper補正の有無で変わりうるため、
`chunk_length_sweep.py`と同じ document-level chrF（全文連結）で比較する。

使い方:
    python evaluation/whisper_reverify_ab_test.py evaluation/benchmarks/technology_moe_2d07bb74_clip2.json
    python evaluation/whisper_reverify_ab_test.py evaluation/benchmarks/technology_moe_2d07bb74_clip{1,2,3,4,5}.json
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

from real_time_translation.transcription.whisper_reverify import reverify_terms  # noqa: E402
from real_time_translation.translation.dictionary import TermDictionary  # noqa: E402

from run_benchmark import (  # noqa: E402
    GEMINI_MODEL,
    GOOGLE_API_KEY,
    load_benchmark,
    merge_raw_utterances,
    score_against_reference,
    translate_merged,
)

REPO_ROOT = Path(__file__).parent.parent
CLIPS_DIR = REPO_ROOT / "clips"
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

# whisper_reverifyはマイク専用機能のため、結合・翻訳ともマイク側の既定値に合わせる
# （video/CLIの既定である20秒/60語・thinking_budget=1024ではない）。
MIC_MAX_DURATION = 8.0
MIC_MAX_WORDS = 30
MIC_CONTEXT_WINDOW_SIZE = 5
MIC_THINKING_BUDGET = 0

WHISPER_MODEL_SIZE = "small.en"

_CLIP_ID_RE = re.compile(r"(2d07bb74(?:_v2)?_clip\d+)")


def resolve_clip_path(benchmark_id: str) -> Path:
    m = _CLIP_ID_RE.search(benchmark_id)
    if not m:
        raise ValueError(
            f"ベンチマークID '{benchmark_id}' から対応する音声クリップを特定できません"
            "（clips/配下の *_clipN.mp4 と対応する命名規則のみ対応）。"
        )
    return CLIPS_DIR / f"{m.group(1)}.mp4"


def extract_pcm_slice(
    video_path: Path, start: float, end: float, pad: float = 0.2
) -> bytes:
    """指定区間 `[start-pad, end+pad]` を16bit/16kHz/monoの生PCMとしてffmpegで切り出す。

    `pipeline.py`の`_AudioRingBuffer.slice()`と同じパディング（0.2秒）を使う。
    """
    lo = max(0.0, start - pad)
    dur = max((end + pad) - lo, 0.05)
    cmd = [
        "ffmpeg", "-loglevel", "error",
        "-i", str(video_path),
        "-ss", f"{lo:.3f}", "-t", f"{dur:.3f}",
        "-f", "s16le", "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
        "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg音声抽出エラー:\n{result.stderr.decode(errors='replace')}"
        )
    return result.stdout


async def apply_reverify(
    merged: list[dict], video_path: Path, keep_terms: list[str]
) -> tuple[list[dict], list[dict]]:
    """merge後の各セグメントに`_reverify_merged`相当の補正を適用する。

    Returns:
        (補正後のmergedリスト, 実際に補正が発生した箇所のログ)
    """
    corrected_segments = []
    fired_log = []
    for seg in merged:
        pcm = await asyncio.to_thread(
            extract_pcm_slice, video_path, seg["start"], seg["end"]
        )
        corrected_text, fixed_terms = await asyncio.to_thread(
            reverify_terms,
            seg["transcript"],
            pcm,
            keep_terms,
            model_size=WHISPER_MODEL_SIZE,
        )
        new_seg = dict(seg)
        if corrected_text != seg["transcript"]:
            new_seg["transcript"] = corrected_text
            fired_log.append(
                {
                    "before": seg["transcript"],
                    "after": corrected_text,
                    "fixed_terms": fixed_terms,
                }
            )
        corrected_segments.append(new_seg)
    return corrected_segments, fired_log


async def run_one(benchmark_path: Path) -> dict:
    benchmark = load_benchmark(benchmark_path)
    benchmark_id = benchmark["benchmark_id"]
    print(f"\n=== {benchmark_id} ===")

    video_path = resolve_clip_path(benchmark_id)
    if not video_path.exists():
        raise FileNotFoundError(f"音声クリップが見つかりません: {video_path}")

    dictionary = TermDictionary()
    dictionary.load_csv(REPO_ROOT / "dictionary.csv")
    keep_terms = dictionary.keep_as_is_terms()

    merged_before = merge_raw_utterances(
        benchmark, max_duration=MIC_MAX_DURATION, max_words=MIC_MAX_WORDS
    )
    print(f"結合後セグメント数: {len(merged_before)}")

    merged_after, fired = await apply_reverify(merged_before, video_path, keep_terms)

    if fired:
        print(f"--- Whisper再検証で補正された箇所（{len(fired)}件） ---")
        for f in fired:
            print(f"  before: {f['before']!r}")
            print(f"  after : {f['after']!r}  (fixed_terms={f['fixed_terms']})")
    else:
        print("--- Whisper再検証で補正された箇所はありませんでした ---")

    refs = benchmark["reference_ja"]

    hyps_before = await translate_merged(
        merged_before,
        benchmark["domain"],
        context_window_size=MIC_CONTEXT_WINDOW_SIZE,
        thinking_budget=MIC_THINKING_BUDGET,
    )
    hyps_after = await translate_merged(
        merged_after,
        benchmark["domain"],
        context_window_size=MIC_CONTEXT_WINDOW_SIZE,
        thinking_budget=MIC_THINKING_BUDGET,
    )

    doc_chrf_before = score_against_reference([" ".join(hyps_before)], [" ".join(refs)])
    doc_chrf_after = score_against_reference([" ".join(hyps_after)], [" ".join(refs)])

    print(f"doc_chrf OFF(before)={doc_chrf_before}  ON(after)={doc_chrf_after}")

    return {
        "benchmark_id": benchmark_id,
        "domain": benchmark["domain"],
        "segment_count": len(merged_before),
        "fired_count": len(fired),
        "fired": fired,
        "doc_chrf_off": doc_chrf_before,
        "doc_chrf_on": doc_chrf_after,
        "merged_before_texts": [s["transcript"] for s in merged_before],
        "merged_after_texts": [s["transcript"] for s in merged_after],
        "translated_before": hyps_before,
        "translated_after": hyps_after,
    }


def save_results(results: list[dict]) -> None:
    """CLAUDE.mdの実験記録ルールに沿って、JSON保存 + results.csvへ追記する。"""
    EXPERIMENTS_DIR.mkdir(exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    model_slug = GEMINI_MODEL.replace("-", "_").replace(".", "")

    json_path = EXPERIMENTS_DIR / f"{today}_{model_slug}_whisper_reverify_ab_test.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": date.today().strftime("%Y-%m-%d"),
                "model": GEMINI_MODEL,
                "whisper_model_size": WHISPER_MODEL_SIZE,
                "results": results,
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
            writer.writerow(
                ["date", "model", "domain", "xcomet_score", "chrf_score", "notes"]
            )
        for r in results:
            notes = (
                f"[benchmark={r['benchmark_id']}][whisper_reverify_ab_test] "
                f"segments={r['segment_count']}, 補正発生={r['fired_count']}件 "
                f"-> doc_chrf(document-level) OFF={r['doc_chrf_off']} / "
                f"ON={r['doc_chrf_on']}"
            )
            writer.writerow(
                [
                    date.today().strftime("%Y-%m-%d"),
                    GEMINI_MODEL,
                    r["domain"],
                    "",
                    r["doc_chrf_on"],
                    notes,
                ]
            )
    print(f"results.csv を更新: {csv_path}")


async def main(benchmark_paths: list[Path]) -> None:
    results = []
    for p in benchmark_paths:
        results.append(await run_one(p))

    print("\n=== まとめ ===")
    total_fired = sum(r["fired_count"] for r in results)
    for r in results:
        delta = round(r["doc_chrf_on"] - r["doc_chrf_off"], 4)
        print(
            f"{r['benchmark_id']}: 補正={r['fired_count']}件, "
            f"doc_chrf OFF={r['doc_chrf_off']} -> ON={r['doc_chrf_on']} "
            f"(delta={delta:+})"
        )
    print(f"\n補正が発生した合計箇所数: {total_fired}")

    save_results(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "WHISPER_REVERIFY_ENABLEDのbefore/after検証"
            "（pipeline.py経路をffmpeg音声切り出しで再現）"
        )
    )
    parser.add_argument(
        "benchmarks", type=Path, nargs="+",
        help="evaluation/benchmarks/*.json へのパス（複数可）",
    )
    args = parser.parse_args()

    missing = [p for p in args.benchmarks if not p.exists()]
    if missing:
        print(f"エラー: ベンチマークファイルが見つかりません: {missing}")
        sys.exit(1)
    if not GOOGLE_API_KEY:
        print("エラー: GOOGLE_API_KEY が設定されていません。")
        sys.exit(1)

    asyncio.run(main(args.benchmarks))
