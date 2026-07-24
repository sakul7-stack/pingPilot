from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("create/", views.create_monitor, name="create_monitor"),
    path("delete/<int:monitor_id>/", views.delete_monitor, name="delete_monitor"),
    path("toggle/<int:monitor_id>/", views.toggle_monitor, name="toggle_monitor"),
    path("edit/<int:monitor_id>/", views.edit_monitor, name="edit_monitor"),
    path("<int:monitor_id>/", views.monitor_detail, name="monitor_detail"),
    path("<int:monitor_id>/export/", views.export_heartbeats_csv, name="export_heartbeats"),
    path("settings/", views.settings, name="settings"),
]
