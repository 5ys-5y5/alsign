"""Auth router for user context."""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import get_current_user, UserContext


router = APIRouter(tags=["Auth"])


class AuthMeResponse(BaseModel):
    role: str
    subscription_status: str
    subscription_expires_at: Optional[str]
    is_admin: bool
    is_subscriber: bool
    is_authenticated: bool
    email: Optional[str]


@router.get("/auth/me", response_model=AuthMeResponse)
async def get_auth_me(user: UserContext = Depends(get_current_user)):
    expires_at = user.subscription_expires_at.isoformat() if user.subscription_expires_at else None
    return AuthMeResponse(
        role=user.role,
        subscription_status=user.subscription_status,
        subscription_expires_at=expires_at,
        is_admin=user.is_admin,
        is_subscriber=user.is_subscriber,
        is_authenticated=user.is_authenticated,
        email=user.email,
    )
