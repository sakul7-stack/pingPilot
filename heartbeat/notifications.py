import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone

from .enums import CheckResult
from .models import Monitor, AlertLog
from .providers import dispatch

logger = logging.getLogger(__name__)

BASE = f"{settings.SITE_URL}/dashboard/"


def send_down_alert(monitor: Monitor, result: CheckResult) -> None:
    payload = {
        "event": "down",
        "monitor": {"name": monitor.name, "url": monitor.url},
        "result": result.to_dict(),
    }
    if monitor.email_alerts:
        _send_email(monitor, "down", payload)
        AlertLog.objects.create(monitor=monitor, event="down", channel="email")
    for ch in monitor.channels.all():
        dispatch(ch.provider, ch.config, payload, ch)
        AlertLog.objects.create(monitor=monitor, event="down", channel=ch.provider)


def send_up_alert(monitor: Monitor) -> None:
    payload = {
        "event": "up",
        "monitor": {"name": monitor.name, "url": monitor.url},
        "recovered_at": timezone.now().isoformat(),
    }
    if monitor.email_alerts:
        _send_email(monitor, "up", payload)
        AlertLog.objects.create(monitor=monitor, event="up", channel="email")
    for ch in monitor.channels.all():
        dispatch(ch.provider, ch.config, payload, ch)
        AlertLog.objects.create(monitor=monitor, event="up", channel=ch.provider)


def _send_email(monitor, event: str, payload: dict) -> None:
    subject = f"DOWN: {monitor.name}" if event == "down" else f"UP: {monitor.name} recovered"
    template = "email/down_alert.html" if event == "down" else "email/up_alert.html"
    html = render_to_string(template, {**payload, "dashboard_url": BASE})
    send_mail(subject, strip_tags(html), None, [monitor.user.email], html_message=html)


def send_test_email(monitor) -> None:
    subject = f"\U0001f9ea TEST: {monitor.name}"
    message = (
        f"Test notification from PingPilot\n"
        f"Monitor: {monitor.name}\n"
        f"URL: {monitor.url}"
    )
    try:
        send_mail(subject, message, None, [monitor.user.email], fail_silently=False)
    except Exception as e:
        logger.error("Test email failed: %s", e)


def send_test_channel(monitor, channel) -> None:
    payload = {
        "event": "test",
        "monitor": {"id": monitor.id, "name": monitor.name, "url": monitor.url},
    }
    dispatch(channel.provider, channel.config, payload, channel)