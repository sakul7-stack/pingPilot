# PingPilot Heartbeat Worker — Architecture Proposal

## Models

```python
class HttpMethod(models.TextChoices):
    GET = "GET"
    HEAD = "HEAD"

class Status(models.TextChoices):
    UP = "UP"
    DOWN = "DOWN"
    DEGRADED = "DEGRADED"

class Monitor(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    url = models.URLField()
    method = models.CharField(max_length=4, choices=HttpMethod.choices, default=HttpMethod.GET)
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
    last_status = models.CharField(max_length=10, choices=Status.choices, null=True)
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
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="heartbeats")
    status = models.CharField(max_length=10, choices=Status.choices)
    status_code = models.IntegerField(null=True, blank=True)
    error = models.CharField(max_length=200, blank=True)
    response_time_ms = models.FloatField(null=True, blank=True)
    body_size = models.IntegerField(null=True, blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["monitor", "-checked_at"])]

class Incident(models.Model):
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name="incidents")
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["monitor", "closed_at"])]
```

## File Structure

```
heartbeat/
    __init__.py
    models.py
    enums.py               # HttpMethod, Status, CheckResult dataclass
    scheduler.py           # get_due_monitors()
    checker.py             # check_monitor() — async HTTP, retry
    services.py            # save_result(), update_monitor(), finish_incident()
    alerts.py              # evaluate_and_alert()
    incidents.py           # open_or_close_incident()
    notifications.py       # send_down_alert(), send_up_alert()
    cleanup.py             # aggregate + bulk delete
    management/
        commands/
            __init__.py
            runworker.py
```

## CheckResult Dataclass

```
CheckResult:
    status: Status
    status_code: int | None
    error: str               # "", "TIMEOUT", "DNS_ERROR", "SSL_ERROR", "HTTP_502"
    response_time_ms: float | None
    body_size: int | None
    checked_at: datetime
```

## Scheduler

```
get_due_monitors(batch_size=500):
    BEGIN TRANSACTION
    SELECT ... FROM monitors
    WHERE is_active=True AND next_check_at <= NOW()
    ORDER BY next_check_at ASC
    LIMIT batch_size
    FOR UPDATE SKIP LOCKED
    COMMIT

    return prefetched monitors (with select_related("user"))
```

Adaptive sleep: `min(5, next_due - now)`. If no monitors, sleep 5s.

## Checker (async)

```
check_monitor(monitor, client) → CheckResult:
    started = now()
    try:
        resp = await client.request(method, url, timeout=monitor.timeout)
        latency = elapsed_ms(started)
        status = evaluate(resp, monitor)
        return CheckResult(status, resp.status_code, ...)
    except TimeoutException:
        return retry_if_transient("TIMEOUT", monitor, client)
    except ConnectError:
        return CheckResult(DOWN, error="DNS_ERROR")
    except SSLError:
        return CheckResult(DOWN, error="SSL_ERROR")

evaluate(resp, monitor) → Status:
    if resp.status_code != monitor.expected_status:
        return DOWN
    if monitor.expected_keyword:
        if keyword not in resp.text:
            return DEGRADED
    return UP

retry_if_transient(error, monitor, client):
    if error not in {TIMEOUT, CONNECTION_RESET, 502, 503, 504}:
        return CheckResult(DOWN, error=error)
    await sleep(2)
    try:
        resp = await client.request(...)
        return evaluate(...)
    except:
        return CheckResult(DOWN, error=error)
```

## Worker Main Loop

```
handle():
    semaphore = Semaphore(100)
    client = httpx.AsyncClient(timeout=10)

    while True:
        monitors = scheduler.get_due_monitors()

        async def process(m):
            async with semaphore:
                result = await checker.check_monitor(m, client)
                await sync_to_async(services.save_result)(m, result)
                await sync_to_async(alerts.evaluate_and_alert)(m, result)
                await sync_to_async(incidents.open_or_close)(m, result)

        await asyncio.gather(*[process(m) for m in monitors])
        await asyncio.sleep(scheduler.next_sleep(monitors))
```

## Alerting Logic

```
evaluate_and_alert(monitor, result):
    if result.status == UP:
        if monitor.last_status == DOWN and monitor.last_alert_sent_at:
            notifications.send_up_alert(monitor)
        return

    F("consecutive_failures") += 1

    if monitor.consecutive_failures + 1 < 3:
        return

    if monitor.last_alert_sent_at and elapsed < 30 minutes:
        return

    notifications.send_down_alert(monitor)
    F("last_alert_sent_at") = now()
```

## Incidents

```
open_or_close(monitor, result):
    if result.status == UP:
        close open incident (closed_at=now, reason="Resolved")
    if result.status == DOWN and no open incident:
        create Incident(opened_at=now())
```

## Notification Abstraction

```python
# heartbeat/notifications.py
def send_down_alert(monitor, result):
    send_mail(subject=f"DOWN: {monitor.name}", ...)

def send_up_alert(monitor):
    send_mail(subject=f"UP: {monitor.name} recovered", ...)
```

Later extendable to Discord, Slack, SMS, Telegram, Webhooks.

## Cleanup

```
aggregate_and_prune():
    1. Aggregate yesterday's heartbeats into daily_stats (uptime %, avg latency)
    2. DELETE heartbeats WHERE checked_at < 30 days ago
       → in batches of 5000
```

## Logging

```
"Checking 14 monitors..."
structured log with {monitor_id, status, latency_ms, error, checked_at}
"Worker started"
"Worker shutting down"
```

## Key Design Decisions

| Concern | Decision |
|---------|----------|
| Worker entry point | `python manage.py runworker` |
| Concurrency | Semaphore(100), one async task per monitor |
| Duplicate prevention | `SELECT ... FOR UPDATE SKIP LOCKED` inside transaction |
| Batching | 500 monitors per cycle |
| ORM + async | Sync ORM via `sync_to_async`; only HTTP is async |
| Retry | Transient errors only (timeout, 502, 503, 504); 1 retry after 2s |
| Alert threshold | 3 consecutive failures |
| Alert suppression | 30 min cooldown |
| Fail counter | `F()` expressions — no race conditions |
| Indexes | `next_check_at`, `user`, `is_active`, `monitor-checked_at`, `monitor-closed_at` |
| Sleep | Adaptive: `min(5, next_due - now)` |
| Notification | Abstracted behind `notifications.py` |
| Cleanup | Aggregated stats + batched deletes |
| Field naming | `check_interval_seconds` documents unit in name |
