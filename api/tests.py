from django.test import TestCase

from .models import Service


class HealthCheckTests(TestCase):

    def test_health_check_returns_ok(self):
        response = self.client.get('/api/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')


class SalonApiTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(name='Haircut', price=500, duration=30)

    def test_service_crud_and_validation(self):
        invalid = self.client.post('/api/services', {'name': '', 'price': 0, 'duration': 0}, content_type='application/json')
        self.assertEqual(invalid.status_code, 400)

        created = self.client.post('/api/services', {'name': 'Facial', 'price': 1500, 'duration': 60}, content_type='application/json')
        self.assertEqual(created.status_code, 201)
        service_id = created.json()['id']

        updated = self.client.put(f'/api/services/{service_id}', {'name': 'Premium Facial', 'price': 1800, 'duration': 75}, content_type='application/json')
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['name'], 'Premium Facial')

        deleted = self.client.delete(f'/api/services/{service_id}')
        self.assertEqual(deleted.status_code, 204)

    def test_appointment_lifecycle_and_conflict(self):
        payload = {
            'customer_name': 'Sita Thapa',
            'customer_phone': '9808741220',
            'service_ids': [self.service.id],
            'appointment_date': '2026-09-18',
            'appointment_time': '11:00',
            'notes': 'Sensitive skin products only',
        }
        created = self.client.post('/api/appointments', payload, content_type='application/json')
        self.assertEqual(created.status_code, 201)
        appointment_id = created.json()['id']
        self.assertEqual(created.json()['total_price'], 500)

        conflict = self.client.post('/api/appointments', {**payload, 'customer_name': 'Ram'}, content_type='application/json')
        self.assertEqual(conflict.status_code, 409)

        changed = self.client.patch(f'/api/appointments/{appointment_id}/status', {'status': 'Confirmed'}, content_type='application/json')
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()['status'], 'Confirmed')

        listed = self.client.get('/api/appointments?status=Confirmed&search=Sita')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()['count'], 1)

        self.assertEqual(self.client.delete(f'/api/appointments/{appointment_id}').status_code, 204)
