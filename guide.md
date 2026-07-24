# PingPilot Heartbeat Worker — Implementation Guide

This guide walks through every file you need to create or modify for the heartbeat monitoring worker.

---

## Step 1: Create the `heartbeat` app

```bash
python manage.py startapp heartbeat
```

Remove the default `views.py`, `tests.py`, and `admin.py` from `heartbeat/`.

Final app layout:

```
heartbeat/
    __init__.py
    models.py
    enums.py
    scheduler.py
    checker.py
    services.py
    alerts.py
    incidents.py
    notifications.py
    cleanup.py
    management/
        __init__.py
        commands/
            __init__.py
            runworker.py
            cleanup.py
```

---

## Step 2: Register the app

In `config/settings.py`, add `'heartbeat'` to `INSTALLED_APPS`.

---

## Step 3: `heartbeat/enums.py` — Shared types

```python
from django.db import models
from dataclasses import dataclass
from datetime import datetime


class HttpMethod(models.TextChoices):
    GET = "GET"
    HEAD = "HEAD"


class Status(models.TextChoices):
    UP = "UP"
    DOWN = "DOWN"
    DEGRADED = "DEGRADED"


@dataclass
class CheckResult:
    status: Status
    status_code: int | None
    error: str
    response_time_ms: float | None
    body_size: int | None
    checked_at: datetime
```

---

## Step 4: `heartbeat/models.py` — Database models

```python
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

from .enums import HttpMethod, Status


class Monitor(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    url = models.URLField()
    method = models.CharField(
        max_length=4, choices=HttpMethod.choices, default=HttpMethod.GET
    )
    expected_status = models.IntegerField(default=200)
    expected_keyword = models.CharField(max_length=500, blank=True)
    timeout = models.IntegerField(default=10)
    check_interval_seconds = models.PositiveIntegerField(
        default=600,
        validators=[MinValueValidator(180), MaxValueValidator(86400)],
    )
    next_check_at = models.DateTimeField(default=timezone.now)
    consecutive_failures = models.IntegerField(default=0)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(
        max_length=10, choices=Status.choices, null=True
    )
    last_alert_sent_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["next_check_at"]),
            models.Index(fields=["user"]),
            models.Index(fields=["is_active"]),
        ]


class Heartbeat(models.Model):
    monitor = models.ForeignKey(
        Monitor, on_delete=models.CASCADE, related_name="heartbeats"
    )
    status = models.CharField(max_length=10, choices=Status.choices)
    status_code = models.IntegerField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)
    response_time_ms = models.FloatField(null=True, blank=True)
    body_size = models.IntegerField(null=True, blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["monitor", "-checked_at"])]


class Incident(models.Model):
    monitor = models.ForeignKey(
        Monitor, on_delete=models.CASCADE, related_name="incidents"
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["monitor", "closed_at"])]
```

### Apply migrations

```bash
python manage.py makemigrations heartbeat
python manage.py migrate heartbeat
```

---

## Step 5: `heartbeat/scheduler.py` — Fetch due monitors

```python
from django.db import models, transaction
from django.utils import timezone

from .models import Monitor


def get_due_monitors(batch_size: int = 500) -> list[Monitor]:
    now = timezone.now()
    with transaction.atomic():
        return list(
            Monitor.objects
            .select_related("user")
            .select_for_update(skip_locked=True)
            .filter(is_active=True, next_check_at__lte=now)
            .order_by("next_check_at")[:batch_size]
        )


def next_sleep(monitors: list[Monitor]) -> float:
    if not monitors:
        return 5.0
    earliest = (
        Monitor.objects
        .filter(is_active=True)
        .aggregate(min=models.Min("next_check_at"))
        ["next_check_at__min"]
    )
    if not earliest or earliest <= timezone.now():
        return 2.0
    return min(5.0, (earliest - timezone.now()).total_seconds())
```

---

## Step 6: `heartbeat/checker.py` — Async HTTP checks

