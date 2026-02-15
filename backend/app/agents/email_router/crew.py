import json
import re

import structlog
from crewai import Crew, Process

from app.agents.email_router.agent import create_email_routing_agent
from app.agents.email_router.tasks import create_email_routing_task

logger = structlog.get_logger()


class EmailRoutingCrew:
    """Single-agent crew for routing emails to the correct software."""

    def __init__(self, email_summary: str, candidates: list[dict]):
        self.email_summary = email_summary
        self.candidates = candidates

    def run(self) -> dict:
        """Run the routing crew.

        Returns {"matched_software_id": str|None, "confidence": float, "reasoning": str}.
        """
        agent = create_email_routing_agent()
        task = create_email_routing_task(
            agent, self.email_summary, json.dumps(self.candidates, indent=2),
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
            logger.info(
                "email_routing_crew_completed",
                matched_id=parsed.get("matched_software_id"),
                confidence=parsed.get("confidence"),
            )
            return parsed
        except Exception as e:
            logger.error("email_routing_crew_failed", error=str(e))
            return {
                "matched_software_id": None,
                "confidence": 0.0,
                "reasoning": f"Crew error: {e}",
            }

    def _parse_result(self, raw: str) -> dict:
        """Extract JSON from crew output."""
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

        logger.warning("email_routing_parse_failed", raw_output=raw[:500])
        return {
            "matched_software_id": None,
            "confidence": 0.0,
            "reasoning": "Failed to parse crew output",
        }
