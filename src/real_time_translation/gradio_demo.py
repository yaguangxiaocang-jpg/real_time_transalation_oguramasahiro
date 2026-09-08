"""Gradio demo for real-time ASR + MT."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import random
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


async def _gemini_generate_with_retry(client: Any, model: str, contents: Any, max_retries: int = 5) -> Any:
    """503/429 エラー時に指数バックオフでリトライしながら Gemini API を呼ぶ。"""
    for attempt in range(max_retries):
        try:
            return await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=contents,
            )
        except Exception as e:
            err_str = str(e)
            if attempt < max_retries - 1 and ("503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str or "ResourceExhausted" in err_str):
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning("Gemini API error (%s), retrying in %.1fs (attempt %d/%d)", e, wait, attempt + 1, max_retries)
                await asyncio.sleep(wait)
            else:
                raise

import audioop
import gradio as gr
import numpy as np

from real_time_translation.audio.capture import QueueAudioCapture
from real_time_translation.config import Config
from real_time_translation.pipeline import TranslationPipeline, TranslationResult

TARGET_SAMPLE_RATE = 16000
MAX_DISPLAY_LINES = 50

# 動画字幕タブ（本番エントリーポイント）向けの設定。add_subtitles.py（実験用CLI）と
# 同じ環境変数を読む。以前はここに utterance 結合・辞書配線が一切なく、
# add_subtitles.py だけの機能になっていたため合わせて追加した。
VIDEO_MERGE_UTTERANCES = os.environ.get("MERGE_UTTERANCES", "true").lower() == "true"
VIDEO_DICTIONARY_PATH = os.environ.get("DICTIONARY_PATH") or None
VIDEO_INCOMPLETE_END_DETECTION_ENABLED = (
    os.environ.get("INCOMPLETE_END_DETECTION_ENABLED", "true").lower() == "true"
)
VIDEO_COMPLETENESS_CHECK_ENABLED = (
    os.environ.get("COMPLETENESS_CHECK_ENABLED", "true").lower() == "true"
)
VIDEO_COMPLETENESS_RATIO_THRESHOLD = float(
    os.environ.get("COMPLETENESS_RATIO_THRESHOLD", "0.5")
)
# Deepgramキーワードブースト（ASR誤認識自体を減らす根本対策）。pipeline.py
# （マイク側）には配線済みだったが、動画字幕タブ（_video_transcribe()）には
# 配線されていなかったため追加（2026-09-08、add_subtitles.pyと同じ修正）。
VIDEO_DEEPGRAM_KEYWORD_BOOST_ENABLED = (
    os.environ.get("DEEPGRAM_KEYWORD_BOOST_ENABLED", "true").lower() == "true"
)
VIDEO_DEEPGRAM_KEYWORD_BOOST_VALUE = float(
    os.environ.get("DEEPGRAM_KEYWORD_BOOST_VALUE", "2.0")
)

# Language options: list of (display name, language code)
LANGUAGE_OPTIONS: list[tuple[str, str]] = [
    ("English", "en"),
    ("Japanese (日本語)", "ja"),
    ("Chinese (中文)", "zh"),
    ("Korean (한국어)", "ko"),
    ("Spanish (Español)", "es"),
    ("French (Français)", "fr"),
    ("German (Deutsch)", "de"),
]
_LANG_CHOICES = [name for name, _ in LANGUAGE_OPTIONS]
_LANG_CODE: dict[str, str] = {name: code for name, code in LANGUAGE_OPTIONS}
_FULL_NAME: dict[str, str] = {
    "en": "English",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}


def _to_code(display_name: str) -> str:
    """Convert display name to language code."""
    return _LANG_CODE.get(display_name, "en")


def _to_full_name(code: str) -> str:
    """Convert language code to full English name for LLM prompts."""
    return _FULL_NAME.get(code, code)


@dataclass
class DemoSession:
    """Per-user demo session state."""

    pipeline: TranslationPipeline
    capture: QueueAudioCapture
    results_queue: asyncio.Queue[TranslationResult]
    window_size: int
    transcript_lines: list[str] = field(default_factory=list)
    translation_lines: list[str] = field(default_factory=list)
    interim_transcript: str = ""  # Current interim transcript
    cancel_requested: bool = False  # Flag to cancel file processing
    recent_delays: list[float] = field(default_factory=list)  # Last N translation delays (seconds)
    latest_delay: float = 0.0  # Most recent ASR→translation latency (seconds)


def _status(message: str) -> str:
    return f"Status: {message}"


def _delay_display(latest_delay: float, avg_delay: float, pending: int) -> str:
    if avg_delay <= 0:
        return "⏱ 音声認識→和訳: 計測中..."
    if avg_delay < 2.0:
        icon = "🟢"
        label = "良好"
    elif avg_delay < 5.0:
        icon = "🟡"
        label = "やや遅延"
    else:
        icon = "🔴"
        label = "遅延大"
    bar_filled = min(10, int(avg_delay / 10 * 10))
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    latest_str = f"{latest_delay:.2f}秒" if latest_delay > 0 else "-"
    return (
        f"{icon} **音声認識→和訳: 最新 {latest_str} / 平均 {avg_delay:.1f}秒** ({label})　"
        f"`{bar}`　翻訳待ち: **{pending}件**"
    )


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _usage_line(pipeline: TranslationPipeline) -> str:
    """LLM使用量とGemini無料枠のレート制限への近さを1行で表示する。"""
    status = pipeline.usage_status()
    line = f"📊 {pipeline.usage_summary_text()}"
    if status.near_limit:
        line += (
            f"　⚠️ 直近1分で{status.calls_last_60s}回呼び出し"
            f"（無料枠目安 {status.limit}回/分 に接近。"
            "しばらく待つとエラーを回避できます）"
        )
    return line


def _convert_file_to_pcm(file_path: str) -> bytes:
    """Convert any audio file to 16kHz mono PCM using ffmpeg."""
    import os
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-i", file_path,
        "-f", "s16le",
        "-ar", "16000",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr.decode()}")
    return result.stdout


def _normalize_audio_chunk(chunk: Any) -> bytes | None:
    if chunk is None:
        return None

    if isinstance(chunk, tuple) and len(chunk) == 2:
        sample_rate, data = chunk
    else:
        return None

    if data is None:
        return None

    if isinstance(data, np.ndarray):
        if data.ndim > 1:
            data = data.mean(axis=1)

        if np.issubdtype(data.dtype, np.integer):
            max_val = np.iinfo(data.dtype).max
            if max_val:
                data = data.astype(np.float32) / max_val

        if data.dtype != np.float32:
            data = data.astype(np.float32)

        data = np.clip(data, -1.0, 1.0)
        data = (data * 32767).astype(np.int16)
        pcm = data.tobytes()
    else:
        return None

    if sample_rate != TARGET_SAMPLE_RATE:
        try:
            if not isinstance(sample_rate, (int, float)):
                return None
            pcm, _ = audioop.ratecv(
                pcm, 2, 1, int(sample_rate), TARGET_SAMPLE_RATE, None
            )
        except Exception:
            return None

    return pcm


async def start_session(
    state: DemoSession | None,
    deepgram_key: str = "",
    google_key: str = "",
    source_lang: str = "English",
    target_lang: str = "Japanese (日本語)",
    domain: str = "general",
) -> tuple[DemoSession | None, str, str, str]:
    if state is not None:
        transcript = "\n".join(state.transcript_lines)
        translation = "\n".join(state.translation_lines)
        return state, _status("running"), transcript, translation

    source_code = _to_code(source_lang)
    target_code = _to_code(target_lang)

    try:
        if deepgram_key.strip() and google_key.strip():
            config = Config(
                deepgram_api_key=deepgram_key.strip(),
                llm_provider="gemini",
                zoom_client_id="",
                zoom_client_secret="",
                google_api_key=google_key.strip(),
                source_language=source_code,
                target_language=target_code,
                domain=domain,
            )
        else:
            config = Config.from_env(require_zoom=False)
            config = Config(
                deepgram_api_key=config.deepgram_api_key,
                llm_provider=config.llm_provider,
                zoom_client_id=config.zoom_client_id,
                zoom_client_secret=config.zoom_client_secret,
                google_api_key=config.google_api_key,
                openai_api_key=config.openai_api_key,
                gemini_model=config.gemini_model,
                openai_model=config.openai_model,
                source_language=source_code,
                target_language=target_code,
                context_window_size=config.context_window_size,
                translation_queue_size=config.translation_queue_size,
                dictionary_path=config.dictionary_path,
                domain=domain,
            )
    except Exception as exc:
        return None, _status(f"error: {exc}"), "", ""

    capture = QueueAudioCapture()
    pipeline = TranslationPipeline(config=config, audio_capture=capture)
    results_queue: asyncio.Queue[TranslationResult] = asyncio.Queue(
        maxsize=200  # Larger queue for file processing
    )

    def on_result(result: TranslationResult) -> None:
        timestamp = _timestamp()
        print(f"[{timestamp}] ASR: {result.original_text}")
        print(f"[{timestamp}] MT: {result.translated_text}")
        if result.kept_terms:
            kept = ", ".join(result.kept_terms)
            print(f"[{timestamp}] Kept terms: {kept}")
        if result.review_flag:
            print(
                f"[{timestamp}] ⚠️ 要確認 ({result.review_flag}): "
                f"{result.translated_text}"
            )
        with contextlib.suppress(asyncio.QueueFull):
            results_queue.put_nowait(result)

    pipeline.set_callback(on_result)
    try:
        await pipeline.start()
    except Exception as exc:
        with contextlib.suppress(Exception):
            await pipeline.stop()
        return None, _status(f"error: {exc}"), "", ""

    return (
        DemoSession(
            pipeline=pipeline,
            capture=capture,
            results_queue=results_queue,
            window_size=config.context_window_size,
        ),
        _status("running"),
        "",
        "",
    )


async def stop_session(state: DemoSession | None) -> tuple[DemoSession | None, str, str]:
    if state is None:
        return None, _status("stopped"), "⏱ 音声認識→和訳: -"

    from real_time_translation.translation.terminology_check import (
        format_terminology_misses,
    )

    usage_line = _usage_line(state.pipeline)
    terminology_line = format_terminology_misses(state.pipeline.terminology_report().misses)

    await state.pipeline.stop()
    summary = f"⏱ 音声認識→和訳: -\n\n{usage_line}\n\n{terminology_line}"
    return None, _status("stopped"), summary


async def clear_logs(state: DemoSession | None) -> tuple[str, str]:
    if state is None:
        return "", ""

    state.transcript_lines.clear()
    state.translation_lines.clear()
    state.pipeline.clear_context()
    return "", ""


def cancel_processing(state: DemoSession | None) -> tuple[DemoSession | None, str]:
    """Cancel ongoing file processing."""
    if state is None:
        return None, _status("stopped")

    state.cancel_requested = True
    return state, _status("Cancelling...")


async def process_audio_file(
    file_path: str | None,
    state: DemoSession | None,
    deepgram_key: str = "",
    google_key: str = "",
    source_lang: str = "English",
    target_lang: str = "Japanese (日本語)",
    domain: str = "general",
) -> tuple[DemoSession | None, str, str, str]:
    """Process an uploaded audio file through the pipeline."""
    if file_path is None:
        return state, _status("No file selected"), "", ""

    # Start session if not already running
    if state is None:
        state, status, _, _ = await start_session(
            None, deepgram_key, google_key, source_lang, target_lang, domain
        )
        if state is None:
            return None, status, "", ""

    # Clear previous results
    state.transcript_lines.clear()
    state.translation_lines.clear()
    state.interim_transcript = ""

    try:
        audio_data = _convert_file_to_pcm(file_path)
        duration = len(audio_data) / (16000 * 2)
    except Exception as e:
        return state, _status(f"Error: {e}"), "", ""

    # Reset cancel flag
    state.cancel_requested = False

    # Stream audio in chunks
    chunk_size = 16000 * 2  # 1 second of audio

    for offset in range(0, len(audio_data), chunk_size):
        if state.cancel_requested:
            break

        chunk = audio_data[offset : offset + chunk_size]
        state.capture.push_audio(chunk)

        # Sleep in shorter intervals to respond more quickly to cancellation
        for _ in range(5):  # 5 x 0.1s = 0.5s total
            if state.cancel_requested:
                break
            await asyncio.sleep(0.1)

        # Drain results queue periodically
        while True:
            try:
                result = state.results_queue.get_nowait()
                if result.is_final and result.translated_text:
                    state.transcript_lines.append(result.original_text)
                    state.translation_lines.append(result.translated_text)
            except asyncio.QueueEmpty:
                break

    if state.cancel_requested:
        transcript = "\n".join(state.transcript_lines)
        translation = "\n".join(state.translation_lines)
        return state, _status("Cancelled"), transcript, translation

    # Wait longer for processing to complete (based on audio duration)
    # Base time of 5 seconds plus 20% of audio duration, minimum 10 seconds
    wait_seconds = max(10, 5 + int(duration * 0.2))

    last_count = 0
    stable_count = 0
    for i in range(wait_seconds * 10):  # Check every 0.1 seconds
        if state.cancel_requested:
            break

        await asyncio.sleep(0.1)

        # Drain results queue
        while True:
            try:
                result = state.results_queue.get_nowait()
                if result.is_final and result.translated_text:
                    state.transcript_lines.append(result.original_text)
                    state.translation_lines.append(result.translated_text)
            except asyncio.QueueEmpty:
                break

        # Check if results have stabilized
        current_count = len(state.transcript_lines)
        if current_count == last_count:
            stable_count += 1
            if stable_count > 30:  # No new results for 3 seconds
                break
        else:
            stable_count = 0
            last_count = current_count

    transcript = "\n".join(state.transcript_lines)
    translation = "\n".join(state.translation_lines)

    if state.cancel_requested:
        status_text = f"Cancelled ({len(state.transcript_lines)} segments)"
    else:
        status_text = f"Done ({len(state.transcript_lines)} segments)"

    return state, _status(status_text), transcript, translation


async def handle_audio(chunk: Any, state: DemoSession | None) -> tuple[str, str, str, str]:
    if state is None:
        return "", "", _status("click Start to initialize"), "⏱ 音声認識→和訳: -"

    audio_bytes = _normalize_audio_chunk(chunk)
    if audio_bytes:
        state.capture.push_audio(audio_bytes)

    latest_slide_window: list[str] | None = None
    while True:
        try:
            result = state.results_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        if not result.is_final:
            # Update interim transcript (shown in real-time)
            state.interim_transcript = result.original_text
            continue

        # Final result - add to history and clear interim
        translated_display = (
            f"⚠️ {result.translated_text}" if result.review_flag else result.translated_text
        )
        state.transcript_lines.append(result.original_text)
        state.translation_lines.append(translated_display)
        state.interim_transcript = ""
        if result.slide_window:
            latest_slide_window = result.slide_window
        if result.translation_delay > 0:
            state.latest_delay = result.translation_delay
            state.recent_delays.append(result.translation_delay)
            if len(state.recent_delays) > 10:
                state.recent_delays.pop(0)

        if len(state.transcript_lines) > MAX_DISPLAY_LINES:
            state.transcript_lines = state.transcript_lines[-MAX_DISPLAY_LINES:]
        if len(state.translation_lines) > MAX_DISPLAY_LINES:
            state.translation_lines = state.translation_lines[-MAX_DISPLAY_LINES:]

    # Show finalized lines + current interim transcript
    finalized = "\n".join(state.transcript_lines[-state.window_size :])
    if state.interim_transcript:
        interim_display = f"[interim] {state.interim_transcript}"
        transcript = f"{finalized}\n{interim_display}" if finalized else interim_display
    else:
        transcript = finalized

    if latest_slide_window is not None:
        translation = "\n".join(latest_slide_window)
    else:
        translation = "\n".join(state.translation_lines[-state.window_size :])

    avg_delay = sum(state.recent_delays) / len(state.recent_delays) if state.recent_delays else 0.0
    pending = state.pipeline.pending_count
    delay_text = _delay_display(state.latest_delay, avg_delay, pending)
    delay_text += "\n\n" + _usage_line(state.pipeline)

    return transcript, translation, _status("running"), delay_text


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def export_as_txt(state: DemoSession | None) -> str | None:
    """Export transcript and translation as a paired TXT file."""
    if state is None or not state.transcript_lines:
        return None

    lines: list[str] = []
    for orig, trans in zip(state.transcript_lines, state.translation_lines):
        lines.append(f"[Original]    {orig}")
        lines.append(f"[Translation] {trans}")
        lines.append("")

    content = "\n".join(lines)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        delete=False,
        encoding="utf-8",
        prefix="translation_export_",
    )
    tmp.write(content)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# Video subtitle helpers (adapted from add_subtitles.py)
# ---------------------------------------------------------------------------

def _video_extract_audio(video_path: str, audio_path: str) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ar", "16000", "-ac", "1", "-f", "wav", audio_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg音声抽出エラー:\n{result.stderr[-500:]}")


def _video_load_deepgram_keywords() -> list[str]:
    """辞書の「そのまま使う」用語をDeepgramキーワードブースト形式に変換する。

    `pipeline.py`（マイク側）・`add_subtitles.py`と同じ
    `TermDictionary.as_asr_keywords()`を使う。辞書未設定・読み込み失敗時は
    キーワードブーストなしで継続する。
    """
    if not VIDEO_DEEPGRAM_KEYWORD_BOOST_ENABLED or not VIDEO_DICTIONARY_PATH:
        return []
    from real_time_translation.translation.dictionary import TermDictionary

    try:
        dictionary = TermDictionary()
        dictionary.load_csv(VIDEO_DICTIONARY_PATH)
        return dictionary.as_asr_keywords(boost=VIDEO_DEEPGRAM_KEYWORD_BOOST_VALUE)
    except OSError:
        return []


def _video_transcribe(audio_path: str, api_key: str, source_language: str = "en") -> list[dict]:
    from deepgram import DeepgramClient

    client = DeepgramClient(api_key=api_key)
    with open(audio_path, "rb") as f:
        audio_data = f.read()

    deepgram_keywords = _video_load_deepgram_keywords()

    response = client.listen.v1.media.transcribe_file(
        request=audio_data,
        model="nova-2-general",
        language=source_language,
        smart_format=True,
        punctuate=True,
        utterances=True,
        utt_split=0.8,
        keywords=deepgram_keywords or None,
    )
    utterances = getattr(response.results, "utterances", None) or []
    if not utterances:
        channels = getattr(response.results, "channels", None) or []
        if not channels:
            raise RuntimeError("文字起こし結果が空です")
        words = channels[0].alternatives[0].words or []
        return _group_words(
            [{"word": w.word, "start": w.start, "end": w.end} for w in words]
        )
    return [
        {"start": u.start, "end": u.end, "transcript": u.transcript}
        for u in utterances
        if u.transcript
    ]


def _group_words(words: list[dict], max_words: int = 12, max_duration: float = 5.0) -> list[dict]:
    if not words:
        return []
    segments: list[dict] = []
    current: list[dict] = []
    seg_start = words[0]["start"]
    for idx, word in enumerate(words):
        current.append(word)
        if len(current) >= max_words or (word["end"] - seg_start) >= max_duration:
            segments.append({"start": seg_start, "end": word["end"],
                              "transcript": " ".join(w["word"] for w in current)})
            current = []
            if idx + 1 < len(words):
                seg_start = words[idx + 1]["start"]
    if current:
        segments.append({"start": seg_start, "end": current[-1]["end"],
                          "transcript": " ".join(w["word"] for w in current)})
    return segments


async def _video_translate_with_pipeline(
    utterances: list[dict],
    api_key: str,
    source_language: str = "en",
    target_language: str = "ja",
    domain: str = "general",
    on_progress=None,  # callback(utt_idx, total)
    dictionary_path: str | None = None,
) -> tuple[list[dict], dict]:
    """Translate video utterances using the same LLMTranslator pipeline as microphone mode.

    Uses context window, domain-aware system prompt, and thinking_budget=1024
    for higher accuracy in offline (non-realtime) processing.

    Returns (translated_segments, report). `report` carries LLM usage summary,
    the count of segments flagged for review, and terminology dictionary misses
    (see `translation.completeness_check` / `translation.terminology_check`).
    """
    from real_time_translation.translation.completeness_check import CompletenessTracker
    from real_time_translation.translation.llm_translator import LLMTranslator
    from real_time_translation.translation.terminology_check import check_terminology
    from real_time_translation.translation.usage_tracking import UsageSink

    usage_sink = UsageSink()
    translator = LLMTranslator(
        provider="gemini",
        api_key=api_key,
        model="gemini-2.5-flash",
        source_language=_to_full_name(source_language),
        target_language=_to_full_name(target_language),
        domain=domain,
        context_window_size=5,
        thinking_budget=1024,
        dictionary_path=dictionary_path,
        usage_sink=usage_sink,
    )
    completeness_tracker = CompletenessTracker(
        ratio_threshold=VIDEO_COMPLETENESS_RATIO_THRESHOLD
    )

    translated: list[dict] = []
    total = len(utterances)
    flagged_count = 0
    for i, utt in enumerate(utterances):
        if on_progress:
            on_progress(i, total)
        output = await translator.translate(utt["transcript"])

        review_flag = None
        if VIDEO_COMPLETENESS_CHECK_ENABLED:
            flag = completeness_tracker.check(utt["transcript"], output.latest_slide)
            if flag is not None:
                review_flag = flag.flag
                flagged_count += 1

        translated.append({
            "start": utt["start"],
            "end": utt["end"],
            "original": utt["transcript"],
            "japanese": output.latest_slide,
            "review_flag": review_flag,
        })

    terminology_result = check_terminology(
        [(seg["original"], seg["japanese"]) for seg in translated],
        translator.dictionary,
    )
    report = {
        "usage_summary": usage_sink.summary_text(),
        "flagged_count": flagged_count,
        "terminology_misses": [
            f"{m.source_term}→{m.target_term}" for m in terminology_result.misses
        ],
    }
    return translated, report


def _seconds_to_srt(s: float) -> str:
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    ms = int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def _video_create_srt(translated: list[dict], srt_path: str) -> None:
    lines: list[str] = []
    for i, seg in enumerate(translated, 1):
        lines += [str(i), f"{_seconds_to_srt(seg['start'])} --> {_seconds_to_srt(seg['end'])}",
                  seg["japanese"], ""]
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _pick_cjk_font() -> str:
    """Return a CJK-capable font name available on the current OS."""
    import platform
    if platform.system() == "Windows":
        # Yu Gothic is bundled with Windows 8.1+; fall back to Meiryo UI
        import subprocess as _sp
        for font in ("Yu Gothic", "Meiryo UI", "MS Gothic"):
            try:
                out = _sp.run(
                    ["fc-list", f":family={font}"],
                    capture_output=True, text=True,
                )
                if out.stdout.strip():
                    return font
            except FileNotFoundError:
                pass
        return "Yu Gothic"
    # Linux / macOS
    return "Noto Sans CJK JP"


def _video_burn_subtitles(video_path: str, srt_path: str, output_path: str) -> None:
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    font_name = _pick_cjk_font()
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path, "-vf",
            f"subtitles='{srt_escaped}':charenc=UTF-8:force_style='FontName={font_name},FontSize=20,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Alignment=2'",
            "-c:a", "copy", output_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"字幕焼き込みエラー:\n{result.stderr[-500:]}")


async def _compute_scores(translated: list[dict], google_key: str) -> tuple[float | None, float | None]:
    """xCOMET（LLM-as-judge）と chrF（逆翻訳）スコアを計算する。"""
    import re
    from google import genai

    client = genai.Client(api_key=google_key)
    sample = translated[:20]
    srcs = [s["original"] for s in sample]
    mts = [s["japanese"] for s in sample]

    # xcomet_score: LLM-as-judge
    judge_prompt = (
        "あなたはプロの翻訳評価者です。以下の英日翻訳ペアをそれぞれ評価し、"
        "翻訳品質を0.00〜1.00のスコアで採点してください。"
        "番号付きリストで数値のみ返してください（例: 1. 0.85）。\n\n"
        + "\n".join(f"{i+1}. EN: {s}\n   JA: {m}" for i, (s, m) in enumerate(zip(srcs, mts)))
    )
    judge_resp = await _gemini_generate_with_retry(client, "gemini-2.5-flash", judge_prompt)
    xcomet_score: float | None = None
    scores = []
    for line in (judge_resp.text or "").split("\n"):
        m = re.match(r"\d+\.\s*([\d.]+)", line.strip())
        if m:
            try:
                scores.append(float(m.group(1)))
            except ValueError:
                pass
    if scores:
        xcomet_score = round(sum(scores) / len(scores), 4)

    # chrf_score: 逆翻訳 + sacrebleu
    back_prompt = (
        "Translate the following Japanese sentences back to English. "
        "Return only the translations as a numbered list (e.g. 1. text). "
        "Do not include explanations.\n\n"
        + "\n".join(f"{i+1}. {m}" for i, m in enumerate(mts))
    )
    back_resp = await _gemini_generate_with_retry(client, "gemini-2.5-flash", back_prompt)
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

    return xcomet_score, chrf_score


async def process_video(
    video_path: str | None,
    domain: str,
    deepgram_key: str = "",
    google_key: str = "",
    evaluate_scores: bool = False,
    source_lang: str = "English",
    target_lang: str = "Japanese (日本語)",
    gr_progress=gr.Progress(),
):
    """動画ファイルに字幕を生成して焼き込む（Gradio generator）。"""
    if video_path is None:
        yield "ファイルを選択してください", None, None, ""
        return

    deepgram_key = deepgram_key.strip() or os.environ.get("DEEPGRAM_API_KEY", "")
    google_key = google_key.strip() or os.environ.get("GOOGLE_API_KEY", "")
    if not deepgram_key or not google_key:
        yield "❌ エラー: APIキーが未設定です（DEEPGRAM_API_KEY, GOOGLE_API_KEY）", None, None, ""
        return

    source_code = _to_code(source_lang)
    target_code = _to_code(target_lang)
    target_display = _to_full_name(target_code)

    tmp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(tmp_dir, "audio.wav")
    srt_path = os.path.join(tmp_dir, "subtitles.srt")
    output_path = os.path.join(tmp_dir, "subtitled.mp4")

    # 日本語などの非 ASCII ファイル名は Windows で問題を起こすため ASCII パスにコピーする
    import shutil
    safe_video_path = os.path.join(tmp_dir, "input.mp4")
    try:
        shutil.copy2(video_path, safe_video_path)
        video_path = safe_video_path
    except Exception:
        pass  # コピー失敗時は元のパスで続行

    log = ""

    def step(msg: str) -> str:
        nonlocal log
        log += msg + "\n"
        return log

    try:
        gr_progress(0.0, desc="開始...")
        yield step("🎵 音声を抽出中..."), None, None, ""
        await asyncio.to_thread(_video_extract_audio, video_path, audio_path)
        gr_progress(0.10, desc="音声抽出完了")
        yield step("✅ 音声抽出完了"), None, None, ""

        gr_progress(0.10, desc="文字起こし中（Deepgram）...")
        yield step("📝 文字起こし中（Deepgram）..."), None, None, ""
        utterances = await asyncio.to_thread(
            _video_transcribe, audio_path, deepgram_key, source_code
        )
        gr_progress(0.25, desc=f"文字起こし完了: {len(utterances)} セグメント")
        yield step(f"✅ 文字起こし完了: {len(utterances)} セグメント"), None, None, ""

        # utterance分断対策（文末で終わっていない断片の結合）。
        # 以前はこのGradio動画タブには適用されておらず、add_subtitles.py（実験用CLI）
        # にしかない機能だったため追加。
        if VIDEO_MERGE_UTTERANCES:
            before_count = len(utterances)
            if VIDEO_INCOMPLETE_END_DETECTION_ENABLED:
                from real_time_translation.transcription.utterance_merge import (
                    DEFAULT_MAX_DURATION,
                    DEFAULT_MAX_WORDS,
                    merge_incomplete_utterances_with_detector,
                )

                detector_config = Config(
                    deepgram_api_key=deepgram_key,
                    llm_provider="gemini",
                    zoom_client_id="",
                    zoom_client_secret="",
                    google_api_key=google_key,
                    gemini_model="gemini-2.5-flash",
                    utterance_merge_max_duration=DEFAULT_MAX_DURATION,
                    utterance_merge_max_words=DEFAULT_MAX_WORDS,
                )
                utterances = await merge_incomplete_utterances_with_detector(
                    utterances, detector_config
                )
            else:
                from real_time_translation.transcription.utterance_merge import (
                    merge_incomplete_utterances,
                )

                utterances = merge_incomplete_utterances(utterances)
            merge_desc = f"utterance結合: {before_count} → {len(utterances)} セグメント"
            gr_progress(0.30, desc=merge_desc)
            yield step(f"✅ {merge_desc}"), None, None, ""

        yield step(f"🌐 {target_display}に翻訳中（Gemini / ドメイン: {domain}）..."), None, None, ""

        def on_progress(utt_idx: int, total: int) -> None:
            frac = 0.30 + 0.40 * (utt_idx / max(total, 1))
            gr_progress(frac, desc=f"翻訳中... ({utt_idx}/{total} セグメント)")

        translated, translation_report = await _video_translate_with_pipeline(
            utterances,
            google_key,
            source_code,
            target_code,
            domain,
            on_progress,
            dictionary_path=VIDEO_DICTIONARY_PATH,
        )
        gr_progress(0.70, desc=f"翻訳完了: {len(translated)} セグメント")
        yield step(f"✅ 翻訳完了: {len(translated)} セグメント"), None, None, ""
        yield step(f"📊 {translation_report['usage_summary']}"), None, None, ""
        if translation_report["flagged_count"]:
            flagged_desc = (
                f"⚠️ 要確認セグメント: {translation_report['flagged_count']}"
                f"/{len(translated)}件"
            )
            yield step(flagged_desc), None, None, ""
        if translation_report["terminology_misses"]:
            misses_str = ", ".join(translation_report["terminology_misses"])
            yield step(f"⚠️ 用語漏れ: {misses_str}"), None, None, ""

        gr_progress(0.72, desc="SRTファイル生成中...")
        yield step("📄 SRTファイル生成中..."), None, None, ""
        _video_create_srt(translated, srt_path)
        gr_progress(0.75, desc="SRTファイル生成完了")
        yield step("✅ SRTファイル生成完了"), None, None, ""

        gr_progress(0.75, desc="字幕焼き込み中（時間がかかります）...")
        yield step("🎬 字幕を動画に焼き込み中（時間がかかります）..."), None, None, ""
        await asyncio.to_thread(_video_burn_subtitles, video_path, srt_path, output_path)
        gr_progress(0.95, desc="字幕焼き込み完了")
        yield step("✅ 字幕焼き込み完了"), None, None, ""

        score_text = ""
        if evaluate_scores:
            gr_progress(0.95, desc="スコア評価中...")
            yield step("📊 翻訳スコアを評価中（LLM-as-judge + 逆翻訳 chrF）..."), srt_path, output_path, ""
            xcomet, chrf = await _compute_scores(translated, google_key)
            xcomet_str = f"{xcomet:.4f}" if xcomet is not None else "計算失敗"
            chrf_str = f"{chrf:.4f}" if chrf is not None else "計算失敗"
            score_text = (
                f"xCOMET（LLM判定）: {xcomet_str}\n"
                f"chrF（逆翻訳）:     {chrf_str}\n\n"
                f"xCOMET は意味的な正確さ（0〜1、高いほど良い）\n"
                f"chrF は文字n-gram一致率（英日間では0.4〜0.5が目安）"
            )
            gr_progress(0.99, desc="スコア評価完了")
            yield step("✅ スコア評価完了"), srt_path, output_path, score_text

        gr_progress(1.0, desc="完了！")
        yield step("\n🎉 完了！下のボタンからダウンロードしてください。"), srt_path, output_path, score_text

    except Exception as exc:
        yield step(f"❌ エラー: {exc}"), None, None, ""


# ---------------------------------------------------------------------------

def build_demo() -> gr.Blocks:
    with gr.Blocks(title="Real-time Translation Demo") as demo:
        gr.Markdown("# Real-time ASR + MT Demo")
        gr.Markdown(
            "Stream microphone audio to Deepgram and translate with Gemini/OpenAI."
        )

        with gr.Accordion("API Keys", open=True):
            gr.Markdown(
                "Enter your API keys below. Keys are used only in your session and never stored.\n\n"
                "- [Deepgram API key](https://console.deepgram.com/) (free tier available)\n"
                "- [Google AI API key](https://aistudio.google.com/apikey) (free tier available)"
            )
            with gr.Row():
                deepgram_key_input = gr.Textbox(
                    label="Deepgram API Key",
                    placeholder="Enter your Deepgram API key",
                    type="password",
                )
                google_key_input = gr.Textbox(
                    label="Google AI API Key",
                    placeholder="Enter your Google AI (Gemini) API key",
                    type="password",
                )

        with gr.Row():
            source_lang_input = gr.Dropdown(
                choices=_LANG_CHOICES,
                value="English",
                label="Source Language",
            )
            target_lang_input = gr.Dropdown(
                choices=_LANG_CHOICES,
                value="Japanese (日本語)",
                label="Target Language",
            )
            domain_input = gr.Dropdown(
                choices=["general", "economics", "technology", "medical", "legal", "particle_physics"],
                value="general",
                label="ドメイン（専門分野）",
            )
        gr.Markdown(
            "_Note: Language/domain changes take effect when you click **Start** (or Process File / 字幕を生成する). "
            "Stop and restart the session to switch languages mid-session._",
        )

        state = gr.State(None)
        status = gr.Markdown(_status("stopped"))
        delay_indicator = gr.Markdown("⏱ 音声認識→和訳: -")

        with gr.Row():
            start_button = gr.Button("Start", variant="primary")
            stop_button = gr.Button("Stop")
            clear_button = gr.Button("Clear")

        with gr.Tabs():
            with gr.TabItem("🎤 Microphone"):
                audio = gr.Audio(
                    sources=["microphone"],
                    streaming=True,
                    type="numpy",
                    label="Microphone",
                )

            with gr.TabItem("📁 Audio File"):
                audio_file = gr.Audio(
                    sources=["upload"],
                    type="filepath",
                    label="Upload audio file (WAV, FLAC, MP3, etc.)",
                )
                with gr.Row():
                    process_button = gr.Button("Process File", variant="primary")
                    cancel_button = gr.Button("Cancel", variant="stop")

            with gr.TabItem("🎬 動画字幕"):
                gr.Markdown("動画ファイルをアップロードすると、字幕を生成して焼き込みます。ドメインは上部の共通設定を使用します。")
                video_input = gr.Video(
                    label="動画ファイル（MP4, MOV, AVI など）",
                    sources=["upload"],
                )
                gr.Markdown("📊 **翻訳スコアを評価する場合はチェック**（Gemini LLM-as-judge + 逆翻訳 chrF。追加で1〜2分かかります）")
                evaluate_scores_checkbox = gr.Checkbox(
                    label="スコアを評価する（xCOMET + chrF）",
                    value=False,
                )
                video_run_btn = gr.Button("🎬 字幕を生成する", variant="primary")
                video_log = gr.Textbox(label="処理ログ", lines=10, interactive=False)
                with gr.Row():
                    srt_output = gr.File(label="📄 SRTファイル ダウンロード")
                    video_output = gr.File(label="🎬 字幕付き動画 ダウンロード")
                score_output = gr.Textbox(
                    label="📊 翻訳スコア評価結果",
                    lines=5,
                    interactive=False,
                    visible=True,
                )

        with gr.Row():
            transcript_box = gr.Textbox(
                label="Transcription (source)",
                lines=12,
                interactive=False,
            )
            translation_box = gr.Textbox(
                label="Translation",
                lines=12,
                interactive=False,
            )

        with gr.Row():
            export_button = gr.Button("📥 Export as TXT")
            export_file = gr.File(label="Download", visible=False)

        export_button.click(
            export_as_txt,
            inputs=[state],
            outputs=[export_file],
        ).then(
            lambda f: gr.File(visible=f is not None),
            inputs=[export_file],
            outputs=[export_file],
        )

        start_button.click(
            start_session,
            inputs=[state, deepgram_key_input, google_key_input, source_lang_input, target_lang_input, domain_input],
            outputs=[state, status, transcript_box, translation_box],
        )
        stop_button.click(
            stop_session,
            inputs=[state],
            outputs=[state, status, delay_indicator],
        )
        clear_button.click(
            clear_logs,
            inputs=[state],
            outputs=[transcript_box, translation_box],
        )

        audio.stream(
            handle_audio,
            inputs=[audio, state],
            outputs=[transcript_box, translation_box, status, delay_indicator],
        )

        process_button.click(
            process_audio_file,
            inputs=[audio_file, state, deepgram_key_input, google_key_input, source_lang_input, target_lang_input, domain_input],
            outputs=[state, status, transcript_box, translation_box],
        )

        cancel_button.click(
            cancel_processing,
            inputs=[state],
            outputs=[state, status],
        )

        video_run_btn.click(
            process_video,
            inputs=[
                video_input, domain_input,
                deepgram_key_input, google_key_input,
                evaluate_scores_checkbox,
                source_lang_input, target_lang_input,
            ],
            outputs=[video_log, srt_output, video_output, score_output],
        )


    return demo


def main() -> None:
    demo = build_demo()
    demo.queue()
    demo.launch()


if __name__ == "__main__":
    main()
