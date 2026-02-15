from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.schemas import AuthResponse, LoginRequest, RefreshRequest, TokenResponse
from app.auth.service import authenticate_company, register_company
from app.companies.schemas import CompanyCreate, CompanyResponse
from app.companies.service import get_company_by_email
from app.database import get_db
from app.dependencies import get_current_company

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(data: CompanyCreate, db: AsyncSession = Depends(get_db)):
    existing = await get_company_by_email(db, data.primary_email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    company, access_token, refresh_token = await register_company(db, data)
    return AuthResponse(
        company=CompanyResponse.model_validate(company),
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/login", response_model=AuthResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await authenticate_company(db, data.email, data.password)
    if not result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    company, access_token, refresh_token = result
    return AuthResponse(
        company=CompanyResponse.model_validate(company),
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest):
    payload = decode_token(data.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    company_id = payload.get("sub")
    return TokenResponse(
        access_token=create_access_token(company_id),
        refresh_token=create_refresh_token(company_id),
    )


@router.get("/me", response_model=CompanyResponse)
async def me(company=Depends(get_current_company)):
    return CompanyResponse.model_validate(company)
