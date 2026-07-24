"""Configuration management for real-time translation."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration."""

    # Deepgram
    deepgram_api_key: str

    # LLM Provider (gemini or openai)
    llm_provider: str

    # Zoom RTMS
    zoom_client_id: str
    zoom_client_secret: str

    # Deepgram options
    deepgram_model: str = "nova-2-general"
    deepgram_interim_results: bool = True
    deepgram_smart_format: bool = True
    deepgram_endpointing: int = 500
    deepgram_utterance_end_ms: int | None = None
    deepgram_vad_events: bool | None = None
    zoom_webhook_port: int = 8080
    zoom_webhook_path: str = "/webhook"

    # Gemini
    google_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    # OpenAI
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    # Translation settings
    source_language: str = "en"
    target_language: str = "ja"
    context_window_size: int = 5
    translation_queue_size: int = 10
    domain: str = "general"
    thinking_budget: int = 0

    # 文分断対策（utterance結合）。マイクのリアルタイム翻訳と動画字幕（add_subtitles.py）
    # で同じアルゴリズム（transcription/utterance_merge.py）を使う。
    merge_utterances: bool = True
    utterance_merge_max_duration: float = 8.0
    utterance_merge_max_words: int = 30

    # utterance分断検出のLLM分類器（incomplete_end_detector）。失敗時は句読点の
    # 正規表現へ自動フォールバックする。動画/CLI（バッチ）とマイク（ストリーミング、
    # タイムアウト付き）でそれぞれ独立にON/OFFできる。
    incomplete_end_detection_enabled: bool = True
    incomplete_end_detection_enabled_realtime: bool = True
    incomplete_end_detection_timeout: float = 0.6
    incomplete_end_detection_model: str | None = None  # 空ならgemini_modelを流用

    # 翻訳完全性チェック（文字数比の異常検知で訳し漏れの疑いを検出）
    completeness_check_enabled: bool = True
    completeness_ratio_threshold: float = 0.5

    # Gemini無料枠のレート制限目安（1分あたりの呼び出し上限）。UI警告表示にのみ使用。
    gemini_free_tier_rpm: int = 15

    # Dictionary
    dictionary_path: Path | None = None

    @classmethod
    def from_env(
        cls, env_file: Path | None = None, *, require_zoom: bool = True
    ) -> "Config":
        """Load configuration from environment variables.

        Args:
            env_file: Optional path to .env file
            require_zoom: Whether Zoom RTMS credentials are required

        Returns:
            Config instance
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        deepgram_api_key = os.getenv("DEEPGRAM_API_KEY", "")
        if not deepgram_api_key:
            raise ValueError("DEEPGRAM_API_KEY is required")

        def _get_bool_env(name: str, default: bool) -> bool:
            value = os.getenv(name)
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "on"}

        def _get_optional_int_env(name: str) -> int | None:
            value = os.getenv(name)
            if value is None:
                return None
            value = value.strip()
            if not value:
                return None
            return int(value)

        def _get_optional_bool_env(name: str) -> bool | None:
            value = os.getenv(name)
            if value is None:
                return None
            value = value.strip()
            if not value:
                return None
            return value.lower() in {"1", "true", "yes", "on"}

        # Zoom RTMS credentials
        zoom_client_id = os.getenv("ZOOM_CLIENT_ID", "")
        zoom_client_secret = os.getenv("ZOOM_CLIENT_SECRET", "")
        if require_zoom and (not zoom_client_id or not zoom_client_secret):
            raise ValueError("ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET are required")

        llm_provider = os.getenv("LLM_PROVIDER", "gemini").lower()

        google_api_key = os.getenv("GOOGLE_API_KEY")
        openai_api_key = os.getenv("OPENAI_API_KEY")

        if llm_provider == "gemini" and not google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when using Gemini")
        if llm_provider == "openai" and not openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when using OpenAI")

        # Dictionary path
        dictionary_path_str = os.getenv("DICTIONARY_PATH")
        dictionary_path = Path(dictionary_path_str) if dictionary_path_str else None

        return cls(
            deepgram_api_key=deepgram_api_key,
            deepgram_model=os.getenv("DEEPGRAM_MODEL", "nova-2-general"),
            deepgram_interim_results=_get_bool_env("DEEPGRAM_INTERIM_RESULTS", True),
            deepgram_smart_format=_get_bool_env("DEEPGRAM_SMART_FORMAT", True),
            deepgram_endpointing=int(os.getenv("DEEPGRAM_ENDPOINTING", "500")),
            deepgram_utterance_end_ms=_get_optional_int_env(
                "DEEPGRAM_UTTERANCE_END_MS"
            ),
            deepgram_vad_events=_get_optional_bool_env("DEEPGRAM_VAD_EVENTS"),
            llm_provider=llm_provider,
            zoom_client_id=zoom_client_id,
            zoom_client_secret=zoom_client_secret,
            zoom_webhook_port=int(os.getenv("ZOOM_WEBHOOK_PORT", "8080")),
            zoom_webhook_path=os.getenv("ZOOM_WEBHOOK_PATH", "/webhook"),
            google_api_key=google_api_key,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            openai_api_key=openai_api_key,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            source_language=os.getenv("SOURCE_LANGUAGE", "en"),
            target_language=os.getenv("TARGET_LANGUAGE", "ja"),
            context_window_size=int(os.getenv("CONTEXT_WINDOW_SIZE", "5")),
            translation_queue_size=int(os.getenv("TRANSLATION_QUEUE_SIZE", "10")),
            domain=os.getenv("DOMAIN", "general"),
            thinking_budget=int(os.getenv("THINKING_BUDGET", "0")),
            merge_utterances=_get_bool_env("MERGE_UTTERANCES", True),
            utterance_merge_max_duration=float(
                os.getenv("UTTERANCE_MERGE_MAX_DURATION", "8.0")
            ),
            utterance_merge_max_words=int(
                os.getenv("UTTERANCE_MERGE_MAX_WORDS", "30")
            ),
            incomplete_end_detection_enabled=_get_bool_env(
                "INCOMPLETE_END_DETECTION_ENABLED", True
            ),
            incomplete_end_detection_enabled_realtime=_get_bool_env(
                "INCOMPLETE_END_DETECTION_ENABLED_REALTIME", True
            ),
            incomplete_end_detection_timeout=float(
                os.getenv("INCOMPLETE_END_DETECTION_TIMEOUT", "0.6")
            ),
            incomplete_end_detection_model=(
                os.getenv("INCOMPLETE_END_DETECTION_MODEL", "").strip() or None
            ),
            completeness_check_enabled=_get_bool_env(
                "COMPLETENESS_CHECK_ENABLED", True
            ),
            completeness_ratio_threshold=float(
                os.getenv("COMPLETENESS_RATIO_THRESHOLD", "0.5")
            ),
            gemini_free_tier_rpm=int(os.getenv("GEMINI_FREE_TIER_RPM", "15")),
            dictionary_path=dictionary_path,
        )
