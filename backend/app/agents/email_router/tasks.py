from crewai import Task


def create_email_routing_task(agent, email_summary: str, candidates_json: str) -> Task:
    return Task(
        description=(
            "An email has been received that matches a shared support email address used by "
            "multiple software products. Determine which specific software this email is about.\n\n"
            f"## Email Content\n{email_summary}\n\n"
            f"## Candidate Software Registrations\n{candidates_json}\n\n"
            "Analyze the email and determine which ONE software registration this email belongs to. "
            "Consider:\n"
            "1. Does the subject or body mention a specific software or vendor product name?\n"
            "2. Does the content relate to the intended_use of any candidate?\n"
            "3. Are there technical terms, feature names, or product-specific language that "
            "point to one candidate over others?\n\n"
            "If the email genuinely cannot be attributed to any single candidate, return a "
            "null matched_software_id with low confidence.\n\n"
            "Return your answer as a JSON object with exactly these fields:\n"
            '- "matched_software_id": a single software_id string, or null if no match\n'
            '- "confidence": float between 0.0 and 1.0\n'
            '- "reasoning": brief explanation of your routing decision\n'
        ),
        expected_output=(
            "A JSON object with keys: matched_software_id (UUID string or null), "
            "confidence (float 0.0-1.0), reasoning (string). "
            'Example: {"matched_software_id": "uuid-here", "confidence": 0.85, '
            '"reasoning": "Subject mentions Datadog APM and body discusses trace analysis"}'
        ),
        agent=agent,
    )
