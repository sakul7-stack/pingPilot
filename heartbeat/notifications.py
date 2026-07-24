from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone

from .enums import CheckResult
from .models import Monitor


def send_down_alert(monitor: Monitor, result: CheckResult) -> None:
    subject = f"DOWN: {monitor.name}"
    context = {
        "monitor": monitor,
        "result": result,
        "dashboard_url": "http://127.0.0.1:8000/dashboard/",
    }
    html = render_to_string("email/down_alert.html", context)
    text = strip_tags(html)
    send_mail(subject, text, None, [monitor.user.email], html_message=html)


def send_up_alert(monitor: Monitor) -> None:
    subject = f"UP: {monitor.name} recovered"
    context = {
        "monitor": monitor,
        "recovered_at": timezone.now(),
        "dashboard_url": "http://127.0.0.1:8000/dashboard/",
    }
    html = render_to_string("email/up_alert.html", context)
    text = strip_tags(html)
    send_mail(subject, text, None, [monitor.user.email], html_message=html)
