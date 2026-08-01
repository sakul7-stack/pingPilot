from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg, Q
from heartbeat.models import HeartBeat, Incident

import dns.resolver
import dns.rdatatype
import dns.rdataclass


def _txt_values(answers):
    values = []
    for r in answers:
        val = b''.join(r.strings)
        values.append(val.decode('utf-8', errors='replace') if isinstance(val, bytes) else val)
    return values


def resolve_txt_authoritative(fqdn):
    """Query the authoritative nameservers directly to bypass stale
    recursive-resolver caches (e.g. a cached NXDOMAIN). Falls back to
    the default recursive resolution if anything fails."""
    nameservers = []
    try:
        ns_answers = dns.resolver.resolve(fqdn, 'NS')
        ns_names = [str(r.target).rstrip('.') for r in ns_answers]
    except Exception:
        ns_names = []
    for ns in ns_names:
        try:
            for a in dns.resolver.resolve(ns, 'A'):
                nameservers.append(a.address)
        except Exception:
            continue
    try:
        if nameservers:
            res = dns.resolver.Resolver()
            res.nameservers = nameservers
            res.lifetime = 10
            answers = res.resolve(fqdn, 'TXT')
            return _txt_values(answers)
    except Exception:
        pass
    answers = dns.resolver.resolve(fqdn, 'TXT')
    return _txt_values(answers)


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
