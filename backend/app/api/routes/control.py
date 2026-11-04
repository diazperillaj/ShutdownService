from fastapi import APIRouter, Depends

from ...models import Source, User
from ...schemas.control import ActionNowIn, ExtendIn, ScheduleIn, StatusOut
from ...services.control_service import ControlService
from ..deps import current_user, get_control_service, require_same_origin

router = APIRouter(prefix="/api", tags=["control"], dependencies=[Depends(current_user)])
_mutating = [Depends(require_same_origin)]


@router.get("/status", response_model=StatusOut)
async def get_status(control: ControlService = Depends(get_control_service)) -> StatusOut:
    return control.status()


@router.post("/schedule", response_model=StatusOut, dependencies=_mutating)
async def schedule(
    body: ScheduleIn,
    user: User = Depends(current_user),
    control: ControlService = Depends(get_control_service),
) -> StatusOut:
    if body.at is not None:
        snapshot = await control.schedule_at(body.action, body.at, source=Source.WEB, user_id=user.id)
    else:
        snapshot = await control.schedule(
            body.action, body.delay_seconds, source=Source.WEB, user_id=user.id
        )
    return snapshot.to_status()


@router.post("/schedule/extend", response_model=StatusOut, dependencies=_mutating)
async def extend(
    body: ExtendIn,
    user: User = Depends(current_user),
    control: ControlService = Depends(get_control_service),
) -> StatusOut:
    snapshot = await control.extend(body.seconds, source=Source.WEB, user_id=user.id)
    return snapshot.to_status()


@router.delete("/schedule", response_model=StatusOut, dependencies=_mutating)
async def cancel(
    user: User = Depends(current_user), control: ControlService = Depends(get_control_service)
) -> StatusOut:
    result = await control.cancel(source=Source.WEB, user_id=user.id)
    return result.snapshot.to_status()


@router.post("/actions/now", response_model=StatusOut, dependencies=_mutating)
async def run_now(
    body: ActionNowIn,
    user: User = Depends(current_user),
    control: ControlService = Depends(get_control_service),
) -> StatusOut:
    snapshot = await control.run_now(body.action, source=Source.WEB, user_id=user.id)
    return snapshot.to_status()
