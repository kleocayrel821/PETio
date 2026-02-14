from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from controller.models import Hardware, ControllerSettings

User = get_user_model()

class HardwarePairingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="u1", email="u1@example.com", password="pass12345")
        self.hw = Hardware.objects.create()

    def test_validate_key(self):
        res = self.client.post("/api/hardware/validate-key/", {"unique_key": str(self.hw.unique_key)}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["valid"])
        self.assertFalse(res.data["is_paired"])

    def test_update_settings_unpaired(self):
        payload = {"unique_key": str(self.hw.unique_key), "portion_size": 15.5, "config": {"mode": "auto"}}
        res = self.client.post("/api/controller/update-settings/", payload, format="json")
        self.assertEqual(res.status_code, 200)
        obj = ControllerSettings.objects.get(hardware=self.hw)
        self.assertEqual(obj.portion_size, 15.5)
        self.assertEqual(obj.config.get("mode"), "auto")

    def test_pair_and_update_settings_owner_only(self):
        self.client.force_authenticate(self.user)
        res = self.client.post("/api/hardware/pair/", {"unique_key": str(self.hw.unique_key)}, format="json")
        self.assertEqual(res.status_code, 200)
        self.hw.refresh_from_db()
        self.assertTrue(self.hw.is_paired)
        self.assertEqual(self.hw.paired_user_id, self.user.id)
        payload = {"unique_key": str(self.hw.unique_key), "portion_size": 22.0}
        res2 = self.client.post("/api/controller/update-settings/", payload, format="json")
        self.assertEqual(res2.status_code, 200)
        obj = ControllerSettings.objects.get(hardware=self.hw)
        self.assertEqual(obj.portion_size, 22.0)

    def test_my_devices(self):
        self.client.force_authenticate(self.user)
        self.client.post("/api/hardware/pair/", {"unique_key": str(self.hw.unique_key)}, format="json")
        res = self.client.get("/api/hardware/my-devices/")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.data["count"], 1)
