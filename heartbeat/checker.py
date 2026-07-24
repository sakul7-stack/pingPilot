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
        response_time=kw.get("response_time"),
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
            response_time=elapsed,
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
            response_time=elapsed,
            body_size=len(body),
        )
    except Exception:
        return _check_result(Status.DOWN, error=error)