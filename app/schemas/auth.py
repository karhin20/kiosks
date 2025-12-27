from pydantic import BaseModel, EmailStr


class AuthUser(BaseModel):
    id: str
    email: EmailStr | None = None
    phone: str | None = None
    role: str | None = "customer"
    name: str | None = None
    avatar_url: str | None = None


class AuthSession(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser

