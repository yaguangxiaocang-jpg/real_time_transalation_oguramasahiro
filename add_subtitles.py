"""
動画ファイルに日本語字幕を追加するスクリプト。

手順:
1. ffmpegで音声抽出
2. Deepgramで文字起こし（タイムスタンプ付き）
3. Geminiで日本語翻訳
4. SRTファイル生成
5. ffmpegで字幕焼き込み
"""

import asyncio
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent / "src"))

# Windowsではコンソール/リダイレクト先のデフォルトエンコーディングがcp932になり、
# 絵文字（⚠️等、terminology_check.pyのformat_terminology_misses()が出力）を
# printしようとするとUnicodeEncodeErrorでクラッシュすることがあるため、
# 標準出力をUTF-8に固定する。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]
GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
SOURCE_LANGUAGE = os.environ.get("SOURCE_LANGUAGE", "en")
TRANSLATION_DOMAIN = os.environ.get("TRANSLATION_DOMAIN", "general")
GEMINI_MODEL = "gemini-2.5-flash"
# 実験記録のファイル名・notesに付与するタグ（同日・同domainで複数バリエーションを
# 比較実験する際に、experiments/*.jsonが上書きされないようにするため）
EXPERIMENT_TAG = os.environ.get("EXPERIMENT_TAG", "")
# 文末で終わっていないDeepgram utteranceを次のutteranceと結合してから翻訳するか
MERGE_UTTERANCES = os.environ.get("MERGE_UTTERANCES", "true").lower() == "true"
# 文字起こしプロバイダ（"deepgram" または "whisper"）。faster-whisperは
# ストリーミングAPIを持たないためオフライン処理のこの経路でのみ選択可能
# （マイクのリアルタイム翻訳はDeepgram固定）。2026-08-11の調査で、
# DeepgramがT5/PaLM/GPT-3等のモデル名を誤認識するケースをfaster-whisperの方が
# 正しく認識できることを確認した（README.md 更新履歴参照）。
TRANSCRIPTION_PROVIDER = os.environ.get("TRANSCRIPTION_PROVIDER", "deepgram").lower()
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "small.en")
# 用語辞書（CSV: source_term,target_term,notes）。マイクのリアルタイム翻訳
# （pipeline.py）にはこれまで渡っていたが、動画字幕パスでは配線されて
# いなかったため追加。
DICTIONARY_PATH = os.environ.get("DICTIONARY_PATH") or None
# utterance分断検出のLLM分類器（失敗時は正規表現へ自動フォールバック）
INCOMPLETE_END_DETECTION_ENABLED = (
    os.environ.get("INCOMPLETE_END_DETECTION_ENABLED", "true").lower() == "true"
)
INCOMPLETE_END_DETECTION_MODEL = (
    os.environ.get("INCOMPLETE_END_DETECTION_MODEL") or GEMINI_MODEL
)
# 翻訳完全性チェック（文字数比の異常検知で訳し漏れの疑いを検出）
COMPLETENESS_CHECK_ENABLED = (
    os.environ.get("COMPLETENESS_CHECK_ENABLED", "true").lower() == "true"
)
COMPLETENESS_RATIO_THRESHOLD = float(
    os.environ.get("COMPLETENESS_RATIO_THRESHOLD", "0.5")
)

# gradio_demo.py の _FULL_NAME と同じマッピング（LLMTranslator のプロンプトに使う言語名）
_LANGUAGE_NAMES = {
    "en": "English", "ja": "Japanese", "zh": "Chinese",
    "ko": "Korean", "es": "Spanish", "fr": "French", "de": "German",
}

EXPERIMENTS_DIR = Path(__file__).parent / "experiments"
TRANSLATED_SCRIPT_DIR = Path(__file__).parent / "translated_script"
SEGMENTS_DIR = Path(__file__).parent / "experiments" / "segments"


