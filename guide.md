# PingPilot Heartbeat Worker — Implementation Guide

This guide walks through every file you need to create or modify to implement the architecture from `proposal.md`.

---

## Step 1: Create the `heartbeat` app

```bash
python manage.py startapp heartbeat
```

Remove the default `views.py`, `tests.py`, and `admin.py` from `heartbeat/` since the worker is a headless process.

App layout after this guide:

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
    apps.py
    management/
        __init__.py
        commands/
            __init__.py
            runworker.py
```

---

## Step 2: Register the app

In `config/settings.py`, add to `INSTALLED_APPS`:

```python
'heartbeat',
```

---

## Step 3: `heartbeat/enums.py` — Shared types

Contains the enums and dataclass used across the worker.

**What to write:**

- `HttpMethod` — `TextChoices` with `GET` and `HEAD`
- `Status` — `TextChoices` with `UP`, `DOWN`, `DEGRADED`
- `CheckResult` — a `@dataclass` with:
  - `status: Status`
  - `status_code: int | None`
  - `error: str` (empty string on success)
  - `response_time_ms: float | None`
  - `body_size: int | None`
  - `checked_at: datetime`

---

## Step 4: `heartbeat/models.py` — Database models

Replace the default empty models with three models.

### Monitor

| Field | Type | Notes |
|-------|------|-------|
| user | ForeignKey(User) | `on_delete=CASCADE` |
| name | CharField(200) | User-facing label |
| url | URLField | Target to monitor |
| method | CharField(4) | Choices from `HttpMethod`, default `GET` |
| expected_status | IntegerField | default `200` |
| expected_keyword | CharField(500) | blank=True, optional |
| timeout | IntegerField | default `10` seconds |
| check_interval_seconds | PositiveIntegerField | default `600`, validators `[MinValue(180), MaxValue(86400)]` |
| next_check_at | DateTimeField | default `timezone.now` |
| consecutive_failures | IntegerField | default `0` |
| last_checked_at | DateTimeField | null, blank |
| last_status | CharField(10) | `Status.choices`, null |
| last_alert_sent_at | DateTimeField | null, blank |
| is_active | BooleanField | default `True` |
| created_at | DateTimeField | auto_now_add |
| updated_at | DateTimeField | auto_now |

**Meta indexes:**

```python
indexes = [
    models.Index(fields=["next_check_at"]),
    models.Index(fields=["user"]),
    models.Index(fields=["is_active"]),
]
```

### Heartbeat

| Field | Type | Notes |
|-------|------|-------|
| monitor | ForeignKey(Monitor) | `related_name="heartbeats"` |
| status | CharField(10) | `Status.choices` |
| status_code | IntegerField | null |
| error | CharField(200) | blank |
| response_time_ms | FloatField | null |
| body_size | IntegerField | null |
| checked_at | DateTimeField | auto_now_add |

**Meta indexes:**

```python
indexes = [models.Index(fields=["monitor", "-checked_at"])]
```

### Incident

| Field | Type | Notes |
|-------|------|-------|
| monitor | ForeignKey(Monitor) | `related_name="incidents"` |
| opened_at | DateTimeField | auto_now_add |
| closed_at | DateTimeField | null, blank |
| reason | TextField | blank |

**Meta indexes:**

```python
indexes = [models.Index(fields=["monitor", "closed_at"])]
```

### After writing models

```bash
python manage.py makemigrations heartbeat
python manage.py migrate heartbeat
```

---

## Step 5: `heartbeat/scheduler.py` — Fetch due monitors

**Function: `get_due_monitors(batch_size=500)`**

```python
from django.db import transaction
from django.utils import timezone
from .models import Monitor

def get_due_monitors(batch_size=500):
    now = timezone.now()
    with transaction.atomic():
        return list(
            Monitor.objects
            .select_related("user")
            .select_for_update(skip_locked=True)
            .filter(is_active=True, next_check_at__lte=now)
            .order_by("next_check_at")[:batch_size]
        )
```

**Function: `next_sleep(monitors)`**

```python
def next_sleep(monitors):
    from django.utils import timezone
    now = timezone.now()
    if not monitors:
        return 5
    # Query the earliest next_check_at across all monitors
    earliest = (
        Monitor.objects
        .filter(is_active=True)
        .aggregate(min=models.Min("next_check_at"))
        ["min__min"]
    )
    if not earliest or earliest <= now:
        return 2
    return min(5, (earliest - now).total_seconds())
