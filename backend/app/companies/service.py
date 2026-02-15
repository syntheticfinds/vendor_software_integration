from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.companies.models import Company
from app.companies.schemas import CompanyUpdate


async def get_company_by_id(db: AsyncSession, company_id: UUID) -> Company | None:
    result = await db.execute(select(Company).where(Company.id == company_id))
    return result.scalar_one_or_none()


async def get_company_by_email(db: AsyncSession, email: str) -> Company | None:
    result = await db.execute(select(Company).where(Company.primary_email == email))
    return result.scalar_one_or_none()


async def update_company(db: AsyncSession, company: Company, data: CompanyUpdate) -> Company:
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(company, field, value)
    await db.commit()
    await db.refresh(company)
    return company
