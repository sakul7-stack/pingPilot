from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Q
from heartbeat.models import HeartBeat, Incident


def build_timeline(monitor, segments=30):
    now = timezone.now()
    range_start = now - timedelta(hours=24)
    total_seconds = (now - range_start).total_seconds()
    segment_seconds = total_seconds / segments

    timeline = []
    for i in range(segments):
        seg_start = range_start + timedelta(seconds=i * segment_seconds)
        seg_end = seg_start + timedelta(seconds=segment_seconds)
        total = HeartBeat.objects.filter(
            monitor=monitor,
            checked_at__gte=seg_start,
            checked_at__lt=seg_end,
        ).count()
        up = HeartBeat.objects.filter(
            monitor=monitor,
            checked_at__gte=seg_start,
            checked_at__lt=seg_end,
            status='UP',
        ).count()
        pct = round((up / total * 100), 1) if total > 0 else None
        if pct == 100:
            segment_status = 'up'
        elif pct is None:
            segment_status = 'no_data'
        elif pct >= 98:
            segment_status = 'degraded'
        else:
            segment_status = 'down'
        timeline.append({
            'uptime': pct,
            'status': segment_status,
            'label': seg_start.strftime('%H:%M'),
        })
    return timeline
