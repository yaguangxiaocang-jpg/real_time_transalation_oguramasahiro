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
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]
GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
SOURCE_LANGUAGE = os.environ.get("SOURCE_LANGUAGE", "en")
TRANSLATION_DOMAIN = os.environ.get("TRANSLATION_DOMAIN", "general")
GEMINI_MODEL = "gemini-2.5-flash"

EXPERIMENTS_DIR = Path(__file__).parent / "experiments"


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
) -> None:
    """実験結果をexperimentsフォルダに保存する。"""
    EXPERIMENTS_DIR.mkdir(exist_ok=True)

    today = date.today().strftime("%Y%m%d")
    model_slug = GEMINI_MODEL.replace("-", "_").replace(".", "")
    json_name = f"{today}_{model_slug}_{TRANSLATION_DOMAIN}.json"
    json_path = EXPERIMENTS_DIR / json_name

    auto_notes = (
        f"{video_path.name} を処理。{len(translated)} セグメント翻訳。"
        + (f" {notes}" if notes else "")
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


async def translate_segments(utterances: list[dict]) -> list[dict]:
    """Geminiで各セグメントを日本語に翻訳する。"""
    from google import genai
    from google.genai import types

    print("Geminiで日本語翻訳中...")
    client = genai.Client(api_key=GOOGLE_API_KEY)

    translated = []
    total = len(utterances)

    batch_size = 10
    for i in range(0, total, batch_size):
        batch = utterances[i : i + batch_size]
        texts = [u["transcript"] for u in batch]

        numbered = "\n".join(f"{j+1}. {t}" for j, t in enumerate(texts))
        prompt = (
            "あなたはプロの翻訳者です。"
            "以下の英語テキストをそれぞれ自然な日本語に翻訳してください。"
            "字幕として表示されるため、簡潔で読みやすい文にしてください。"
            "番号付きリストで返してください（例: 1. 翻訳文）。説明や原文は含めないでください。\n\n"
            f"{numbered}"
        )

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw_text = response.text if response.text else ""
        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]

        ja_texts = []
        for line in lines:
            if line and line[0].isdigit() and ". " in line:
                ja_texts.append(line.split(". ", 1)[1])
            elif line and line[0].isdigit() and "." in line:
                ja_texts.append(line.split(".", 1)[1].strip())
            else:
                ja_texts.append(line)

        # 不足分は原文で補完
        while len(ja_texts) < len(batch):
            ja_texts.append(batch[len(ja_texts)]["transcript"])

        for u, ja in zip(batch, ja_texts):
            translated.append({
                "start": u["start"],
                "end": u["end"],
                "original": u["transcript"],
                "japanese": ja,
            })

        print(f"  翻訳済み: {min(i + batch_size, total)}/{total}")

    print("翻訳完了")
    return translated


def seconds_to_srt_time(seconds: float) -> str:
    """秒数をSRT時間形式（HH:MM:SS,mmm）に変換する。"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def create_srt(translated: list[dict], srt_path: str) -> None:
    """SRT字幕ファイルを生成する。"""
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
    srt_path = str(output_dir / f"{stem}_ja.srt")
    output_path = str(output_dir / f"{stem}_subtitled.mp4")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name

    try:
        # 1. 音声抽出
        extract_audio(str(video_path), audio_path)

        # 2. 文字起こし
        utterances = await asyncio.to_thread(transcribe_audio, audio_path)

        if not utterances:
            print("文字起こし結果が空です。動画に音声が含まれているか確認してください。")
            sys.exit(1)

        # 3. 翻訳
        translated = await translate_segments(utterances)

        # 4. SRT生成
        create_srt(translated, srt_path)
        print(f"\nSRTファイル: {srt_path}")

        # プレビュー
        print("\n--- 字幕プレビュー（最初の5件） ---")
        for seg in translated[:5]:
            print(f"[{seconds_to_srt_time(seg['start'])}] {seg['original']}")
            print(f"  → {seg['japanese']}")
        print("---\n")

        # 5. 字幕焼き込み
        burn_subtitles(str(video_path), srt_path, output_path)

        print(f"\n完了!")
        print(f"字幕付き動画: {output_path}")
        print(f"SRTファイル:  {srt_path}")

        # 6. 自動評価スコアを計算して実験記録を保存
        xcomet_score, chrf_score = await compute_scores(translated)
        save_experiment_record(translated, video_path, xcomet_score, chrf_score)

    finally:
        if os.path.exists(audio_path):
            os.unlink(audio_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        video = r"C:\Users\yagua\OneDrive\Desktop\index.mp4"
    else:
        video = sys.argv[1]

    asyncio.run(main(video))
