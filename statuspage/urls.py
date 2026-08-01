from django.urls import path
from . import views

app_name = 'statuspage'

urlpatterns = [
    path('', views.statuspage_list, name='list'),
    path('create/', views.statuspage_create, name='create'),
    path('<int:pk>/', views.statuspage_edit, name='edit'),
    path('<int:pk>/delete/', views.statuspage_delete, name='delete'),
    path('<int:pk>/preview/', views.statuspage_preview, name='preview'),

    path('public/status/<slug:slug>/', views.public_status_page, name='public'),
    path('public/status/<slug:slug>/incidents/', views.public_incidents, name='public_incidents'),

    path('verify-domain/<int:pk>/', views.verify_domain, name='verify_domain'),

    path('public/status/<slug:slug>/graph/<int:monitor_id>/',
         views.graph_data_api, name='graph_data'),
]
