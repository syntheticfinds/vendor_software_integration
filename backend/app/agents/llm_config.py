import os

from crewai import LLM

from app.config import settings

# CrewAI's native Anthropic provider reads from the env var directly
if settings.ANTHROPIC_API_KEY:
    os.environ["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY


def get_llm() -> LLM:
    return LLM(
        model="anthropic/claude-sonnet-4-20250514",
        api_key=settings.ANTHROPIC_API_KEY,
        temperature=0.1,
        max_tokens=4096,
    )


def get_llm_creative() -> LLM:
    return LLM(
        model="anthropic/claude-sonnet-4-20250514",
        api_key=settings.ANTHROPIC_API_KEY,
        temperature=0.4,
        max_tokens=4096,
    )
