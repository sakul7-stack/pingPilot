import json
from datetime import timedelta
from django.db.models import Avg, Count, Q, F
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.utils.crypto import get_random_string
from django.conf import settings
from django.http import Http404, JsonResponse
from django_ratelimit.decorators import ratelimit

import dns.resolver
from urllib.parse import urlparse

from heartbeat.models import HeartBeat as Heartbeat, Incident, Monitor
from .models import StatusPage, StatusPageIncident
from .forms import StatusPageForm, StatusPageCreateForm, StatusPageMonitorFormSet
from .utils import build_timeline, resolve_txt_authoritative


# ---------------------------------------------------------------------------
# Dashboard views (user-facing)
# ---------------------------------------------------------------------------

@login_required
def statuspage_list(request):
    pages = StatusPage.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'statuspage/list.html', {
        'pages': pages,
        'site_url': settings.SITE_URL.rstrip('/'),
    })


@login_required
def statuspage_create(request):
    if request.method == 'POST':
        form = StatusPageCreateForm(request.POST)
        if form.is_valid():
            page = form.save(commit=False)
            page.user = request.user
            import uuid
            page.slug = uuid.uuid4().hex[:12]
            page.domain_verification_token = get_random_string(64)
            page.save()
            messages.success(request, 'Status page created!')
            return redirect('statuspage:edit', pk=page.pk)
    else:
        form = StatusPageCreateForm()
    return render(request, 'statuspage/create.html', {
        'form': form,
        'site_url': settings.SITE_URL.rstrip('/'),
    })


@login_required
def statuspage_edit(request, pk):
    page = get_object_or_404(StatusPage, pk=pk, user=request.user)
    if not page.domain_verification_token:
        page.domain_verification_token = get_random_string(64)
        page.save(update_fields=["domain_verification_token"])
    groups = list(
        Monitor.objects.filter(user=request.user)
        .exclude(group="")
        .values_list("group", flat=True)
        .distinct()
        .order_by("group")
    )
    if request.method == 'POST':
        form = StatusPageForm(request.POST, instance=page)
        formset = StatusPageMonitorFormSet(request.POST, instance=page, user=request.user)
        if form.is_valid() and formset.is_valid():
            form.save()
            spms = formset.save(commit=False)
            for i, spm in enumerate(spms):
                spm.order = i
                spm.save()
            for deleted in formset.deleted_objects:
                deleted.delete()
            formset.save_m2m()
            messages.success(request, 'Status page updated!')
            tab = request.POST.get('active_tab', 'general')
            url = reverse('statuspage:edit', kwargs={'pk': page.pk})
            if tab != 'general':
                url += f'?tab={tab}'
            return redirect(url)
    else:
        form = StatusPageForm(instance=page)
        formset = StatusPageMonitorFormSet(instance=page, user=request.user)
    monitors = list(
        Monitor.objects.filter(user=request.user)
        .order_by("group", "name")
        .values_list("id", "group", "name")
    )
    monitor_options = [
        {"value": mid, "label": f"[{g}] {n}" if g else n}
        for mid, g, n in monitors
    ]
    return render(request, 'statuspage/edit.html', {
        'form': form,
        'formset': formset,
        'page': page,
        'groups': groups,
        'monitor_options': monitor_options,
        'active_tab': request.GET.get('tab', 'general'),
        'site_url': settings.SITE_URL.rstrip('/'),
        'status_page_domain': settings.STATUS_PAGE_DOMAIN,
        'verification_prefix': settings.VERIFICATION_PREFIX,
    })


@login_required
def statuspage_delete(request, pk):
    page = get_object_or_404(StatusPage, pk=pk, user=request.user)
    if request.method == 'POST':
        page.delete()
        messages.success(request, 'Status page deleted.')
    return redirect('statuspage:list')


@login_required
def statuspage_preview(request, pk):
    page = get_object_or_404(StatusPage, pk=pk, user=request.user)
    return render_public_page(request, page, preview=True)


# ---------------------------------------------------------------------------
# Public view
# ---------------------------------------------------------------------------

def resolve_page(request, slug=None, custom_domain=None):
    if custom_domain:
        page = get_object_or_404(StatusPage, custom_domain=custom_domain,
                                 domain_verified=True, is_published=True)
    else:
        page = get_object_or_404(StatusPage, slug=slug, is_published=True)
    return page


