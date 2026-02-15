from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.database import get_db
from app.dependencies import get_current_company
from app.analytics.service import (
    get_event_type_distribution,
    get_health_trends,
    get_issue_categories,
    get_overview,
    get_software_health_summary,
    get_source_distribution,
    get_support_burden,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(
    software_ids: list[UUID] | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    return await get_overview(db, company.id, software_ids=software_ids)


@router.get("/software-summary")
async def software_summary(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    return await get_software_health_summary(db, company.id)


@router.get("/health-trends")
async def health_trends(
    days: int = Query(30, ge=1, le=365),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    return await get_health_trends(db, company.id, days)


@router.get("/issue-categories")
async def issue_categories(
    software_ids: list[UUID] | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    return await get_issue_categories(db, company.id, software_ids=software_ids)


@router.get("/support-burden")
async def support_burden(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    return await get_support_burden(db, company.id)


@router.get("/event-types")
async def event_types(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    return await get_event_type_distribution(db, company.id)


@router.get("/source-distribution")
async def source_distribution(
    software_ids: list[UUID] | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    return await get_source_distribution(db, company.id, software_ids=software_ids)