```

---

## Step 6: `heartbeat/checker.py` — Async HTTP checks

**Function: `check_monitor(monitor, client) -> CheckResult`**

Logic flow:

1. Record `started = timezone.now()`
2. Try `await client.request(monitor.method, monitor.url, timeout=monitor.timeout)`
3. On success:
   - Compute `response_time_ms` from elapsed time
   - Call `evaluate_response(resp, monitor)` to get status
   - Return `CheckResult(status=..., status_code=resp.status_code, error="", ...)`
4. On `httpx.TimeoutException`:
   - Call `retry_if_transient("TIMEOUT", monitor, client, started)`
5. On `httpx.ConnectError`:
   - Return `CheckResult(status=DOWN, status_code=None, error="DNS_ERROR", ...)`
6. On `httpx.SSLError`:
   - Return `CheckResult(status=DOWN, status_code=None, error="SSL_ERROR", ...)`

**Function: `evaluate_response(resp, monitor) -> Status`**

```python
def evaluate_response(resp, monitor):
    from .enums import Status
    if resp.status_code != monitor.expected_status:
        return Status.DOWN
    if monitor.expected_keyword:
        if monitor.expected_keyword not in resp.text:
            return Status.DEGRADED
    return Status.UP
```

**Function: `retry_if_transient(error, monitor, client, started)`**

1. If error not in `{"TIMEOUT", "CONNECTION_RESET", "HTTP_502", "HTTP_503", "HTTP_504"}`:
   - Return `CheckResult(status=DOWN, error=error, ...)`
2. `await asyncio.sleep(2)`
3. Retry the request once
4. On success: return `CheckResult(status=UP, ...)`
5. On failure: return `CheckResult(status=DOWN, error=error, ...)`

---

## Step 7: `heartbeat/services.py` — ORM persistence

**Function: `save_result(monitor, result)`**

1. Create a `Heartbeat` record from the `CheckResult`
2. Update the `Monitor`:
   - `consecutive_failures`: use `F("consecutive_failures") + 1` if DOWN, else set to `0`
   - `last_checked_at = now()`
   - `last_status = result.status`
   - `next_check_at = now() + timedelta(seconds=monitor.check_interval_seconds)`

**Function: `update_monitor(monitor_id, **kwargs)`**

A thin wrapper around `Monitor.objects.filter(pk=monitor_id).update(...)` for atomic field updates.

---

## Step 8: `heartbeat/notifications.py` — Notification abstraction

**Function: `send_down_alert(monitor, result)`**

```python
from django.core.mail import send_mail

def send_down_alert(monitor, result):
    subject = f"DOWN: {monitor.name}"
    message = (
        f"Monitor: {monitor.name}\n"
        f"URL: {monitor.url}\n"
        f"Error: {result.error}\n"
        f"Status: {result.status_code}\n"
        f"Time: {result.checked_at}"
    )
    send_mail(subject, message, None, [monitor.user.email])
```

**Function: `send_up_alert(monitor)`**

```python
def send_up_alert(monitor):
    subject = f"UP: {monitor.name} recovered"
    message = f"{monitor.name} ({monitor.url}) is back online."
    send_mail(subject, message, None, [monitor.user.email])
```

Later, this file can grow to support Discord webhooks, Slack, SMS, etc. without touching `alerts.py`.

---

## Step 9: `heartbeat/alerts.py` — Alert evaluation

**Function: `evaluate_and_alert(monitor, result)`**

Use `sync_to_async` when calling from the async worker loop.

Logic:

```
if result.status == UP:
    if monitor.last_status == "DOWN" and monitor.last_alert_sent_at:
        send_up_alert(monitor)
    return

if monitor.consecutive_failures + 1 < 3:
    return   # not yet confirmed down

if monitor.last_alert_sent_at and \
   (now - monitor.last_alert_sent_at).total_seconds() < 1800:
    return   # suppression (30 min cooldown)

send_down_alert(monitor, result)
Monitor.objects.filter(pk=monitor.pk).update(last_alert_sent_at=now)
```

---

## Step 10: `heartbeat/incidents.py` — Incident lifecycle

**Function: `open_or_close_incident(monitor, result)`**

```
if result.status == UP:
    close any Incident where monitor=monitor and closed_at=None
    set closed_at=now, reason="Resolved"

