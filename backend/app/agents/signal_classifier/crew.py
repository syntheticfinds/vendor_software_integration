import json
import re

import structlog
from crewai import Crew, Process

from app.agents.signal_classifier.agent import create_signal_classifier_agent
from app.agents.signal_classifier.tasks import create_classification_task

logger = structlog.get_logger()

VALID_VALENCES = {"positive", "negative", "neutral"}
VALID_SUBJECTS = {"internal_impl", "vendor_issue", "vendor_request", "vendor_comm"}
VALID_STAGE_TOPICS = {"onboarding", "integration", "stabilization", "productive", "optimization"}
VALID_HEALTH_CATEGORIES = {"reliability", "performance", "fitness_for_purpose"}


class SignalClassifierCrew:
    """Single-agent crew for classifying signal events."""

    def __init__(
        self,
        source_type: str,
        event_type: str,
        severity: str,
        title: str,
        body: str,
        software_name: str,
        days_since_registration: int,
    ):
        self.source_type = source_type
        self.event_type = event_type
        self.severity = severity
        self.title = title
        self.body = body
        self.software_name = software_name
        self.days_since_registration = days_since_registration

    def run(self) -> dict:
        """Run the classification crew.

        Returns {"valence": str, "subject": str, "stage_topic": str} or {} on failure.
        """
        agent = create_signal_classifier_agent()
        task = create_classification_task(
            agent,
            self.source_type,
            self.event_type,
            self.severity,
            self.title,
            self.body,
            self.software_name,
            self.days_since_registration,
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        try:
            result = crew.kickoff()
            raw = result.raw if hasattr(result, "raw") else str(result)
            parsed = self._parse_result(raw)
            if self._validate(parsed):
                # Normalize health_categories — ensure it's always a list of valid values
                raw_cats = parsed.get("health_categories", [])
                if isinstance(raw_cats, list):
                    parsed["health_categories"] = [
                        c for c in raw_cats if c in VALID_HEALTH_CATEGORIES
                    ]
                else:
                    parsed["health_categories"] = []
                logger.info(
                    "signal_classifier_crew_completed",
                    valence=parsed.get("valence"),
                    subject=parsed.get("subject"),
                    stage_topic=parsed.get("stage_topic"),
                    health_categories=parsed.get("health_categories"),
                )
                return parsed
            logger.warning("signal_classifier_invalid_tags", parsed=parsed)
            return {}
        except Exception as e:
            logger.warning("signal_classifier_crew_failed", error=str(e))
            return {}

    def _parse_result(self, raw: str) -> dict:
        """Extract JSON from crew output (3-tier parsing)."""
        # Direct parse
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass

        # Markdown code block
        code_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Bare JSON object
        obj_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if obj_match:
            try:
                return json.loads(obj_match.group())
            except json.JSONDecodeError:
                pass

        logger.warning("signal_classifier_parse_failed", raw_output=raw[:500])
        return {}

    def _validate(self, tags: dict) -> bool:
        return (
            tags.get("valence") in VALID_VALENCES
            and tags.get("subject") in VALID_SUBJECTS
            and tags.get("stage_topic") in VALID_STAGE_TOPICS
        )
