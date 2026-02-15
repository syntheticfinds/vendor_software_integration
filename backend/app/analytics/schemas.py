from datetime import datetime

from pydantic import BaseModel


class OverviewStats(BaseModel):
    total_software: int
    active_software: int
    total_signals: int
    avg_health_score: float | None
    pending_reviews: int
    critical_signals: int


class SoftwareHealthSummary(BaseModel):
    software_id: str
    software_name: str
    vendor_name: str
    latest_score: int | None
    signal_count: int
    critical_count: int
    status: str


class HealthTrendPoint(BaseModel):
    date: str
    score: int
    software_id: str
    software_name: str


class IssueCategoryBreakdown(BaseModel):
    category: str
    count: int
    percentage: float


class SoftwareBurden(BaseModel):
    software_id: str
    software_name: str
    vendor_name: str
    total_signals: int
    critical_signals: int
    high_signals: int
    open_tickets: int
    burden_score: float


class SentimentPoint(BaseModel):
    date: str
    positive: int
    negative: int
    neutral: int
