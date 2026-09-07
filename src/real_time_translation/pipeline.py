"""Translation pipeline for real-time audio translation."""

import asyncio
import contextlib
import dataclasses
import logging
import threading
import time
from collections import deque
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
from real_time_translation.transcription.naturalness_detector import (
    score_unnaturalness_with_timeout,
)
from real_time_translation.transcription.utterance_merge import (
    MergedUtterance,
    StreamingUtteranceMerger,
)
from real_time_translation.transcription.whisper_reverify import reverify_terms
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

logger = logging.getLogger(__name__)


class _AudioRingBuffer:
    """マイク音声チャンクを一定時間分バッファし、Whisper再検証
    （`whisper_reverify_enabled`）用に音声区間を切り出せるようにする。

    Deepgramの`start_time`/`end_time`は音声ストリーム開始からの経過秒数
    （送信済みバイト数ベース）を指すため、`_audio_to_transcription`で
    `send_audio`に渡すのと同じ順序・同じチャンクを`append`することで
    タイムスタンプの基準を一致させる。
    """

    _BYTES_PER_SAMPLE = 2  # 16-bit PCM

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        max_seconds: float = 20.0,
    ) -> None:
        self._bytes_per_second = sample_rate * channels * self._BYTES_PER_SAMPLE
        self._max_seconds = max_seconds
        self._chunks: deque[tuple[float, bytes]] = deque()
        self._cursor = 0.0

    def append(self, data: bytes) -> None:
        if not data:
            return
        self._chunks.append((self._cursor, data))
        self._cursor += len(data) / self._bytes_per_second

        cutoff = self._cursor - self._max_seconds
        while self._chunks:
            start, chunk = self._chunks[0]
            if start + len(chunk) / self._bytes_per_second >= cutoff:
                break
            self._chunks.popleft()

    def slice(
        self, start_time: float, end_time: float, pad: float = 0.2
    ) -> bytes | None:
        """`[start_time - pad, end_time + pad]`秒に対応するPCMバイト列を切り出す。

        バッファ範囲外（古すぎて既に破棄された等）の場合は`None`を返す。
        """
        lo = max(0.0, start_time - pad)
        hi = end_time + pad
        out = bytearray()
        found = False
        for chunk_start, data in self._chunks:
            chunk_end = chunk_start + len(data) / self._bytes_per_second
            if chunk_end <= lo or chunk_start >= hi:
                continue
            found = True
            # round()（int()の切り捨てではなく）を使うのは、浮動小数点誤差
            # （例: 0.6 - 0.4 == 0.19999999999999998）でチャンク境界が
            # 1サンプル分削れるのを防ぐため。
            byte_lo = max(0, round((lo - chunk_start) * self._bytes_per_second))
            byte_hi = min(len(data), round((hi - chunk_start) * self._bytes_per_second))
            byte_lo -= byte_lo % self._BYTES_PER_SAMPLE
            byte_hi -= byte_hi % self._BYTES_PER_SAMPLE
            out.extend(data[byte_lo:byte_hi])
        return bytes(out) if found else None


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

        # ASRキーワードブースト（Deepgramの誤認識自体を減らす根本対策）。
        # dictionary_pathの「そのまま使う」用語（T5/PaLM/MOE/AWS等）を自動的に
        # Deepgramへ渡す。辞書読み込みに失敗してもキーワードブーストなしで
        # 翻訳自体は継続できるようにする。
        deepgram_keywords: list[str] = []
        if config.deepgram_keyword_boost_enabled and config.dictionary_path:
            try:
                keyword_dictionary = TermDictionary()
                keyword_dictionary.load_csv(config.dictionary_path)
                deepgram_keywords = keyword_dictionary.as_asr_keywords(
                    boost=config.deepgram_keyword_boost_value
                )
            except OSError as exc:
                import logging

                logging.getLogger(__name__).warning(
                    "Failed to load dictionary for ASR keyword boost %s: %s",
                    config.dictionary_path,
                    exc,
                )

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
            keywords=deepgram_keywords,
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

        # Whisper再検証（ハイブリッドASR）。既知の「そのまま使う」用語がある
        # 場合のみ動作する（無ければ照合対象が無いので何もしない）。
        self._whisper_keep_terms: list[str] = (
            self._dictionary.keep_as_is_terms()
            if config.whisper_reverify_enabled
            else []
        )
        self._audio_ring: _AudioRingBuffer | None = (
            _AudioRingBuffer(max_seconds=config.utterance_merge_max_duration + 5.0)
            if config.whisper_reverify_enabled
            else None
        )

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
            remaining = await self._reverify_merged(remaining)
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
                if self._audio_ring is not None:
                    self._audio_ring.append(audio_chunk)
                await self._transcriber.send_audio(audio_chunk)
        except asyncio.CancelledError:
            pass

    async def _reverify_text(
        self, text: str, start_time: float, end_time: float
    ) -> str:
        """`text`（Deepgram確定文）をfaster-whisperで再検証し、既知用語の誤認識
        だけを補正する（`whisper_reverify_enabled`時のみ）。

        `incomplete_end_detection`/`unnaturalness_check`と同じ安全弁設計:
        タイムアウトまたはエラー時は元のテキストをそのまま返す。
        """
        if self._audio_ring is None or not self._whisper_keep_terms:
            return text

        pcm = self._audio_ring.slice(start_time, end_time)
        if not pcm:
            return text

        try:
            corrected, fixed_terms = await asyncio.wait_for(
                asyncio.to_thread(
                    reverify_terms,
                    text,
                    pcm,
                    self._whisper_keep_terms,
                    model_size=self._config.whisper_reverify_model_size,
                    language=self._config.source_language,
                    min_confidence=self._config.whisper_reverify_min_confidence,
                ),
                timeout=self._config.whisper_reverify_timeout,
            )
        except TimeoutError:
            logger.debug(
                "whisper reverify timed out (%.2fs)",
                self._config.whisper_reverify_timeout,
            )
            return text
        except Exception as exc:  # noqa: BLE001
            logger.debug("whisper reverify error: %s", exc)
            return text

        if fixed_terms:
            logger.info("whisper reverify corrected terms: %s", fixed_terms)
        return corrected

    async def _reverify_result(
        self, result: TranscriptionResult
    ) -> TranscriptionResult:
        corrected = await self._reverify_text(
            result.text, result.start_time, result.end_time
        )
        if corrected == result.text:
            return result
        return dataclasses.replace(result, text=corrected)

    async def _reverify_merged(self, merged: MergedUtterance) -> MergedUtterance:
        corrected = await self._reverify_text(
            merged.text, merged.start_time, merged.end_time
        )
        if corrected == merged.text:
            return merged
        return dataclasses.replace(merged, text=corrected)

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
                    result = await self._reverify_result(result)
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

                # 不自然度スコアによるチャンク動的延長（設定で有効な場合のみ、既定OFF）。
                # 文法的には文末に達していても、直前の字幕（共有コンテキストの原文・
                # 訳文の両方）を踏まえると今訳すと唐突に見える候補はLLMに採点させ、
                # 閾値以上なら強制的に結合を継続する。こちらもタイムアウト付きで
                # リアルタイム性を壊さない（`incomplete_end_detection` と同じ安全弁の設計）。
                force_incomplete = False
                if (
                    self._config.unnaturalness_check_enabled
                    and self._config.google_api_key
                ):
                    candidate_text = self._utterance_merger.peek_combined_text(text)
                    src_ctx, tgt_ctx = self._shared_context.snapshot()
                    n = self._config.unnaturalness_context_size
                    # 原文だけでなく、既に確定済みの日本語訳も参考情報として渡す
                    # （不自然さの手がかりが日本語側の方が見えやすいことがあるため）。
                    context_pairs = list(zip(src_ctx[-n:], tgt_ctx[-n:]))
                    model = (
                        self._config.unnaturalness_check_model
                        or self._config.gemini_model
                    )
                    result = await score_unnaturalness_with_timeout(
                        candidate_text,
                        context_pairs,
                        self._config.google_api_key,
                        model,
                        self._config.unnaturalness_check_timeout,
                        self._usage_sink,
                    )
                    # ガード（2026-09-07追加）: スコアが閾値以上でも、モデル自身が
                    # 理由を"complete"（実は完結している）と答えた場合は強制継続
                    # させない。単一のスコアだけで判定すると、既に句点で終わった
                    # 完結文を無関係な次発話と過剰結合してしまう誤検知が
                    # 2026-08-25のAB testで確認されていたため
                    # （`naturalness_detector.NaturalnessResult`のdocstring参照）。
                    if (
                        result is not None
                        and result.score >= self._config.unnaturalness_threshold
                        and result.reason != "complete"
                    ):
                        force_incomplete = True

                # 文末で終わっていなければ None が返り、次のfinalと結合するまで待つ
                # （＝字幕確定を少し遅らせて、より自然な訳を得る）
                merged = self._utterance_merger.feed(
                    text,
                    result.start_time,
                    result.end_time,
                    result.confidence,
                    is_incomplete_override=is_incomplete_override,
                    force_incomplete=force_incomplete,
                )
                if merged is None:
                    continue
                merged = await self._reverify_merged(merged)
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
