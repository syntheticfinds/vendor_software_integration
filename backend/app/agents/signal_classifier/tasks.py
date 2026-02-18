from crewai import Agent, Task


def create_classification_task(
    agent: Agent,
    source_type: str,
    event_type: str,
    severity: str,
    title: str,
    body: str,
    software_name: str,
    days_since_registration: int,
) -> Task:
    return Task(
        description=(
            f"Classify this signal from the '{software_name}' integration.\n\n"
            f"Source: {source_type} | Event type: {event_type} | Severity: {severity}\n"
            f"Title: {title}\n"
            f"Body: {body[:1500]}\n"
            f"Days since software was registered: {days_since_registration}\n\n"
            "Return a JSON object with exactly four keys:\n"
            '- "valence": one of "positive", "negative", "neutral"\n'
            '- "subject": one of "internal_impl", "vendor_issue", "vendor_request", "vendor_comm"\n'
            '- "stage_topic": one of "onboarding", "integration", "stabilization", '
            '"productive", "optimization"\n'
            '- "health_categories": a list of zero or more of "reliability", '
            '"performance", "fitness_for_purpose"\n\n'
            "Classification guidelines:\n\n"
            "VALENCE — read the title and body carefully:\n"
            "- Resolved tickets, fixes confirmed, successful deployments = positive\n"
            "- Outages, errors, failures, breaking changes, crashes = negative\n"
            "- Feature requests, status updates, routine emails = neutral\n"
            "- A ticket_created about an error is negative; a ticket_resolved is positive\n"
            "- A vendor email saying 'planned for Q2' is neutral (acknowledgment)\n\n"
            "SUBJECT — who is doing what:\n"
            "- internal_impl: The company is doing work to adopt/configure/deploy/train on "
            "the software (e.g., 'Set up SSO', 'Deploy agent to staging', 'Train team')\n"
            "- vendor_issue: A problem caused by the vendor — bugs, outages, regressions, "
            "breaking changes, slow performance on vendor's side\n"
            "- vendor_request: Asking the vendor for something — feature requests, "
            "enhancement asks, capability gaps\n"
            "- vendor_comm: Routine vendor communication — maintenance notices, "
            "acknowledgments, follow-ups, roadmap updates\n\n"
            "STAGE_TOPIC — what lifecycle stage the content relates to:\n"
            "- onboarding: Initial setup, account creation, first config, team access, "
            "getting started, provisioning, invitations\n"
            "- integration: API connections, webhook setup, data migration, sync "
            "pipelines, SSO/OAuth, endpoint configuration, testing integrations\n"
            "- stabilization: Bug fixes, patches, outages, incidents, crashes, downtime, "
            "investigating errors, 5xx errors, degraded service, intermittent issues, "
            "edge cases, performance tuning, flaky behavior, regressions, breaking changes\n"
            "- productive: Routine usage, regular operations, steady-state, "
            "monthly reports, status updates, renewals (NOT outages or incidents)\n"
            "- optimization: Scaling, automation, cost optimization, advanced features, "
            "rate limits, batch processing, caching, throughput improvements\n\n"
            "HEALTH_CATEGORIES — which health score areas this signal is relevant to "
            "(can be multiple, or empty if none apply clearly):\n"
            "- reliability: Incidents, outages, downtime, uptime reports, errors, "
            "crashes, service availability, recovery, failover, SLA breaches\n"
            "- performance: Latency, slowness, timeouts, rate limiting, throttling, "
            "throughput issues, response time, API speed, load concerns\n"
            "- fitness_for_purpose: Feature requests, capability gaps, enhancement asks, "
            "missing functionality, workarounds for missing features, fulfillment of "
            "previously requested features\n"
            "- A signal can belong to multiple categories (e.g., 'API outage causing "
            "slow responses' is both reliability and performance)\n"
            "- Routine communication, internal implementation, and general updates "
            "typically get an empty list []\n\n"
            f"Time context: At {days_since_registration} days in, earlier stages are less "
            "likely but content always wins. If the content clearly describes onboarding "
            "activity, classify as onboarding regardless of time elapsed."
        ),
        expected_output=(
            'A JSON object with exactly four keys: '
            '{"valence": "...", "subject": "...", "stage_topic": "...", '
            '"health_categories": ["...", ...]}'
        ),
        agent=agent,
    )