async def compute_scores(translated: list[dict]) -> tuple[float | None, float | None]:
    """自動評価スコアを計算する。

    xcomet_score: Gemini LLM-as-judge（0〜1）
    chrf_score:   逆翻訳（日→英）後に sacrebleu chrF で計算（0〜1）
    """
    from google import genai

    client = genai.Client(api_key=GOOGLE_API_KEY)
    sample = translated[:20]
    srcs = [s["original"] for s in sample]
    mts = [s["japanese"] for s in sample]

    # --- xcomet_score: LLM-as-judge ---
    print("自動評価（LLM判定）を計算中...")
    judge_prompt = (
        "あなたはプロの翻訳評価者です。以下の英日翻訳ペアをそれぞれ評価し、"
        "翻訳品質を0.00〜1.00のスコアで採点してください。"
        "番号付きリストで数値のみ返してください（例: 1. 0.85）。\n\n"
        + "\n".join(f"{i+1}. EN: {s}\n   JA: {m}" for i, (s, m) in enumerate(zip(srcs, mts)))
    )
    judge_resp = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=judge_prompt,
    )
    xcomet_score: float | None = None
    scores = []
    import re
    for line in (judge_resp.text or "").split("\n"):
        m = re.match(r"\d+\.\s*([\d.]+)", line.strip())
        if m:
            try:
                scores.append(float(m.group(1)))
            except ValueError:
                pass
    if scores:
        xcomet_score = round(sum(scores) / len(scores), 4)
        print(f"  xcomet_score (LLM judge): {xcomet_score}")

    # --- chrf_score: 逆翻訳 + sacrebleu ---
    print("自動評価（逆翻訳 chrF）を計算中...")
    back_prompt = (
        "Translate the following Japanese sentences back to English. "
        "Return only the translations as a numbered list (e.g. 1. text). "
        "Do not include explanations.\n\n"
        + "\n".join(f"{i+1}. {m}" for i, m in enumerate(mts))
    )
    back_resp = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=back_prompt,
    )
    chrf_score: float | None = None
    back_texts: list[str] = []
    for line in (back_resp.text or "").split("\n"):
        line = line.strip()
        if line and line[0].isdigit() and ". " in line:
            back_texts.append(line.split(". ", 1)[1])
        elif line and line[0].isdigit() and "." in line:
            back_texts.append(line.split(".", 1)[1].strip())
    if len(back_texts) >= len(srcs) // 2:
        back_texts = back_texts[: len(srcs)]
        from sacrebleu.metrics import CHRF
        chrf = CHRF()
        raw = chrf.corpus_score(back_texts, [srcs]).score  # 0〜100
        chrf_score = round(raw / 100, 4)
        print(f"  chrf_score (back-translation): {chrf_score}")

    return xcomet_score, chrf_score


def save_experiment_record(
    translated: list[dict],
    video_path: Path,
    xcomet_score: float | None = None,
    chrf_score: float | None = None,
    notes: str = "",
    report: dict | None = None,
) -> None:
    """実験結果をexperimentsフォルダに保存する。"""
    EXPERIMENTS_DIR.mkdir(exist_ok=True)

    today = date.today().strftime("%Y%m%d")
    model_slug = GEMINI_MODEL.replace("-", "_").replace(".", "")
    tag_suffix = f"_{EXPERIMENT_TAG}" if EXPERIMENT_TAG else ""
    json_name = f"{today}_{model_slug}_{TRANSLATION_DOMAIN}{tag_suffix}.json"
    json_path = EXPERIMENTS_DIR / json_name

    report_notes = ""
    if report:
        flagged = report.get("flagged_count", 0)
        misses = report.get("terminology_misses") or []
        report_notes = f" [{report.get('usage_summary', '')}]"
        if flagged:
            report_notes += f" [要確認: {flagged}件]"
        if misses:
            report_notes += f" [用語漏れ: {', '.join(misses)}]"

    auto_notes = (
        f"{video_path.name} を処理。{len(translated)} セグメント翻訳。"
        + f" [asr={TRANSCRIPTION_PROVIDER}]"
        + (f" [tag={EXPERIMENT_TAG}]" if EXPERIMENT_TAG else "")
        + (f" {notes}" if notes else "")
        + report_notes
    )

    record = {
        "date": date.today().strftime("%Y-%m-%d"),
        "model": GEMINI_MODEL,
        "domain": TRANSLATION_DOMAIN,
        "xcomet_score": xcomet_score,
        "chrf_score": chrf_score,
        "notes": auto_notes,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"実験記録を保存: {json_path}")

    csv_path = EXPERIMENTS_DIR / "results.csv"
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["date", "model", "domain", "xcomet_score", "chrf_score", "notes"])
        writer.writerow([
            record["date"],
            record["model"],
            record["domain"],
            "" if xcomet_score is None else xcomet_score,
            "" if chrf_score is None else chrf_score,
            record["notes"],
        ])
    print(f"results.csv を更新: {csv_path}")


