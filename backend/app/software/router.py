import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.database import get_db
from app.dependencies import get_current_company
from app.software.schemas import SoftwareCreate, SoftwareListResponse, SoftwareResponse, SoftwareUpdate
from app.software.service import archive_software, create_software, get_software_by_id, get_software_list, update_software

router = APIRouter(prefix="/software", tags=["software"])


@router.post("", response_model=SoftwareResponse, status_code=status.HTTP_201_CREATED)
async def create(
    data: SoftwareCreate,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    try:
        software = await create_software(db, company.id, data)
        return SoftwareResponse.model_validate(software)
    except Exception as e:
        if "UNIQUE" in str(e).upper():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Software already registered for this company",
            )
        raise


@router.get("", response_model=SoftwareListResponse)
async def list_software(
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    items, total = await get_software_list(db, company.id, status_filter, search, page, per_page)
    return SoftwareListResponse(
        items=[SoftwareResponse.model_validate(s) for s in items],
        total=total,
    )


@router.get("/{software_id}", response_model=SoftwareResponse)
async def get_software(
    software_id: uuid.UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    software = await get_software_by_id(db, software_id)
    if not software or software.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Software not found")
    return SoftwareResponse.model_validate(software)


@router.patch("/{software_id}", response_model=SoftwareResponse)
async def update(
    software_id: uuid.UUID,
    data: SoftwareUpdate,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    software = await get_software_by_id(db, software_id)
    if not software or software.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Software not found")
    updated = await update_software(db, software, data)
    return SoftwareResponse.model_validate(updated)


@router.delete("/{software_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    software_id: uuid.UUID,
    company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    software = await get_software_by_id(db, software_id)
    if not software or software.company_id != company.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Software not found")
    await archive_software(db, software)
