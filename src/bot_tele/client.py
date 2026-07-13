"""Async client for any OpenAI-compatible chat API (OpenRouter or local)."""

from collections.abc import Sequence
from typing import Final

import openai
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from .config import Settings
from .conversation import ChatMessage, Role
from .errors import ModelError

SYSTEM_PROMPT: Final = "You are a helpful assistant inside a Telegram bot."

DOCUMENT_ANALYSIS_PROMPT: Final = (
    "You are a helpful assistant inside a Telegram bot. "
    "The user uploaded a document. Summarize its key points and explain "
    "what it contains in a concise, structured way so the user can ask "
    "follow-up questions about it."
)


class ChatClient:
    """Thin async wrapper over an OpenAI-compatible chat completions API.

    Works with OpenRouter (cloud) and local servers such as Ollama or
    LM Studio simply by pointing ``base_url`` at the local endpoint.
    """

    def __init__(self, settings: Settings) -> None:
        """Build the OpenAI client pointed at the configured endpoint."""
        self._model: str = settings.openrouter_model
        headers: dict[str, str] = {}
        if settings.openrouter_referer:
            headers["HTTP-Referer"] = settings.openrouter_referer
        if settings.openrouter_title:
            headers["X-Title"] = settings.openrouter_title
        self._client: AsyncOpenAI = AsyncOpenAI(
            api_key=settings.openrouter_api_key or "not-needed",
            base_url=settings.openrouter_base_url,
            timeout=30.0,
            default_headers=headers,
        )

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        """Send the conversation to the model and return its reply text."""
        payload: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
            *(self._to_param(msg) for msg in messages),
        ]
        return await self._request(payload)

    async def analyze_document(self, text: str) -> str:
        """Analyze an uploaded document's text and return a summary."""
        payload: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system", content=DOCUMENT_ANALYSIS_PROMPT
            ),
            ChatCompletionUserMessageParam(role="user", content=text),
        ]
        return await self._request(payload)

    async def _request(self, payload: list[ChatCompletionMessageParam]) -> str:
        """Send `payload` to the model and return the reply content."""
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=payload,
            )
        except openai.APIError as e:
            raise ModelError(f"Model request failed: {e}") from e
        if not response.choices:
            raise ModelError("Model returned no completion choices")
        content = response.choices[0].message.content
        if content is None:
            raise ModelError("Model returned empty content")
        return content

    @staticmethod
    def _to_param(message: ChatMessage) -> ChatCompletionMessageParam:
        content = message["content"]
        match message["role"]:
            case Role.SYSTEM:
                return ChatCompletionSystemMessageParam(role="system", content=content)
            case Role.USER:
                return ChatCompletionUserMessageParam(role="user", content=content)
            case Role.ASSISTANT:
                return ChatCompletionAssistantMessageParam(
                    role="assistant", content=content
                )
