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

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from translator_service.dictionary import TermDictionary


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

    SYSTEM_PROMPT_TEMPLATE = """You are a professional simultaneous interpreter.
Translate from {source_language} to {target_language}.
Rules:
- Keep proper nouns (person/org/product/place names), acronyms, and code identifiers
  EXACTLY as they appear in the source text (do not translate, transliterate, or
  normalize).
- If a term is ambiguous/unknown, keep it unchanged rather than guessing.
If confidence indicators like [uncertain: ...] appear, infer meaning from context.
Maintain the original tone and style.
{dictionary_section}"""

    def __init__(
        self,
        provider: Literal["gemini", "openai"],
        api_key: str,
        model: str,
        source_language: str = "English",
        target_language: str = "Japanese",
        dictionary_path: Path | str | None = None,
        context_window_size: int = 3,
    ) -> None:
        """Initialize LLM translator."""
        self._provider = provider
        self._api_key = api_key
        self._model_name = model
        self._source_language = source_language
        self._target_language = target_language
        self._context_window_size = context_window_size

        self._openai_llm: BaseChatModel | None = None
        self._openai_structured_llm: Any | None = None
        self._context_buffer: list[str] = []
        self._slide_window: list[str] = []
        self._system_prompt_cache: str | None = None

        self._gemini_client: Any | None = None

        self._dictionary = TermDictionary()
        if dictionary_path:
            self.load_dictionary(dictionary_path)

    def load_dictionary(self, path: Path | str) -> int:
        """Load terminology dictionary from CSV file."""
        count = self._dictionary.load_csv(path)
        self._system_prompt_cache = None
        return count

    @property
    def dictionary(self) -> TermDictionary:
        return self._dictionary

    async def prepare(self) -> None:
        """Warm up translator state."""
        # Context caching is not used (requires paid Gemini plan).
        pass

    def refresh_cache(self) -> None:
        """Invalidate cached system prompt."""
        self._system_prompt_cache = None

    def _get_openai_llm(self) -> BaseChatModel:
        if self._openai_llm is None:
            from langchain_openai import ChatOpenAI

            self._openai_llm = ChatOpenAI(
                model=self._model_name,
                api_key=self._api_key,
                temperature=0.3,
            )
        return self._openai_llm

    def _get_system_prompt(self) -> str:
        if self._system_prompt_cache is not None:
            return self._system_prompt_cache

        dictionary_section = ""
        if self._dictionary:
            formatted = self._dictionary.format_for_prompt()
            dictionary_section = f"\n\n<dictionary>\n{formatted}\n</dictionary>"

        self._system_prompt_cache = self.SYSTEM_PROMPT_TEMPLATE.format(
            source_language=self._source_language,
            target_language=self._target_language,
            dictionary_section=dictionary_section,
        )
        return self._system_prompt_cache

    def _build_user_prompt(
        self,
        text: str,
        *,
        context_lines: list[str] | None = None,
    ) -> str:
        if context_lines is None:
            context_lines = self._context_buffer[-self._context_window_size :]
        else:
            context_lines = context_lines[-self._context_window_size :]
        context_block = "\n".join(context_lines)
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
        """Gemini APIを直接呼び出して翻訳する（コンテキストキャッシュ不使用）。

        503/429エラー時は指数バックオフでリトライ。
        """
        from google.genai import types

        client = self._get_gemini_client()
        system_prompt = self._get_system_prompt()

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3,
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
        context_lines: list[str] | None = None,
        update_context: bool = True,
    ) -> TranslationOutput:
        """Translate text using LLM."""
        if not text.strip():
            return TranslationOutput(latest_slide="", kept_terms=[], slide_window=[])

        prompt = self._build_user_prompt(text, context_lines=context_lines)

        if self._provider == "gemini":
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

        should_update_context = update_context and context_lines is None
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
        """Translate text with streaming output."""
        if not text.strip():
            return

        result = await self.translate(text)
        yield result.latest_slide

    def clear_context(self) -> None:
        """Clear the context buffer."""
        self._context_buffer.clear()
        self._slide_window.clear()
