"""Main entry point for real-time translation."""

import argparse
import asyncio
import signal

from real_time_translation.audio.capture import (
    MicrophoneCapture,
    ZoomRTMSCapture,
    ZoomRTMSConfig,
)
from real_time_translation.config import Config
from real_time_translation.pipeline import TranslationPipeline, TranslationResult


def print_result(result: TranslationResult) -> None:
    """Print translation result to console.

    Args:
        result: Translation result to print
    """
    status = "✓" if result.is_final else "..."
    confidence = f"({result.confidence:.0%})" if result.confidence < 0.9 else ""

    print(f"\n{status} Original: {result.original_text}")
    print(f"  Translated: {result.translated_text} {confidence}")


async def run_pipeline(*, use_mic: bool = False, mic_device: int | str | None = None) -> None:
    """Run the translation pipeline.

    Args:
        use_mic: Use system microphone instead of Zoom RTMS
        mic_device: sounddevice device index or name (None = system default)
    """
    if use_mic:
        config = Config.from_env(require_zoom=False)
        audio_capture = MicrophoneCapture(device=mic_device)
    else:
        config = Config.from_env()
        rtms_config = ZoomRTMSConfig(
            client_id=config.zoom_client_id,
            client_secret=config.zoom_client_secret,
            webhook_port=config.zoom_webhook_port,
            webhook_path=config.zoom_webhook_path,
        )
        audio_capture = ZoomRTMSCapture(rtms_config)

    pipeline = TranslationPipeline(
        config=config,
        audio_capture=audio_capture,
    )
    pipeline.set_callback(print_result)

    loop = asyncio.get_running_loop()

    def shutdown() -> None:
        asyncio.create_task(pipeline.stop())

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown)
    except NotImplementedError:
        # Windows does not support add_signal_handler
        signal.signal(signal.SIGINT, lambda _s, _f: shutdown())

    if use_mic:
        print("Starting real-time translation (microphone mode)...")
    else:
        print("Starting real-time translation...")
        print(
            f"Webhook server: http://localhost:{config.zoom_webhook_port}{config.zoom_webhook_path}"
        )
    print("Press Ctrl+C to stop")
    print("-" * 50)

    await pipeline.run()


def main() -> None:
    """Entry point for the application."""
    parser = argparse.ArgumentParser(description="Real-time translation")
    parser.add_argument(
        "--mic",
        action="store_true",
        help="Capture audio from system microphone (requires sounddevice)",
    )
    parser.add_argument(
        "--mic-device",
        metavar="DEVICE",
        default=None,
        help="Microphone device index or name (default: system default). "
             "Run with --list-devices to see available devices.",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio input devices and exit",
    )
    args = parser.parse_args()

    if args.list_devices:
        MicrophoneCapture.list_devices()
        return

    mic_device: int | str | None = args.mic_device
    if mic_device is not None:
        try:
            mic_device = int(mic_device)
        except ValueError:
            pass  # keep as string (device name)

    try:
        asyncio.run(run_pipeline(use_mic=args.mic, mic_device=mic_device))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
