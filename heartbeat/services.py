from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from .enums import CheckResult, Status
from .models import HeartBeat as Heartbeat, Monitor


def save_result(monitor: Monitor, result: CheckResult) -> Heartbeat:
    now = timezone.now()
    hb = Heartbeat.objects.create(
        monitor=monitor,
        status=result.status,
        status_code=result.status_code,
        error=result.error,
        response_time_ms=result.response_time_ms,
        body_size=result.body_size,
    )
    if result.status == Status.DOWN:
        Monitor.objects.filter(pk=monitor.pk).update(
            consecutive_failures=F("consecutive_failures") + 1,
            last_checked_at=now,
            last_status=result.status,
            next_check_at=now + timedelta(seconds=monitor.check_interval_seconds),
        )
    else:
        Monitor.objects.filter(pk=monitor.pk).update(
            consecutive_failures=0,
            last_checked_at=now,
            last_status=result.status,
            next_check_at=now + timedelta(seconds=monitor.check_interval_seconds),
        )
    return hb


def update_monitor(monitor_id: int, **kwargs) -> None:
    Monitor.objects.filter(pk=monitor_id).update(**kwargs)
