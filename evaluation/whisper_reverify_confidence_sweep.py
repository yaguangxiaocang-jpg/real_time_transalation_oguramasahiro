"""`whisper_reverify.py`の`min_confidence`のチューニング（report.txtの優先課題(2)、
2026-09-07のガード追加で生じた適合率/再現率トレードオフへの対応）。

`whisper_reverify_ab_test.py`の2026-09-07実行（両ガード込み、min_confidence=0.6）で、
既知の誤補正MOA→MOE（false positive）は解消できたが、正しい補正のうち2件
（TIFINE→T5、"g p t three"→GPT-3）も一緒に発火しなくなったことが判明した
（README更新履歴・report.txt参照）。

本スクリプトは、`technology_moe_2d07bb74_clip{1..5}`の全結合セグメントに対して
faster-whisperの再文字起こしを**1回だけ**実行し（閾値ごとに再実行すると
CPU推論のスレッド間非決定性でconfidence自体が試行ごとに微妙にブレるため、
同一の文字起こし結果に対して閾値だけを変えて比較する）、複数の`min_confidence`
候補について`apply_term_corrections`を適用し、発火した補正の一覧を閾値ごとに
比較できるようにする。翻訳（Gemini API）は呼ばないため、ローカルのfaster-whisper
推論とffmpeg音声切り出しのみで完結する（コスト・所要時間が小さい）。

既知の分類（report.txt・2026-08-26のbefore/after検証より）:
    正しい補正（true positive）: TIFINE/TFI/TIFI→T5, t five→T5, Parm/PARM two→PaLM/PaLM2,
        g p three/g p g three→GPT-3, memory war→memory wall
    誤補正（false positive）   : MOA→MOE（音響的に紛らわしい2つの正当な用語の取り違え）

使い方:
    python evaluation/whisper_reverify_confidence_sweep.py
"""

from __future__ import annotations

import difflib
import json
import sys
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
    _normalize,
    _WORD_RE,
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

# 現行既定値(0.6)を含め、それより緩い/厳しい候補を横断する。
MIN_CONFIDENCE_CANDIDATES = [0.0, 0.3, 0.4, 0.5, 0.55, 0.6, 0.7, 0.8]


def find_candidates(text: str, whisper_text: str, whisper_word_confidences, keep_terms_lower):
    """`apply_term_corrections`の候補抽出部分だけを再現し、閾値未適用の生候補を返す
    （原文側があいまい=既登録の別用語 かどうかも合わせて返す）。
    """
    orig_words = _WORD_RE.findall(text)
    whisper_words = [w for w, _ in whisper_word_confidences]
    confidences = [c for _, c in whisper_word_confidences]
    if not orig_words or not whisper_words:
        return []

    orig_norm = [_normalize(w) for w in orig_words]
    whisper_norm = [_normalize(w) for w in whisper_words]
    matcher = difflib.SequenceMatcher(a=orig_norm, b=whisper_norm, autojunk=False)

    candidates = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag not in ("replace", "insert"):
            continue
        candidate_words = whisper_norm[j1:j2]
        candidate_norm = " ".join(candidate_words)
        if candidate_norm not in keep_terms_lower:
            # whisper_reverify.pyの2026-09-08修正と同じフォールバック:
            # faster-whisperがハイフン区切り複合語（"GPT-3,"→"GPT"+"-3,"）を
            # 複数トークンに分割することがあり、空白結合だと一致しないため
            # 空白なし結合でも試す。
            candidate_compact = "".join(candidate_words)
            if candidate_compact not in keep_terms_lower:
                continue
            candidate_norm = candidate_compact
        if candidate_norm in orig_norm[i1:i2]:
            continue
        original_span = " ".join(orig_norm[i1:i2])
        span_conf = confidences[j1:j2]
        candidates.append(
            {
                "original_span": original_span,
                "candidate": candidate_norm,
                "replacement": " ".join(whisper_words[j1:j2]),
                "min_span_confidence": round(min(span_conf), 4) if span_conf else None,
                "ambiguous_original": original_span in keep_terms_lower,
            }
        )
    return candidates


