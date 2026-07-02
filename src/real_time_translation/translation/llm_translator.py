"""LLM-based translator with Gemini/OpenAI support."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

_DOMAIN_DESCRIPTIONS: dict[str, str] = {
    "general": "",
    "economics": "Domain context: economics, finance, and business. Use accurate financial and economic terminology. Keep ticker symbols and currency codes (USD, JPY, etc.) unchanged.",
    "technology": "Domain context: technology, software engineering, and computer science. Preserve technical terms, library names, API names, and acronyms exactly as they appear.",
    "medical": "Domain context: medicine, clinical practice, and healthcare. Use accurate medical terminology. Maintain clinical precision; do not paraphrase diagnoses or drug names.",
    "legal": "Domain context: law, regulations, and compliance. Use formal legal register and accurate legal terminology. Keep article/section references unchanged.",
    "particle_physics": "Domain context: particle physics and high-energy physics research. Preserve particle names, physics symbols, equation terms, and experiment names (e.g., LHC, CMS) exactly.",
}

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field  # noqa: F401 (kept for OpenAI structured output)

from real_time_translation.translation.dictionary import TermDictionary


class TranslationLLMOutput(BaseModel):
    """Structured output returned by the LLM."""

    latest_slide: str = Field(
        ...,
        description=(
            "Translated text for the current <target> only. Do not include any extra "
            "commentary."
        ),
    )
    kept_terms: list[str] = Field(
        default_factory=list,
        description=(
            "Source terms intentionally kept unchanged because they are proper nouns, "
            "acronyms, code identifiers, or ambiguous/unknown."
        ),
    )


@dataclass(frozen=True)
class TranslationOutput:
    """Application-level translation output."""

    latest_slide: str
    kept_terms: list[str]
    slide_window: list[str]


class LLMTranslator:
    """Translator using Gemini or OpenAI with contextual prompting."""

    SYSTEM_PROMPT_TEMPLATE = """You are a professional simultaneous interpreter specializing in real-time subtitle translation from {source_language} to {target_language}.
{domain_section}
Output rules:
- Output ONLY the translated text. No explanations, no alternatives, no parenthetical notes.
- Keep proper nouns (person/org/product/place names), acronyms, and code identifiers
  EXACTLY as they appear in the source text (do not translate, transliterate, or normalize).
- If a term is ambiguous or unknown, keep it unchanged rather than guessing.
- Maintain strict terminology consistency with translations shown in <context>.
- If confidence indicators like [uncertain: ...] appear, infer meaning from context and translate naturally.
- Ignore any content inside <cache_padding>...</cache_padding>.
- Never add content that does not exist in the source text.

