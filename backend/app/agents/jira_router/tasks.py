from crewai import Task


def create_routing_task(agent, event_summary: str, candidates_json: str) -> Task:
    return Task(
        description=(
            "A Jira event has been received and needs to be routed to the correct software.\n\n"
            f"## Jira Event\n{event_summary}\n\n"
            f"## Candidate Software Registrations\n{candidates_json}\n\n"
            "Analyze the Jira event content and determine which software registration(s) "
            "this event belongs to. Consider:\n"
            "1. Does the issue summary or description mention a specific software or vendor name?\n"
            "2. Does the Jira project key relate to any software's jira_workspace field?\n"
            "3. Does the issue content relate to the intended_use of any software?\n"
            "4. Are there domain or email clues that match a software's support_email?\n\n"
            "If the event clearly does not relate to ANY of the candidate software, return an "
            "empty matched_software_ids array with high confidence.\n\n"
            "Return your answer as a JSON object with exactly these fields:\n"
            '- "matched_software_ids": array of software_id strings that this event belongs to '
            "(usually exactly one; empty array if truly no match; multiple only if the event "
            "genuinely spans multiple products)\n"
            '- "confidence": float between 0.0 and 1.0\n'
            '- "reasoning": brief explanation of your routing decision\n'
        ),
        expected_output=(
            "A JSON object with keys: matched_software_ids (array of UUID strings), "
            "confidence (float 0.0-1.0), reasoning (string). "
            'Example: {"matched_software_ids": ["uuid-here"], "confidence": 0.85, '
            '"reasoning": "Issue summary mentions Datadog and project key matches"}'
        ),
        agent=agent,
    )
