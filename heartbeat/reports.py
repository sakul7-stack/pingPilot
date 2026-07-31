import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone

from .models import HeartBeat as Heartbeat, Incident, Monitor

logger = logging.getLogger(__name__)


def _monitor_stats(monitor, days):
    cutoff = timezone.now() - timedelta(days=days)
    hbs = Heartbeat.objects.filter(monitor=monitor, checked_at__gte=cutoff)
    total = hbs.count()
    up = hbs.filter(status="UP").count()
    incidents = Incident.objects.filter(
        monitor=monitor, opened_at__gte=cutoff
    ).count()
    return {
        "name": monitor.name,
        "url": monitor.url,
        "uptime": round(up / total * 100, 2) if total else None,
        "checks": total,
        "incidents": incidents,
    }


def build_report(user, days, period_display):
    monitors = Monitor.objects.filter(user=user)
    stats = [_monitor_stats(m, days) for m in monitors]
    total_incidents = sum(s["incidents"] for s in stats)
    uptimes = [s["uptime"] for s in stats if s["uptime"] is not None]
    avg_uptime = round(sum(uptimes) / len(uptimes), 2) if uptimes else None
    return {
        "period_display": period_display,
        "avg_uptime": avg_uptime,
        "total_incidents": total_incidents,
        "monitors": stats,
        "dashboard_url": f"{settings.SITE_URL}/dashboard/",
    }


def _send_report(user, days, period_type, subject):
    from accounts.models import Profile
    profile, _ = Profile.objects.get_or_create(user=user)
    if period_type == "weekly" and not profile.weekly_report:
        return
    if period_type == "monthly" and not profile.monthly_report:
        return

    period_display = {"weekly": "This Week", "monthly": "This Month"}[period_type]
    ctx = build_report(user, days, period_display)
    if not ctx["monitors"]:
        return
    html = render_to_string("email/report.html", ctx)
    try:
        send_mail(subject, strip_tags(html), None, [user.email], html_message=html)
    except Exception as e:
        logger.error("Report email to %s failed: %s", user.email, e)


def send_weekly_reports():
    from django.contrib.auth.models import User
    for user in User.objects.exclude(email="").iterator():
        _send_report(user, 7, "weekly", "PingPilot Weekly Report")


def send_monthly_reports():
    from django.contrib.auth.models import User
    for user in User.objects.exclude(email="").iterator():
        _send_report(user, 30, "monthly", "PingPilot Monthly Report")


def check_ssl_expiry():
    from dashboard.views import get_ssl_info
    now = timezone.now()
    for monitor in Monitor.objects.filter(is_active=True).select_related("user"):
        if not monitor.user.email:
            continue
        info = get_ssl_info(monitor.url)
        if not info or info["remaining"] is None:
            continue
        remaining = info["remaining"]
        if remaining > 7:
            if monitor.ssl_alert_sent_at:
                Monitor.objects.filter(pk=monitor.pk).update(ssl_alert_sent_at=None)
            continue
        if monitor.ssl_alert_sent_at and monitor.ssl_alert_sent_at > now - timedelta(days=1):
            continue
        try:
            html = render_to_string("email/ssl_expiry.html", {
                "monitor": monitor,
                "expiry": info["expiry"],
                "remaining": remaining,
                "dashboard_url": f"{settings.SITE_URL}/dashboard/",
            })
            send_mail(
                f"SSL Certificate Expiring Soon: {monitor.name}",
                strip_tags(html),
                None,
                [monitor.user.email],
                html_message=html,
            )
            Monitor.objects.filter(pk=monitor.pk).update(ssl_alert_sent_at=now)
            logger.info("SSL expiry alert sent for monitor %s (%d days left)", monitor.name, remaining)
        except Exception as e:
            logger.error("SSL expiry email for %s failed: %s", monitor.name, e)
