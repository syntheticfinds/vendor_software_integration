from crewai import Agent

from app.agents.llm_config import get_llm


def create_jira_routing_agent() -> Agent:
    return Agent(
        role="Jira Event Router",
        goal=(
            "Determine which registered software product a Jira issue event belongs to, "
            "given the Jira event content and a list of candidate software registrations."
        ),
        backstory=(
            "You are an IT operations analyst who understands how companies organize Jira "
            "projects for different vendor software products. You analyze issue keys, project "
            "keys, issue summaries, descriptions, and comments to determine which specific "
            "vendor software an issue relates to. You consider software names, vendor names, "
            "intended use descriptions, and any integration identifiers to make your determination. "
            "When uncertain, you indicate low confidence rather than guessing."
        ),
        llm=get_llm(),
        tools=[],
        verbose=False,
        max_iter=3,
        memory=False,
    )
