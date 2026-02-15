import json
import re

import structlog
from crewai import Crew, Process

from app.agents.signal_analyzer.agents import (
    create_health_scorer,
    create_review_drafter,
    create_signal_summarizer,
)
from app.agents.signal_analyzer.tasks import (
    create_draft_task,
    create_scoring_task,
    create_summarize_task,
)

logger = structlog.get_logger()


class SignalAnalysisCrew:
    def __init__(self, software_name: str, vendor_name: str, events_json: str, intended_use: str | None = None):
        self.software_name = software_name
        self.vendor_name = vendor_name
        self.events_json = events_json
        self.intended_use = intended_use

    def run(self) -> dict | None:
        summarizer = create_signal_summarizer()
        scorer = create_health_scorer()
        drafter = create_review_drafter()

        summarize_task = create_summarize_task(
            summarizer, self.software_name, self.vendor_name, self.events_json, self.intended_use
        )
        scoring_task = create_scoring_task(scorer, self.software_name, self.intended_use)
        draft_task = create_draft_task(drafter, self.software_name, self.vendor_name, self.intended_use)

        crew = Crew(
            agents=[summarizer, scorer, drafter],
            tasks=[summarize_task, scoring_task, draft_task],
            process=Process.sequential,
            verbose=True,
        )

        logger.info(
            "signal_analysis_crew_started",
            software=self.software_name,
            vendor=self.vendor_name,
        )

        result = crew.kickoff()

        parsed = self._parse_results(result)
        logger.info(
            "signal_analysis_crew_completed",
            software=self.software_name,
            has_summary=parsed.get("summary") is not None,
            has_score=parsed.get("score") is not None,
            has_draft=parsed.get("draft") is not None,
        )
        return parsed

    def _parse_results(self, crew_result) -> dict:
        """Extract structured data from crew task outputs."""
        parsed = {}

        try:
            tasks_output = crew_result.tasks_output if hasattr(crew_result, "tasks_output") else []

            if len(tasks_output) > 0:
                parsed["summary"] = self._extract_json(
                    tasks_output[0].raw if hasattr(tasks_output[0], "raw") else str(tasks_output[0])
                )

            if len(tasks_output) > 1:
                parsed["score"] = self._extract_json(
                    tasks_output[1].raw if hasattr(tasks_output[1], "raw") else str(tasks_output[1])
                )

            if len(tasks_output) > 2:
                parsed["draft"] = self._extract_json(
                    tasks_output[2].raw if hasattr(tasks_output[2], "raw") else str(tasks_output[2])
                )

        except Exception as e:
            logger.warning("signal_analysis_parse_partial", error=str(e))
            if not parsed:
                raw = crew_result.raw if hasattr(crew_result, "raw") else str(crew_result)
                fallback = self._extract_json(raw)
                if fallback:
                    parsed = fallback if isinstance(fallback, dict) else {}

        return parsed

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from text that may contain markdown or prose."""
        if not text:
            return None

        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        code_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        obj_match = re.search(r"\{.*\}", text, re.DOTALL)
        if obj_match:
            try:
                return json.loads(obj_match.group())
            except json.JSONDecodeError:
                pass

        return None
