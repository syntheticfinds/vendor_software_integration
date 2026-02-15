from crewai import Agent

from app.agents.llm_config import get_llm
from app.agents.integration_detector.tools import EmailFetchTool, SoftwareRegistryTool


def create_integration_detector_agent(
    email_tool: EmailFetchTool,
    registry_tool: SoftwareRegistryTool,
) -> Agent:
    return Agent(
        role="Software Integration Detector",
        goal=(
            "Analyze email content to identify new vendor software being adopted "
            "by the company. Detect vendor names, software products, and assess "
            "confidence that this represents actual software adoption (not spam or marketing)."
        ),
        backstory=(
            "You are a meticulous IT analyst who reads company emails to detect "
            "when new software tools are being onboarded. You distinguish between "
            "actual adoption signals (welcome emails, setup confirmations, license "
            "activations) and noise (marketing, spam, newsletters). "
            "You only report genuine software adoption signals."
        ),
        llm=get_llm(),
        tools=[email_tool, registry_tool],
        verbose=True,
        max_iter=10,
        memory=False,
    )
