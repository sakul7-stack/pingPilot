from datetime import timedelta

from django.utils import timezone

from .models import HeartBeat as Heartbeat


def prune_old_heartbeats(days: int = 90) -> int:
    cutoff = timezone.now() - timedelta(days=days)
    qs = Heartbeat.objects.filter(checked_at__lt=cutoff)
    total = 0
    while True:
        ids = list(qs.values_list("pk", flat=True)[:5000])
        if not ids:
            break
        deleted, _ = Heartbeat.objects.filter(pk__in=ids).delete()
        total += deleted
    return total