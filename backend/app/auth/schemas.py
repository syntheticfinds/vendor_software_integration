from pydantic import BaseModel, EmailStr, Field

from app.companies.schemas import CompanyResponse


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str


class AuthResponse(BaseModel):
    company: CompanyResponse
    access_token: str
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
