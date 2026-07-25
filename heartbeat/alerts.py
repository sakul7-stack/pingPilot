from django.utils import timezone
from django.db.models import F

from .enums import CheckResult, Status
from .models import Monitor
from .notifications import send_down_alert, send_up_alert


def evaluate_and_alert(monitor: Monitor, result: CheckResult) -> None:
    now = timezone.now()

    if result.status == Status.UP:
        if monitor.last_status == Status.DOWN and monitor.last_alert_sent_at:
            send_up_alert(monitor)
            Monitor.objects.filter(pk=monitor.pk).update(last_alert_sent_at=None)
        return

    if monitor.last_alert_sent_at:
        return

    send_down_alert(monitor, result)
    Monitor.objects.filter(pk=monitor.pk).update(last_alert_sent_at=now)