def main() -> None:
    dictionary = TermDictionary()
    dictionary.load_csv(REPO_ROOT / "dictionary.csv")
    keep_terms = dictionary.keep_as_is_terms()
    keep_terms_lower = {t.lower() for t in keep_terms}

    # ステップ1: 各クリップの結合セグメントごとにWhisper再文字起こしを1回だけ実行し、
    # 生候補（原文スパン・候補用語・信頼度・原文があいまいか）を収集する。
    all_candidates: list[dict] = []
    segment_count_by_clip: dict[str, int] = {}
    for clip_id in CLIP_IDS:
        benchmark = load_benchmark(REPO_ROOT / f"evaluation/benchmarks/{clip_id}.json")
        video_path = resolve_clip_path(clip_id)
        merged = merge_raw_utterances(
            benchmark, max_duration=MIC_MAX_DURATION, max_words=MIC_MAX_WORDS
        )
        segment_count_by_clip[clip_id] = len(merged)
        print(f"{clip_id}: {len(merged)}セグメントを再文字起こし中...")
        for seg in merged:
            pcm = extract_pcm_slice(video_path, seg["start"], seg["end"])
            whisper_text, confidences = transcribe_pcm_with_whisper(
                pcm, model_size=WHISPER_MODEL_SIZE, language="en"
            )
            for cand in find_candidates(
                seg["transcript"], whisper_text, confidences, keep_terms_lower
            ):
                cand.update(
                    {
                        "clip_id": clip_id,
                        "segment_start": seg["start"],
                        "segment_end": seg["end"],
                        "deepgram_text": seg["transcript"],
                        "whisper_text": whisper_text,
                    }
                )
                all_candidates.append(cand)

    print(f"\n生候補数（閾値・あいまいガード適用前）: {len(all_candidates)}")
    for c in all_candidates:
        print(
            f"  [{c['clip_id']}] {c['original_span']!r} -> {c['candidate']!r} "
            f"min_conf={c['min_span_confidence']} ambiguous_original={c['ambiguous_original']}"
        )

    # ステップ2: 閾値候補ごとに、実際に発火する補正（あいまいガードも含めて）を集計する。
    sweep_results = []
    print("\n=== min_confidence 別の発火状況 ===")
    for min_conf in MIN_CONFIDENCE_CANDIDATES:
        fired = []
        for c in all_candidates:
            if c["ambiguous_original"]:
                continue  # ガード1は閾値と無関係に常に適用
            if c["min_span_confidence"] is None or c["min_span_confidence"] < min_conf:
                continue
            fired.append(c)
        sweep_results.append({"min_confidence": min_conf, "fired": fired})
        fired_desc = ", ".join(
            f"{c['original_span']}->{c['candidate']}({c['min_span_confidence']})" for c in fired
        )
        print(f"  min_confidence={min_conf:<4} fired={len(fired):>2}件  {fired_desc}")

    save_results(all_candidates, sweep_results, segment_count_by_clip)


def save_results(all_candidates, sweep_results, segment_count_by_clip) -> None:
    EXPERIMENTS_DIR.mkdir(exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    json_path = EXPERIMENTS_DIR / f"{today}_whisper_reverify_confidence_sweep.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": date.today().strftime("%Y-%m-%d"),
                "whisper_model_size": WHISPER_MODEL_SIZE,
                "segment_count_by_clip": segment_count_by_clip,
                "candidates": all_candidates,
                "sweep": sweep_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n結果を保存: {json_path}")

    import csv

    csv_path = EXPERIMENTS_DIR / "results.csv"
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["date", "model", "domain", "xcomet_score", "chrf_score", "notes"])
        for r in sweep_results:
            fired_desc = "; ".join(
                f"{c['original_span']}->{c['candidate']}(conf={c['min_span_confidence']})"
                for c in r["fired"]
            )
            notes = (
                f"[whisper_reverify_confidence_sweep] min_confidence={r['min_confidence']} -> "
                f"{len(r['fired'])}件発火: {fired_desc or 'なし'}"
            )
            writer.writerow(
                [date.today().strftime("%Y-%m-%d"), WHISPER_MODEL_SIZE, "technology", "", "", notes]
            )
    print(f"results.csv を更新: {csv_path}")


if __name__ == "__main__":
    main()
