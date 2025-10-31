import os
import json
import pytest
import requests


BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:8001')
API_KEY = os.environ.get('API_KEY', os.environ.get('PETIO_DEVICE_API_KEY', 'petio_secure_key_2025'))
DEVICE_ID = os.environ.get('DEVICE_ID', 'TEST-DEVICE-001')


def _url(path: str) -> str:
    if not BASE_URL.endswith('/'):
        return BASE_URL + path
    return BASE_URL.rstrip('/') + path


def _headers():
    return {
        'Accept': 'application/json',
        'X-API-Key': API_KEY,
    }


@pytest.mark.parametrize("endpoint", [
    "/api/device/config/",
])
def test_config_endpoint_exists(endpoint):
    resp = requests.get(_url(endpoint), params={'device_id': DEVICE_ID}, headers=_headers(), timeout=5)
    # Presence/compatibility check: must not be 404 Not Found
    assert resp.status_code in (200, 403), f"Unexpected status {resp.status_code}: {resp.text[:200]}"
    # Response should be JSON even when 403
    try:
        json.loads(resp.text)
    except Exception:
        pytest.fail("Config endpoint did not return JSON")


def test_feed_command_endpoint_exists():
    endpoint = "/api/device/feed-command/"
    resp = requests.get(_url(endpoint), params={'device_id': DEVICE_ID}, headers=_headers(), timeout=5)
    assert resp.status_code in (200, 403), f"Unexpected status {resp.status_code}: {resp.text[:200]}"


def test_logs_endpoint_exists():
    endpoint = "/api/device/logs/"
    # Minimal payload; server may return 403 without valid key but should not 404
    resp = requests.post(_url(endpoint), json={'device_id': DEVICE_ID, 'logs': []}, headers=_headers(), timeout=5)
    assert resp.status_code in (200, 403, 405), f"Unexpected status {resp.status_code}: {resp.text[:200]}"


def test_status_endpoint_exists():
    endpoint = "/api/device/status/"
    payload = {'device_id': DEVICE_ID, 'is_online': True}
    resp = requests.post(_url(endpoint), json=payload, headers=_headers(), timeout=5)
    assert resp.status_code in (200, 403, 405), f"Unexpected status {resp.status_code}: {resp.text[:200]}"


def test_acknowledge_endpoint_exists():
    endpoint = "/api/device/acknowledge/"
    payload = {'device_id': DEVICE_ID, 'command_id': 0, 'result': 'ok'}
    resp = requests.post(_url(endpoint), json=payload, headers=_headers(), timeout=5)
    assert resp.status_code in (200, 403, 405), f"Unexpected status {resp.status_code}: {resp.text[:200]}"


def test_check_schedule_endpoint_exists():
    # Firmware expects non-API prefixed route
    endpoint = "/check-schedule/"
    resp = requests.get(_url(endpoint), timeout=5)
    # This endpoint allows any; should be 200 OK
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"