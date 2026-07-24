from django.db import models,transaction
from django.utils import timezone

from .models import Monitor


def get_due_monitors(batch_size:int=500)->list[Monitor]:
    now=timezone.now()
    with transaction.atomic():
        return list(
            Monitor.objects
            .select_related("user")
            .select_for_update(skip_locked=True)
            .filter(is_active=True,next_check_at__lte=now)
            .order_by("next_check_at")[:batch_size]
        )


def next_sleep(monitors: list[Monitor]) -> float:
    if not monitors:
        return 5.0
    earliest = (
        Monitor.objects
        .filter(is_active=True)
        .aggregate(min=models.Min("next_check_at"))
        ["min"]
    )
    if not earliest or earliest <= timezone.now():
        return 2.0
    return min(5.0, (earliest - timezone.now()).total_seconds())