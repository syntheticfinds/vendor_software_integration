from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    software_id: UUID
    source_type: str | None = None  # if None, ingest from all connectors


class IngestResponse(BaseModel):
    ingested_count: int
    software_id: UUID


class AnalyzeRequest(BaseModel):
    software_id: UUID
    window_days: int = Field(30, ge=1, le=365)


class AnalyzeResponse(BaseModel):
    status: str
    software_id: UUID


class SignalEventResponse(BaseModel):
    id: UUID
    company_id: UUID
    software_id: UUID
    source_type: str
    source_id: str | None
    event_type: str
    severity: str | None
    title: str | None
    body: str | None
    event_metadata: dict | None
    occurred_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class SignalEventListResponse(BaseModel):
    items: list[SignalEventResponse]
    total: int


class HealthScoreResponse(BaseModel):
    id: UUID
    company_id: UUID
    software_id: UUID
    score: int
    category_breakdown: dict
    signal_summary: str | None
    signal_count: int
    confidence_tier: str
    scoring_window_start: datetime
    scoring_window_end: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewDraftResponse(BaseModel):
    id: UUID
    company_id: UUID
    software_id: UUID
    health_score_id: UUID | None
    draft_subject: str | None
    draft_body: str
    confidence_tier: str
    status: str
    edited_body: str | None
    reviewed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewDraftUpdate(BaseModel):
    status: str = Field(pattern="^(approved|declined|edited)$")
    edited_body: str | None = None


class StageSmoothnessMetrics(BaseModel):
    friction: float
    recurrence: float
    escalation: float
    resolution: float
    effort: float


class TrajectoryStage(BaseModel):
    name: str
    status: str  # completed, current, upcoming
    signal_count: int
    smoothness_score: float | None
    date_range: dict | None
    explanation: str
    metrics: StageSmoothnessMetrics | None
    metric_details: dict[str, str] | None = None
    metric_confidence: dict[str, str] | None = None


class BenchmarkComparison(BaseModel):
    average: float
    median: float
    percentile: int
    peer_count: int


class StageBenchmark(BenchmarkComparison):
    metrics: dict[str, BenchmarkComparison] | None = None


class TrajectoryBenchmarks(BaseModel):
    category: str | None
    peer_count: int
    overall: BenchmarkComparison | None
    stages: dict[str, StageBenchmark]


class TrajectoryResponse(BaseModel):
    current_stage: str
    stages: list[TrajectoryStage]
    regression_detected: bool
    regression_detail: str | None
    overall_smoothness: float
    confidence: str
    benchmarks: TrajectoryBenchmarks | None = None


# ---------------------------------------------------------------------------
# Issue rate over time
# ---------------------------------------------------------------------------


class IssueRatePoint(BaseModel):
    date: str
    count: int


class IssueRateCommentary(BaseModel):
    trend: str  # declining, stable, increasing
    message: str


class PeerIssueRate(BaseModel):
    category: str | None
    peer_count: int
    points: list[IssueRatePoint]


class IssueRateResponse(BaseModel):
    points: list[IssueRatePoint]
    commentary: IssueRateCommentary
    days_since_registration: int
    peer: PeerIssueRate | None = None


# ---------------------------------------------------------------------------
# Issue recurrence rate over time
# ---------------------------------------------------------------------------


class RecurrenceRatePoint(BaseModel):
    date: str
    rate: float  # percentage of threads that are recurring
    recurring_count: int
    total_threads: int
    top_topics: list[str]


class RecurrenceCommentary(BaseModel):
    trend: str  # improving, worsening, stable
    message: str


class PeerRecurrenceRate(BaseModel):
    category: str | None
    peer_count: int
    points: list[IssueRatePoint]  # reuse: date + count (rate as int)


class RecurrenceRateResponse(BaseModel):
    points: list[RecurrenceRatePoint]
    commentary: RecurrenceCommentary
    peer: PeerRecurrenceRate | None = None


# ---------------------------------------------------------------------------
# Resolution time over time
# ---------------------------------------------------------------------------


class ResolutionTimePoint(BaseModel):
    date: str
    median_hours: float | None
    p90_hours: float | None
    pair_count: int
    open_count: int


class ResolutionTimeCommentary(BaseModel):
    trend: str  # improving, worsening, stable
    message: str


class PeerResolutionTime(BaseModel):
    category: str | None
    peer_count: int
    points: list[ResolutionTimePoint]


class ResolutionTimeCategoryResponse(BaseModel):
    category: str  # "issue" or "feature"
    points: list[ResolutionTimePoint]
    commentary: ResolutionTimeCommentary
    peer: PeerResolutionTime | None = None


class ResolutionTimeResponse(BaseModel):
    categories: list[ResolutionTimeCategoryResponse]
    days_since_registration: int


# ---------------------------------------------------------------------------
# Vendor responsiveness over time
# ---------------------------------------------------------------------------


class ResponsivenessPoint(BaseModel):
    date: str
    median_lag_hours: float | None
    p90_lag_hours: float | None
    response_count: int
    proactive_count: int
    unanswered_count: int


class ResponsivenessCommentary(BaseModel):
    trend: str  # improving, worsening, stable
    message: str


