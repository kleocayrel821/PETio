# PETio Firmware ↔ Backend Compatibility Report

Date: {{ auto-generated }}

## Endpoint Analysis

- `/api/device/config/`
  - Backend: `controller/urls.py` line 36 → `device_api.device_config`
  - Status: OK
- `/api/device/feed-command/`
  - Backend: `controller/urls.py` line 39 → `device_api.device_feed_command`
  - Status: OK
- `/api/device/logs/`
  - Backend: `controller/urls.py` line 40 → `device_api.device_logs`
  - Status: OK
- `/api/device/status/`
  - Backend: `controller/urls.py` line 41 → `device_api.device_status_heartbeat`
  - Status: OK
- `/api/device/acknowledge/`
  - Backend: `controller/urls.py` line 42 → `device_api.device_acknowledge`
  - Status: OK
- `/check-schedule/`
  - Firmware expectation: non-API prefixed route
  - Before: Mismatch (only `path("api/check-schedule/", ...)` at `controller/urls.py` line 29)
  - After: Added `path("check-schedule/", views.check_schedule, name="check_schedule_firmware")` at `controller/urls.py` line 31 → OK

## Fixes Applied

- Added firmware-compatible route:
  - `controller/urls.py`: `path('check-schedule/', views.check_schedule, name='check_schedule_firmware')`
- Configured API key default in active settings:
  - `project/settings/dev.py`: `PETIO_DEVICE_API_KEY = os.getenv('PETIO_DEVICE_API_KEY', 'petio_secure_key_2025')`

## Tests

- Created `test_firmware_backend.py` at project root using `requests`.
- Tests cover: config, feed-command, logs, status, acknowledge, and check-schedule.
- Env vars: `BASE_URL`, `API_KEY`, `DEVICE_ID` (defaults: `http://127.0.0.1:8001`, `'petio_secure_key_2025'`, `'TEST-DEVICE-001'`).

## Notes

- Firmware has `BASE_URL` hardcoded; update per `firmware_patch.md` to point to your host IP and match the API key.
- Device endpoints validate header `X-API-Key`; 403 is expected if keys don’t match.