"""
Backend tests for Feed and Connect Automatic Pet Feeder.
Covers key API endpoints and viewsets to ensure functionality.
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from .models import FeedingLog, FeedingSchedule, PendingCommand, PetProfile, DeviceStatus, Hardware, ControllerSettings
from django.utils import timezone
from django.contrib.auth import get_user_model


class APITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_log_feed_creates_feeding_log(self):
        payload = {"portion_dispensed": 10.0, "source": "web"}
        resp = self.client.post(reverse('log_feed'), payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(FeedingLog.objects.count(), 1)

    def test_logs_viewset_list(self):
        FeedingLog.objects.create(portion_dispensed=5.0, source='button')
        resp = self.client.get('/logs/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # When no pagination configured globally, list may be array; ensure non-empty
        self.assertTrue(len(resp.data) >= 1)

    def test_stop_feeding_endpoint(self):
        User = get_user_model()
        u = User.objects.create_user(username="t1", password="pass12345")
        hw = Hardware.objects.create(device_id="feeder-1", is_paired=True, paired_user=u)
        self.client.force_authenticate(user=u)
        resp = self.client.post(reverse('stop_feeding'), {"device_id": "feeder-1"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(PendingCommand.objects.filter(command='stop_feeding').count(), 1)

    def test_api_router_under_prefix(self):
        """Ensure /api/ prefix exposes routers (e.g., /api/logs/)."""
        FeedingLog.objects.create(portion_dispensed=3.0, source='web')
        resp = self.client.get('/api/logs/?limit=1')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # DRF pagination returns count/results
        self.assertIn('results', resp.data)
        self.assertLessEqual(len(resp.data['results']), 1)

    def test_logs_stats_endpoint(self):
        """Verify /api/logs/stats/ returns expected aggregate keys."""
        # Create some logs today and in the past
        FeedingLog.objects.create(portion_dispensed=5.0, source='web')
        FeedingLog.objects.create(portion_dispensed=7.5, source='button')
        resp = self.client.get('/api/logs/stats/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for key in ['total_feeds', 'total_amount', 'today_feeds', 'avg_daily']:
            self.assertIn(key, resp.data)

    def test_logs_export_csv(self):
        """Verify /api/logs/export/ returns CSV content and includes header row."""
        FeedingLog.objects.create(portion_dispensed=4.5, source='web')
        resp = self.client.get('/api/logs/export/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('text/csv', resp.headers.get('Content-Type', ''))
        content = resp.content.decode('utf-8')
        self.assertTrue(content.startswith('timestamp,amount_g,source'))

    def test_feeding_log_serializer_amount_alias(self):
        """Ensure 'amount' alias is present for frontend compatibility."""
        FeedingLog.objects.create(portion_dispensed=12.3, source='web')
        resp = self.client.get('/api/logs/?limit=1')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        first = resp.data['results'][0]
        self.assertIn('amount', first)
        self.assertAlmostEqual(first['amount'], first['portion_dispensed'])

    def test_feeding_log_includes_action_and_success(self):
        """Ensure logs include 'action' and 'success' fields used by home.html recent activity."""
        FeedingLog.objects.create(portion_dispensed=5.0, source='web')
        FeedingLog.objects.create(portion_dispensed=0.0, source='schedule')
        resp = self.client.get('/api/logs/?limit=5')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('results', resp.data)
        for item in resp.data['results']:
            self.assertIn('action', item)
            self.assertIn('success', item)
            self.assertIn(item['action'], ['feed', 'scheduled'])
            self.assertIsInstance(item['success'], bool)


class BackendAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        PetProfile.objects.create(name="Buddy", weight=5.0, portion_size=10.0)
        FeedingSchedule.objects.create(time="08:30", portion_size=12.0, enabled=True)

    def test_feed_now_queues_command(self):
        User = get_user_model()
        u = User.objects.create_user(username="feeduser", password="pass12345")
        Hardware.objects.create(device_id="feeder-1", is_paired=True, paired_user=u)
        self.client.force_authenticate(user=u)
        resp = self.client.post(reverse('feed_now'), {"portion_size": 15, "device_id": "feeder-1"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data.get('status'), 'ok')
        self.assertEqual(PendingCommand.objects.filter(command='feed_now', device_id='feeder-1').count(), 1)

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
        User = get_user_model()
        u = User.objects.create_user(username="t2", password="pass12345")
        Hardware.objects.create(device_id="feeder-1", is_paired=True, paired_user=u)
        self.client.force_authenticate(user=u)
        resp = self.client.post(reverse('stop_feeding'), {"device_id": "feeder-1"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(PendingCommand.objects.filter(command='stop_feeding').count(), 1)

    def test_calibrate_endpoint(self):
        User = get_user_model()
        u = User.objects.create_user(username="t3", password="pass12345")
        Hardware.objects.create(device_id="feeder-1", is_paired=True, paired_user=u)
        self.client.force_authenticate(user=u)
        resp = self.client.post(reverse('calibrate'), {"device_id": "feeder-1"}, format='json')
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

    def test_check_schedule_respects_days_of_week(self):
        # Disable any existing schedules from setUp
        FeedingSchedule.objects.all().update(enabled=False)
        # Determine current local time rounded to minute
        now_local = timezone.localtime(timezone.now())
        hhmm = now_local.strftime("%H:%M")
        today_abbr = now_local.strftime("%a")
        # Create a schedule at current time but exclude today's day
        days = [d for d in ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"] if d != today_abbr]
        FeedingSchedule.objects.create(time=hhmm, portion_size=10.0, enabled=True, days_of_week=days)
        # Call check_schedule
        resp = self.client.get(reverse('check_schedule'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data.get("should_feed"))
        # Ensure schedules list includes our days_of_week field
        self.assertTrue(any(isinstance(s.get("days_of_week"), list) for s in resp.data.get("schedules", [])))

    def test_schedule_time_fallback_on_bad_input(self):
        # Invalid time should fallback to 08:00 per serializer policy
        payload = {"time": "not-a-time", "portion_size": 10, "enabled": True}
        resp = self.client.post('/schedules/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # Representation is 24-hour HH:MM:SS
        self.assertEqual(resp.data.get("time"), "08:00:00")

    def test_feed_now_replaces_stale_pending_for_device(self):
        from datetime import timedelta
        old = PendingCommand.objects.create(command='feed_now', portion_size=10.0, device_id='feeder-1')
        PendingCommand.objects.filter(id=old.id).update(created_at=timezone.now() - timedelta(seconds=120))
        User = get_user_model()
        u = User.objects.create_user(username="feedstale", password="pass12345")
        Hardware.objects.create(device_id="feeder-1", is_paired=True, paired_user=u)
        self.client.force_authenticate(user=u)
        from django.core.cache import cache
        cache.clear()
        with override_settings(REST_FRAMEWORK={'DEFAULT_THROTTLE_RATES': {'feed_now': '1000000/minute', 'device_status': '1000000/minute'}}):
            resp = self.client.post(reverse('feed_now'), {"portion_size": 15, "device_id": "feeder-1"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        old.refresh_from_db()
        self.assertEqual(old.status, 'failed')
        self.assertEqual(PendingCommand.objects.filter(command='feed_now', device_id='feeder-1', status='pending').count(), 1)

    def test_feed_now_conflict_when_recent_pending_for_device(self):
        from datetime import timedelta
        recent = PendingCommand.objects.create(command='feed_now', portion_size=10.0, device_id='feeder-1')
        PendingCommand.objects.filter(id=recent.id).update(created_at=timezone.now() - timedelta(seconds=10))
        User = get_user_model()
        u = User.objects.create_user(username="feedconf", password="pass12345")
        Hardware.objects.create(device_id="feeder-1", is_paired=True, paired_user=u)
        self.client.force_authenticate(user=u)
        with override_settings(REST_FRAMEWORK={'DEFAULT_THROTTLE_RATES': {'feed_now': '1000/minute', 'device_status': '1000/minute'}}):
            resp = self.client.post(reverse('feed_now'), {"portion_size": 15, "device_id": "feeder-1"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

class DeviceStatusEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.device_id = 'feeder-1'

    def test_get_unknown_when_device_not_found(self):
        resp = self.client.get(reverse('device_status'), {'device_id': self.device_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data.get('status'), 'unknown')
        self.assertEqual(resp.data.get('device_id'), self.device_id)

    def test_post_heartbeat_marks_online_and_sets_last_seen(self):
        payload = {
            'device_id': self.device_id,
            'wifi_rssi': -65,
            'uptime': 123,
            'daily_feeds': 2,
        }
        resp = self.client.post(reverse('device_status'), payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data.get('status'), 'ok')
        self.assertEqual(resp.data.get('device_id'), self.device_id)
        # Verify model updated
        ds = DeviceStatus.objects.get(device_id=self.device_id)
        self.assertEqual(ds.status, 'online')
        self.assertIsNotNone(ds.last_seen)
        self.assertEqual(ds.wifi_rssi, -65)
        self.assertEqual(ds.uptime, 123)
        self.assertEqual(ds.daily_feeds, 2)

    def test_get_online_when_recent_last_seen(self):
        now = timezone.now()
        DeviceStatus.objects.create(device_id=self.device_id, status='online', last_seen=now)
        resp = self.client.get(reverse('device_status'), {'device_id': self.device_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data.get('status'), 'online')

    def test_get_offline_when_last_seen_expired(self):
        from datetime import timedelta
        old = timezone.now() - timedelta(seconds=120)
        DeviceStatus.objects.create(device_id=self.device_id, status='online', last_seen=old)
        resp = self.client.get(reverse('device_status'), {'device_id': self.device_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data.get('status'), 'offline')


class HardwarePairingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()
        self.user = self.User.objects.create_user(username="u1", email="u1@example.com", password="pass12345")
        self.hardware = Hardware.objects.create()

    def auth(self):
        self.client.force_authenticate(user=self.user)

    def test_validate_key_invalid(self):
        resp = self.client.post(reverse('validate_hardware_key'), {"unique_key": "not-a-uuid"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data.get("valid"))

    def test_validate_key_valid(self):
        resp = self.client.post(reverse('validate_hardware_key'), {"unique_key": str(self.hardware.unique_key)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data.get("valid"))
        self.assertFalse(resp.data.get("paired"))

    def test_pair_hardware(self):
        self.auth()
        resp = self.client.post(reverse('pair_hardware'), {"unique_key": str(self.hardware.unique_key)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.hardware.refresh_from_db()
        self.assertTrue(self.hardware.is_paired)
        self.assertEqual(self.hardware.paired_user, self.user)
        self.assertTrue(ControllerSettings.objects.filter(hardware=self.hardware).exists())

    def test_pair_conflict(self):
        other = self.User.objects.create_user(username="u2", email="u2@example.com", password="pass12345")
        self.hardware.paired_user = other
        self.hardware.is_paired = True
        self.hardware.save()
        self.auth()
        resp = self.client.post(reverse('pair_hardware'), {"unique_key": str(self.hardware.unique_key)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_my_devices_lists_paired(self):
        self.auth()
        self.client.post(reverse('pair_hardware'), {"unique_key": str(self.hardware.unique_key)}, format='json')
        resp = self.client.get(reverse('my_devices'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data.get("count", 0), 1)

    def test_update_settings_unpaired_allowed(self):
        resp = self.client.post(reverse('update_controller_settings'), {"unique_key": str(self.hardware.unique_key), "portion_size": 15}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        cfg = ControllerSettings.objects.get(hardware=self.hardware)
        self.assertEqual(cfg.portion_size, 15)

    def test_update_settings_requires_owner_when_paired(self):
        self.auth()
        self.client.post(reverse('pair_hardware'), {"unique_key": str(self.hardware.unique_key)}, format='json')
        self.client.force_authenticate(user=None)
        resp = self.client.post(reverse('update_controller_settings'), {"unique_key": str(self.hardware.unique_key), "portion_size": 10}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class PinPairingFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()
        self.user = self.User.objects.create_user(username="pairer", email="p@example.com", password="pass12345")
        self.device_id = "ESP-TEST1234"

    def test_register_claim_and_heartbeat(self):
        # Register PIN
        resp = self.client.post(reverse('device_pair_register'),
                                {"device_id": self.device_id, "pin": "123456", "ttl_seconds": 300},
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Claim as authenticated user
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(reverse('device_pair_claim'),
                                {"device_id": self.device_id, "pin": "123456"},
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Device fetches key
        self.client.force_authenticate(user=None)
        resp = self.client.get(reverse('device_pair_claimed'), {"device_id": self.device_id, "pin": "123456"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        key = resp.data.get("api_key", "")
        self.assertTrue(len(key) > 0)
        # Heartbeat with headers succeeds (legacy key disabled via override)
        with override_settings(PETIO_DEVICE_API_KEY=None):
            resp = self.client.post(reverse('device_status_heartbeat'),
                                    {"device_id": self.device_id, "wifi_rssi": -50, "uptime": 10},
                                    HTTP_DEVICE_ID=self.device_id,
                                    HTTP_X_DEVICE_KEY=key,
                                    format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_expired_pin_rejected(self):
        # Register PIN
        self.client.post(reverse('device_pair_register'),
                         {"device_id": self.device_id, "pin": "654321", "ttl_seconds": 1},
                         format='json')
        # Simulate expiry by waiting via direct DB manipulation
        from .models import Hardware, PairingSession
        hw = Hardware.objects.get(device_id=self.device_id)
        ps = PairingSession.objects.filter(hardware=hw).latest("created_at")
        from django.utils import timezone
        ps.expires_at = timezone.now() - timezone.timedelta(seconds=10)
        ps.save(update_fields=["expires_at"])
        # Claim should now fail
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(reverse('device_pair_claim'),
                                {"device_id": self.device_id, "pin": "654321"},
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_pin_rejected(self):
        self.client.post(reverse('device_pair_register'),
                         {"device_id": self.device_id, "pin": "111111", "ttl_seconds": 300},
                         format='json')
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(reverse('device_pair_claim'),
                                {"device_id": self.device_id, "pin": "222222"},
                                format='json')
        self.assertIn(resp.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND))

    def test_key_rotation_forces_repair(self):
        # Register/claim/fetch key
        self.client.post(reverse('device_pair_register'),
                         {"device_id": self.device_id, "pin": "777777", "ttl_seconds": 300},
                         format='json')
        self.client.force_authenticate(user=self.user)
        self.client.post(reverse('device_pair_claim'),
                         {"device_id": self.device_id, "pin": "777777"},
                         format='json')
        self.client.force_authenticate(user=None)
        resp = self.client.get(reverse('device_pair_claimed'),
                               {"device_id": self.device_id, "pin": "777777"})
        key = resp.data.get("api_key", "")
        # Ensure a bad key gets 403 (legacy disabled)
        with override_settings(PETIO_DEVICE_API_KEY="legacy-never-used"):
            bad = "bad" + key
            resp = self.client.post(reverse('device_status_heartbeat'),
                                    {"device_id": self.device_id, "wifi_rssi": -40, "uptime": 5},
                                    HTTP_DEVICE_ID=self.device_id,
                                    HTTP_X_DEVICE_KEY=bad,
                                    format='json')
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class OwnershipUITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()
        self.owner = self.User.objects.create_user(username="owner", password="pass12345")
        self.other = self.User.objects.create_user(username="other", password="pass12345")
        Hardware.objects.create(device_id="ESP-UI-1", is_paired=True, paired_user=self.owner)

    def test_my_devices_page_requires_login(self):
        resp = self.client.get("/devices/")
        # Redirect to login (302) or 302->200 depending on test settings
        self.assertIn(resp.status_code, (302, 301))

    def test_my_devices_page_renders(self):
        # Use session login for Django view auth
        self.client.login(username="owner", password="pass12345")
        resp = self.client.get("/devices/")
        self.assertEqual(resp.status_code, 200)

    def test_non_owner_cannot_feed(self):
        self.client.force_authenticate(user=self.other)
        resp = self.client.post(reverse('feed_now'), {"portion_size": 10, "device_id": "ESP-UI-1"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
