import csv
import json
import hashlib
import secrets
import ssl
import socket
from urllib.parse import urlparse

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST
from datetime import timedelta, datetime

import httpx

from django.conf import settings as django_settings
from django.contrib.auth.models import User
from allauth.socialaccount.models import SocialAccount

from accounts.models import Profile, TelegramConnection
from heartbeat.models import HeartBeat as Heartbeat, Incident, Monitor, APIKey, NotificationChannel, AlertLog


@login_required
def dashboard(request):
    monitors = Monitor.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "dashboard.html", {"monitors": monitors})


@login_required
def create_monitor(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        url = request.POST.get("url", "").strip()
        method = request.POST.get("method", "GET")
        expected_status = request.POST.get("expected_status", 200)
        check_interval = request.POST.get("check_interval_seconds", 600)
        timeout = request.POST.get("timeout", 10)
        expected_keyword = request.POST.get("expected_keyword", "").strip()

        if not name or not url:
            messages.error(request, "Name and URL are required.")
            return redirect("dashboard")

        if Monitor.objects.filter(user=request.user).count() >= 100:
            messages.error(request, "Limit reached. You can create up to 100 monitors.")
            return redirect("dashboard")

        monitor = Monitor.objects.create(
            user=request.user,
            name=name,
            url=url,
            method=method,
            expected_status=int(expected_status),
            check_interval_seconds=int(check_interval),
            timeout=int(timeout),
            expected_keyword=expected_keyword,
            email_alerts=request.POST.get("email_alerts") == "on",
        )
        _save_channels(monitor, request.POST, user=request.user)
        messages.success(request, f"Monitor '{name}' created.")
    return redirect("dashboard")


@login_required
def delete_monitor(request, monitor_id):
    monitor = get_object_or_404(Monitor, pk=monitor_id, user=request.user)
    monitor.delete()
    messages.success(request, f"Monitor '{monitor.name}' deleted.")
    return redirect("dashboard")


@login_required
def toggle_monitor(request, monitor_id):
    monitor = get_object_or_404(Monitor, pk=monitor_id, user=request.user)
    monitor.is_active = not monitor.is_active
    monitor.save()
    status = "activated" if monitor.is_active else "paused"
    messages.success(request, f"Monitor '{monitor.name}' {status}.")
    return redirect("dashboard")


@login_required
def edit_monitor(request, monitor_id):
    monitor = get_object_or_404(Monitor, pk=monitor_id, user=request.user)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        url = request.POST.get("url", "").strip()
        method = request.POST.get("method", "GET")
        expected_status = request.POST.get("expected_status", 200)
        check_interval = request.POST.get("check_interval_seconds", 600)
        timeout = request.POST.get("timeout", 10)
        expected_keyword = request.POST.get("expected_keyword", "").strip()

        if name and url:
            monitor.name = name
            monitor.url = url
            monitor.method = method
            monitor.expected_status = int(expected_status)
            monitor.check_interval_seconds = int(check_interval)
            monitor.timeout = int(timeout)
            monitor.expected_keyword = expected_keyword
            monitor.email_alerts = request.POST.get("email_alerts") == "on"
            monitor.save()
            _save_channels(monitor, request.POST, user=request.user)
            messages.success(request, f"Monitor '{name}' updated.")

        return redirect("dashboard")

    return render(request, "edit_monitor.html", {"monitor": monitor})


def get_ssl_info(url):
    try:
        host = urlparse(url).hostname
        if not host:
            return None
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        raw = cert["notAfter"]
        expiry = datetime.strptime(raw.replace(" GMT", ""), "%b %d %H:%M:%S %Y")
        remaining = (expiry - timezone.now().replace(tzinfo=None)).days
        issuer = ""
        if cert.get("issuer"):
            for pair in cert["issuer"]:
                if pair[0] == "commonName":
                    issuer = pair[1]
                    break
        return {"expiry": expiry.strftime("%Y-%m-%d"), "remaining": remaining, "issuer": issuer}
    except Exception:
        return None


@login_required
def monitor_detail(request, monitor_id):
    monitor = get_object_or_404(Monitor, pk=monitor_id, user=request.user)
    if not monitor.share_token:
        monitor.share_token = secrets.token_urlsafe(16)
        monitor.save(update_fields=["share_token"])
    days = int(request.GET.get("days", 1))
    cutoff = timezone.now() - timedelta(days=days)

    heartbeats_qs = Heartbeat.objects.filter(
        monitor=monitor, checked_at__gte=cutoff
    ).order_by("-checked_at")
    incidents = Incident.objects.filter(monitor=monitor).order_by("-opened_at")
    all_time = Heartbeat.objects.filter(monitor=monitor).count()

    total = heartbeats_qs.count()
    ups = heartbeats_qs.filter(status="UP").count()
    uptime = round(ups / total * 100, 2) if total > 0 else None

    if uptime is None:
        uptime_color = "var(--pp-muted)"
    elif uptime == 100:
        uptime_color = "var(--pp-signal)"
    elif uptime >= 98:
        uptime_color = "var(--pp-warning)"
    else:
        uptime_color = "var(--pp-danger)"

    uptime_label = {1: "Last 24h", 7: "Last 7 days", 30: "Last 30 days", 90: "Last 90 days"}.get(days, f"Last {days} days")

    all_hb = list(heartbeats_qs.order_by("checked_at").values("status", "checked_at"))
    now = timezone.now()
    start = now - timedelta(days=days)
    total_secs = (now - start).total_seconds()
    seg_secs = total_secs / 30
    aggregated_bar = []
    for i in range(30):
        seg_start = start + timedelta(seconds=i * seg_secs)
        seg_end = seg_start + timedelta(seconds=seg_secs)
        in_seg = [h for h in all_hb if seg_start <= h["checked_at"] < seg_end]
        total_in = len(in_seg)
        up_in = sum(1 for h in in_seg if h["status"] == "UP")
        pct = round(up_in / total_in * 100) if total_in > 0 else -1
        label = seg_start.strftime("%H:%M" if days == 1 else "%m-%d")
        aggregated_bar.append({"label": label, "pct": pct})

    paginator = Paginator(heartbeats_qs, 50)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    hb_list = list(heartbeats_qs.order_by("checked_at")[:100].values(
        "checked_at", "response_time_ms", "status"
    ))
    def serialize_hb(hb):
        dt = hb["checked_at"]
        return {
            "t": dt.strftime("%H:%M"),
            "r": hb["response_time_ms"],
            "s": hb["status"],
        }

    chart_data = json.dumps([serialize_hb(h) for h in hb_list])
    ssl_info = get_ssl_info(monitor.url)

    channels = NotificationChannel.objects.filter(monitor=monitor)
    alert_logs = AlertLog.objects.filter(monitor=monitor)[:50]

    for inc in incidents:
        if inc.closed_at:
            td = inc.closed_at - inc.opened_at
            total_secs = int(td.total_seconds())
            hours, remainder = divmod(total_secs, 3600)
            minutes, _ = divmod(remainder, 60)
            if hours:
                inc.duration_display = f"{hours}h {minutes}m"
            else:
                inc.duration_display = f"{minutes}m"
        else:
            inc.duration_display = None

    return render(request, "monitor_detail.html", {
        "monitor": monitor,
        "heartbeats": page_obj.object_list,
        "page_obj": page_obj,
        "incidents": incidents,
        "uptime": uptime,
        "uptime_color": uptime_color,
        "uptime_label": uptime_label,
        "total_checks": total,
        "all_time_checks": all_time,
        "days": days,
        "status_bar": aggregated_bar,
        "chart_data": chart_data,
        "ssl_info": ssl_info,
        "channels": channels,
        "alert_logs": alert_logs,
    })


def public_monitor_detail(request, token):
    monitor = get_object_or_404(Monitor, share_token=token, is_active=True)
    days = int(request.GET.get("days", 1))
    cutoff = timezone.now() - timedelta(days=days)

    heartbeats_qs = Heartbeat.objects.filter(
        monitor=monitor, checked_at__gte=cutoff
    ).order_by("-checked_at")
    incidents = Incident.objects.filter(monitor=monitor).order_by("-opened_at")
    all_time = Heartbeat.objects.filter(monitor=monitor).count()

    total = heartbeats_qs.count()
    ups = heartbeats_qs.filter(status="UP").count()
    uptime = round(ups / total * 100, 2) if total > 0 else None

    if uptime is None:
        uptime_color = "var(--pp-muted)"
    elif uptime == 100:
        uptime_color = "var(--pp-signal)"
    elif uptime >= 98:
        uptime_color = "var(--pp-warning)"
    else:
        uptime_color = "var(--pp-danger)"

    uptime_label = {1: "Last 24h", 7: "Last 7 days", 30: "Last 30 days", 90: "Last 90 days"}.get(days, f"Last {days} days")

    all_hb = list(heartbeats_qs.order_by("checked_at").values("status", "checked_at"))
    now = timezone.now()
    start = now - timedelta(days=days)
    total_secs = (now - start).total_seconds()
    seg_secs = total_secs / 30
    aggregated_bar = []
    for i in range(30):
        seg_start = start + timedelta(seconds=i * seg_secs)
        seg_end = seg_start + timedelta(seconds=seg_secs)
        in_seg = [h for h in all_hb if seg_start <= h["checked_at"] < seg_end]
        total_in = len(in_seg)
        up_in = sum(1 for h in in_seg if h["status"] == "UP")
        pct = round(up_in / total_in * 100) if total_in > 0 else -1
        label = seg_start.strftime("%H:%M" if days == 1 else "%m-%d")
        aggregated_bar.append({"label": label, "pct": pct})

    paginator = Paginator(heartbeats_qs, 50)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    hb_list = list(heartbeats_qs.order_by("checked_at")[:100].values(
        "checked_at", "response_time_ms", "status"
    ))
    def serialize_hb(hb):
        dt = hb["checked_at"]
        return {
            "t": dt.strftime("%H:%M"),
            "r": hb["response_time_ms"],
            "s": hb["status"],
        }

    chart_data = json.dumps([serialize_hb(h) for h in hb_list])
    ssl_info = get_ssl_info(monitor.url)

    for inc in incidents:
        if inc.closed_at:
            td = inc.closed_at - inc.opened_at
            total_secs = int(td.total_seconds())
            hours, remainder = divmod(total_secs, 3600)
            minutes, _ = divmod(remainder, 60)
            if hours:
                inc.duration_display = f"{hours}h {minutes}m"
            else:
                inc.duration_display = f"{minutes}m"
        else:
            inc.duration_display = None

    return render(request, "monitor_detail.html", {
        "monitor": monitor,
        "heartbeats": page_obj.object_list,
        "page_obj": page_obj,
        "incidents": incidents,
        "uptime": uptime,
        "uptime_color": uptime_color,
        "uptime_label": uptime_label,
        "total_checks": total,
        "all_time_checks": all_time,
        "days": days,
        "status_bar": aggregated_bar,
        "chart_data": chart_data,
        "ssl_info": ssl_info,
        "is_public": True,
    })


@login_required
def export_heartbeats_csv(request, monitor_id):
    monitor = get_object_or_404(Monitor, pk=monitor_id, user=request.user)
    days = int(request.GET.get("days", 1))
    cutoff = timezone.now() - timedelta(days=days)
    qs = Heartbeat.objects.filter(monitor=monitor, checked_at__gte=cutoff).order_by("-checked_at")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{monitor.name}_heartbeats.csv"'
    writer = csv.writer(response)
    writer.writerow(["Time (UTC)", "Status", "Status Code", "Response Time (ms)", "Body Size", "Error"])
    for hb in qs:
        writer.writerow([
            hb.checked_at.strftime("%Y-%m-%d %H:%M:%S"),
            hb.status,
            hb.status_code or "",
            hb.response_time_ms or "",
            hb.body_size or "",
            hb.error or "",
        ])
    return response


@login_required
def export_incidents_csv(request, monitor_id):
    monitor = get_object_or_404(Monitor, pk=monitor_id, user=request.user)
    qs = Incident.objects.filter(monitor=monitor).order_by("-opened_at")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{monitor.name}_incidents.csv"'
    writer = csv.writer(response)
    writer.writerow(["Opened (UTC)", "Closed (UTC)", "Duration", "Reason"])
    for inc in qs:
        duration = ""
        if inc.closed_at:
            td = inc.closed_at - inc.opened_at
            hours, remainder = divmod(int(td.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            duration = f"{hours}h {minutes}m" if hours else f"{minutes}m"
        writer.writerow([
            inc.opened_at.strftime("%Y-%m-%d %H:%M:%S"),
            inc.closed_at.strftime("%Y-%m-%d %H:%M:%S") if inc.closed_at else "Open",
            duration,
            inc.reason or "",
        ])
    return response


@login_required
def settings(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    social_accounts = SocialAccount.objects.filter(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "delete_account":
            request.user.delete()
            messages.success(request, "Account deleted.")
            return redirect("/")

        first_name = request.POST.get("first_name", "").strip()
        if first_name:
            request.user.first_name = first_name
        request.user.save()

        if "avatar" in request.FILES:
            profile.avatar = request.FILES["avatar"]

        tz = request.POST.get("timezone", "").strip()
        if tz:
            profile.timezone = tz

        profile.save()
        messages.success(request, "Settings saved.")
        return redirect("settings")

    return render(request, "settings.html", {
        "profile": profile,
        "social_accounts": social_accounts,
    })


@login_required
def api_keys(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip() or "Unnamed"
        raw = secrets.token_hex(32)
        prefix = raw[:8]
        key_hash = hashlib.sha256(raw.encode()).hexdigest()
        APIKey.objects.create(
            user=request.user, name=name, prefix=prefix, key_hash=key_hash
        )
        return render(request, "api_keys.html", {
            "keys": APIKey.objects.filter(user=request.user).order_by("-created_at"),
            "new_key": f"pp_{raw}",
            "site_url": django_settings.SITE_URL,
        })
    return render(request, "api_keys.html", {
        "keys": APIKey.objects.filter(user=request.user).order_by("-created_at"),
        "site_url": django_settings.SITE_URL,
    })


@login_required
@require_POST
def revoke_api_key(request, key_id):
    key = get_object_or_404(APIKey, pk=key_id, user=request.user)
    key.is_active = False
    key.save()
    messages.success(request, "API key revoked.")
    return redirect("api_keys")


@login_required
def api_docs(request):
    return render(request, "api_docs.html", {
        "site_url": django_settings.SITE_URL,
    })


def api_auth(request):
    auth = request.headers.get("X-API-Key", "")
    if not auth.startswith("pp_"):
        return None
    key_hash = hashlib.sha256(auth[3:].encode()).hexdigest()
    try:
        key = APIKey.objects.get(key_hash=key_hash, is_active=True)
        key.last_used_at = timezone.now()
        key.save(update_fields=["last_used_at"])
        return key.user
    except APIKey.DoesNotExist:
        return None


def api_monitors(request):
    user = api_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    monitors = Monitor.objects.filter(user=user).values(
        "id", "name", "url", "method", "expected_status",
        "check_interval_seconds", "last_status", "last_checked_at",
        "is_active", "created_at"
    )
    return JsonResponse(list(monitors), safe=False)


def api_monitor_detail(request, monitor_id):
    user = api_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    monitor = get_object_or_404(Monitor, pk=monitor_id, user=user)
    return JsonResponse({
        "id": monitor.id,
        "name": monitor.name,
        "url": monitor.url,
        "method": monitor.method,
        "expected_status": monitor.expected_status,
        "expected_keyword": monitor.expected_keyword,
        "timeout": monitor.timeout,
        "check_interval_seconds": monitor.check_interval_seconds,
        "last_status": monitor.last_status,
        "last_checked_at": monitor.last_checked_at,
        "is_active": monitor.is_active,
        "created_at": monitor.created_at,
    })


def api_monitor_heartbeats(request, monitor_id):
    user = api_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    monitor = get_object_or_404(Monitor, pk=monitor_id, user=user)
    days = int(request.GET.get("days", 1))
    cutoff = timezone.now() - timedelta(days=days)
    heartbeats = Heartbeat.objects.filter(
        monitor=monitor, checked_at__gte=cutoff
    ).order_by("-checked_at")[:100].values(
        "status", "status_code", "error", "response_time_ms",
        "body_size", "checked_at"
    )
    return JsonResponse(list(heartbeats), safe=False)


def api_monitor_incidents(request, monitor_id):
    user = api_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    monitor = get_object_or_404(Monitor, pk=monitor_id, user=user)
    incidents = Incident.objects.filter(monitor=monitor).order_by("-opened_at").values(
        "id", "opened_at", "closed_at", "reason"
    )
    return JsonResponse(list(incidents), safe=False)


def api_monitor_stats(request, monitor_id):
    user = api_auth(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=401)
    monitor = get_object_or_404(Monitor, pk=monitor_id, user=user)
    total = Heartbeat.objects.filter(monitor=monitor).count()
    ups = Heartbeat.objects.filter(monitor=monitor, status="UP").count()
    uptime = round(ups / total * 100, 2) if total > 0 else None
    return JsonResponse({
        "total_checks": total,
        "up_checks": ups,
        "uptime_pct": uptime,
        "current_status": monitor.last_status,
        "is_active": monitor.is_active,
    })


@login_required
def telegram_connect(request):
    conn = TelegramConnection.objects.filter(user=request.user).first()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "verify":
            code = request.session.get("telegram_code")
            if not code:
                messages.error(request, "No verification code found. Click 'Get Code' first.")
                return redirect("telegram_connect")

            token = django_settings.TELEGRAM_BOT_TOKEN
            if not token:
                messages.error(request, "Telegram bot not configured.")
                return redirect("telegram_connect")

            try:
                resp = httpx.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    timeout=10
                )
                data = resp.json()
                found = False
                for update in data.get("result", []):
                    msg = update.get("message", {})
                    text = msg.get("text", "").strip()
                    if text == code:
                        chat = msg.get("chat", {})
                        chat_id = chat.get("id")
                        if chat_id:
                            TelegramConnection.objects.update_or_create(
                                user=request.user,
                                defaults={"chat_id": chat_id}
                            )
                            request.session.pop("telegram_code", None)
                            messages.success(request, f"Telegram connected! Chat ID: {chat_id}")
                            found = True
                            break
                if not found:
                    messages.error(request, "Code not found. Send the code to @pingpilot_alerts_bot on Telegram, then click Verify.")
            except Exception:
                messages.error(request, "Failed to check messages. Try again.")

        elif action == "disconnect":
            if conn:
                conn.delete()
                messages.success(request, "Telegram disconnected.")
            return redirect("telegram_connect")

        return redirect("telegram_connect")

    code = None
    if not conn:
        code = str(secrets.randbelow(1000000)).zfill(6)
        request.session["telegram_code"] = code

    return render(request, "telegram_connect.html", {
        "connection": conn,
        "code": code,
    })


def _save_channels(monitor, data, user=None):
    kept_ids = []
    i = 0
    while f"ch_{i}_provider" in data:
        provider = data[f"ch_{i}_provider"]
        channel_id = data.get(f"ch_{i}_id", "")
        label = data.get(f"ch_{i}_label", provider)
        if provider == "webhook":
            config = {"url": data.get(f"ch_{i}_url", "")}
        elif provider == "telegram":
            conn = TelegramConnection.objects.filter(user=user).first() if user else None
            if conn:
                config = {"chat_id": str(conn.chat_id)}
            else:
                config = {"chat_id": data.get(f"ch_{i}_chat_id", "").strip()}
        elif provider == "discord":
            config = {"webhook_url": data.get(f"ch_{i}_webhook_url", "")}
        elif provider == "slack":
            config = {"webhook_url": data.get(f"ch_{i}_webhook_url", "")}
        elif provider == "teams":
            config = {"webhook_url": data.get(f"ch_{i}_webhook_url", "")}
        elif provider == "pushover":
            config = {"user_key": data.get(f"ch_{i}_user_key", "").strip()}
        elif provider == "googlechat":
            config = {"webhook_url": data.get(f"ch_{i}_webhook_url", "")}
        elif provider == "mattermost":
            config = {"webhook_url": data.get(f"ch_{i}_webhook_url", "")}
        elif provider == "zulip":
            config = {"webhook_url": data.get(f"ch_{i}_webhook_url", "")}
        elif provider == "pagerduty":
            config = {"routing_key": data.get(f"ch_{i}_routing_key", "").strip()}
        elif provider in ("ntfy", "gotify", "rocketchat", "zapier", "make", "n8n", "ifttt"):
            config = {"webhook_url": data.get(f"ch_{i}_webhook_url", "")}
        else:
            i += 1
            continue

        has_value = any(config.values())
        if not has_value and not channel_id:
            i += 1
            continue

        if channel_id:
            ch = NotificationChannel.objects.get(pk=channel_id, monitor=monitor)
            ch.provider = provider
            ch.label = label
            ch.config = config
            ch.save()
            kept_ids.append(ch.pk)
        else:
            ch = NotificationChannel.objects.create(
                monitor=monitor, provider=provider, label=label, config=config
            )
            kept_ids.append(ch.pk)
        i += 1

    monitor.channels.exclude(pk__in=kept_ids).delete()
