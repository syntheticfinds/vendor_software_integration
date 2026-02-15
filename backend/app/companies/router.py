from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.companies.schemas import CompanyResponse, CompanyUpdate
from app.companies.service import get_company_by_id, update_company
from app.database import get_db
from app.dependencies import get_current_company

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: UUID,
    current_company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    if current_company.id != company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    company = await get_company_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    return CompanyResponse.model_validate(company)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update(
    company_id: UUID,
    data: CompanyUpdate,
    current_company: Company = Depends(get_current_company),
    db: AsyncSession = Depends(get_db),
):
    if current_company.id != company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    company = await get_company_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    updated = await update_company(db, company, data)
    return CompanyResponse.model_validate(updated)
