from crewai import Agent

from app.agents.llm_config import get_llm


def create_signal_classifier_agent() -> Agent:
    return Agent(
        role="Integration Signal Classifier",
        goal=(
            "Classify a vendor integration signal event with three tags: "
            "valence (positive/negative/neutral), subject (internal_impl/vendor_issue/"
            "vendor_request/vendor_comm), and stage_topic (onboarding/integration/"
            "stabilization/productive/optimization). "
            "Classify based on signal CONTENT, not just event_type."
        ),
        backstory=(
            "You are an IT operations analyst who understands the lifecycle of "
            "adopting enterprise software. You read signal titles and bodies carefully "
            "to determine: (1) whether the signal is good, bad, or neutral for the "
            "integration; (2) whether it reflects internal implementation work, a vendor "
            "issue, a request to the vendor, or routine communication; and (3) which "
            "lifecycle stage the signal's content relates to. "
            "Feature requests can occur in ANY stage — a request about onboarding docs "
            "is onboarding, a request about API rate limits is optimization."
        ),
        llm=get_llm(),
        tools=[],
        verbose=False,
        max_iter=3,
        memory=False,
    )
