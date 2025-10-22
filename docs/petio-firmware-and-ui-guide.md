# PETio Firmware & UI Controller Guide

This guide explains how to provision Wi‑Fi on the ESP8266, run the main PETio firmware, connect to your Django backend, and use the web UI to control feeding, schedules, and history.

## Overview
- Two sketches:
  - `petio_provisioning.ino`: SoftAP config portal to save Wi‑Fi credentials to LittleFS and EEPROM.
  - `petio_esp8266.ino`: Main firmware that connects to Wi‑Fi, talks to the Django backend, handles button feeds, logs, heartbeat, and commands.
- Storage:
  - LittleFS file `/wifi.json` has `{"ssid":"...","password":"..."}`.
  - EEPROM stores a copy of SSID/password with a flag for presence.
- GPIO safety:
  - GPIO0 (D3) is LED output only; do not use as input to avoid boot issues.
  - Button on GPIO12 (D6) triggers provisioning (long press at boot) and manual feed (short press).
- Backend endpoints (all require `X-API-Key`):
  - `GET /api/device/config/`
  - `GET /api/device/feed-command/`
  - `POST /api/device/logs/`
  - `POST /api/device/status/`
  - `POST /api/device/acknowledge/`

## Prerequisites
- Arduino IDE with ESP8266 core installed.
- Libraries: `ESP8266WiFi`, `ESP8266WebServer`, `ESP8266HTTPClient`, `WiFiClient`, `LittleFS`, `EEPROM`, `ArduinoJson` (v6), `Servo`.
- Board: `NodeMCU 1.0 (ESP-12E)` (or your ESP8266 variant). Ensure LittleFS is enabled in Flash layout.
- Django server running PETio with `PETIO_DEVICE_API_KEY` configured.

## Provisioning: petio_provisioning.ino
Use when no credentials exist or button (D6) is held at boot.
1. Upload `firmware/petio_esp8266/petio_provisioning.ino`.
2. ESP8266 starts SoftAP `SSID: PETio_Config`, `password: petio123`.
3. Connect from phone/PC to `PETio_Config` Wi‑Fi.
4. Open `http://192.168.4.1/` and submit the form:
   - SSID
   - Password
5. Firmware writes credentials to LittleFS `/wifi.json` and EEPROM, prints "Credentials saved, rebooting…", waits 2s, then restarts.

### `/wifi.json` format
```json
{
  "ssid": "MyWiFi",
  "password": "mypassword"
}
```

### EEPROM Map
- Byte `0`: presence flag `0x42`.
- Bytes `1–32`: SSID (null‑terminated).
- Bytes `33–96`: Password (null‑terminated).
- Remaining: unused.

## Main Firmware: petio_esp8266.ino
1. Upload `firmware/petio_esp8266/petio_esp8266.ino`.
2. It loads credentials from LittleFS first, then EEPROM fallback.
3. Connects to Wi‑Fi and backend, polls every 30s by default (configurable via `/api/device/config/`).
4. Button behavior (GPIO12/D6):
   - Short press: immediate feed (one portion).
   - Long press (>2s): mark provisioning needed; on next reboot, hold to enter provisioning.

### Device configuration
- Set `BASE_URL` to your server IP, e.g., `http://192.168.1.14:8000`.
- Set `API_KEY` to match `PETIO_DEVICE_API_KEY` from Django settings.
- Device ID default: `esp8266-01` (customize as needed).

### LED status
- Red: no Wi‑Fi.
- Blue: connecting.
- Green: connected.
- White: feeding.

### Backend communication
- `GET /api/device/config/` → returns settings like `poll_interval`.
- `GET /api/device/feed-command/` → returns pending feed command: `{ "id": 123, "command": "feed", "portion_size": 1 }`.
- `POST /api/device/logs/` → `{ "logs": [ { "timestamp": 1234, "message": "..." } ] }`.
- `POST /api/device/status/` → heartbeat with RSSI, uptime, etc.
- `POST /api/device/acknowledge/` → acknowledges processed command.
- All requests must include header `X-API-Key: <your-secret-key>`.

## Django Server Setup
1. Set API key: in `project/settings/dev.py`, `PETIO_DEVICE_API_KEY = os.getenv('PETIO_DEVICE_API_KEY', 'CHANGE_ME')`.
   - Recommended: set env var `PETIO_DEVICE_API_KEY` to your secret value and use the same in firmware.
2. Run migrations: `python manage.py migrate` (settings: `project.settings.dev`).
3. Start dev server for LAN access: `python manage.py runserver 0.0.0.0:8000`.
4. Allow Windows Firewall inbound TCP 8000.
5. Use host IP in firmware `BASE_URL` (e.g., `http://192.168.1.14:8000`).

## Using the UI Controller
- Base paths (see `controller/urls.py`):
  - Home / Control Panel: `GET /` (`name='home'`)
  - Schedules UI: `GET /schedules-ui/` (`name='schedules_ui'`)
  - History: `GET /history/` (`name='history'`)

### Home / Control Panel
- Feed Now: set portion and trigger a feed.
- Device status card shows connectivity and heartbeat.
- Quick links to schedules and history.

### Schedules UI
- Add recurring feeds: set time, portion size, label, days of week, and enable.
- Manage schedules: edit, enable/disable, delete.
- These map to `FeedingSchedule` API and drive automatic commands.

### History
- View `FeedingLog` entries (time, portion, source).
- Filter by date range and paginate.

## Typical Workflow
1. Provision device Wi‑Fi via `PETio_Config` portal.
2. Set `BASE_URL` and `API_KEY` in main firmware, upload.
3. Start Django server and verify `http://<host-ip>:8000/` is reachable.
4. Watch device LEDs and serial log for connection and heartbeat.
5. Use UI to configure schedules and monitor history.
6. Trigger manual feed from UI or device button; device acknowledges command via `/api/device/acknowledge/`.

## Troubleshooting
- 403 from backend: `API_KEY` mismatch; ensure firmware matches server `PETIO_DEVICE_API_KEY`.
- ESP can’t reach server: use host LAN IP, not `localhost`; check firewall and same subnet.
- Wi‑Fi fails: re-run provisioning by holding button at boot or re-upload provisioning sketch.
- LED stays red: no Wi‑Fi connection; check SSID/password and signal strength.

## Serial Log Samples
### Provisioning
```
[Provisioning] AP started: 192.168.4.1
[Provisioning] Web server started on 192.168.4.1
Credentials saved, rebooting...
```
### Normal Operation
```
[Main] Connecting Wi‑Fi...
Connected: 192.168.1.50
Heartbeat POST:200
Logs sync POST:200
Fed portion:1
Ack POST:200
```

## Notes 
- GPIO0 (D3) used only for LED; never as input.
- Logs are buffered in RAM and synced when online. For power-loss resilience, you can extend to persist logs to LittleFS.
- Consider reserving a DHCP lease for your host IP to avoid `BASE_URL` changes.