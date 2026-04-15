from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    agency_id: str | None = None
    full_name: str
    active_modules: list[str] = Field(default_factory=list)


class RefreshRequest(BaseModel):
    refresh_token: str
