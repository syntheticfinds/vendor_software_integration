from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.database import get_db
from app.dependencies import get_current_company
from app.intelligence.schemas import (
    CUJResponse,
    DrilldownResponse,
    GenerateOutreachRequest,
    GenerateOutreachResponse,
    IndexResponse,
    SolutionDetailResponse,
)
from app.intelligence.service import (
    generate_targeted_outreach,
    get_cuj_drilldown,
    get_intelligence_index,
    get_solution_detail,
    rebuild_intelligence_index,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/index", response_model=IndexResponse)
async def get_index(
    category: str | None = Query(None),
    search: str | None = Query(None),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Searchable Software Intelligence Index, filterable by auto-category and text search."""
    result = await get_intelligence_index(db, category=category, search=search)
    return IndexResponse(**result)


@router.post("/rebuild")
async def rebuild_index(
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Trigger intelligence index rebuild (LLM categorization + CUJ derivation)."""
    count = await rebuild_intelligence_index(db)
    return {"status": "rebuilt", "entries": count}


@router.get("/solution/{vendor_name}/{software_name}", response_model=SolutionDetailResponse)
async def solution_detail(
    vendor_name: str,
    software_name: str,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Per-solution detail: health score, industry/size distributions, CUJ."""
    result = await get_solution_detail(db, vendor_name, software_name)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Software not found in intelligence index")
    return SolutionDetailResponse(**result)


@router.get(
    "/cuj/{vendor_name}/{software_name}/drilldown/{stage}",
    response_model=DrilldownResponse,
)
async def cuj_drilldown(
    vendor_name: str,
    software_name: str,
    stage: int,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Drill down to companies at a specific CUJ stage."""
    result = await get_cuj_drilldown(db, vendor_name, software_name, stage)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CUJ stage not found")
    return DrilldownResponse(**result)


@router.post("/outreach", response_model=GenerateOutreachResponse)
async def generate_outreach(
    data: GenerateOutreachRequest,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    """Generate LLM-powered targeted outreach for a company at a CUJ stage."""
    result = await generate_targeted_outreach(
        db, data.vendor_name, data.software_name, data.stage_order, data.company_id,
        contact_name=data.contact_name,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company or software not found")
    return GenerateOutreachResponse(**result)
