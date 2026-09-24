"""実音声からのエンドツーエンド精度確認（ASR→結合→翻訳）。

`run_benchmark.py`はベンチマークJSONに凍結された`raw_utterances`（2026-07-11時点の
Deepgram出力、キーワードブースト導入前）を入力にしており、翻訳部分しか測れない。
このスクリプトは同じクリップの**実音声**を現在の本番設定（`add_subtitles.py`の
`extract_audio`/`transcribe_audio`＝nova-2-general・キーワードブーストあり）で
文字起こしし直し、同じ結合・翻訳（辞書あり）を通して`reference_ja`と比較する。

比較のため、同一実行内で凍結テキスト入力（従来のベンチマーク経路）も同じ翻訳器
設定で翻訳する。両者の差が「現在のASRを通したときの精度変化」の目安になる。

実音声経路では結合後のセグメント数が`reference_ja`と一致するとは限らないため、
全セグメントを連結した文書単位chrF（doc_chrF）で比較する。

使い方:
    python evaluation/real_audio_e2e_check.py
    python evaluation/real_audio_e2e_check.py --clips 1 3
    python evaluation/real_audio_e2e_check.py --no-keyword-boost  # ブースト無しの対照条件
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

import add_subtitles  # noqa: E402
from add_subtitles import extract_audio, transcribe_audio  # noqa: E402
from real_time_translation.transcription.utterance_merge import (  # noqa: E402
    merge_incomplete_utterances,
)
from real_time_translation.translation.terminology_check import (  # noqa: E402
    check_terminology,
)
from run_benchmark import (  # noqa: E402
    GEMINI_MODEL,
    load_benchmark,
    merge_raw_utterances,
    score_with_llm_judge,
)

EXPERIMENTS_DIR = ROOT / "experiments"
BENCHMARKS_DIR = Path(__file__).parent / "benchmarks"
DICTIONARY_PATH = Path(os.environ.get("DICTIONARY_PATH") or ROOT / "dictionary.csv")


def doc_chrf(hyps: list[str], refs: list[str]) -> float:
    from sacrebleu.metrics import CHRF

    return round(CHRF().corpus_score(["".join(hyps)], [["".join(refs)]]).score / 100, 4)


async def translate_all(segments: list[dict], domain: str) -> tuple[list[str], list[str]]:
    """add_subtitles.translate_segmentsと同じ翻訳器設定で翻訳し、(訳, 用語漏れ)を返す。"""
    from real_time_translation.translation.llm_translator import LLMTranslator

    translator = LLMTranslator(
        provider="gemini",
        api_key=os.environ.get("GOOGLE_API_KEY", ""),
        model=GEMINI_MODEL,
        source_language="English",
        target_language="Japanese",
        domain=domain,
        context_window_size=5,
        thinking_budget=1024,
        dictionary_path=DICTIONARY_PATH,
    )
    hyps = []
    for seg in segments:
        hyps.append((await translator.translate(seg["transcript"])).latest_slide)
    misses = check_terminology(
        [(s["transcript"], h) for s, h in zip(segments, hyps)], translator.dictionary
    ).misses
    return hyps, [f"{m.source_term}→{m.target_term}" for m in misses]


async def run_clip(n: int) -> dict:
    bench_path = BENCHMARKS_DIR / f"technology_moe_2d07bb74_clip{n}.json"
    video = ROOT / "clips" / f"2d07bb74_clip{n}.mp4"
    benchmark = load_benchmark(bench_path)
    refs = benchmark["reference_ja"]
    domain = benchmark["domain"]

    with tempfile.TemporaryDirectory() as tmpdir:
        wav = str(Path(tmpdir) / "audio.wav")
        extract_audio(str(video), wav)
        fresh_raw = transcribe_audio(wav)
    audio_merged = merge_incomplete_utterances(fresh_raw)
    frozen_merged = merge_raw_utterances(benchmark)

    audio_hyps, audio_misses = await translate_all(audio_merged, domain)
    frozen_hyps, frozen_misses = await translate_all(frozen_merged, domain)

    audio_judge = await score_with_llm_judge(
        [s["transcript"] for s in audio_merged], audio_hyps
    )

    result = {
        "clip": f"clips/{video.name}",
        "benchmark_id": benchmark["benchmark_id"],
        "audio_segments": len(audio_merged),
        "reference_segments": len(refs),
        "audio_doc_chrf": doc_chrf(audio_hyps, refs),
        "frozen_text_doc_chrf": doc_chrf(frozen_hyps, refs),
        "audio_llm_judge": audio_judge,
        "audio_terminology_misses": audio_misses,
        "frozen_terminology_misses": frozen_misses,
        "audio_source_en": " ".join(s["transcript"] for s in audio_merged),
        "frozen_source_en": " ".join(s["transcript"] for s in frozen_merged),
        "audio_mt_ja": audio_hyps,
        "frozen_mt_ja": frozen_hyps,
    }
    result["delta_doc_chrf"] = round(
        result["audio_doc_chrf"] - result["frozen_text_doc_chrf"], 4
    )
    print(
        f"[clip{n}] audio doc_chrF={result['audio_doc_chrf']} "
        f"frozen doc_chrF={result['frozen_text_doc_chrf']} "
        f"(delta={result['delta_doc_chrf']:+}) judge={audio_judge} "
        f"segs={len(audio_merged)}/{len(refs)} misses={audio_misses}"
    )
    return result


def save(results: list[dict], keyword_boost: bool) -> None:
    today = date.today()
    mean = lambda k: round(sum(r[k] for r in results) / len(results), 4)  # noqa: E731
    judges = [r["audio_llm_judge"] for r in results if r["audio_llm_judge"] is not None]
    summary = {
        "audio_doc_chrf_mean": mean("audio_doc_chrf"),
        "frozen_text_doc_chrf_mean": mean("frozen_text_doc_chrf"),
        "delta_doc_chrf_mean": mean("delta_doc_chrf"),
        "audio_llm_judge_mean": round(sum(judges) / len(judges), 4) if judges else None,
    }
    notes = (
        f"[real_audio_e2e_check] clips={[r['clip'] for r in results]} 実音声→Deepgram"
        f"(nova-2-general,キーワードブースト{'あり' if keyword_boost else 'なし'})→結合→{GEMINI_MODEL}(辞書あり)。"
        f"doc_chrF 実音声={summary['audio_doc_chrf_mean']} / 凍結テキスト="
        f"{summary['frozen_text_doc_chrf_mean']} (差={summary['delta_doc_chrf_mean']:+})。"
        "reference_jaは人手レビュー未了(draft)。"
    )
    record = {
        "date": today.isoformat(),
        "model": GEMINI_MODEL,
        "domain": "technology",
        "xcomet_score": summary["audio_llm_judge_mean"],
        "chrf_score": summary["audio_doc_chrf_mean"],
        "notes": notes,
        "keyword_boost": keyword_boost,
        "summary": summary,
        "clips": results,
    }
    suffix = "" if keyword_boost else "_no_keyword_boost"
    json_path = EXPERIMENTS_DIR / f"{today:%Y%m%d}_real_audio_e2e_check{suffix}.json"
    json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(EXPERIMENTS_DIR / "results.csv", "a", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerow(
            [record["date"], GEMINI_MODEL, "technology",
             record["xcomet_score"] if record["xcomet_score"] is not None else "",
             record["chrf_score"], notes]
        )
    print(f"\n結果を保存: {json_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


async def main(clips: list[int], keyword_boost: bool) -> None:
    add_subtitles.DEEPGRAM_KEYWORD_BOOST_ENABLED = keyword_boost
    results = [await run_clip(n) for n in clips]
    save(results, keyword_boost)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clips", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument(
        "--no-keyword-boost",
        action="store_true",
        help="Deepgramキーワードブーストを無効化して文字起こしする（対照条件）",
    )
    args = parser.parse_args()
    asyncio.run(main(args.clips, keyword_boost=not args.no_keyword_boost))
