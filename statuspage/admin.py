from django.contrib import admin
from .models import StatusPage, StatusPageMonitor, StatusPageIncident


class StatusPageMonitorInline(admin.TabularInline):
    model = StatusPageMonitor
    extra = 1


class StatusPageIncidentInline(admin.TabularInline):
    model = StatusPageIncident
    extra = 0


@admin.register(StatusPage)
class StatusPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'user', 'theme', 'is_published',
                    'custom_domain', 'domain_verified', 'view_count')
    list_filter = ('theme', 'is_published', 'domain_verified')
    search_fields = ('title', 'slug', 'custom_domain')
    inlines = [StatusPageMonitorInline, StatusPageIncidentInline]


@admin.register(StatusPageMonitor)
class StatusPageMonitorAdmin(admin.ModelAdmin):
    list_display = ('status_page', 'monitor', 'order', 'show_on_page')
    list_filter = ('show_on_page',)


@admin.register(StatusPageIncident)
class StatusPageIncidentAdmin(admin.ModelAdmin):
    list_display = ('title', 'status_page', 'severity', 'started_at', 'resolved_at')
    list_filter = ('severity',)
