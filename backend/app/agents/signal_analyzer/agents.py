from crewai import Agent

from app.agents.llm_config import get_llm, get_llm_creative


def create_signal_summarizer() -> Agent:
    return Agent(
        role="Signal Summarizer",
        goal=(
            "Analyze raw signal events from vendor software integrations and produce a clear, "
            "categorized summary with trend assessment."
        ),
        backstory=(
            "You are an expert at analyzing operational signals from software integrations. "
            "You categorize events by type and severity, identify patterns, and assess whether "
            "the overall trend is improving, stable, or degrading."
        ),
        llm=get_llm(),
        verbose=True,
    )


def create_health_scorer() -> Agent:
    return Agent(
        role="Integration Health Scorer",
        goal=(
            "Score the health of a vendor software integration on a 0-100 scale with breakdowns "
            "for reliability, support quality, and performance."
        ),
        backstory=(
            "You are a quantitative analyst specializing in vendor integration health assessment. "
            "You use a consistent rubric to score integrations: reliability (uptime, error rates), "
            "support quality (response time, resolution), and performance (latency, throughput). "
            "Higher scores mean healthier integrations."
        ),
        llm=get_llm(),
        verbose=True,
    )


def create_review_drafter() -> Agent:
    return Agent(
        role="Customer Review Writer",
        goal=(
            "Draft a customer review of vendor software strictly grounded in actual signal data. "
            "NEVER fabricate, infer, or embellish experiences that are not directly evidenced by "
            "the signals. If data is limited, write a shorter review that acknowledges this."
        ),
        backstory=(
            "You write evidence-based customer reviews. Every claim in your review must trace "
            "back to a specific signal event. You write in first-person plural ('we') and your "
            "tone is candid and helpful. When you only have a few signals, you write a brief, "
            "honest review that covers only what is known — you NEVER pad with assumptions about "
            "uptime, performance, or support quality that the data doesn't show. A one-paragraph "
            "review backed by real data is far better than a long review filled with fabrications."
        ),
        llm=get_llm_creative(),
        verbose=True,
    )
