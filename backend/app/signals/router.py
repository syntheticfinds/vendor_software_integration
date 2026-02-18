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
    RecurrenceRateResponse,
    CorePeripheralResponse,
    EscalationRateResponse,
    FitnessResponse,
    PerformanceResponse,
    ReliabilityResponse,
    ResponsivenessResponse,
    ResolutionTimeResponse,
    ReviewDraftResponse,
    ReviewDraftUpdate,
    SignalEventListResponse,
    SignalEventResponse,
    IssueRateResponse,
    SummariesResponse,
    TrajectoryResponse,
)
from app.signals.service import (
    get_health_scores,
    get_latest_health_score,
    get_review_draft_by_id,
    get_review_drafts,
    get_signal_events,
    ingest_signals,
    run_analysis,
    update_review_draft,
)

router = APIRouter(prefix="/signals", tags=["signals"])


async def _background_analyze(company_id: uuid.UUID, software_id: uuid.UUID) -> None:
    """Run full LLM analysis in the background with its own DB session."""
    from app.database import async_session_factory

    async with async_session_factory() as db:
        await run_analysis(db, company_id, software_id)


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest(
    data: IngestRequest,
    background_tasks: BackgroundTasks,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    count = await ingest_signals(db, company.id, data.software_id, data.source_type)

    # Auto-analyze after ingestion so health scores, summaries, and review
    # drafts stay current without a manual "Analyze" click.
    if count > 0:
        background_tasks.add_task(
            _background_analyze, company.id, data.software_id,
        )

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


@router.get("/health-score-benchmarks")
async def get_health_score_benchmarks(
    software_id: uuid.UUID = Query(...),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_health_score_benchmarks

    result = await compute_health_score_benchmarks(db, company.id, software_id)
    return result


@router.get("/summaries", response_model=SummariesResponse | None)
async def get_summaries(
    software_id: uuid.UUID = Query(...),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    latest_hs = await get_latest_health_score(db, company.id, software_id)
    if latest_hs and latest_hs.summaries:
        return latest_hs.summaries
    return None


@router.get("/trajectory", response_model=TrajectoryResponse)
async def get_trajectory(
    software_id: uuid.UUID = Query(...),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    # Prefer stored trajectory data from the latest analysis run
    latest_hs = await get_latest_health_score(db, company.id, software_id)
    if latest_hs and latest_hs.trajectory_data:
        result = dict(latest_hs.trajectory_data)
        # Benchmarks are computed live (depend on peer data that changes independently)
        from app.signals.trajectory import compute_trajectory_benchmarks
        benchmarks = await compute_trajectory_benchmarks(db, company.id, software_id)
        result["benchmarks"] = benchmarks
        return result

    # Fallback: compute on-the-fly (first page load before analysis runs)
    from app.signals.trajectory import compute_trajectory

    result = await compute_trajectory(db, company.id, software_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/friction-events")
async def get_friction_events(
    software_id: uuid.UUID = Query(...),
    stage_topic: str | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_friction_events

    result = await compute_friction_events(db, company.id, software_id, stage_topic=stage_topic)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/recurrence-events")
async def get_recurrence_events(
    software_id: uuid.UUID = Query(...),
    stage_topic: str | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_recurrence_events

    result = await compute_recurrence_events(db, company.id, software_id, stage_topic=stage_topic)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/issue-rate", response_model=IssueRateResponse)
async def get_issue_rate(
    software_id: uuid.UUID = Query(...),
    stage_topic: str | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_issue_rate

    result = await compute_issue_rate(db, company.id, software_id, stage_topic=stage_topic)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/recurrence-rate", response_model=RecurrenceRateResponse)
async def get_recurrence_rate(
    software_id: uuid.UUID = Query(...),
    stage_topic: str | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_recurrence_rate

    result = await compute_recurrence_rate(db, company.id, software_id, stage_topic=stage_topic)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/resolution-time", response_model=ResolutionTimeResponse)
async def get_resolution_time(
    software_id: uuid.UUID = Query(...),
    stage_topic: str | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_resolution_time

    result = await compute_resolution_time(db, company.id, software_id, stage_topic=stage_topic)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/vendor-responsiveness", response_model=ResponsivenessResponse)
async def get_vendor_responsiveness(
    software_id: uuid.UUID = Query(...),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_vendor_responsiveness

    result = await compute_vendor_responsiveness(db, company.id, software_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/escalation-events")
async def get_escalation_events(
    software_id: uuid.UUID = Query(...),
    stage_topic: str | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_escalation_events

    result = await compute_escalation_events(db, company.id, software_id, stage_topic=stage_topic)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/resolution-events")
async def get_resolution_events(
    software_id: uuid.UUID = Query(...),
    stage_topic: str | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_resolution_events

    result = await compute_resolution_events(db, company.id, software_id, stage_topic=stage_topic)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/effort-events")
async def get_effort_events(
    software_id: uuid.UUID = Query(...),
    stage_topic: str | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_effort_events

    result = await compute_effort_events(db, company.id, software_id, stage_topic=stage_topic)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/escalation-rate", response_model=EscalationRateResponse)
async def get_escalation_rate(
    software_id: uuid.UUID = Query(...),
    stage_topic: str | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_escalation_rate

    result = await compute_escalation_rate(db, company.id, software_id, stage_topic=stage_topic)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/core-peripheral", response_model=CorePeripheralResponse)
async def get_core_peripheral(
    software_id: uuid.UUID = Query(...),
    stage_topic: str | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_core_peripheral

    result = await compute_core_peripheral(db, company.id, software_id, stage_topic=stage_topic)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/fitness-metrics", response_model=FitnessResponse)
async def get_fitness_metrics(
    software_id: uuid.UUID = Query(...),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_fitness_metrics

    result = await compute_fitness_metrics(db, company.id, software_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/fitness-events")
async def get_fitness_events(
    software_id: uuid.UUID = Query(...),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_fitness_events

    result = await compute_fitness_events(db, company.id, software_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/reliability", response_model=ReliabilityResponse)
async def get_reliability(
    software_id: uuid.UUID = Query(...),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_reliability

    result = await compute_reliability(db, company.id, software_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/reliability-events")
async def get_reliability_events(
    software_id: uuid.UUID = Query(...),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_reliability_events

    result = await compute_reliability_events(db, company.id, software_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/performance", response_model=PerformanceResponse)
async def get_performance(
    software_id: uuid.UUID = Query(...),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_performance

    result = await compute_performance(db, company.id, software_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/performance-events")
async def get_performance_events(
    software_id: uuid.UUID = Query(...),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    from app.signals.trajectory import compute_performance_events

    result = await compute_performance_events(db, company.id, software_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


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
