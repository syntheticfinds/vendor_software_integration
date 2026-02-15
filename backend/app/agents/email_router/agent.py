from crewai import Agent

from app.agents.llm_config import get_llm


def create_email_routing_agent() -> Agent:
    return Agent(
        role="Email Router",
        goal=(
            "Determine which registered software product an email belongs to, "
            "given the email content (subject, sender, body snippet) and a list "
            "of candidate software registrations that share the same support email."
        ),
        backstory=(
            "You are an IT operations analyst who reviews email correspondence between "
            "a company and its software vendors. Multiple software products from the same "
            "vendor may share a single support email address. Your job is to determine "
            "which specific software product an email is about based on the subject line, "
            "body content, sender context, and each candidate's intended use description. "
            "When the email is ambiguous or could apply to any product, you indicate low "
            "confidence rather than guessing."
        ),
        llm=get_llm(),
        tools=[],
        verbose=False,
        max_iter=3,
        memory=False,
    )
