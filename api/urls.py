from django.urls import path

from .views import (
    appointment_detail,
    appointment_status,
    appointments,
    health_check,
    service_detail,
    services,
)

urlpatterns = [
    path('', health_check, name='health-check'),
    path('services', services, name='services'),
    path('services/', services),
    path('services/<int:service_id>', service_detail, name='service-detail'),
    path('services/<int:service_id>/', service_detail),
    path('appointments', appointments, name='appointments'),
    path('appointments/', appointments),
    path('appointments/<int:appointment_id>/status', appointment_status, name='appointment-status'),
    path('appointments/<int:appointment_id>/status/', appointment_status),
    path('appointments/<int:appointment_id>', appointment_detail, name='appointment-detail'),
    path('appointments/<int:appointment_id>/', appointment_detail),
]
