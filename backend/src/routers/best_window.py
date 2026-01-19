"""Router for Best Window policy management."""

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ..auth import require_admin, UserContext
from ..database.connection import db_pool
from ..services.best_window_policy import (
    BEST_WINDOW_POLICY_ENDPOINT,
    BEST_WINDOW_POLICY_FUNCTION,
    merge_best_window_policy,
)

logger = logging.getLogger("alsign")

router = APIRouter(prefix="/bestWindow", tags=["BestWindow"])


class BestWindowPolicyResponse(BaseModel):
    endpoint: str
    function: str
    description: Optional[str]
    policy: Dict[str, Any]
    isDefault: bool = False


class BestWindowPolicyUpdate(BaseModel):
    policy: Dict[str, Any] = Field(..., description="Best Window policy JSON")
    description: Optional[str] = Field(None, description="Policy description")
    endpoint: Optional[str] = Field(None, description="Policy endpoint override")


@router.get("/policy", response_model=BestWindowPolicyResponse)
async def get_best_window_policy(user: UserContext = Depends(require_admin)):
    try:
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT endpoint, function, description, policy
                FROM config_lv0_policy
                WHERE function = $1
                """,
                BEST_WINDOW_POLICY_FUNCTION,
            )

        if not row:
            return BestWindowPolicyResponse(
                endpoint=BEST_WINDOW_POLICY_ENDPOINT,
                function=BEST_WINDOW_POLICY_FUNCTION,
                description="Default (not stored in config_lv0_policy)",
                policy=merge_best_window_policy(None),
                isDefault=True,
            )

        policy_value = row["policy"]
        if isinstance(policy_value, str):
            try:
                policy_value = json.loads(policy_value)
            except json.JSONDecodeError:
                policy_value = {}
        elif policy_value is None:
            policy_value = {}

        return BestWindowPolicyResponse(
            endpoint=row["endpoint"] or BEST_WINDOW_POLICY_ENDPOINT,
            function=row["function"] or BEST_WINDOW_POLICY_FUNCTION,
            description=row["description"],
            policy=policy_value,
            isDefault=False,
        )

    except Exception as e:
        logger.error(f"action=get_best_window_policy status=error error={str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch Best Window policy: {str(e)}")


@router.put("/policy", response_model=BestWindowPolicyResponse)
async def update_best_window_policy(
    update: BestWindowPolicyUpdate,
    user: UserContext = Depends(require_admin),
):
    try:
        endpoint = update.endpoint or BEST_WINDOW_POLICY_ENDPOINT
        policy_json = json.dumps(update.policy)
        pool = await db_pool.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO config_lv0_policy (endpoint, function, description, policy, created_at)
                VALUES ($1, $2, $3, $4::jsonb, NOW())
                ON CONFLICT (function)
                DO UPDATE SET
                    endpoint = EXCLUDED.endpoint,
                    description = EXCLUDED.description,
                    policy = EXCLUDED.policy
                RETURNING endpoint, function, description, policy
                """,
                endpoint,
                BEST_WINDOW_POLICY_FUNCTION,
                update.description,
                policy_json,
            )

        policy_value = row["policy"]
        if isinstance(policy_value, str):
            try:
                policy_value = json.loads(policy_value)
            except json.JSONDecodeError:
                policy_value = {}
        elif policy_value is None:
            policy_value = {}

        return BestWindowPolicyResponse(
            endpoint=row["endpoint"] or BEST_WINDOW_POLICY_ENDPOINT,
            function=row["function"] or BEST_WINDOW_POLICY_FUNCTION,
            description=row["description"],
            policy=policy_value,
            isDefault=False,
        )

    except Exception as e:
        logger.error(f"action=update_best_window_policy status=error error={str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update Best Window policy: {str(e)}")
