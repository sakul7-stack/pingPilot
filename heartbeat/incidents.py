from django.utils import timezone

from .enums import CheckResult, Status
from .models import Incident, Monitor


def open_or_close_incident(monitor: Monitor, result: CheckResult) -> None:
    now = timezone.now()

    if result.status == Status.UP:
        Incident.objects.filter(
            monitor=monitor, closed_at__isnull=True
        ).update(closed_at=now, reason="Resolved")
        return

    if result.status == Status.DOWN:
        has_open = Incident.objects.filter(
            monitor=monitor, closed_at__isnull=True
        ).exists()
        if not has_open:
            Incident.objects.create(monitor=monitor, opened_at=now)