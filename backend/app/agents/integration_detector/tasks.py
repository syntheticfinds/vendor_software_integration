from crewai import Task


def create_detection_task(agent, company_id: str) -> Task:
    return Task(
        description=(
            f"Analyze unprocessed emails for company {company_id}. "
            "First, fetch the unprocessed emails using the fetch_unprocessed_emails tool. "
            "For each email:\n"
            "1. Determine if it indicates new software adoption (welcome emails, "
            "setup confirmations, license activations, account provisioning).\n"
            "2. Ignore marketing emails, newsletters, promotional content, and spam.\n"
            "3. If it's a genuine adoption signal, extract the vendor_name and software_name.\n"
            "4. Check if this software is already registered for this company using "
            "the check_software_registry tool.\n"
            "5. Assign a confidence_score between 0.0 and 1.0.\n"
            "Only include detections with confidence >= 0.5.\n"
        ),
        expected_output=(
            "A JSON array of detections. Each detection must have these exact fields: "
            "detected_vendor_name (string), detected_software (string), "
            "confidence_score (float between 0.0 and 1.0), "
            "is_new (boolean - true if not already registered), "
            "reasoning (string - brief explanation of why this is a detection). "
            "Example: [{\"detected_vendor_name\": \"Slack\", \"detected_software\": \"Slack\", "
            "\"confidence_score\": 0.95, \"is_new\": true, "
            "\"reasoning\": \"Welcome email confirming workspace creation\"}]"
        ),
        agent=agent,
    )