def save_segments(
    translated: list[dict], video_path: Path, report: dict | None = None
) -> Path:
    """セグメント単位の生データ（原文・訳文・タイムスタンプ）を保存する。

    experiments/*.json の集計スコア・notesだけでは、後から「この動画・この訳が
    正しかったか」を検証できない（原文がどこにも残らない）。ここで生データを
    残しておくことで、evaluation/benchmarks/ 用のベンチマークデータセットを
    後から人手でレビュー・選定できるようにする（正解データを都度作り直す手間を防ぐ）。

    `report`（translate_segments が返す使用量・要確認件数・用語漏れ）も
    合わせて残し、後からパラメータ変更の影響を追跡できるようにする。
    """
    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)

    today = date.today().strftime("%Y%m%d")
    tag_suffix = f"_{EXPERIMENT_TAG}" if EXPERIMENT_TAG else ""
    json_path = SEGMENTS_DIR / f"{today}_{video_path.stem}{tag_suffix}.json"

    record = {
        "date": date.today().strftime("%Y-%m-%d"),
        "video": video_path.name,
        "model": GEMINI_MODEL,
        "domain": TRANSLATION_DOMAIN,
        "merge_utterances": MERGE_UTTERANCES,
        "transcription_provider": TRANSCRIPTION_PROVIDER,
        "report": report or {},
        "segments": [
            {
                "start": seg["start"],
                "end": seg["end"],
                "source": seg["original"],
                "mt_ja": seg["japanese"],
                "review_flag": seg.get("review_flag"),
            }
            for seg in translated
        ],
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"セグメント生データを保存: {json_path}")
    return json_path


def extract_audio(video_path: str, audio_path: str) -> None:
    """動画から音声をWAV形式で抽出する。"""
    print(f"音声を抽出中: {video_path}")
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            audio_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg音声抽出に失敗しました:\n{result.stderr}")
    print("音声抽出完了")


def transcribe_audio_with_provider(audio_path: str) -> list[dict]:
    """TRANSCRIPTION_PROVIDER環境変数に応じてDeepgram/faster-whisperを切り替える。"""
    if TRANSCRIPTION_PROVIDER == "whisper":
        from real_time_translation.transcription.whisper_client import (
            transcribe_with_whisper,
        )

        print(f"faster-whisperで文字起こし中...（model={WHISPER_MODEL_SIZE}）")
        result = transcribe_with_whisper(
            audio_path, model_size=WHISPER_MODEL_SIZE, language=SOURCE_LANGUAGE
        )
        print(f"文字起こし完了: {len(result)} セグメント")
        return result
    return transcribe_audio(audio_path)


def transcribe_audio(audio_path: str) -> list[dict]:
    """Deepgramで音声を文字起こしし、utterancesリストを返す。"""
    from deepgram import DeepgramClient

    print("Deepgramで文字起こし中...")
    client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    response = client.listen.v1.media.transcribe_file(
        request=audio_data,
        model="nova-2-general",
        language=SOURCE_LANGUAGE,
        smart_format=True,
        punctuate=True,
        utterances=True,
        utt_split=0.8,
    )

    utterances = getattr(response.results, "utterances", None) or []

    if not utterances:
        # フォールバック: channelsからwordsを取得してセグメント化
        channels = getattr(response.results, "channels", None) or []
        if not channels:
            raise RuntimeError("文字起こし結果が空です")

        words = channels[0].alternatives[0].words or []
        utterances = group_words_into_segments(
            [{"word": w.word, "start": w.start, "end": w.end} for w in words]
        )
        print(f"文字起こし完了（wordsから生成）: {len(utterances)} セグメント")
        return utterances

    result = [
        {
            "start": u.start,
            "end": u.end,
            "transcript": u.transcript,
        }
        for u in utterances
        if u.transcript
    ]
    print(f"文字起こし完了: {len(result)} セグメント")
    return result


def group_words_into_segments(
    words: list[dict],
    max_words: int = 12,
    max_duration: float = 5.0,
) -> list[dict]:
    """単語リストを字幕セグメントにグループ化する。"""
    if not words:
        return []

    segments = []
    current_words = []
    seg_start = words[0]["start"]

    for idx, word in enumerate(words):
        current_words.append(word)
        duration = word["end"] - seg_start

        if len(current_words) >= max_words or duration >= max_duration:
            text = " ".join(w["word"] for w in current_words)
            segments.append({
                "start": seg_start,
                "end": word["end"],
                "transcript": text,
            })
            current_words = []
            if idx + 1 < len(words):
                seg_start = words[idx + 1]["start"]

    if current_words:
        text = " ".join(w["word"] for w in current_words)
        segments.append({
            "start": seg_start,
            "end": current_words[-1]["end"],
            "transcript": text,
        })

    return segments


