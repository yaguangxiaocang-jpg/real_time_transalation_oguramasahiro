"""Translation pipeline for real-time audio translation."""

import asyncio
import contextlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from real_time_translation.audio.capture import AudioCapture
from real_time_translation.config import Config
from real_time_translation.transcription.deepgram_client import (
    DeepgramTranscriber,
    TranscriptionResult,
)
from real_time_translation.transcription.incomplete_end_detector import (
    detect_incomplete_end_one,
)
from real_time_translation.transcription.utterance_merge import (
    MergedUtterance,
    StreamingUtteranceMerger,
)
from real_time_translation.translation.completeness_check import CompletenessTracker
from real_time_translation.translation.dictionary import TermDictionary
from real_time_translation.translation.llm_translator import LLMTranslator
from real_time_translation.translation.terminology_check import (
    TerminologyCheckResult,
    check_terminology,
)
from real_time_translation.translation.usage_tracking import RateLimitStatus, UsageSink

# 用語カバレッジ検査（terminology_misses）用に保持する直近ペア数。
# 無制限に貯めるとメモリを圧迫するため、直近のセッション状況を代表できる件数に絞る。
_TERMINOLOGY_HISTORY_SIZE = 200


@dataclass
class TranslationResult:
    """Complete translation result."""

    original_text: str
    translated_text: str
    is_final: bool
    confidence: float
    kept_terms: list[str] = field(default_factory=list)
    slide_window: list[str] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    translation_delay: float = 0.0
    # 例: "possible_undertranslation" / "empty_translation"
    review_flag: str | None = None


class SharedTranslationContext:
    """全ワーカーが共有する翻訳コンテキスト。

    - ワーカーは翻訳前にスナップショットを取得（読み取り並列OK）
    - 翻訳後はシーケンス番号順に結果をコミット（順序保証）
    - これにより並列処理しながらも文脈の一貫性を保つ
    """

    def __init__(self, window_size: int = 5) -> None:
        self._lock = threading.Lock()
        self._src_buffer: list[str] = []
        self._tgt_buffer: list[str] = []
        self._window_size = window_size
        self._next_commit_seq: int = 0
        self._pending: dict[int, tuple[str, str]] = {}

    def snapshot(self) -> tuple[list[str], list[str]]:
        """翻訳前に呼ぶ。現時点のコンテキストのコピーを返す。"""
        with self._lock:
            return list(self._src_buffer), list(self._tgt_buffer)

    def commit(self, seq: int, src_text: str, tgt_text: str) -> None:
        """翻訳後に呼ぶ。seq順にコンテキストへ追記する。"""
        with self._lock:
            self._pending[seq] = (src_text, tgt_text)
            while self._next_commit_seq in self._pending:
                s, t = self._pending.pop(self._next_commit_seq)
                self._src_buffer.append(s)
                self._tgt_buffer.append(t)
                if len(self._src_buffer) > self._window_size:
                    self._src_buffer.pop(0)
                if len(self._tgt_buffer) > self._window_size:
                    self._tgt_buffer.pop(0)
                self._next_commit_seq += 1

    def clear(self) -> None:
        with self._lock:
            self._src_buffer.clear()
            self._tgt_buffer.clear()
            self._pending.clear()
            self._next_commit_seq = 0


@dataclass
class QueuedTranscription:
    """Queued transcription with masked text when needed."""

    original: TranscriptionResult
    text_for_translation: str
    seq: int = 0
    queued_at: float = field(default_factory=time.monotonic)


