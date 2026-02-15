import json
import uuid
from datetime import datetime, timezone

import structlog
from crewai import Crew, Process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.integration_detector.agent import create_integration_detector_agent
from app.agents.integration_detector.tasks import create_detection_task
from app.agents.integration_detector.tools import EmailFetchTool, SoftwareRegistryTool
from app.monitoring.models import DetectedSoftware, MonitoredEmail

logger = structlog.get_logger()


class IntegrationDetectionCrew:
    def __init__(self, company_id: uuid.UUID, emails: list[dict], registered_software: list[dict]):
        self.company_id = company_id
        self.emails = emails
        self.registered_software = registered_software

    def run(self) -> list[dict]:
        email_tool = EmailFetchTool()
        email_tool._cached_emails = self.emails

        registry_tool = SoftwareRegistryTool()
        registry_tool._registered_software = self.registered_software

        agent = create_integration_detector_agent(email_tool, registry_tool)
        task = create_detection_task(agent, str(self.company_id))

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )

        logger.info("crew_started", crew="integration_detector", company_id=str(self.company_id))

        try:
            result = crew.kickoff()
            raw = result.raw if hasattr(result, 'raw') else str(result)

            # Try to parse JSON from the result
            detections = self._parse_detections(raw)
            logger.info(
                "crew_completed",
                crew="integration_detector",
                company_id=str(self.company_id),
                detection_count=len(detections),
            )
            return detections
        except Exception as e:
            logger.error(
                "crew_failed",
                crew="integration_detector",
                company_id=str(self.company_id),
                error=str(e),
            )
            return []

    def _parse_detections(self, raw: str) -> list[dict]:
        # Try to find JSON array in the response
        try:
            # Direct parse
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON array from markdown code block or mixed text
        import re
        json_match = re.search(r'\[.*\]', raw, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        logger.warning("crew_parse_failed", raw_output=raw[:500])
        return []


async def load_registered_software(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Load registered software for a company (used by detection loop)."""
    from app.software.models import SoftwareRegistration

    try:
        result = await db.execute(
            select(SoftwareRegistration).where(SoftwareRegistration.company_id == company_id)
        )
        registered = result.scalars().all()
        return [
            {"id": str(s.id), "vendor_name": s.vendor_name, "software_name": s.software_name}
            for s in registered
        ]
    except Exception:
        return []


async def run_single_email_detection(
    db: AsyncSession,
    company_id: uuid.UUID,
    email: MonitoredEmail,
    registered_data: list[dict],
) -> DetectedSoftware | None:
    """Process a single email through the detection crew."""
    email_data = {
        "id": str(email.id),
        "sender": email.sender,
        "subject": email.subject,
        "body_snippet": email.body_snippet,
        "received_at": email.received_at.isoformat() if email.received_at else None,
    }

    crew = IntegrationDetectionCrew(company_id, [email_data], registered_data)
    detections = crew.run()

    result_detection = None
    for det in detections:
        if det.get("confidence_score", 0) < 0.5:
            continue

        result_detection = DetectedSoftware(
            company_id=company_id,
            source_email_id=email.id,
            detected_vendor_name=det.get("detected_vendor_name", "Unknown"),
            detected_software=det.get("detected_software", "Unknown"),
            confidence_score=min(det.get("confidence_score", 0.5), 1.0),
            status="pending",
            agent_reasoning=det.get("reasoning", ""),
            detected_at=datetime.now(timezone.utc),
        )
        db.add(result_detection)
        break  # One detection per email

    email.processed = True
    await db.commit()
    if result_detection:
        await db.refresh(result_detection)

    return result_detection
