from uuid import UUID

from pydantic import BaseModel


class IndexEntry(BaseModel):
    vendor_name: str
    software_name: str
    auto_category: str | None
    avg_health_score: int | None
    company_count: int


class IndexResponse(BaseModel):
    items: list[IndexEntry]
    categories: list[str]


class DistributionItem(BaseModel):
    label: str
    count: int


class CUJStage(BaseModel):
    order: int
    name: str
    description: str
    satisfied_count: int
    dissatisfied_count: int
    total: int
    avg_duration_days: float | None = None


class CUJResponse(BaseModel):
    vendor_name: str
    software_name: str
    stages: list[CUJStage]


class SolutionDetailResponse(BaseModel):
    vendor_name: str
    software_name: str
    auto_category: str | None
    avg_health_score: int | None
    company_count: int
    industry_distribution: list[DistributionItem]
    size_distribution: list[DistributionItem]
    cuj: CUJResponse | None


class DrilldownCompany(BaseModel):
    company_id: str
    company_name: str
    industry: str | None
    company_size: str | None
    satisfied: bool
    contacts: list[str]


class DrilldownResponse(BaseModel):
    stage_order: int
    stage_name: str
    companies: list[DrilldownCompany]


class GenerateOutreachRequest(BaseModel):
    vendor_name: str
    software_name: str
    stage_order: int
    company_id: UUID
    contact_name: str | None = None


class GenerateOutreachResponse(BaseModel):
    company_name: str
    contact_name: str | None = None
    generated_message: str
    pain_points: list[str]
