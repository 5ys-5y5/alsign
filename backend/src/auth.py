"""Authentication helpers for Supabase JWT."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import logging

import jwt
from dateutil.parser import isoparse
from fastapi import Request, HTTPException

from .config import settings
from .database.connection import db_pool

logger = logging.getLogger("alsign")


@dataclass
class UserContext:
    role: str = "anonymous"
    subscription_status: str = "inactive"
    subscription_expires_at: Optional[datetime] = None
    is_authenticated: bool = False
    email: Optional[str] = None
    user_id: Optional[str] = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_subscriber(self) -> bool:
        if self.subscription_status != "active":
            return False
        if self.subscription_expires_at is None:
            return True
        return self.subscription_expires_at > datetime.now(timezone.utc)


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = isoparse(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        logger.warning("Failed to parse subscription_expires_at", extra={"value": value})
        return None


def _decode_token(token: str) -> Optional[Dict[str, Any]]:
    if not settings.SUPABASE_JWT_SECRET:
        logger.warning("SUPABASE_JWT_SECRET not configured; treating user as anonymous")
        return None

    try:
        return jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        logger.warning("JWT decode failed", extra={"error": str(exc)})
        return None


def get_current_user(request: Request) -> UserContext:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return UserContext()

    token = auth_header.replace("Bearer ", "", 1).strip()
    claims = _decode_token(token)
    if not claims:
        return UserContext()

    app_metadata = claims.get("app_metadata") or {}
    user_metadata = claims.get("user_metadata") or {}
    merged_metadata = {**app_metadata, **user_metadata}

    role = merged_metadata.get("role") or claims.get("role") or "user"
    subscription_status = merged_metadata.get("subscription_status") or "inactive"
    subscription_expires_at = _parse_datetime(merged_metadata.get("subscription_expires_at"))
    user_id = claims.get("sub")

    return UserContext(
        role=role,
        subscription_status=subscription_status,
        subscription_expires_at=subscription_expires_at,
        is_authenticated=True,
        email=claims.get("email"),
        user_id=user_id,
    )


async def _is_profile_admin(user_id: Optional[str]) -> bool:
    if not user_id:
        return False
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT is_admin FROM public.user_profiles WHERE user_id = $1",
                user_id,
            )
        return bool(value)
    except Exception as exc:
        logger.warning("Admin lookup failed", extra={"error": str(exc)})
        return False


async def require_admin(request: Request) -> UserContext:
    user = get_current_user(request)
    if not user.is_authenticated:
        raise HTTPException(status_code=403, detail="Admin access required")
    if user.is_admin:
        return user
    if not await _is_profile_admin(user.user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