# merge_incomplete_utterances はマイクのリアルタイム翻訳（pipeline.py の
# StreamingUtteranceMerger）と同じアルゴリズムを共有する（transcription/utterance_merge.py）。
from real_time_translation.transcription.utterance_merge import (
    merge_incomplete_utterances,
)


async def translate_segments(utterances: list[dict]) -> tuple[list[dict], dict]:
    """マイクのリアルタイム翻訳と同じ LLMTranslator パイプラインで各セグメントを翻訳する。

    文脈窓・ドメイン別プロンプトを共有し、オフライン処理なので
    thinking_budget=1024 で精度を優先する（gradio_demo.py の
    _video_translate_with_pipeline と同じ設定）。

    戻り値は (翻訳済みセグメント一覧, レポート) のタプル。レポートには
    LLM使用量サマリ・要確認セグメント件数・用語漏れ一覧を含む。
    """
    from real_time_translation.translation.completeness_check import CompletenessTracker
    from real_time_translation.translation.llm_translator import LLMTranslator
    from real_time_translation.translation.terminology_check import (
        check_terminology,
        format_terminology_misses,
    )
    from real_time_translation.translation.usage_tracking import UsageSink

    print("Geminiで日本語翻訳中...")
    usage_sink = UsageSink()
    translator = LLMTranslator(
        provider="gemini",
        api_key=GOOGLE_API_KEY,
        model=GEMINI_MODEL,
        source_language=_LANGUAGE_NAMES.get(SOURCE_LANGUAGE, "English"),
        target_language="Japanese",
        domain=TRANSLATION_DOMAIN,
        context_window_size=5,
        thinking_budget=1024,
        dictionary_path=DICTIONARY_PATH,
        usage_sink=usage_sink,
    )
    completeness_tracker = CompletenessTracker(
        ratio_threshold=COMPLETENESS_RATIO_THRESHOLD
    )

    translated = []
    total = len(utterances)
    flagged_count = 0

    for i, u in enumerate(utterances):
        output = await translator.translate(u["transcript"])

        review_flag = None
        if COMPLETENESS_CHECK_ENABLED:
            flag = completeness_tracker.check(u["transcript"], output.latest_slide)
            if flag is not None:
                review_flag = flag.flag
                flagged_count += 1
                print(f"  ⚠️ 要確認（{flag.flag}）: {u['transcript'][:60]}")

        translated.append({
            "start": u["start"],
            "end": u["end"],
            "original": u["transcript"],
            "japanese": output.latest_slide,
            "review_flag": review_flag,
        })
        print(f"  翻訳済み: {i + 1}/{total}")

    print("翻訳完了")

    terminology_result = check_terminology(
        [(seg["original"], seg["japanese"]) for seg in translated],
        translator.dictionary,
    )
    print(f"  {usage_sink.summary_text()}")
    print(f"  {format_terminology_misses(terminology_result.misses)}")
    if flagged_count:
        print(f"  ⚠️ 要確認セグメント: {flagged_count}/{total}件")

    report = {
        "usage_summary": usage_sink.summary_text(),
        "usage_calls": sum(a.calls for a in usage_sink.aggregate_by_model()),
        "usage_prompt_tokens": sum(
            a.prompt_tokens for a in usage_sink.aggregate_by_model()
        ),
        "usage_completion_tokens": sum(
            a.completion_tokens for a in usage_sink.aggregate_by_model()
        ),
        "flagged_count": flagged_count,
        "terminology_misses": [
            f"{m.source_term}→{m.target_term}" for m in terminology_result.misses
        ],
    }
    return translated, report