if result.status == "DOWN":
    if no open Incident exists for this monitor:
        create Incident(monitor=monitor, opened_at=now)
```

---

## Step 11: `heartbeat/cleanup.py` — Data pruning

**Function: `aggregate_and_prune(days_to_keep=30)`**

1. Query heartbeats older than `days_to_keep` days
2. Delete in batches of 5000 to avoid long table locks:

```python
from .models import Heartbeat

def prune_old_heartbeats(days=30):
    cutoff = timezone.now() - timedelta(days=days)
    qs = Heartbeat.objects.filter(checked_at__lt=cutoff)
    while True:
        batch = qs[:5000]
        if not batch:
            break
        Heartbeat.objects.filter(pk__in=[b.pk for b in batch]).delete()
```

3. Optional: compute daily uptime stats and store in a `DailyStats` model for graph rendering

Run via a separate management command or cron.

---

## Step 12: `heartbeat/management/commands/runworker.py` — The worker

**Structure:** Subclass `BaseCommand`

**`handle(self, *args, **options)`**

```python
import asyncio, logging, signal
from django.db.models import F
from asgiref.sync import sync_to_async
import httpx

logger = logging.getLogger(__name__)

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

            if monitors:
                await asyncio.gather(*[process(m) for m in monitors])

            await asyncio.sleep(next_sleep(monitors))
```

Note: `next_sleep` queries the DB for the earliest `next_check_at` to sleep adaptively.

---

## Step 13: `heartbeat/apps.py` — App config

No changes needed from the default, but verify:

```python
class HeartbeatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "heartbeat"
```

---

## Step 14: Register the cleanup command

Optionally, create a separate management command:

**`heartbeat/management/commands/cleanup.py`**

```python
from django.core.management.base import BaseCommand
from heartbeat.cleanup import prune_old_heartbeats

class Command(BaseCommand):
    help = "Prune old heartbeats and aggregate stats"
    def handle(self, *args, **options):
        prune_old_heartbeats(days=30)
        self.stdout.write("Cleanup complete")
```

Run with: `python manage.py cleanup` (via cron, daily).

---

## Step 15: Add `httpx` to requirements

`httpx` is needed for async HTTP. Add to `requirements.txt`:

```
httpx
```

Then:

```bash
pip install httpx
```

---

## Summary of all files to create/modify

| Action | File | What to write |
|--------|------|--------------|
| Create | `heartbeat/enums.py` | `HttpMethod`, `Status` enums, `CheckResult` dataclass |
| Create | `heartbeat/models.py` | `Monitor`, `Heartbeat`, `Incident` models |
| Create | `heartbeat/scheduler.py` | `get_due_monitors()`, `next_sleep()` |
| Create | `heartbeat/checker.py` | `check_monitor()`, `evaluate_response()`, `retry_if_transient()` |
| Create | `heartbeat/services.py` | `save_result()`, `update_monitor()` |
| Create | `heartbeat/notifications.py` | `send_down_alert()`, `send_up_alert()` |
| Create | `heartbeat/alerts.py` | `evaluate_and_alert()` |
| Create | `heartbeat/incidents.py` | `open_or_close_incident()` |
| Create | `heartbeat/cleanup.py` | `prune_old_heartbeats()` |
| Create | `heartbeat/management/commands/runworker.py` | Main event loop |
| Create | `heartbeat/management/commands/cleanup.py` | Optional pruning command |
| Edit | `config/settings.py` | Add `heartbeat` to `INSTALLED_APPS` |
| Edit | `requirements.txt` | Add `httpx` |

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

## Verification checklist

- [ ] `python manage.py makemigrations heartbeat` succeeds
- [ ] `python manage.py migrate heartbeat` succeeds
- [ ] `python manage.py runworker` starts without errors
- [ ] Worker logs `"Checking N monitors..."` when a monitor is due
- [ ] `Heartbeat` rows appear in the database after checks
- [ ] Email is sent after 3 consecutive failures
- [ ] No duplicate emails within 30 minutes
- [ ] `Incident` opens on DOWN, closes on UP
- [ ] `python manage.py cleanup` deletes old heartbeats