def render_public_page(request, page, preview=False):
    if not preview:
        StatusPage.objects.filter(pk=page.pk).update(view_count=F('view_count') + 1)

    sp_monitors = page.monitors.filter(show_on_page=True).select_related('monitor')
    now = timezone.now()
    range_start = now - timedelta(days=90)

    monitors_data = []
    overall_uptime = []

    for spm in sp_monitors:
        monitor = spm.monitor
        total = Heartbeat.objects.filter(
            monitor=monitor, checked_at__gte=range_start
        ).count()
        up_count = Heartbeat.objects.filter(
            monitor=monitor, checked_at__gte=range_start, status='UP'
        ).count()
        uptime = round((up_count / total * 100), 2) if total > 0 else 100.0

        timeline = build_timeline(monitor, 30)

        avg_r = Heartbeat.objects.filter(
            monitor=monitor,
            checked_at__gte=now - timedelta(hours=24),
            response_time_ms__isnull=False
        ).aggregate(avg=Avg('response_time_ms'))['avg']

        monitors_data.append({
            'spm': spm,
            'monitor': monitor,
            'uptime': uptime,
            'total_checks': total,
            'avg_response_time': round(avg_r, 1) if avg_r else None,
            'timeline': json.dumps(timeline),
            'status': monitor.last_status or 'PENDING',
            'current_incident': Incident.objects.filter(
                monitor=monitor, closed_at__isnull=True
            ).first(),
        })
        overall_uptime.append(uptime)

    avg_overall = round(
        sum(overall_uptime) / len(overall_uptime), 2
    ) if overall_uptime else 100.0

    if page.sort_order == 'status':
        status_order = {'DOWN': 0, 'DEGRADED': 1, 'PENDING': 2, 'UP': 3}
        monitors_data.sort(key=lambda m: (
            status_order.get(m['status'], 99),
            m['monitor'].name.lower()
        ))
    elif page.sort_order == 'alpha':
        monitors_data.sort(key=lambda m: m['monitor'].name.lower())

    monitor_ids = [m['monitor'].id for m in monitors_data]
    active_incidents = Incident.objects.filter(
        monitor_id__in=monitor_ids, closed_at__isnull=True
    ).select_related('monitor')

    incident_posts = page.incident_posts.filter(
        resolved_at__isnull=True
    ) if page.show_incidents else []

    recent_incidents = Incident.objects.filter(
        monitor_id__in=monitor_ids,
        closed_at__isnull=False,
        closed_at__gte=now - timedelta(days=7)
    ).select_related('monitor')[:20]

    site_url = settings.SITE_URL.rstrip('/')

    context = {
        'page': page,
        'monitors_data': monitors_data,
        'overall_uptime': avg_overall,
        'active_incidents': active_incidents,
        'incident_posts': incident_posts,
        'recent_incidents': recent_incidents,
        'preview': preview,
        'now': now,
        'site_url': site_url,
    }
    return render(request, 'statuspage/public.html', context)


@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def public_status_page(request, slug):
    page = resolve_page(request, slug=slug)
    if page.password_protected and not request.session.get(f'sp_auth_{page.pk}'):
        if request.method == 'POST':
            if check_password(request.POST.get('password', ''), page.access_password):
                request.session[f'sp_auth_{page.pk}'] = True
            else:
                return render(request, 'statuspage/unlock.html', {'page': page})
        else:
            return render(request, 'statuspage/unlock.html', {'page': page})
    return render_public_page(request, page)


def public_incidents(request, slug):
    page = resolve_page(request, slug=slug)
    monitor_ids = page.monitors.filter(show_on_page=True).values_list('monitor_id', flat=True)
    incidents = Incident.objects.filter(
        monitor_id__in=monitor_ids,
        closed_at__isnull=False
    ).order_by('-closed_at')[:10].values('monitor__name', 'opened_at', 'closed_at', 'reason')
    return JsonResponse(list(incidents), safe=False)


# ---------------------------------------------------------------------------
# Custom domain verification
# ---------------------------------------------------------------------------

@ratelimit(key='ip', rate='5/m', method='POST', block=True)
@login_required
def verify_domain(request, pk):
    page = get_object_or_404(StatusPage, pk=pk, user=request.user)
    verification_prefix = settings.VERIFICATION_PREFIX

    if request.method == 'POST':
        domain = page.custom_domain
        if not domain:
            return JsonResponse({'verified': False, 'error': 'No domain set'})

        try:
            txt_values = resolve_txt_authoritative(f'{verification_prefix}.{domain}')
            if any(page.domain_verification_token in tv for tv in txt_values):
                page.domain_verified = True
                page.save()
                return JsonResponse({'verified': True})

            return JsonResponse({
                'verified': False,
                'error': f'TXT record "{verification_prefix}.{domain}" not found or token mismatch',
                'expected_token': page.domain_verification_token,
            })
        except Exception as e:
            return JsonResponse({'verified': False, 'error': str(e)})

    return JsonResponse({
        'dns_instructions': get_dns_instructions(page),
    })


def get_dns_instructions(page):
    status_domain = settings.STATUS_PAGE_DOMAIN
    verification_prefix = settings.VERIFICATION_PREFIX
    return {
        'type': 'CNAME',
        'name': page.custom_domain,
        'target': status_domain,
        'txt_record': {
            'name': f'{verification_prefix}.{page.custom_domain}',
            'value': page.domain_verification_token,
            'ttl': '300',
        },
    }


# ---------------------------------------------------------------------------
# Custom domain handling
# ---------------------------------------------------------------------------

def custom_domain_handler(request, path=''):
    page = getattr(request, 'status_page', None)
    if not page:
        raise Http404('Unknown status page domain')
    return render_public_page(request, page)


# ---------------------------------------------------------------------------
# Mini graph data API
# ---------------------------------------------------------------------------

@ratelimit(key='ip', rate='30/m', method='GET', block=True)
def graph_data_api(request, slug, monitor_id):
    page = resolve_page(request, slug=slug)
    if not page.monitors.filter(monitor_id=monitor_id, show_on_page=True).exists():
        return JsonResponse({'error': 'not found'}, status=404)

    now = timezone.now()
    hbs = Heartbeat.objects.filter(
        monitor_id=monitor_id,
        checked_at__gte=now - timedelta(hours=24),
        response_time_ms__isnull=False,
    ).order_by('checked_at').values('checked_at', 'response_time_ms')

    labels = [hb['checked_at'].strftime('%H:%M') for hb in hbs]
    values = [hb['response_time_ms'] for hb in hbs]

    return JsonResponse({'labels': labels, 'values': values})
