"""Thin async wrapper around the Anthropic SDK for direct LLM calls.

Bypasses CrewAI overhead for parallelizable summarization tasks.
"""

import asyncio
import re

import structlog
from anthropic import AsyncAnthropic

from app.config import settings

logger = structlog.get_logger()

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"\*(.+?)\*")
_MD_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_BULLET = re.compile(r"^[ \t]*[-*]\s+", re.MULTILINE)


def _strip_markdown(text: str) -> str:
    """Remove common markdown formatting from LLM output."""
    text = _MD_BOLD.sub(r"\1", text)
    text = _MD_ITALIC.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BULLET.sub("", text)
    return text.strip()


async def summarize(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> str:
    """Single async LLM call for summarization."""
    client = _get_client()
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return _strip_markdown(response.content[0].text)


async def parallel_summarize(
    calls: list[tuple[str, str]],
    temperature: float = 0.2,
) -> list[str]:
    """Run multiple summarize calls in parallel.

    Each element in `calls` is (system_prompt, user_prompt).
    Returns results in the same order.
    """
    return await asyncio.gather(
        *[summarize(sys, usr, temperature=temperature) for sys, usr in calls]
    )
