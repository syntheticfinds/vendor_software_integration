import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.database import get_db
from app.dependencies import get_current_company
from app.intelligence.service import rebuild_intelligence_index
from app.signals.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    HealthScoreResponse,
    IngestRequest,
    IngestResponse,
    ReviewDraftResponse,
    ReviewDraftUpdate,
    SignalEventListResponse,
    SignalEventResponse,
)
from app.signals.service import (
    get_health_scores,
    get_review_draft_by_id,
    get_review_drafts,
    get_signal_events,
    ingest_signals,
    run_analysis,
    update_review_draft,
)

router = APIRouter(prefix="/signals", tags=["signals"])


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest(
    data: IngestRequest,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    count = await ingest_signals(db, company.id, data.software_id, data.source_type)
    return IngestResponse(ingested_count=count, software_id=data.software_id)


@router.get("/events", response_model=SignalEventListResponse)
async def list_events(
    software_id: uuid.UUID | None = Query(None),
    source_type: str | None = Query(None),
    severity: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    items, total = await get_signal_events(
        db, company.id, software_id, source_type, severity, page=page, per_page=per_page
    )
    return SignalEventListResponse(
        items=[SignalEventResponse.model_validate(e) for e in items],
        total=total,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    data: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    result = await run_analysis(db, company.id, data.software_id, data.window_days)
    return AnalyzeResponse(status=result["status"], software_id=data.software_id)


@router.get("/health-scores", response_model=list[HealthScoreResponse])
async def list_health_scores(
    software_id: uuid.UUID | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    scores = await get_health_scores(db, company.id, software_id)
    return [HealthScoreResponse.model_validate(s) for s in scores]


@router.get("/review-drafts", response_model=list[ReviewDraftResponse])
async def list_review_drafts(
    status_filter: str | None = Query(None, alias="status"),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    drafts = await get_review_drafts(db, company.id, status_filter)
    return [ReviewDraftResponse.model_validate(d) for d in drafts]


@router.get("/review-drafts/{draft_id}", response_model=ReviewDraftResponse)
async def get_draft(
    draft_id: uuid.UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    draft = await get_review_draft_by_id(db, draft_id)
    if not draft or draft.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review draft not found")
    return ReviewDraftResponse.model_validate(draft)


@router.patch("/review-drafts/{draft_id}", response_model=ReviewDraftResponse)
async def update_draft(
    draft_id: uuid.UUID,
    data: ReviewDraftUpdate,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    draft = await get_review_draft_by_id(db, draft_id)
    if not draft or draft.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review draft not found")
    updated = await update_review_draft(db, draft, data.status, data.edited_body)
    return ReviewDraftResponse.model_validate(updated)


@router.post("/review-drafts/{draft_id}/send", status_code=status.HTTP_200_OK)
async def send_draft(
    draft_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    draft = await get_review_draft_by_id(db, draft_id)
    if not draft or draft.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review draft not found")
    if draft.status != "approved":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only approved drafts can be sent")
    # In production, this would send the email via Gmail API / SMTP
    await update_review_draft(db, draft, "sent")
    # Rebuild intelligence index in background so data stays fresh
    background_tasks.add_task(rebuild_intelligence_index, db)
    return {"status": "sent", "draft_id": str(draft_id)}