Japanese subtitle guidelines:
- Use natural, colloquial Japanese — avoid overly literal or stiff translations.
- Default register: ですます調 for presentations/lectures; plain form (だ・である) for narration.
- Keep sentences concise; subtitles must be readable at a glance.
- Prefer active voice and shorter clauses over long subordinate chains.
- Do not add filler phrases (「なお」「つまり」「ということです」) unless present in the source.
- For numbers and units, use the convention natural in Japanese (e.g., 百万 for million if fitting).
{dictionary_section}"""

    def __init__(
        self,
        provider: Literal["gemini", "openai"],
        api_key: str,
        model: str,
        source_language: str = "English",
        target_language: str = "Japanese",
        dictionary_path: Path | str | None = None,
        context_window_size: int = 5,
        domain: str = "general",
        thinking_budget: int = 0,
    ) -> None:
        """Initialize LLM translator.

        Args:
            provider: LLM provider ("gemini" or "openai")
            api_key: API key for the provider
            model: Model name to use
            source_language: Source language name
            target_language: Target language name
            dictionary_path: Optional path to CSV dictionary file
            context_window_size: Number of previous lines to keep as context
        """
        self._provider = provider
        self._api_key = api_key
        self._model_name = model
        self._source_language = source_language
        self._target_language = target_language
        self._context_window_size = context_window_size
        self._domain = domain
        self._thinking_budget = thinking_budget

        self._openai_llm: BaseChatModel | None = None
        self._openai_structured_llm: Any | None = None
        self._context_buffer: list[str] = []
        self._slide_window: list[str] = []
        self._system_prompt_cache: str | None = None

        self._gemini_client: Any | None = None

        # Load dictionary if provided
        self._dictionary = TermDictionary()
        if dictionary_path:
            self.load_dictionary(dictionary_path)

    def load_dictionary(self, path: Path | str) -> int:
        """Load terminology dictionary from CSV file.

        Args:
            path: Path to CSV file (format: source_term,target_term,notes)

        Returns:
            Number of entries loaded
        """
        count = self._dictionary.load_csv(path)
        self._system_prompt_cache = None
        return count

    @property
    def dictionary(self) -> TermDictionary:
        """Get the terminology dictionary."""
        return self._dictionary

    async def prepare(self) -> None:
        """Warm up translator state."""
        # Context caching is not used (requires paid Gemini plan).
        pass

    def refresh_cache(self) -> None:
        """Invalidate cached system prompt."""
        self._system_prompt_cache = None

    def _get_openai_llm(self) -> BaseChatModel:
        """Get or create LLM instance for OpenAI.

        Returns:
            LangChain chat model
        """
        if self._openai_llm is None:
            from langchain_openai import ChatOpenAI

            self._openai_llm = ChatOpenAI(
                model=self._model_name,
                api_key=self._api_key,
                temperature=0.1,
            )
        return self._openai_llm

    def _get_system_prompt(self) -> str:
        """Get system prompt with language settings and dictionary.

        Returns:
            Formatted system prompt
        """
        if self._system_prompt_cache is not None:
            return self._system_prompt_cache

        domain_desc = _DOMAIN_DESCRIPTIONS.get(self._domain, "")
        domain_section = f"\n{domain_desc}" if domain_desc else ""

        dictionary_section = ""
        if self._dictionary:
            formatted = self._dictionary.format_for_prompt()
            dictionary_section = f"\n\n<dictionary>\n{formatted}\n</dictionary>"

        self._system_prompt_cache = self.SYSTEM_PROMPT_TEMPLATE.format(
            source_language=self._source_language,
            target_language=self._target_language,
            domain_section=domain_section,
            dictionary_section=dictionary_section,
        )
        return self._system_prompt_cache

    def _build_user_prompt(
        self,
        text: str,
        *,
        src_context: list[str] | None = None,
        tgt_context: list[str] | None = None,
    ) -> str:
        if src_context is not None:
            src_lines = src_context[-self._context_window_size:]
            tgt_lines = (tgt_context or [])[-self._context_window_size:]
        else:
            src_lines = self._context_buffer[-self._context_window_size:]
            tgt_lines = self._slide_window[-self._context_window_size:]

        # Build bilingual context pairs (EN + JA) for better term consistency
        if src_lines and tgt_lines:
            pairs = zip(src_lines[-len(tgt_lines):], tgt_lines)
            context_block = "\n".join(
                f"[EN] {src}\n[JA] {tgt}" for src, tgt in pairs
            )
        elif src_lines:
            context_block = "\n".join(src_lines)
        else:
            context_block = ""

        return f"<context>\n{context_block}\n</context>\n<target>\n{text}\n</target>"

    def _get_gemini_client(self) -> Any:
        if self._gemini_client is None:
            from google import genai

            self._gemini_client = genai.Client(api_key=self._api_key)
        return self._gemini_client

    def _get_openai_structured_llm(self) -> Any:
        if self._openai_structured_llm is None:
            self._openai_structured_llm = self._get_openai_llm().with_structured_output(
                TranslationLLMOutput
            )
        return self._openai_structured_llm

    async def _translate_gemini_direct(self, prompt: str, max_retries: int = 5) -> str:
        """Gemini APIを直接呼び出して翻訳する（LangChain・構造化出力を省略）。

        - structured output（JSON生成）を使わず平文で返すため高速
        - thinking_budget=0 でThinkingを無効化
        - システムプロンプトを毎回直接渡す（コンテキストキャッシュ不使用）
        - 503/429エラー時は指数バックオフでリトライ
        """
        from google.genai import types

        client = self._get_gemini_client()
        system_prompt = self._get_system_prompt()

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
            thinking_config=types.ThinkingConfig(thinking_budget=self._thinking_budget),
        )

        for attempt in range(max_retries):
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=self._model_name,
                    contents=prompt,
                    config=config,
                )
                return (response.text or "").strip()
            except Exception as e:
                err = str(e)
                retryable = any(k in err for k in ("503", "429", "UNAVAILABLE", "ResourceExhausted", "quota"))
                if attempt < max_retries - 1 and retryable:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning("Gemini API error (%s), retrying in %.1fs (attempt %d/%d)", e, wait, attempt + 1, max_retries)
                    await asyncio.sleep(wait)
                else:
                    raise

    async def translate(
        self,
        text: str,
        *,
        src_context: list[str] | None = None,
        tgt_context: list[str] | None = None,
        update_context: bool = True,
    ) -> TranslationOutput:
        """Translate text using LLM.

        Args:
            text: Text to translate
            src_context: Explicit source-language context lines (shared context mode)
            tgt_context: Explicit target-language context lines (shared context mode)
            update_context: Whether to update internal context buffers

        Returns:
            Translation output including the latest slide and current slide window
        """
        if not text.strip():
            return TranslationOutput(latest_slide="", kept_terms=[], slide_window=[])

        prompt = self._build_user_prompt(text, src_context=src_context, tgt_context=tgt_context)

        if self._provider == "gemini":
            # 直接API呼び出し（LangChain・structured output不使用）
            translation = await self._translate_gemini_direct(prompt)
            kept_terms: list[str] = []
        else:
            llm = self._get_openai_structured_llm()
            messages = [
                SystemMessage(content=self._get_system_prompt()),
                HumanMessage(content=prompt),
            ]
            output = await llm.ainvoke(messages)
            translation = output.latest_slide.strip()
            kept_terms = list(output.kept_terms or [])

        should_update_context = update_context and src_context is None
        if should_update_context:
            self._context_buffer.append(text)
            if len(self._context_buffer) > self._context_window_size:
                self._context_buffer.pop(0)

        if should_update_context:
            self._slide_window.append(translation)
            if len(self._slide_window) > self._context_window_size:
                self._slide_window.pop(0)

        return TranslationOutput(
            latest_slide=translation,
            kept_terms=kept_terms,
            slide_window=list(self._slide_window),
        )

    async def translate_stream(self, text: str) -> AsyncIterator[str]:
        """Translate text with streaming output.

        Args:
            text: Text to translate

        Yields:
            Translation chunks
        """
        if not text.strip():
            return

        result = await self.translate(text)
        yield result.latest_slide

    def clear_context(self) -> None:
        """Clear the context buffer."""
        self._context_buffer.clear()
        self._slide_window.clear()
