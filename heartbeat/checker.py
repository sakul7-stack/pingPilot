import asyncio
import time
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


def capture_meta(resp: httpx.Response, monitor: Monitor, started: float) -> dict:
    keyword_found = None
    if monitor.expected_keyword:
        keyword_found = monitor.expected_keyword in resp.text
    ttfb_time = resp.extensions.get("ttfb_time")
    ttfb_ms = round((ttfb_time - started) * 1000, 2) if ttfb_time else None
    return {
        "redirects": len(resp.history),
        "final_url": str(resp.url),
        "http_version": resp.http_version,
        "server": resp.headers.get("server"),
        "content_type": resp.headers.get("content-type"),
        "keyword_found": keyword_found,
        "ttfb_ms": ttfb_ms,
    }


def _check_result(status: Status, error: str, **kw) -> CheckResult:
    return CheckResult(
        status=status,
        status_code=kw.get("status_code"),
        error=error,
        response_time_ms=kw.get("response_time_ms"),
        body_size=kw.get("body_size"),
        meta=kw.get("meta"),
        checked_at=datetime.now(),
    )


async def check_monitor(
    monitor: Monitor, client: httpx.AsyncClient
) -> CheckResult:
    started = time.perf_counter()
    method = monitor.method.lower()
    headers = {h["name"]: h["value"] for h in monitor.headers if h.get("name") and h.get("value")}
    try:
        resp = await client.request(
            method, monitor.url, timeout=monitor.timeout, headers=headers
        )
        elapsed = (time.perf_counter() - started) * 1000
        status = evaluate_response(resp, monitor)
        body = resp.content
        return _check_result(
            status,
            error="",
            status_code=resp.status_code,
            response_time_ms=elapsed,
            body_size=len(body),
            meta=capture_meta(resp, monitor, started),
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
    started: float,
) -> CheckResult:
    if error not in TRANSIENT_ERRORS:
        return _check_result(Status.DOWN, error=error)
    await asyncio.sleep(2)
    method = monitor.method.lower()
    headers = {h["name"]: h["value"] for h in monitor.headers if h.get("name") and h.get("value")}
    try:
        resp = await client.request(
            method, monitor.url, timeout=monitor.timeout, headers=headers
        )
        elapsed = (time.perf_counter() - started) * 1000
        status = evaluate_response(resp, monitor)
        body = resp.content
        return _check_result(
            status,
            error="",
            status_code=resp.status_code,
            response_time_ms=elapsed,
            body_size=len(body),
            meta=capture_meta(resp, monitor, started),
        )
    except Exception:
        return _check_result(Status.DOWN, error=error)
