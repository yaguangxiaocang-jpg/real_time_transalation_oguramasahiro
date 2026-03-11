"""Test translation pipeline with an audio file."""

import asyncio
import os
import subprocess
import sys

from real_time_translation.audio.capture import QueueAudioCapture
from real_time_translation.config import Config
from real_time_translation.pipeline import TranslationPipeline


FFMPEG_FALLBACK = (
    r"C:\Users\yagua\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
)


def _find_ffmpeg() -> str:
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    if os.path.isfile(FFMPEG_FALLBACK):
        return FFMPEG_FALLBACK
    raise FileNotFoundError("ffmpeg not found. Install it or add it to PATH.")


def convert_to_pcm(audio_path: str) -> bytes:
    """Convert any audio file to 16kHz mono PCM using ffmpeg."""
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    print(f"Converting {audio_path} to 16kHz mono PCM...")

    ffmpeg = _find_ffmpeg()
    cmd = [
        ffmpeg,
        "-loglevel", "error",
        "-i", audio_path,
        "-f", "s16le",      # 16-bit signed little-endian PCM
        "-ar", "16000",     # 16kHz sample rate
        "-ac", "1",         # mono
        "-acodec", "pcm_s16le",
        "pipe:1",           # output to stdout
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        print(f"ffmpeg error: {result.stderr.decode()}")
        raise RuntimeError("Failed to convert audio file")

    return result.stdout


def seconds_to_srt(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt(subtitles: list, srt_path: str) -> None:
    """Generate an SRT subtitle file from (start, end, text) list."""
    # Adjust end times: minimum display 1.5s, no overlap with next
    adjusted = []
    for i, (start, end, text) in enumerate(subtitles):
        min_end = start + 1.5
        end = max(end, min_end)
        # Trim if overlapping with next subtitle
        if i + 1 < len(subtitles):
            next_start = subtitles[i + 1][0]
            end = min(end, next_start - 0.05)
            end = max(end, start + 0.5)
        adjusted.append((start, end, text))

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(adjusted, 1):
            f.write(f"{i}\n")
            f.write(f"{seconds_to_srt(start)} --> {seconds_to_srt(end)}\n")
            f.write(f"{text}\n\n")

    print(f"SRTファイル保存: {srt_path}")


def burn_subtitles(input_mp4: str, srt_path: str, output_mp4: str) -> None:
    """Burn SRT subtitles into MP4 using ffmpeg."""
    srt_dir = os.path.dirname(os.path.abspath(srt_path))
    srt_name = os.path.basename(srt_path)

    ffmpeg = _find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-i", input_mp4,
        "-vf", (
            f"subtitles={srt_name}:"
            "force_style='FontName=Meiryo,FontSize=22,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "Outline=2,Shadow=1,Alignment=2'"
        ),
        "-c:a", "copy",
        output_mp4,
    ]

    print(f"字幕を動画に焼き込み中...")
    result = subprocess.run(cmd, capture_output=True, check=False, cwd=srt_dir)

    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")
        print(f"ffmpeg error: {err}")
        raise RuntimeError("Failed to burn subtitles into video")

    print(f"字幕付き動画を保存しました: {output_mp4}")


async def test_with_audio_file(audio_path: str) -> None:
    """Test the translation pipeline with an audio file (WAV, FLAC, MP3, MP4, etc.)."""
    config = Config.from_env(require_zoom=False)
    capture = QueueAudioCapture(max_queue_size=500)  # Large queue for file processing
    pipeline = TranslationPipeline(config=config, audio_capture=capture)

    result_count = [0]  # Use list to allow modification in nested function
    all_asr = []  # Final ASR results
    all_translations = []
    all_subtitles = []  # (start_time, end_time, translated_text)
    latest_interim = [""]  # Track latest interim for full ASR capture

    def on_result(result):
        # Track all interim results for full ASR
        if not result.is_final:
            latest_interim[0] = result.original_text
            return

        # Final result
        if result.translated_text:
            result_count[0] += 1
            all_asr.append(result.original_text)
            all_translations.append(result.translated_text)
            all_subtitles.append((result.start_time, result.end_time, result.translated_text))
            print(f"\n[{result_count[0]}] {'='*46}")
            print(f"ASR: {result.original_text}")
            print(f"翻訳: {result.translated_text}")
            if result.kept_terms:
                print(f"保持用語: {', '.join(result.kept_terms)}")
            print(f"{'='*50}\n")
            # Reset interim after final
            latest_interim[0] = ""
        else:
            # Final without translation - just track ASR
            all_asr.append(result.original_text)
            latest_interim[0] = ""

    pipeline.set_callback(on_result)

    print(f"Loading audio file: {audio_path}")

    # Convert to PCM using ffmpeg (supports WAV, FLAC, MP3, MP4, etc.)
    audio_data = convert_to_pcm(audio_path)

    sample_rate = 16000
    duration = len(audio_data) / (sample_rate * 2)  # 2 bytes per sample
    print(f"Duration: {duration:.2f} seconds")

    print("\nStarting pipeline...")
    await pipeline.start()

    try:
        # Send audio in chunks (simulating real-time streaming)
        chunk_size = 16000 * 2  # 1 second of 16kHz 16-bit audio
        total_chunks = len(audio_data) // chunk_size

        print(f"Sending {total_chunks} chunks...")

        for i, offset in enumerate(range(0, len(audio_data), chunk_size)):
            chunk = audio_data[offset : offset + chunk_size]
            capture.push_audio(chunk)
            await asyncio.sleep(1.0)  # Real-time pace for Deepgram

            # Show progress
            if (i + 1) % 10 == 0 or i == total_chunks - 1:
                progress = int((i + 1) / total_chunks * 100)
                print(f"Sending: {progress}% ({i + 1}/{total_chunks}) - ASR: {len(all_asr)}, Trans: {result_count[0]}")

        # Give Deepgram time to process last chunks
        print(f"\nAll audio sent. Waiting 10 seconds for Deepgram to catch up...")
        await asyncio.sleep(10)

        print("Waiting for remaining ASR and translations...")
        last_asr_count = len(all_asr)
        last_trans_count = result_count[0]
        stable_seconds = 0
        max_wait = 180  # Maximum 3 minutes

        for i in range(max_wait):
            await asyncio.sleep(1)
            current_asr = len(all_asr)
            current_trans = result_count[0]

            if current_asr == last_asr_count and current_trans == last_trans_count:
                stable_seconds += 1
            else:
                stable_seconds = 0
                last_asr_count = current_asr
                last_trans_count = current_trans

            if (i + 1) % 10 == 0:
                print(f"  Waiting... {i + 1}s - ASR segments: {len(all_asr)}, Translations: {result_count[0]}")

            # Stop if no new results for 20 seconds
            if stable_seconds >= 20:
                print(f"  No new results for 20 seconds, finishing...")
                break
    finally:
        await pipeline.stop()

    # Print summary
    print(f"\n{'='*60}")
    print(f"完了！合計 {result_count[0]} 件の翻訳を出力しました。")
    print(f"{'='*60}")

    # Print full ASR text (from finals)
    print(f"\n{'='*60}")
    print("【全文 ASR (確定分)】")
    print('='*60)
    full_asr = " ".join(all_asr)
    print(full_asr)

    # If there's remaining interim content, show it
    if latest_interim[0]:
        print(f"\n{'='*60}")
        print("【未確定の中間結果】")
        print('='*60)
        print(latest_interim[0])

    # Print full translation
    print(f"\n{'='*60}")
    print("【全文 翻訳】")
    print('='*60)
    print("".join(all_translations))

    # Generate SRT and burn subtitles into video
    if all_subtitles:
        input_dir = os.path.dirname(os.path.abspath(audio_path))
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        srt_path = os.path.join(input_dir, f"{base_name}_ja.srt")
        output_mp4 = os.path.join(input_dir, f"{base_name}_ja.mp4")

        print(f"\n{'='*60}")
        print("【字幕付き動画を生成中】")
        print('='*60)
        generate_srt(all_subtitles, srt_path)
        burn_subtitles(audio_path, srt_path, output_mp4)
    else:
        print("\n翻訳結果がないため、字幕付き動画は生成されませんでした。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: uv run python test_audio_file.py <audio_file>")
        print("\nSupported formats: WAV, FLAC, MP3, MP4, etc. (anything ffmpeg supports)")
        print("\nExample:")
        print("  uv run python test_audio_file.py video.mp4")
        sys.exit(1)

    asyncio.run(test_with_audio_file(sys.argv[1]))