class TranslationPipeline:
    """Pipeline for real-time audio translation.

    Coordinates audio capture, transcription, and translation.
    """

    def __init__(
        self,
        config: Config,
        audio_capture: AudioCapture,
    ) -> None:
        """Initialize translation pipeline.

        Args:
            config: Application configuration
            audio_capture: Audio capture instance
        """
        self._config = config
        self._audio_capture = audio_capture

        # Initialize transcriber
        self._transcriber = DeepgramTranscriber(
            api_key=config.deepgram_api_key,
            language=config.source_language,
            model=config.deepgram_model,
            interim_results=config.deepgram_interim_results,
            smart_format=config.deepgram_smart_format,
            endpointing=config.deepgram_endpointing,
            utterance_end_ms=config.deepgram_utterance_end_ms,
            vad_events=config.deepgram_vad_events,
            emit_interim=True,  # Emit interim results for real-time UI
        )

        # Initialize translator
        api_key = (
            config.google_api_key
            if config.llm_provider == "gemini"
            else config.openai_api_key
        )
        model = (
            config.gemini_model
            if config.llm_provider == "gemini"
            else config.openai_model
        )

        # LLM使用量トラッキング。Gradioは複数セッションが同時に動きうるため、
        # グローバル共有ではなく pipeline インスタンスごとに専用のsinkを持つ。
        self._usage_sink = UsageSink()

        _num_workers = 3
        self._translators: list[LLMTranslator] = [
            LLMTranslator(
                provider=config.llm_provider,  # type: ignore
                api_key=api_key or "",
                model=model,
                source_language=self._language_name(config.source_language),
                target_language=self._language_name(config.target_language),
                dictionary_path=config.dictionary_path,
                context_window_size=config.context_window_size,
                domain=config.domain,
                thinking_budget=config.thinking_budget,
                usage_sink=self._usage_sink,
            )
            for _ in range(_num_workers)
        ]
        self._translator = self._translators[0]

        self._shared_context = SharedTranslationContext(
            window_size=config.context_window_size
        )
        self._seq_counter: int = 0

        # 文分断対策: 文末で終わっていないfinal結果を次の結果と結合してから翻訳する
        # （動画字幕のmerge_incomplete_utterancesと同じアルゴリズム）
        self._merge_utterances = config.merge_utterances
        self._utterance_merger = StreamingUtteranceMerger(
            max_duration=config.utterance_merge_max_duration,
            max_words=config.utterance_merge_max_words,
        )

        # 翻訳完全性チェック（訳し漏れの疑いを検出）と用語辞書カバレッジ検査
        self._completeness_tracker = CompletenessTracker(
            ratio_threshold=config.completeness_ratio_threshold,
        )
        self._dictionary: TermDictionary = self._translator.dictionary
        self._terminology_pairs: list[tuple[str, str]] = []

        self._running = False
        self._on_result: Callable[[TranslationResult], None] | None = None
        self._tasks: list[asyncio.Task[Any]] = []
        self._transcription_queue: asyncio.Queue[QueuedTranscription] = asyncio.Queue(
            maxsize=config.translation_queue_size
        )

    @staticmethod
    def _language_name(code: str) -> str:
        """Convert language code to language name.

        Args:
            code: Language code (e.g., "en", "ja")

        Returns:
            Language name
        """
        names = {
            "en": "English",
            "ja": "Japanese",
            "zh": "Chinese",
            "ko": "Korean",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
        }
        return names.get(code, code)

    def set_callback(self, callback: Callable[[TranslationResult], None]) -> None:
        """Set callback for translation results.

        Args:
            callback: Function to call with results
        """
        self._on_result = callback

    async def start(self) -> None:
        """Start the translation pipeline."""
        self._running = True

        # Initialize translators (e.g., Gemini context cache)
        await asyncio.gather(*[t.prepare() for t in self._translators])

        # Connect to Deepgram
        await self._transcriber.connect()

        # Start audio capture
        await self._audio_capture.start()

        # Start processing tasks
        self._tasks = [
            asyncio.create_task(self._audio_to_transcription()),
            asyncio.create_task(self._collect_transcriptions()),
            *[asyncio.create_task(self._translation_worker(t)) for t in self._translators],
        ]

    async def stop(self) -> None:
        """Stop the translation pipeline."""
        # Signal tasks to stop first to prevent blocking
        self._running = False

        # Stop audio capture to signal no more audio
        await self._audio_capture.stop()

        # Finalize the transcriber (signal end of audio stream)
        await self._transcriber.finalize()

        # 結合バッファに残っている未確定の断片があれば、失わずに翻訳キューへ流す
        remaining = self._utterance_merger.flush()
        if remaining is not None:
            self._enqueue_merged(remaining)

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Disconnect transcriber
        await self._transcriber.disconnect()

    async def _audio_to_transcription(self) -> None:
        """Send audio data to transcriber."""
        try:
            async for audio_chunk in self._audio_capture.stream():
                if not self._running:
                    break
                await self._transcriber.send_audio(audio_chunk)
        except asyncio.CancelledError:
            pass

    async def _collect_transcriptions(self) -> None:
        """Collect transcription results into a queue."""
        try:
            async for result in self._transcriber.results():
                if not self._running:
                    break

                text = result.text.strip()
                if not text:
                    continue

                # Emit interim results to UI (without translation)
                if not result.is_final:
                    if self._on_result:
                        interim_result = TranslationResult(
                            original_text=text,
                            translated_text="",
                            is_final=False,
                            confidence=result.confidence,
                        )
                        self._on_result(interim_result)
                    continue

                if not self._merge_utterances:
                    self._enqueue_transcription(result)
                    continue

                # utterance分断検出のLLM分類器（設定で有効な場合のみ）。マイクは
                # 1件ずつ同期的に流れる経路なので、タイムアウト付きで呼び、
                # 間に合わなければ None を返して従来の正規表現判定にフォールバックする
                # （＝リアルタイム性を絶対に壊さない安全弁）。
                is_incomplete_override: bool | None = None
                if (
                    self._config.incomplete_end_detection_enabled_realtime
                    and self._config.google_api_key
                ):
                    model = (
                        self._config.incomplete_end_detection_model
                        or self._config.gemini_model
                    )
                    is_incomplete_override = await detect_incomplete_end_one(
                        text,
                        self._config.google_api_key,
                        model,
                        self._config.incomplete_end_detection_timeout,
                        self._usage_sink,
                    )

                # 文末で終わっていなければ None が返り、次のfinalと結合するまで待つ
                # （＝字幕確定を少し遅らせて、より自然な訳を得る）
                merged = self._utterance_merger.feed(
                    text,
                    result.start_time,
                    result.end_time,
                    result.confidence,
                    is_incomplete_override=is_incomplete_override,
                )
                if merged is None:
                    continue
                self._enqueue_merged(merged)
        except asyncio.CancelledError:
            pass

    def _enqueue_transcription(self, result: TranscriptionResult) -> None:
        """utterance結合を使わない場合の従来経路（1件ずつそのままキューへ）。"""
        masked_text = (
            f"[uncertain: {result.text}]" if result.is_low_confidence else result.text
        )
        self._enqueue(result, masked_text)

    def _enqueue_merged(self, merged: MergedUtterance) -> None:
        """結合済みutteranceを翻訳キューへ積む。"""
        masked_text = (
            f"[uncertain: {merged.text}]" if merged.is_low_confidence else merged.text
        )
        result = TranscriptionResult(
            text=merged.text,
            is_final=True,
            confidence=merged.confidence,
            start_time=merged.start_time,
            end_time=merged.end_time,
        )
        self._enqueue(result, masked_text)

    def _enqueue(self, result: TranscriptionResult, masked_text: str) -> None:
        if self._transcription_queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._transcription_queue.get_nowait()

        queued = QueuedTranscription(
            original=result,
            text_for_translation=masked_text,
            seq=self._seq_counter,
        )
        self._seq_counter += 1
        with contextlib.suppress(asyncio.QueueFull):
            self._transcription_queue.put_nowait(queued)

    async def _translation_worker(self, translator: LLMTranslator) -> None:
        """Consume queued transcriptions and translate using shared context."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            while self._running:
                queued = await self._transcription_queue.get()

                # 翻訳前に共有コンテキストのスナップショットを取得
                # （複数ワーカーが同じ文脈を読むため表記ゆれを防ぐ）
                src_ctx, tgt_ctx = self._shared_context.snapshot()

                try:
                    output = await translator.translate(
                        queued.text_for_translation,
                        src_context=src_ctx,
                        tgt_context=tgt_ctx,
                        update_context=False,  # 個別バッファは使わない
                    )
                except Exception as exc:
                    logger.error("Translation error: %s", exc)
                    # エラーでもシーケンスを進めてコンテキストが詰まらないようにする
                    self._shared_context.commit(queued.seq, queued.original.text, "")
                    continue

                # 順序を守ってコンテキストへコミット
                self._shared_context.commit(
                    queued.seq,
                    queued.original.text,
                    output.latest_slide,
                )

                _, current_tgt = self._shared_context.snapshot()

                review_flag: str | None = None
                if self._config.completeness_check_enabled:
                    flag = self._completeness_tracker.check(
                        queued.original.text, output.latest_slide
                    )
                    if flag is not None:
                        review_flag = flag.flag
                        logger.warning(
                            "completeness check flagged segment: %s "
                            "(ratio=%.2f, median=%s)",
                            flag.flag,
                            flag.ratio,
                            flag.median_ratio,
                        )

                if self._dictionary:
                    self._terminology_pairs.append(
                        (queued.original.text, output.latest_slide)
                    )
                    if len(self._terminology_pairs) > _TERMINOLOGY_HISTORY_SIZE:
                        self._terminology_pairs.pop(0)

                translation_result = TranslationResult(
                    original_text=queued.original.text,
                    translated_text=output.latest_slide,
                    is_final=queued.original.is_final,
                    confidence=queued.original.confidence,
                    kept_terms=output.kept_terms,
                    slide_window=current_tgt,
                    start_time=queued.original.start_time,
                    end_time=queued.original.end_time,
                    translation_delay=time.monotonic() - queued.queued_at,
                    review_flag=review_flag,
                )
                if self._on_result:
                    self._on_result(translation_result)
        except asyncio.CancelledError:
            pass

    @property
    def pending_count(self) -> int:
        """Number of transcriptions waiting to be translated."""
        return self._transcription_queue.qsize()

    def usage_status(self) -> RateLimitStatus:
        """直近1分間のLLM呼び出し数と、Gemini無料枠目安に対する近さ。"""
        return self._usage_sink.rate_limit_status(self._config.gemini_free_tier_rpm)

    def usage_summary_text(self) -> str:
        """UI表示用の使用量サマリ（1行）。"""
        return self._usage_sink.summary_text()

    def terminology_report(self) -> TerminologyCheckResult:
        """直近セッションの用語辞書カバレッジ検査結果。"""
        return check_terminology(self._terminology_pairs, self._dictionary)

    def clear_context(self) -> None:
        """Clear translation context buffer."""
        self._shared_context.clear()
        for translator in self._translators:
            translator.clear_context()
        self._utterance_merger.flush()
        self._terminology_pairs.clear()

    async def run(self) -> None:
        """Run the pipeline until stopped."""
        await self.start()
        try:
            while self._running:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
