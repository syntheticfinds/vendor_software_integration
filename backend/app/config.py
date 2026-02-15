from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./vendor_intel.db"
    TEST_DATABASE_URL: str = "sqlite+aiosqlite:///./test.db"

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ANTHROPIC_API_KEY: str = ""

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/gmail/callback"

    # Set to your ngrok URL (e.g. https://abc123.ngrok-free.app) for local Jira webhook testing
    WEBHOOK_BASE_URL: str = ""

    K_ANONYMITY_THRESHOLD: int = 5

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
