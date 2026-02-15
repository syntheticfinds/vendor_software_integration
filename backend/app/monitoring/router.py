import uuid

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.database import get_db
from app.dependencies import get_current_company
from app.monitoring.schemas import (
    DetectionListResponse,
    DetectionResponse,
    DetectionUpdate,
    ScanRequest,
    ScanResponse,
)
from app.monitoring.service import (
    get_detection_by_id,
    get_detections,
    get_unprocessed_emails,
    trigger_scan,
    update_detection_status,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/monitoring", tags=["monitoring"])


async def _run_detection_background(company_id: uuid.UUID):
    """Background task to run CrewAI detection per email."""
    from app.agents.integration_detector.crew import load_registered_software, run_single_email_detection
    from app.database import async_session_factory

    async with async_session_factory() as db:
        emails = await get_unprocessed_emails(db, company_id)
        if not emails:
            return

        registered_data = await load_registered_software(db, company_id)
        total_detections = 0

        for email in emails:
            detection = await run_single_email_detection(db, company_id, email, registered_data)
            if detection:
                total_detections += 1
            logger.info(
                "email_processed",
                company_id=str(company_id),
                email_id=str(email.id),
                detected=detection is not None,
            )

        logger.info(
            "detection_complete",
            company_id=str(company_id),
            emails_processed=len(emails),
            detections_created=total_detections,
        )


@router.post("/scan", response_model=ScanResponse)
async def scan(
    data: ScanRequest,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    result = await trigger_scan(db, company.id, data.source)

    # Run detection in background
    background_tasks.add_task(_run_detection_background, company.id)

    return ScanResponse(**result)


@router.get("/detections", response_model=DetectionListResponse)
async def list_detections(
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    items, total = await get_detections(db, company.id, status_filter, page, per_page)
    return DetectionListResponse(
        items=[DetectionResponse.model_validate(d) for d in items],
        total=total,
    )


@router.get("/detections/{detection_id}", response_model=DetectionResponse)
async def get_detection(
    detection_id: uuid.UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    detection = await get_detection_by_id(db, detection_id)
    if not detection or detection.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
    return DetectionResponse.model_validate(detection)


@router.patch("/detections/{detection_id}", response_model=DetectionResponse)
async def update_detection(
    detection_id: uuid.UUID,
    data: DetectionUpdate,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    detection = await get_detection_by_id(db, detection_id)
    if not detection or detection.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")

    updated = await update_detection_status(db, detection, data.status)
    return DetectionResponse.model_validate(updated)
