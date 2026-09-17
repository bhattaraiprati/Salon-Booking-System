from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Appointment, Service


def service_data(service):
    """Return the public representation without decimal trailing zeroes."""
    price = float(service.price)
    return {
        'id': service.id,
        'name': service.name,
        'price': int(price) if price.is_integer() else price,
        'duration': service.duration,
    }


def appointment_data(appointment, include_created_at=True):
    services = list(appointment.services.all())
    data = {
        'id': appointment.id,
        'customer_name': appointment.customer_name,
        'customer_phone': appointment.customer_phone,
        'services': [service_data(service) for service in services],
        'appointment_date': appointment.appointment_date.isoformat(),
        'appointment_time': appointment.appointment_time.strftime('%H:%M'),
        'status': appointment.status,
        'notes': appointment.notes,
        'total_price': sum((service_data(service)['price'] for service in services), 0),
        'total_duration': sum(service.duration for service in services),
    }
    if include_created_at:
        data['created_at'] = appointment.created_at.isoformat().replace('+00:00', 'Z')
    return data


def service_payload(data):
    errors = {}
    name = str(data.get('name', '')).strip()
    if not name:
        errors['name'] = ['This field is required and cannot be empty.']

    try:
        price = Decimal(str(data.get('price', '')))
        if not price.is_finite() or price <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        errors['price'] = ['Price must be a positive number.']
        price = None

    try:
        duration = int(data.get('duration', ''))
        if isinstance(data.get('duration'), bool) or duration <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errors['duration'] = ['Duration must be greater than zero.']
        duration = None
    return name, price, duration, errors


def appointment_payload(data):
    errors = {}
    customer_name = str(data.get('customer_name', '')).strip()
    customer_phone = str(data.get('customer_phone', '')).strip()
    if not customer_name:
        errors['customer_name'] = ['This field is required and cannot be empty.']
    if not customer_phone:
        errors['customer_phone'] = ['This field is required and cannot be empty.']

    service_ids = data.get('service_ids')
    if not isinstance(service_ids, list) or not service_ids:
        errors['service_ids'] = ['Select at least one service.']
        services = []
    elif any(isinstance(item, bool) or not isinstance(item, int) for item in service_ids):
        errors['service_ids'] = ['Service IDs must be integers.']
        services = []
    else:
        services = list(Service.objects.filter(id__in=set(service_ids)))
        missing = sorted(set(service_ids) - {service.id for service in services})
        if missing:
            errors['service_ids'] = [f'Service IDs do not exist: {missing}.']

    date_value = data.get('appointment_date')
    time_value = data.get('appointment_time')
    appointment_date = None
    appointment_time = None
    if not date_value:
        errors['appointment_date'] = ['This field is required.']
    else:
        try:
            appointment_date = datetime.strptime(str(date_value), '%Y-%m-%d').date()
        except ValueError:
            errors['appointment_date'] = ['Use YYYY-MM-DD format.']
    if not time_value:
        errors['appointment_time'] = ['This field is required.']
    else:
        try:
            appointment_time = datetime.strptime(str(time_value), '%H:%M').time()
        except ValueError:
            errors['appointment_time'] = ['Use HH:mm (24-hour) format.']
    return customer_name, customer_phone, services, appointment_date, appointment_time, errors


@api_view(['GET'])
def health_check(request):
    return Response({'status': 'ok', 'service': 'salon-booking-api'})


@api_view(['GET', 'POST'])
def services(request):
    if request.method == 'GET':
        return Response([service_data(service) for service in Service.objects.all().order_by('id')])

    name, price, duration, errors = service_payload(request.data)
    if errors:
        return Response({'detail': 'Validation failed.', 'fields': errors}, status=status.HTTP_400_BAD_REQUEST)
    service = Service.objects.create(name=name, price=price, duration=duration)
    return Response(service_data(service), status=status.HTTP_201_CREATED)


@api_view(['PUT', 'DELETE'])
def service_detail(request, service_id):
    service = get_object_or_404(Service, id=service_id)
    if request.method == 'DELETE':
        if service.appointments.exists():
            return Response(
                {'detail': 'This service belongs to existing appointments and cannot be deleted.'},
                status=status.HTTP_409_CONFLICT,
            )
        service.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    name, price, duration, errors = service_payload(request.data)
    if errors:
        return Response({'detail': 'Validation failed.', 'fields': errors}, status=status.HTTP_400_BAD_REQUEST)
    service.name, service.price, service.duration = name, price, duration
    service.save()
    return Response(service_data(service))


@api_view(['GET', 'POST'])
def appointments(request):
    if request.method == 'GET':
        queryset = Appointment.objects.prefetch_related('services').order_by('-appointment_date', '-appointment_time', '-id')
        if request.query_params.get('status'):
            queryset = queryset.filter(status=request.query_params['status'])
        if request.query_params.get('date'):
            queryset = queryset.filter(appointment_date=request.query_params['date'])
        if request.query_params.get('search'):
            search = request.query_params['search'].strip()
            queryset = queryset.filter(Q(customer_name__icontains=search) | Q(customer_phone__icontains=search))

        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        except ValueError:
            return Response({'detail': 'page and page_size must be positive integers.'}, status=status.HTTP_400_BAD_REQUEST)
        count = queryset.count()
        page_items = queryset[(page - 1) * page_size:page * page_size]
        return Response({'count': count, 'results': [appointment_data(item, include_created_at=False) for item in page_items]})

    name, phone, selected_services, date, time, errors = appointment_payload(request.data)
    if errors:
        return Response({'detail': 'Validation failed.', 'fields': errors}, status=status.HTTP_400_BAD_REQUEST)

    conflicts = Appointment.objects.filter(
        appointment_date=date,
        appointment_time=time,
        status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED, Appointment.Status.COMPLETED],
        services__in=selected_services,
    ).values_list('services__id', flat=True)
    conflict_ids = sorted(set(conflicts) & {service.id for service in selected_services})
    if conflict_ids:
        return Response(
            {'detail': 'One or more selected services are already booked at this date and time.', 'fields': {'service_ids': conflict_ids}},
            status=status.HTTP_409_CONFLICT,
        )

    with transaction.atomic():
        appointment = Appointment.objects.create(
            customer_name=name,
            customer_phone=phone,
            appointment_date=date,
            appointment_time=time,
            notes=str(request.data.get('notes', '')).strip(),
        )
        appointment.services.set(selected_services)
    return Response(appointment_data(appointment), status=status.HTTP_201_CREATED)


@api_view(['PATCH'])
def appointment_status(request, appointment_id):
    appointment = get_object_or_404(Appointment.objects.prefetch_related('services'), id=appointment_id)
    value = request.data.get('status')
    if value not in Appointment.Status.values:
        return Response(
            {'detail': 'Validation failed.', 'fields': {'status': ['Choose Pending, Confirmed, Completed, or Cancelled.']}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    appointment.status = value
    appointment.save(update_fields=['status', 'updated_at'])
    return Response(appointment_data(appointment))


@api_view(['DELETE'])
def appointment_detail(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    appointment.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