def seconds_to_srt_time(seconds: float) -> str:
    """秒数をSRT時間形式（HH:MM:SS,mmm）に変換する。"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def create_srt(translated: list[dict], srt_path: str) -> None:
    """SRT字幕ファイル（日本語のみ、動画への焼き込み用）を生成する。"""
    print(f"SRTファイル生成中: {srt_path}")
    lines = []
    for i, seg in enumerate(translated, 1):
        start = seconds_to_srt_time(seg["start"])
        end = seconds_to_srt_time(seg["end"])
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(seg["japanese"])
        lines.append("")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("SRTファイル生成完了")


def create_bilingual_srt(translated: list[dict], srt_path: str) -> None:
    """英語原文と日本語訳を1ブロックに並記したSRTファイルを生成する（translated_script/保存用）。"""
    print(f"英日併記SRTファイル生成中: {srt_path}")
    lines = []
    for i, seg in enumerate(translated, 1):
        start = seconds_to_srt_time(seg["start"])
        end = seconds_to_srt_time(seg["end"])
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(seg["original"])
        lines.append(seg["japanese"])
        lines.append("")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("英日併記SRTファイル生成完了")


def burn_subtitles(video_path: str, srt_path: str, output_path: str) -> None:
    """ffmpegで字幕を動画に焼き込む。"""
    print(f"字幕を焼き込み中 → {output_path}")

    # Windows: パスのコロンをエスケープ（ffmpegのsubstitlesフィルタ用）
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf",
            f"subtitles='{srt_escaped}':force_style='FontName=Arial Unicode MS,FontSize=20,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Alignment=2'",
            "-c:a", "copy",
            output_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"字幕焼き込みに失敗しました:\n{result.stderr}")
    print("字幕焼き込み完了")


async def main(video_path: str) -> None:
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        print(f"エラー: ファイルが見つかりません: {video_path}")
        sys.exit(1)

    output_dir = video_path.parent
    stem = video_path.stem
    TRANSLATED_SCRIPT_DIR.mkdir(exist_ok=True)
    srt_path = str(TRANSLATED_SCRIPT_DIR / f"{stem}_ja.srt")
    output_path = str(output_dir / f"{stem}_subtitled.mp4")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
        burn_srt_path = tmp.name

    try:
        # 1. 音声抽出
        extract_audio(str(video_path), audio_path)

        # 2. 文字起こし
        utterances = await asyncio.to_thread(transcribe_audio_with_provider, audio_path)

        if MERGE_UTTERANCES:
            before = len(utterances)
            if INCOMPLETE_END_DETECTION_ENABLED:
                from real_time_translation.config import Config as _Config
                from real_time_translation.transcription.utterance_merge import (
                    DEFAULT_MAX_DURATION,
                    DEFAULT_MAX_WORDS,
                    merge_incomplete_utterances_with_detector,
                )

                detector_config = _Config(
                    deepgram_api_key=DEEPGRAM_API_KEY,
                    llm_provider="gemini",
                    zoom_client_id="",
                    zoom_client_secret="",
                    google_api_key=GOOGLE_API_KEY,
                    gemini_model=GEMINI_MODEL,
                    incomplete_end_detection_model=INCOMPLETE_END_DETECTION_MODEL,
                    utterance_merge_max_duration=DEFAULT_MAX_DURATION,
                    utterance_merge_max_words=DEFAULT_MAX_WORDS,
                )
                utterances = await merge_incomplete_utterances_with_detector(
                    utterances, detector_config
                )
            else:
                utterances = merge_incomplete_utterances(utterances)
            print(f"utterance結合: {before} → {len(utterances)} セグメント")

        if not utterances:
            print("文字起こし結果が空です。動画に音声が含まれているか確認してください。")
            sys.exit(1)

        # 3. 翻訳
        translated, report = await translate_segments(utterances)

        # 原文・訳文・タイムスタンプの生データを保存
        # （経験的に、集計スコアだけ残すと後からベンチマークデータを作れなくなるため）
        save_segments(translated, video_path, report)

        # 4. SRT生成（動画焼き込み用は日本語のみ、translated_script/保存用は英日併記）
        create_srt(translated, burn_srt_path)
        create_bilingual_srt(translated, srt_path)
        print(f"\nSRTファイル（英日併記）: {srt_path}")

        # プレビュー
        print("\n--- 字幕プレビュー（最初の5件） ---")
        for seg in translated[:5]:
            print(f"[{seconds_to_srt_time(seg['start'])}] {seg['original']}")
            print(f"  → {seg['japanese']}")
        print("---\n")

        # 5. 字幕焼き込み（日本語のみ）
        burn_subtitles(str(video_path), burn_srt_path, output_path)

        print(f"\n完了!")
        print(f"字幕付き動画: {output_path}")
        print(f"SRTファイル（英日併記）: {srt_path}")

        # 6. 自動評価スコアを計算して実験記録を保存
        xcomet_score, chrf_score = await compute_scores(translated)
        save_experiment_record(
            translated, video_path, xcomet_score, chrf_score, report=report
        )

    finally:
        if os.path.exists(audio_path):
            os.unlink(audio_path)
        if os.path.exists(burn_srt_path):
            os.unlink(burn_srt_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        video = r"C:\Users\yagua\OneDrive\Desktop\index.mp4"
    else:
        video = sys.argv[1]

    asyncio.run(main(video))