class PeerResponsiveness(BaseModel):
    category: str | None
    peer_count: int
    points: list[ResponsivenessPoint]


class ResponsivenessResponse(BaseModel):
    points: list[ResponsivenessPoint]
    commentary: ResponsivenessCommentary
    days_since_registration: int
    peer: PeerResponsiveness | None = None


# ---------------------------------------------------------------------------
# Severity escalation rate over time
# ---------------------------------------------------------------------------


class EscalationRatePoint(BaseModel):
    date: str
    rate: float  # percentage of threads that escalated
    escalation_count: int
    total_threads: int
    top_escalations: list[str]


class EscalationCommentary(BaseModel):
    trend: str  # improving, worsening, stable
    message: str


class PeerEscalationRate(BaseModel):
    category: str | None
    peer_count: int
    points: list[IssueRatePoint]  # reuse: date + count (rate as int)


class EscalationRateResponse(BaseModel):
    points: list[EscalationRatePoint]
    commentary: EscalationCommentary
    peer: PeerEscalationRate | None = None


# ---------------------------------------------------------------------------
# Core vs Peripheral issue ratio over time
# ---------------------------------------------------------------------------


class CorePeripheralPoint(BaseModel):
    date: str
    peripheral_ratio: float  # percentage of signals that are peripheral
    core_count: int
    peripheral_count: int
    total_count: int
    top_peripheral_categories: list[str]


class CorePeripheralCommentary(BaseModel):
    trend: str  # improving, worsening, stable
    message: str


class PeerCorePeripheral(BaseModel):
    category: str | None
    peer_count: int
    points: list[IssueRatePoint]  # reuse: date + count (ratio as int)


class CorePeripheralResponse(BaseModel):
    points: list[CorePeripheralPoint]
    commentary: CorePeripheralCommentary
    peer: PeerCorePeripheral | None = None


# ---------------------------------------------------------------------------
# Fitness for Purpose – feature request pressure
# ---------------------------------------------------------------------------


class FitnessPoint(BaseModel):
    date: str
    request_ratio: float  # % of signals that are feature requests
    request_count: int
    total_signals: int
    repeat_count: int  # topics asked >1 time in window
    unique_request_topics: int
    fulfilled_count: int  # request threads with subsequent positive signal
    total_request_threads: int  # all request threads to date
    fulfillment_rate: float  # fulfilled / total * 100
    top_repeats: list[str]


class FitnessCommentary(BaseModel):
    trend: str  # improving, worsening, stable
    message: str


class PeerFitness(BaseModel):
    category: str | None
    peer_count: int
    points: list[IssueRatePoint]  # reuse: date + count (ratio as int)


class FitnessResponse(BaseModel):
    points: list[FitnessPoint]
    commentary: FitnessCommentary
    peer: PeerFitness | None = None


# ---------------------------------------------------------------------------
# Reliability metrics
# ---------------------------------------------------------------------------


class ReliabilityPoint(BaseModel):
    date: str
    incident_count: int  # keyword-matched incident signals in window
    weighted_density: float  # severity-weighted incident score
    mtbf_hours: float | None  # mean time between failures
    extracted_downtime_hours: float | None  # total extracted downtime in window
    extracted_uptime_pct: float | None  # latest extracted uptime %
    extraction_count: int  # signals with extractable numbers
    top_incidents: list[str]


class ReliabilityCommentary(BaseModel):
    trend: str  # improving, worsening, stable
    message: str


class PeerReliability(BaseModel):
    category: str | None
    peer_count: int
    points: list[IssueRatePoint]  # reuse: date + count (weighted_density rounded)


class ReliabilityResponse(BaseModel):
    points: list[ReliabilityPoint]
    commentary: ReliabilityCommentary
    peer: PeerReliability | None = None


# ---------------------------------------------------------------------------
# Performance metrics – latency & rate-limiting complaints
# ---------------------------------------------------------------------------


class PerformancePoint(BaseModel):
    date: str
    latency_count: int  # signals mentioning latency / slowness
    rate_limit_count: int  # signals mentioning rate limiting / throttling
    total_signals: int  # all signals in window
    top_latency_issues: list[str]
    top_rate_limit_issues: list[str]


class PerformanceCommentary(BaseModel):
    trend: str  # improving, worsening, stable
    message: str


class PeerPerformance(BaseModel):
    category: str | None
    peer_count: int
    points: list[IssueRatePoint]  # reuse: date + count (combined perf complaints)


class PerformanceResponse(BaseModel):
    points: list[PerformancePoint]
    commentary: PerformanceCommentary
    peer: PeerPerformance | None = None


# ---------------------------------------------------------------------------
# Hierarchical summaries
# ---------------------------------------------------------------------------


class HealthSummaries(BaseModel):
    reliability: str | None = None
    performance: str | None = None
    fitness_for_purpose: str | None = None
    overall: str | None = None


class StageSummaries(BaseModel):
    friction: str | None = None
    recurrence: str | None = None
    escalation: str | None = None
    resolution: str | None = None
    effort: str | None = None
    overall: str | None = None


class TrajectorySummaries(BaseModel):
    stages: dict[str, StageSummaries] = {}
    overall: str | None = None


class SummariesResponse(BaseModel):
    health: HealthSummaries | None = None
    trajectory: TrajectorySummaries | None = None
