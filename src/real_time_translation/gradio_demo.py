"""Gradio demo for real-time ASR + MT."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import audioop
import gradio as gr
import numpy as np

from real_time_translation.audio.capture import QueueAudioCapture
from real_time_translation.config import Config
from real_time_translation.pipeline import TranslationPipeline, TranslationResult

TARGET_SAMPLE_RATE = 16000
MAX_DISPLAY_LINES = 50


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


def _status(message: str) -> str:
    return f"Status: {message}"


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
) -> tuple[DemoSession | None, str, str, str]:
    if state is not None:
        transcript = "\n".join(state.transcript_lines)
        translation = "\n".join(state.translation_lines)
        return state, _status("running"), transcript, translation

    try:
        if deepgram_key.strip() and google_key.strip():
            config = Config(
                deepgram_api_key=deepgram_key.strip(),
                llm_provider="gemini",
                zoom_client_id="",
                zoom_client_secret="",
                google_api_key=google_key.strip(),
            )
        else:
            config = Config.from_env(require_zoom=False)
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


async def stop_session(state: DemoSession | None) -> tuple[DemoSession | None, str]:
    if state is None:
        return None, _status("stopped")

    await state.pipeline.stop()
    return None, _status("stopped")


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
) -> tuple[DemoSession | None, str, str, str]:
    """Process an uploaded audio file through the pipeline."""
    if file_path is None:
        return state, _status("No file selected"), "", ""

    # Start session if not already running
    if state is None:
        state, status, _, _ = await start_session(None, deepgram_key, google_key)
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


async def handle_audio(chunk: Any, state: DemoSession | None) -> tuple[str, str, str]:
    if state is None:
        return "", "", _status("click Start to initialize")

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
        state.transcript_lines.append(result.original_text)
        state.translation_lines.append(result.translated_text)
        state.interim_transcript = ""
        if result.slide_window:
            latest_slide_window = result.slide_window

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

    return transcript, translation, _status("running")


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


def _video_transcribe(audio_path: str, api_key: str) -> list[dict]:
    from deepgram import DeepgramClient

    client = DeepgramClient(api_key=api_key)
    with open(audio_path, "rb") as f:
        audio_data = f.read()

    response = client.listen.v1.media.transcribe_file(
        request=audio_data,
        model="nova-2-general",
        language=os.environ.get("SOURCE_LANGUAGE", "en"),
        smart_format=True,
        punctuate=True,
        utterances=True,
        utt_split=0.8,
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


async def _video_translate(utterances: list[dict], api_key: str) -> list[dict]:
    from google import genai

    client = genai.Client(api_key=api_key)
    translated: list[dict] = []
    batch_size = 10
    for i in range(0, len(utterances), batch_size):
        batch = utterances[i : i + batch_size]
        numbered = "\n".join(f"{j+1}. {u['transcript']}" for j, u in enumerate(batch))
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
        raw = response.text or ""
        ja_texts: list[str] = []
        for line in (ln.strip() for ln in raw.split("\n") if ln.strip()):
            m = re.match(r"\d+\.\s*(.*)", line)
            ja_texts.append(m.group(1) if m else line)
        while len(ja_texts) < len(batch):
            ja_texts.append(batch[len(ja_texts)]["transcript"])
        for u, ja in zip(batch, ja_texts):
            translated.append({"start": u["start"], "end": u["end"],
                                "original": u["transcript"], "japanese": ja})
    return translated


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


def _video_burn_subtitles(video_path: str, srt_path: str, output_path: str) -> None:
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path, "-vf",
            f"subtitles='{srt_escaped}':force_style='FontName=Arial Unicode MS,FontSize=20,"
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
    judge_resp = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.5-flash",
        contents=judge_prompt,
    )
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
    back_resp = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.5-flash",
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

    return xcomet_score, chrf_score


async def process_video(
    video_path: str | None,
    domain: str,
    deepgram_key: str = "",
    google_key: str = "",
    evaluate_scores: bool = False,
):
    """動画ファイルに日本語字幕を生成して焼き込む（Gradio generator）。"""
    if video_path is None:
        yield "ファイルを選択してください", None, None, ""
        return

    deepgram_key = deepgram_key.strip() or os.environ.get("DEEPGRAM_API_KEY", "")
    google_key = google_key.strip() or os.environ.get("GOOGLE_API_KEY", "")
    if not deepgram_key or not google_key:
        yield "❌ エラー: APIキーが未設定です（DEEPGRAM_API_KEY, GOOGLE_API_KEY）", None, None, ""
        return

    tmp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(tmp_dir, "audio.wav")
    srt_path = os.path.join(tmp_dir, "subtitles_ja.srt")
    output_path = os.path.join(tmp_dir, "subtitled.mp4")
    log = ""

    def step(msg: str) -> str:
        nonlocal log
        log += msg + "\n"
        return log

    try:
        yield step("🎵 音声を抽出中..."), None, None, ""
        await asyncio.to_thread(_video_extract_audio, video_path, audio_path)
        yield step("✅ 音声抽出完了"), None, None, ""

        yield step("📝 文字起こし中（Deepgram）..."), None, None, ""
        utterances = await asyncio.to_thread(_video_transcribe, audio_path, deepgram_key)
        yield step(f"✅ 文字起こし完了: {len(utterances)} セグメント"), None, None, ""

        yield step(f"🌐 日本語に翻訳中（Gemini / ドメイン: {domain}）..."), None, None, ""
        translated = await _video_translate(utterances, google_key)
        yield step(f"✅ 翻訳完了: {len(translated)} セグメント"), None, None, ""

        yield step("📄 SRTファイル生成中..."), None, None, ""
        _video_create_srt(translated, srt_path)
        yield step("✅ SRTファイル生成完了"), None, None, ""

        yield step("🎬 字幕を動画に焼き込み中（時間がかかります）..."), None, None, ""
        await asyncio.to_thread(_video_burn_subtitles, video_path, srt_path, output_path)
        yield step("✅ 字幕焼き込み完了"), None, None, ""

        score_text = ""
        if evaluate_scores:
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
            yield step("✅ スコア評価完了"), srt_path, output_path, score_text

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

        state = gr.State(None)
        status = gr.Markdown(_status("stopped"))

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
                gr.Markdown("動画ファイルをアップロードすると、日本語字幕を生成して焼き込みます。")
                video_input = gr.Video(
                    label="動画ファイル（MP4, MOV, AVI など）",
                    sources=["upload"],
                )
                domain_input = gr.Dropdown(
                    choices=["general", "economics", "technology", "medical", "legal", "particle_physics"],
                    value="general",
                    label="ドメイン（専門分野）",
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

        start_button.click(
            start_session,
            inputs=[state, deepgram_key_input, google_key_input],
            outputs=[state, status, transcript_box, translation_box],
        )
        stop_button.click(
            stop_session,
            inputs=[state],
            outputs=[state, status],
        )
        clear_button.click(
            clear_logs,
            inputs=[state],
            outputs=[transcript_box, translation_box],
        )

        audio.stream(
            handle_audio,
            inputs=[audio, state],
            outputs=[transcript_box, translation_box, status],
        )

        process_button.click(
            process_audio_file,
            inputs=[audio_file, state, deepgram_key_input, google_key_input],
            outputs=[state, status, transcript_box, translation_box],
        )

        cancel_button.click(
            cancel_processing,
            inputs=[state],
            outputs=[state, status],
        )

        video_run_btn.click(
            process_video,
            inputs=[video_input, domain_input, deepgram_key_input, google_key_input, evaluate_scores_checkbox],
            outputs=[video_log, srt_output, video_output, score_output],
        )

    return demo


def main() -> None:
    demo = build_demo()
    demo.queue()
    demo.launch()


if __name__ == "__main__":
    main()
