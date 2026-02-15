from crewai import Agent, Task


def create_summarize_task(
    agent: Agent, software_name: str, vendor_name: str, events_json: str, intended_use: str | None
) -> Task:
    use_context = ""
    if intended_use:
        use_context = (
            f"\nThe company adopted {software_name} for the following intended use:\n"
            f'"{intended_use}"\n\n'
            "When analyzing events, note which ones relate directly to this intended use "
            "and which represent side concerns (e.g., general reliability vs. specific feature gaps).\n"
        )

    return Task(
        description=(
            f"Analyze the following signal events for {software_name} by {vendor_name}.\n"
            f"{use_context}"
            f"Events JSON:\n{events_json}\n\n"
            "IMPORTANT: Read the title and body of each event carefully to determine its actual "
            "sentiment. The same event_type can be positive or negative depending on content:\n"
            '- A comment_added saying "502 root cause found, vendor bug confirmed" is NEGATIVE\n'
            '- A comment_added saying "Security validation passed, all checks green" is POSITIVE\n'
            '- A ticket_created about "Complete outage" is strongly NEGATIVE\n'
            '- A ticket_created about "Minor UI suggestion" is mildly NEGATIVE or NEUTRAL\n'
            "- A support_email about planned maintenance is NEUTRAL\n"
            "- A support_email about a breaking API change is NEGATIVE\n\n"
            "Produce a JSON summary with:\n"
            '- "summary": a 2-3 sentence overview\n'
            '- "categories": count of events by severity (critical, high, medium, low)\n'
            '- "event_types": count of events by type\n'
            '- "trend": one of "improving", "stable", "degrading"\n'
            '- "key_issues": list of the top 3 most important issues\n'
            '- "what_works": list of specific things working well (backed by signal data)\n'
            '- "what_doesnt": list of specific things not working well (backed by signal data)\n'
            '- "event_sentiments": for EACH event, classify its sentiment based on its content as '
            '"positive", "negative", or "neutral". Return as a list of objects: '
            '[{"title": "...", "sentiment": "positive|negative|neutral", "reasoning": "brief explanation"}]\n'
        ),
        expected_output=(
            "A JSON object with keys: summary, categories, event_types, trend, key_issues, "
            "what_works, what_doesnt, event_sentiments"
        ),
        agent=agent,
    )


def create_scoring_task(agent: Agent, software_name: str, intended_use: str | None) -> Task:
    if intended_use:
        fitness_section = (
            f'- Fitness for Purpose (20% weight): How well does {software_name} serve the intended use: "{intended_use}"?\n'
            "  Start at 75. For each event whose content relates to the core use case:\n"
            "    positive sentiment → +5 to +15 (scaled by severity)\n"
            "    negative sentiment → -5 to -20 (scaled by severity)\n"
            "  Adjust the other weights to: Reliability 30%, Support Quality 25%, Performance 25%.\n\n"
        )
        breakdown_keys = '{"reliability": N, "support_quality": N, "performance": N, "fitness_for_purpose": N}'
    else:
        fitness_section = ""
        breakdown_keys = '{"reliability": N, "support_quality": N, "performance": N}'

    if intended_use:
        weights = "Reliability 30%, Support Quality 25%, Performance 25%, Fitness for Purpose 20%"
    else:
        weights = "Reliability 40%, Support Quality 30%, Performance 30%"

    return Task(
        description=(
            f"Based on the signal summary for {software_name}, calculate a health score.\n\n"
            "IMPORTANT: Use the event_sentiments from the summary to score each event based on\n"
            "what it ACTUALLY describes, not just its severity level. The same event type can\n"
            "help or hurt depending on its content.\n\n"
            "Scoring approach — start each category at 75 (healthy baseline), then adjust:\n\n"
            "- Reliability: How stable and available is the integration?\n"
            "  For each event, use its content sentiment to determine direction:\n"
            "    positive (resolved issues, uptime confirmations) → +2 to +8 (scaled by severity)\n"
            "    negative (outages, errors, failures) → -3 to -15 (scaled by severity: critical=highest)\n"
            "    neutral (informational, routine) → small nudge ±1\n\n"
            "- Support Quality: How responsive and effective is vendor support?\n"
            "  positive (issues resolved quickly, helpful responses) → +3 to +10\n"
            "  negative (escalations, slow responses, unresolved) → -2 to -8\n"
            "  neutral (acknowledgments, status updates) → +1 to +3 (engagement is mildly good)\n"
            "  NOTE: Even negative events give a small support boost if they show the issue is\n"
            "  being tracked (e.g., a ticket filed = someone engaged the support process).\n\n"
            "- Performance: How well does the integration perform (speed, throughput, reliability)?\n"
            "  positive (performance improvements, optimizations confirmed) → +2 to +8\n"
            "  negative (slowness, timeouts, degradation) → -3 to -12 (scaled by severity)\n"
            "  neutral → small nudge ±1\n\n"
            f"{fitness_section}"
            f"Weights: {weights}\n\n"
            "Clamp all category scores to 0-100. Compute the overall weighted score.\n\n"
            "Produce a JSON object with:\n"
            f'- "score": overall weighted score (0-100)\n'
            f'- "category_breakdown": {breakdown_keys}\n'
        ),
        expected_output=(
            "A JSON object with keys: score, category_breakdown"
        ),
        agent=agent,
    )


def create_draft_task(
    agent: Agent, software_name: str, vendor_name: str, intended_use: str | None
) -> Task:
    use_instructions = ""
    if intended_use:
        use_instructions = (
            f'   - States the intended use up front: "{intended_use}"\n'
            "   - Evaluates how well the software fulfills that intended use, citing specific signals\n"
        )
    else:
        use_instructions = (
            "   - Mentions what the software is used for based on context from the signals\n"
        )

    return Task(
        description=(
            f"Write a customer review of {software_name} by {vendor_name}.\n\n"
            "CRITICAL RULE: Every statement in the review must be directly backed by a specific\n"
            "signal event from the summary. Do NOT fabricate, assume, or infer any experiences\n"
            "that are not explicitly present in the signal data. Specifically:\n"
            "- Do NOT claim uptime/reliability is good unless a signal confirms it\n"
            "- Do NOT describe performance characteristics unless a signal mentions them\n"
            "- Do NOT praise support quality unless a resolved ticket or helpful response is in the data\n"
            "- Do NOT describe features, scaling behavior, or product capabilities unless a signal references them\n\n"
            "SCALE THE REVIEW TO THE DATA:\n"
            "- 1-2 signals: Write 1-2 short paragraphs. Acknowledge this is an early-stage review.\n"
            "- 3-6 signals: Write a moderate review with what-went-well and what-didn't sections.\n"
            "- 7+ signals: Write a full review with detailed sections.\n"
            "A brief, honest review is always better than a padded one.\n\n"
            "Using the signal summary and health score from previous analysis:\n"
            "1. Write a short review title\n"
            "2. Write the review body that:\n"
            "   - Uses first-person plural ('we', 'our team')\n"
            f"{use_instructions}"
            "   - Only includes 'What went well' if there are positive signals to cite\n"
            "   - Only includes 'What didn't go well' if there are negative signals to cite\n"
            "   - References actual events from the data (titles, dates, specifics)\n"
            "   - If data is thin, says so: 'Based on our limited experience so far...'\n\n"
            "Produce a JSON object with:\n"
            '- "subject": review title/headline\n'
            '- "body": full review text\n'
        ),
        expected_output=(
            "A JSON object with keys: subject, body"
        ),
        agent=agent,
    )
