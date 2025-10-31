# Firmware Patch Notes

Update the following constants in your ESP8266 firmware before flashing:

- `BASE_URL` — Set to your server URL (host IP preferred). Example: `http://192.168.1.100:8001`.
- `API_KEY` — Must match Django `PETIO_DEVICE_API_KEY`. Default in dev is `'petio_secure_key_2025'`.
- `DEVICE_ID` — Unique ID for the device, e.g., `"PETIO-DEVICE-01"`.

Recommended steps:
- Use a reserved DHCP lease for the host to avoid changing `BASE_URL`.
- Store `API_KEY` securely; avoid committing secrets to source control.
- After updating, verify:
  - `GET /api/device/config/` returns 200/403 with JSON.
  - `GET /api/device/feed-command/` responds (200/403).
  - `GET /check-schedule/` returns 200.

Endpoints used by firmware:
- `/api/device/config/`
- `/api/device/feed-command/`
- `/api/device/acknowledge/`
- `/api/device/logs/`
- `/api/device/status/`
- `/check-schedule/`