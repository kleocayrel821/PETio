"""
Backend tests for Feed and Connect Automatic Pet Feeder.
Covers key API endpoints and viewsets to ensure functionality.
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from .models import FeedingLog, FeedingSchedule, PendingCommand, PetProfile

class BackendAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        PetProfile.objects.create(name="Buddy", weight=5.0, portion_size=10.0)
        FeedingSchedule.objects.create(time="08:30", portion_size=12.0, enabled=True)

    def test_feed_now_queues_command(self):
        resp = self.client.post(reverse('feed_now'), {"portion_size": 15}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data.get('status'), 'ok')
        self.assertEqual(PendingCommand.objects.filter(command='feed_now').count(), 1)

    def test_get_command_returns_pending(self):
        cmd = PendingCommand.objects.create(command='feed_now', portion_size=10.0)
        resp = self.client.get(reverse('get_command'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data.get('command'))
        self.assertEqual(resp.data.get('command'), 'feed_now')

    def test_log_feed_creates_feeding_log(self):
        payload = {"portion_dispensed": 10.0, "source": "web"}
        resp = self.client.post(reverse('log_feed'), payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(FeedingLog.objects.count(), 1)

    def test_logs_viewset_list(self):
        FeedingLog.objects.create(portion_dispensed=5.0, source='button')
        resp = self.client.get('/logs/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(len(resp.data) >= 1)

    def test_stop_feeding_endpoint(self):
        resp = self.client.post(reverse('stop_feeding'), {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(PendingCommand.objects.filter(command='stop_feeding').count(), 1)

    def test_calibrate_endpoint(self):
        resp = self.client.post(reverse('calibrate'), {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(PendingCommand.objects.filter(command='calibrate').count(), 1)

    def test_schedules_crud(self):
        # Create via API expects 12-hour string per serializer
        payload = {"time": "08:30:00 AM", "portion_size": 10, "enabled": True}
        resp = self.client.post('/schedules/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        sch_id = resp.data['id']
        # List
        resp_list = self.client.get('/schedules/')
        self.assertEqual(resp_list.status_code, status.HTTP_200_OK)
        # Update
        update_payload = {"time": "09:00:00 AM", "portion_size": 11, "enabled": True}
        resp_upd = self.client.put(f'/schedules/{sch_id}/', update_payload, format='json')
        self.assertIn(resp_upd.status_code, (status.HTTP_200_OK, status.HTTP_202_ACCEPTED))
        # Delete
        resp_del = self.client.delete(f'/schedules/{sch_id}/')
        self.assertIn(resp_del.status_code, (status.HTTP_204_NO_CONTENT, status.HTTP_200_OK))
