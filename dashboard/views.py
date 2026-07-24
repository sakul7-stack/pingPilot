import csv
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta

from accounts.models import Profile
from heartbeat.models import HeartBeat as Heartbeat, Incident, Monitor


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

        Monitor.objects.create(
            user=request.user,
            name=name,
            url=url,
            method=method,
            expected_status=int(expected_status),
            check_interval_seconds=int(check_interval),
            timeout=int(timeout),
            expected_keyword=expected_keyword,
        )
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
            monitor.save()
            messages.success(request, f"Monitor '{name}' updated.")

        return redirect("dashboard")

    return render(request, "edit_monitor.html", {"monitor": monitor})


@login_required
def monitor_detail(request, monitor_id):
    monitor = get_object_or_404(Monitor, pk=monitor_id, user=request.user)
    days = int(request.GET.get("days", 1))
    cutoff = timezone.now() - timedelta(days=days)

    heartbeats = Heartbeat.objects.filter(
        monitor=monitor, checked_at__gte=cutoff
    ).order_by("-checked_at")
    incidents = Incident.objects.filter(monitor=monitor).order_by("-opened_at")
    all_time = Heartbeat.objects.filter(monitor=monitor).count()

    total = heartbeats.count()
    ups = heartbeats.filter(status="UP").count()
    uptime = round(ups / total * 100, 2) if total > 0 else None

    status_bar = list(
        heartbeats.filter(checked_at__gte=cutoff)
        .order_by("-checked_at")[:100]
        .values("status", "checked_at")
    )
    status_bar.reverse()

    hb_list = list(
        heartbeats.order_by("checked_at")[:100].values(
            "checked_at", "response_time_ms", "status"
        )
    )
    def serialize_hb(hb):
        dt = hb["checked_at"]
        return {
            "t": dt.strftime("%H:%M"),
            "r": hb["response_time_ms"],
            "s": hb["status"],
        }

    chart_data = json.dumps([serialize_hb(h) for h in hb_list])

    return render(request, "monitor_detail.html", {
        "monitor": monitor,
        "heartbeats": heartbeats[:100],
        "incidents": incidents,
        "uptime": uptime,
        "total_checks": total,
        "all_time_checks": all_time,
        "days": days,
        "status_bar": status_bar,
        "chart_data": chart_data,
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
def settings(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        if first_name:
            request.user.first_name = first_name
        request.user.save()

        if "avatar" in request.FILES:
            profile.avatar = request.FILES["avatar"]
            profile.save()

        messages.success(request, "Settings saved.")
        return redirect("settings")

    return render(request, "settings.html", {"profile": profile})
