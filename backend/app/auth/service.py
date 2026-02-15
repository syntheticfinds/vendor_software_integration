from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token, create_refresh_token
from app.companies.models import Company
from app.companies.schemas import CompanyCreate
from app.companies.service import get_company_by_email

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


async def register_company(db: AsyncSession, data: CompanyCreate) -> tuple[Company, str, str]:
    company = Company(
        company_name=data.company_name,
        industry=data.industry,
        company_size=data.company_size,
        primary_email=data.primary_email,
        password_hash=hash_password(data.password),
    )
    db.add(company)
    await db.commit()
    await db.refresh(company)

    access_token = create_access_token(str(company.id))
    refresh_token = create_refresh_token(str(company.id))
    return company, access_token, refresh_token


async def authenticate_company(db: AsyncSession, email: str, password: str) -> tuple[Company, str, str] | None:
    company = await get_company_by_email(db, email)
    if not company or not verify_password(password, company.password_hash):
        return None

    access_token = create_access_token(str(company.id))
    refresh_token = create_refresh_token(str(company.id))
    return company, access_token, refresh_token
