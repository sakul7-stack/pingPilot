from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from dashboard import views as dashboard_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("accounts/", include("allauth.urls")),
    path("api/monitors/", dashboard_views.api_monitors, name="api_monitors"),
    path("api/monitors/<int:monitor_id>/", dashboard_views.api_monitor_detail, name="api_monitor_detail"),
    path("api/monitors/<int:monitor_id>/heartbeats/", dashboard_views.api_monitor_heartbeats, name="api_monitor_heartbeats"),
    path("api/monitors/<int:monitor_id>/incidents/", dashboard_views.api_monitor_incidents, name="api_monitor_incidents"),
    path("api/monitors/<int:monitor_id>/stats/", dashboard_views.api_monitor_stats, name="api_monitor_stats"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