```python
import asyncio
from datetime import datetime

import httpx

from .enums import CheckResult, Status
from .models import Monitor

TRANSIENT_ERRORS = {"TIMEOUT", "CONNECTION_RESET", "HTTP_502", "HTTP_503", "HTTP_504"}


def evaluate_response(resp: httpx.Response, monitor: Monitor) -> Status:
    if resp.status_code != monitor.expected_status:
        return Status.DOWN
    if monitor.expected_keyword:
        if monitor.expected_keyword not in resp.text:
            return Status.DEGRADED
    return Status.UP


def _check_result(status: Status, error: str, **kw) -> CheckResult:
    return CheckResult(
        status=status,
        status_code=kw.get("status_code"),
        error=error,
        response_time_ms=kw.get("response_time_ms"),
        body_size=kw.get("body_size"),
        checked_at=datetime.now(),
    )


async def check_monitor(
    monitor: Monitor, client: httpx.AsyncClient
) -> CheckResult:
    started = datetime.now()
    method = monitor.method.lower()
    try:
        resp = await client.request(
            method, monitor.url, timeout=monitor.timeout
        )
        elapsed = (datetime.now() - started).total_seconds() * 1000
        status = evaluate_response(resp, monitor)
        body = resp.content
        return _check_result(
            status,
            error="",
            status_code=resp.status_code,
            response_time_ms=elapsed,
            body_size=len(body),
        )
    except httpx.TimeoutException:
        return await retry_if_transient("TIMEOUT", monitor, client, started)
    except httpx.ConnectError:
        return _check_result(Status.DOWN, error="DNS_ERROR")
    except httpx.SSLError:
        return _check_result(Status.DOWN, error="SSL_ERROR")


async def retry_if_transient(
    error: str,
    monitor: Monitor,
    client: httpx.AsyncClient,
    started: datetime,
) -> CheckResult:
    if error not in TRANSIENT_ERRORS:
        return _check_result(Status.DOWN, error=error)
    await asyncio.sleep(2)
    method = monitor.method.lower()
    try:
        resp = await client.request(
            method, monitor.url, timeout=monitor.timeout
        )
        elapsed = (datetime.now() - started).total_seconds() * 1000
        status = evaluate_response(resp, monitor)
        body = resp.content
        return _check_result(
            status,
            error="",
            status_code=resp.status_code,
            response_time_ms=elapsed,
            body_size=len(body),
        )
    except Exception:
        return _check_result(Status.DOWN, error=error)
```

---

## Step 7: `heartbeat/services.py` — ORM persistence

```python
from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from .enums import CheckResult, Status
from .models import Heartbeat, Monitor


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
```

---

## Step 8: `heartbeat/notifications.py` — Email alerts

```python
from django.core.mail import send_mail

from .enums import CheckResult
from .models import Monitor


def send_down_alert(monitor: Monitor, result: CheckResult) -> None:
    subject = f"DOWN: {monitor.name}"
    message = (
        f"Monitor: {monitor.name}\n"
        f"URL: {monitor.url}\n"
        f"Error: {result.error}\n"
        f"Status code: {result.status_code}\n"
        f"Time: {result.checked_at}"
    )
    send_mail(subject, message, None, [monitor.user.email])


def send_up_alert(monitor: Monitor) -> None:
    subject = f"UP: {monitor.name} recovered"
    message = f"{monitor.name} ({monitor.url}) is back online."
    send_mail(subject, message, None, [monitor.user.email])
```

Later extendable to Discord, Slack, SMS, etc. by adding new send functions.

---

## Step 9: `heartbeat/alerts.py` — Alert logic

```python
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
        return

    if monitor.consecutive_failures + 1 < 3:
        return

    if monitor.last_alert_sent_at:
        cooldown = (now - monitor.last_alert_sent_at).total_seconds()
        if cooldown < 1800:
            return

    send_down_alert(monitor, result)
    Monitor.objects.filter(pk=monitor.pk).update(last_alert_sent_at=now)
```

