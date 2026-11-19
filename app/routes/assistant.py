"""The farm assistant: a question in, a reply worded from the caller's own figures out."""

from datetime import date, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings
from app.core.time_window import day_window, time_zone
from app.dependencies import (
    Clock,
    CurrentUser,
    Scope,
    Visible,
    get_alert_store,
    get_app_settings,
    get_camera_store,
    get_clock,
    get_detection_log_store,
    get_event_store,
    require_assistant_model,
)
from app.schemas.assistant import AssistantQuestion, AssistantReply
from app.schemas.camera import effective_status
from app.services.alert_store import AlertStore
from app.services.assistant_model import AssistantModel, AssistantUnavailableError
from app.services.camera_store import CameraStore
from app.services.daily_report import DailyReportBuilder
from app.services.detection_log_store import DetectionLogStore
from app.services.event_store import EventStore

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

Detections = Annotated[DetectionLogStore, Depends(get_detection_log_store)]
Alerts = Annotated[AlertStore, Depends(get_alert_store)]
Events = Annotated[EventStore, Depends(get_event_store)]
Cameras = Annotated[CameraStore, Depends(get_camera_store)]


def _day_facts(
    day: date, tz: str, zone: ZoneInfo, now: datetime, scope: Scope,
    detections: DetectionLogStore, alerts: AlertStore, events: EventStore,
) -> dict[str, Any]:
    span = day_window(day, zone)
    entries = (item for item in detections.entries(None, span.start, span.end) if scope.sees_camera(item.camera_id))
    detected = [event for event in events.list_since(span.start, scope.camera_ids) if event.timestamp < span.end]
    report = DailyReportBuilder(day, tz, span, now).build(
        entries, alerts.created_between(span.start, span.end, scope.camera_ids), len(detected),
    )
    return report.model_dump(mode="json", exclude={"start", "end", "generated_at", "time_zone"})


@router.post("/messages", response_model=AssistantReply)
def ask_assistant(
    body: AssistantQuestion,
    _user: CurrentUser,
    scope: Visible,
    model: Annotated[AssistantModel, Depends(require_assistant_model)],
    detections: Detections,
    alerts: Alerts,
    events: Events,
    cameras: Cameras,
    settings: Annotated[Settings, Depends(get_app_settings)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> AssistantReply:
    """Answers from today's and yesterday's reports and the cameras' state, all limited to the caller's account.

    The account comes from the token and the figures are computed here before the model is called, so a question
    cannot reach another farm's data whatever it says. Alert texts, emails and camera addresses are not sent: they
    leave this server for a third party, and counts and camera names are enough to answer.
    """
    zone = time_zone(body.time_zone)
    now = clock()
    today = now.astimezone(zone).date()
    names = {item.id: item.name for item in cameras.saved(scope.account_id)}
    facts = {
        "now": now.astimezone(zone).isoformat(timespec="minutes"),
        "cameras": [
            {
                "id": record.id, "name": names.get(record.id),
                "status": effective_status(record, now, settings.camera_offline_after_seconds).value,
            }
            for record in cameras.list() if scope.sees_camera(record.id)
        ],
        "open_alerts": alerts.count_open(scope.camera_ids),
        "today": _day_facts(today, body.time_zone, zone, now, scope, detections, alerts, events),
        "yesterday": _day_facts(
            today - timedelta(days=1), body.time_zone, zone, now, scope, detections, alerts, events,
        ),
    }
    try:
        return AssistantReply(reply=model.answer(body.message, body.history, facts))
    except AssistantUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="The assistant is unavailable") from exc
