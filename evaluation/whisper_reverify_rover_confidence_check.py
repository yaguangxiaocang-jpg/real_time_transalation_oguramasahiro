"""confidence-weighted ROVER化（README 2026/09/21）の実音声での回帰確認。

`whisper_reverify_confidence_sweep.py`はWhisper側の信頼度だけを見た絶対閾値
min_confidenceのスイープだったが、今回`whisper_reverify.apply_term_corrections`に
`deepgram_word_confidences`を渡すと相対比較（Whisper信頼度 > Deepgram信頼度）に
切り替わるよう変更した（`transcription/whisper_reverify.py`のdocstring参照）。
この変更がユニットテストだけでなく実音声（`technology_moe_2d07bb74_clip{1..5}`）
でも既知の挙動を壊していないかを確認する。

やること:
1. 各クリップの音声全体をDeepgramのバッチAPI（`add_subtitles.py`と同じ
   `client.listen.v1.media.transcribe_file`）で1回だけ再文字起こしし、
   単語ごとの(punctuated_word, confidence, start, end)を取得する
   （ベンチマークJSONの`raw_utterances`にはテキストしか保存されておらず、
   単語レベル信頼度が無いため）。
2. `merge_raw_utterances`で結合したセグメントごとに、その時間区間に収まる
   Deepgram単語を抽出し`deepgram_word_confidences`として使う。
3. faster-whisperで同じ区間を再文字起こしし、
   (a) 絶対閾値のみ（`deepgram_word_confidences=None`、変更前の挙動）
   (b) confidence-weighted ROVER（`deepgram_word_confidences`あり、変更後の挙動）
   の両方で`apply_term_corrections`を実行し、発火した補正を比較する。

既知の期待値（report.txt・2026-09-12のconfidence sweep結果より）:
    正しい補正（true positive）が変更後も発火し続けること: TIFINE→T5, g p t three→GPT-3
    誤補正（false positive）が変更後も抑止され続けること: MOA→MOE

使い方:
    python evaluation/whisper_reverify_rover_confidence_check.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

from real_time_translation.transcription.whisper_client import (  # noqa: E402
    transcribe_pcm_with_whisper,
)
from real_time_translation.transcription.whisper_reverify import (  # noqa: E402
    DEFAULT_MIN_CONFIDENCE,
    apply_term_corrections,
)
from real_time_translation.translation.dictionary import TermDictionary  # noqa: E402

from run_benchmark import load_benchmark, merge_raw_utterances  # noqa: E402
from whisper_reverify_ab_test import (  # noqa: E402
    MIC_MAX_DURATION,
    MIC_MAX_WORDS,
    WHISPER_MODEL_SIZE,
    extract_pcm_slice,
    resolve_clip_path,
)

REPO_ROOT = Path(__file__).parent.parent
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

CLIP_IDS = [
    "technology_moe_2d07bb74_clip1",
    "technology_moe_2d07bb74_clip2",
    "technology_moe_2d07bb74_clip3",
    "technology_moe_2d07bb74_clip4",
    "technology_moe_2d07bb74_clip5",
]

# セグメント境界に対する単語の割当ての揺れ（Deepgramのutterance分割points と
# merge_raw_utterancesが使うstart/endが完全には一致しない場合があるため）を吸収する。
_TIME_TOLERANCE = 0.15


def _extract_wav(video_path: Path) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video_path),
        "-vn", "-ar", "16000", "-ac", "1", "-f", "wav",
        tmp.name,
    ]
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg音声抽出エラー:\n{result.stderr.decode(errors='replace')}")
    return Path(tmp.name)


def _deepgram_words_for_clip(video_path: Path) -> list[dict]:
    """クリップ全体をDeepgramバッチAPIで文字起こしし、単語リストを返す。

    `add_subtitles.py`の`transcribe_audio()`と同じAPI呼び出し（keywordsブースト
    なしのプレーン設定）。各要素は{"word": str, "start": float, "end": float,
    "confidence": float}。
    """
    from deepgram import DeepgramClient

    wav_path = _extract_wav(video_path)
    try:
        client = DeepgramClient(api_key=os.environ["DEEPGRAM_API_KEY"])
        with open(wav_path, "rb") as f:
            audio_data = f.read()
        response = client.listen.v1.media.transcribe_file(
            request=audio_data,
            model="nova-2-general",
            language="en",
            smart_format=True,
            punctuate=True,
            utterances=True,
        )
        channels = response.results.channels
        words = channels[0].alternatives[0].words or []
        return [
            {
                "word": w.punctuated_word or w.word,
                "start": float(w.start),
                "end": float(w.end),
                "confidence": float(w.confidence),
            }
            for w in words
        ]
    finally:
        wav_path.unlink(missing_ok=True)


def _words_in_range(
    words: list[dict], start: float, end: float
) -> list[tuple[str, float]]:
    lo, hi = start - _TIME_TOLERANCE, end + _TIME_TOLERANCE
    return [
        (w["word"], w["confidence"])
        for w in words
        if lo <= (w["start"] + w["end"]) / 2 <= hi
    ]


def main() -> None:
    dictionary = TermDictionary()
    dictionary.load_csv(REPO_ROOT / "dictionary.csv")
    keep_terms = dictionary.keep_as_is_terms()

    all_rows: list[dict] = []
    for clip_id in CLIP_IDS:
        benchmark = load_benchmark(REPO_ROOT / f"evaluation/benchmarks/{clip_id}.json")
        video_path = resolve_clip_path(clip_id)
        merged = merge_raw_utterances(
            benchmark, max_duration=MIC_MAX_DURATION, max_words=MIC_MAX_WORDS
        )
        print(f"\n{clip_id}: {len(merged)}セグメント。Deepgramで全体を再文字起こし中...")
        deepgram_words = _deepgram_words_for_clip(video_path)
        print(f"  Deepgram単語数: {len(deepgram_words)}")

        for seg in merged:
            pcm = extract_pcm_slice(video_path, seg["start"], seg["end"])
            whisper_text, whisper_confidences = transcribe_pcm_with_whisper(
                pcm, model_size=WHISPER_MODEL_SIZE, language="en"
            )
            seg_deepgram_confidences = _words_in_range(
                deepgram_words, seg["start"], seg["end"]
            )

            text_absolute, fixed_absolute = apply_term_corrections(
                seg["transcript"],
                whisper_text,
                keep_terms,
                whisper_word_confidences=whisper_confidences,
                min_confidence=DEFAULT_MIN_CONFIDENCE,
            )
            text_rover, fixed_rover = apply_term_corrections(
                seg["transcript"],
                whisper_text,
                keep_terms,
                whisper_word_confidences=whisper_confidences,
                min_confidence=DEFAULT_MIN_CONFIDENCE,
                deepgram_word_confidences=seg_deepgram_confidences,
            )

            if fixed_absolute or fixed_rover:
                print(f"  [{clip_id}] {seg['transcript']!r}")
                print(f"    absolute(before): {fixed_absolute} -> {text_absolute!r}")
                print(f"    ROVER(after)    : {fixed_rover} -> {text_rover!r}")

            all_rows.append(
                {
                    "clip_id": clip_id,
                    "segment_start": seg["start"],
                    "segment_end": seg["end"],
                    "deepgram_text": seg["transcript"],
                    "whisper_text": whisper_text,
                    "deepgram_word_count_in_range": len(seg_deepgram_confidences),
                    "orig_word_count": len(seg["transcript"].split()),
                    "fixed_absolute": fixed_absolute,
                    "text_absolute": text_absolute,
                    "fixed_rover": fixed_rover,
                    "text_rover": text_rover,
                }
            )

    fired_absolute = {
        (r["clip_id"], r["deepgram_text"], tuple(r["fixed_absolute"]))
        for r in all_rows
        if r["fixed_absolute"]
    }
    fired_rover = {
        (r["clip_id"], r["deepgram_text"], tuple(r["fixed_rover"]))
        for r in all_rows
        if r["fixed_rover"]
    }
    print("\n=== まとめ ===")
    print(f"絶対閾値(変更前)で発火: {len(fired_absolute)}件")
    print(f"ROVER相対比較(変更後)で発火: {len(fired_rover)}件")
    only_absolute = fired_absolute - fired_rover
    only_rover = fired_rover - fired_absolute
    if only_absolute:
        print(f"変更前のみ発火（変更後に消えた）: {only_absolute}")
    if only_rover:
        print(f"変更後のみ発火（新たに増えた）: {only_rover}")
    if not only_absolute and not only_rover:
        print("差分なし（絶対閾値でもROVERでも同じ箇所が発火）")

    save_results(all_rows)


def save_results(rows: list[dict]) -> None:
    EXPERIMENTS_DIR.mkdir(exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    json_path = EXPERIMENTS_DIR / f"{today}_whisper_reverify_rover_confidence_check.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {"date": date.today().strftime("%Y-%m-%d"), "rows": rows},
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n結果を保存: {json_path}")

    import csv

    csv_path = EXPERIMENTS_DIR / "results.csv"
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    fired_rows = [r for r in rows if r["fixed_absolute"] or r["fixed_rover"]]
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["date", "model", "domain", "llm_judge", "chrf_score", "notes"])
        for r in fired_rows:
            notes = (
                f"[whisper_reverify_rover_confidence_check][{r['clip_id']}] "
                f"absolute(before)={r['fixed_absolute']} -> ROVER(after)={r['fixed_rover']} "
                f"(deepgram_text={r['deepgram_text']!r})"
            )
            writer.writerow(
                [date.today().strftime("%Y-%m-%d"), WHISPER_MODEL_SIZE, "technology", "", "", notes]
            )
    print(f"results.csv を更新: {csv_path}")


if __name__ == "__main__":
    main()