---

## Step 10: `heartbeat/incidents.py` — Incident lifecycle

```python
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
```

---

## Step 11: `heartbeat/cleanup.py` — Data pruning

```python
from datetime import timedelta

from django.utils import timezone

from .models import Heartbeat


def prune_old_heartbeats(days: int = 30) -> int:
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
```

---

## Step 12: `heartbeat/management/commands/runworker.py` — Worker loop

```python
import asyncio
import logging

import httpx
from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand

from heartbeat.alerts import evaluate_and_alert
from heartbeat.checker import check_monitor
from heartbeat.incidents import open_or_close_incident
from heartbeat.scheduler import get_due_monitors, next_sleep
from heartbeat.services import save_result

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the heartbeat monitoring worker"

    def handle(self, *args, **options):
        logger.info("Worker started")
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            logger.info("Worker shutting down")

    async def _run(self):
        semaphore = asyncio.Semaphore(100)
        async with httpx.AsyncClient(timeout=10) as client:
            while True:
                monitors = get_due_monitors()
                logger.info("Checking %d monitors...", len(monitors))

                async def process(monitor):
                    async with semaphore:
                        result = await check_monitor(monitor, client)
                        await sync_to_async(save_result)(monitor, result)
                        await sync_to_async(evaluate_and_alert)(monitor, result)
                        await sync_to_async(open_or_close_incident)(monitor, result)
                        logger.info(
                            "monitor=%s status=%s latency=%.0fms error=%s",
                            monitor.name, result.status,
                            result.response_time_ms or 0, result.error,
                        )

                if monitors:
                    await asyncio.gather(*[process(m) for m in monitors])

                await asyncio.sleep(next_sleep(monitors))
```

---

## Step 13: `heartbeat/management/commands/cleanup.py` — Cleanup command

```python
from django.core.management.base import BaseCommand

from heartbeat.cleanup import prune_old_heartbeats


class Command(BaseCommand):
    help = "Prune old heartbeats and aggregate stats"

    def handle(self, *args, **options):
        deleted = prune_old_heartbeats(days=30)
        self.stdout.write(f"Cleanup complete — {deleted} heartbeats deleted")
```

---

## Step 14: Add `httpx` to requirements

`httpx` is needed for async HTTP. Add to `requirements.txt`:

```
httpx
```

Then:

```bash
pip install httpx
```

---

## Running the worker

```bash
# Terminal 1 — web server
python manage.py runserver

# Terminal 2 — worker
python manage.py runworker

# Cleanup (cron: daily)
python manage.py cleanup
```

---

## Summary of all files

| Action | File |
|--------|------|
| Create | `heartbeat/enums.py` |
| Create | `heartbeat/models.py` |
| Create | `heartbeat/scheduler.py` |
| Create | `heartbeat/checker.py` |
| Create | `heartbeat/services.py` |
| Create | `heartbeat/notifications.py` |
| Create | `heartbeat/alerts.py` |
| Create | `heartbeat/incidents.py` |
| Create | `heartbeat/cleanup.py` |
| Create | `heartbeat/management/commands/runworker.py` |
| Create | `heartbeat/management/commands/cleanup.py` |
| Edit | `config/settings.py` — add `'heartbeat'` to `INSTALLED_APPS` |
| Edit | `requirements.txt` — add `httpx` |

---

## Verification checklist

- [ ] `python manage.py makemigrations heartbeat` succeeds
- [ ] `python manage.py migrate heartbeat` succeeds
- [ ] `python manage.py runworker` starts without errors
- [ ] Worker logs `"Checking N monitors..."` when a monitor is due
- [ ] `Heartbeat` rows appear in DB after checks
- [ ] Email sent after 3 consecutive failures
- [ ] No duplicate emails within 30 minutes
- [ ] `Incident` opens on DOWN, closes on UP
- [ ] `python manage.py cleanup` deletes old heartbeats
