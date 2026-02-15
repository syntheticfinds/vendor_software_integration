import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.software.models import SoftwareRegistration
from app.software.schemas import SoftwareCreate, SoftwareUpdate


async def create_software(db: AsyncSession, company_id: uuid.UUID, data: SoftwareCreate) -> SoftwareRegistration:
    software = SoftwareRegistration(
        company_id=company_id,
        vendor_name=data.vendor_name,
        software_name=data.software_name,
        intended_use=data.intended_use,
        jira_workspace=data.jira_workspace,
        support_email=data.support_email,
        detection_id=data.detection_id,
    )
    db.add(software)
    await db.commit()
    await db.refresh(software)
    return software


async def get_software_list(
    db: AsyncSession,
    company_id: uuid.UUID,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[SoftwareRegistration], int]:
    query = select(SoftwareRegistration).where(SoftwareRegistration.company_id == company_id)
    count_query = select(func.count()).select_from(SoftwareRegistration).where(
        SoftwareRegistration.company_id == company_id
    )

    if status:
        query = query.where(SoftwareRegistration.status == status)
        count_query = count_query.where(SoftwareRegistration.status == status)

    if search:
        like = f"%{search}%"
        query = query.where(
            SoftwareRegistration.vendor_name.ilike(like) | SoftwareRegistration.software_name.ilike(like)
        )
        count_query = count_query.where(
            SoftwareRegistration.vendor_name.ilike(like) | SoftwareRegistration.software_name.ilike(like)
        )

    query = query.order_by(SoftwareRegistration.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    count_result = await db.execute(count_query)

    return list(result.scalars().all()), count_result.scalar_one()


async def get_software_by_id(db: AsyncSession, software_id: uuid.UUID) -> SoftwareRegistration | None:
    result = await db.execute(select(SoftwareRegistration).where(SoftwareRegistration.id == software_id))
    return result.scalar_one_or_none()


async def update_software(
    db: AsyncSession, software: SoftwareRegistration, data: SoftwareUpdate
) -> SoftwareRegistration:
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(software, field, value)
    await db.commit()
    await db.refresh(software)
    return software


async def archive_software(db: AsyncSession, software: SoftwareRegistration) -> SoftwareRegistration:
    software.status = "archived"
    await db.commit()
    await db.refresh(software)
    return software
