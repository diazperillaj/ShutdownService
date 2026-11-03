from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agent_hub import AgentHub, history_entry
from ..auth import current_user, require_same_origin
from ..control import ControlService
from ..db import get_db, utcnow
from ..models import ActionLog, Source, User
from ..schemas import ActionNowIn, ExtendIn, ScheduleIn

router = APIRouter(prefix="/api", tags=["control"], dependencies=[Depends(current_user)])
mutating = [Depends(require_same_origin)]


def _hub(request: Request) -> AgentHub:
    return request.app.state.hub


def _control(request: Request) -> ControlService:
    return request.app.state.control


@router.get("/status")
async def get_status(hub: AgentHub = Depends(_hub)) -> dict[str, Any]:
    return hub.snapshot.to_api()


@router.post("/schedule", dependencies=mutating)
async def schedule(
    body: ScheduleIn,
    user: User = Depends(current_user),
    control: ControlService = Depends(_control),
) -> dict[str, Any]:
    if body.at is not None:
        delay = round((body.at - utcnow()).total_seconds())
    else:
        delay = body.delay_seconds
    snapshot = await control.schedule(body.action, delay, source=Source.WEB, user_id=user.id)
    return snapshot.to_api()


@router.post("/schedule/extend", dependencies=mutating)
async def extend(
    body: ExtendIn,
    user: User = Depends(current_user),
    control: ControlService = Depends(_control),
) -> dict[str, Any]:
    snapshot = await control.extend(body.seconds, source=Source.WEB, user_id=user.id)
    return snapshot.to_api()


@router.delete("/schedule", dependencies=mutating)
async def cancel(
    user: User = Depends(current_user), control: ControlService = Depends(_control)
) -> dict[str, Any]:
    result = await control.cancel(source=Source.WEB, user_id=user.id)
    return result.snapshot.to_api()


@router.post("/actions/now", dependencies=mutating)
async def run_now(
    body: ActionNowIn,
    user: User = Depends(current_user),
    control: ControlService = Depends(_control),
) -> dict[str, Any]:
    snapshot = await control.run_now(body.action, source=Source.WEB, user_id=user.id)
    return snapshot.to_api()


@router.get("/history")
async def history(
    limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    rows = await db.scalars(
        select(ActionLog).order_by(ActionLog.created_at.desc(), ActionLog.id.desc()).limit(limit)
    )
    return [history_entry(row) for row in rows]
