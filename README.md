Feed and Connect Automatic Pet Feeder

A full-stack, Wi‑Fi connected pet feeder system built with Django (backend + web UI) and ESP8266 firmware controlling an MG996R servo. It supports manual and scheduled feeding, local/offline operation, and automatic synchronization of feeding logs to the server.

 Key Features
- Web control panel with Feed Now, portion control, and schedules management
- Feeding history with searchable filters, export, and statistics
- Manual Button, Automatic Button, and Schedule trigger types with consistent UI labels
- ESP8266 firmware with non‑blocking control, RGB LED status, and local log queue
- REST API for logs, schedules, and device commands (DRF)
- Works offline: physical button remains functional and logs are synced later

System Architecture
See the high-level architecture diagram:

- docs/system-architecture.svg

Feeding Flow (End-to-End)
See the detailed flowchart showing trigger → command → dispense → log → UI render:

- docs/flowchart-feed-sequence.svg

Repository Structure
```
PETio/
├── pet_feeder_simple/                 # ESP8266 firmware (Arduino/PlatformIO)
│   └── pet_feeder_simple.ino
└── project/                           # Django project (Backend + Web UI)
    ├── app/
    │   ├── models.py                  # FeedingLog, FeedingSchedule, PendingCommand, PetProfile
    │   ├── serializers.py             # Normalizes feed_type, action; API serializers
    │   ├── views.py                   # CBVs + API endpoints for UI and firmware
    │   ├── templates/app/             # HTML templates (Home, History, Schedules, Control)
    │   └── urls.py                    # Routes: UI + DRF + firmware endpoints
    ├── manage.py                      # Django management
    └── project/settings.py            # Django settings
```

Data Model Overview
- FeedingLog: timestamp, source (manual_button | automatic_button | schedule | legacy), portion_dispensed
- FeedingSchedule: time, portion_size, enabled, days
- PendingCommand: command (e.g., feed_now), portion_size, status
- PetProfile: name, weight, portion_size

Notes:
- Serializer provides derived fields:
  - amount (alias of portion_dispensed)
  - action: 'scheduled' for schedule/scheduled; 'feed' otherwise
  - feed_type: one of manual | automatic | scheduled (from source)

 API Overview
All endpoints are available under both legacy and new prefixes. Examples below use the new /api/ prefix when available.

- UI Pages
  - GET /           → Home dashboard
  - GET /history/   → Feeding history
  - GET /schedules-ui/ → Schedule management
  - GET /control/   → Control panel (legacy)

- Firmware Integration
  - GET /command/                 → Poll for next PendingCommand
  - POST /feed_now/               → Queue immediate feed (web-triggered)
  - POST /log/                    → Log result from firmware
  - GET /command_status/          → Check current command status
  - GET /api/check-schedule/      → Backend helper for schedule logic
  - GET /api/device-status/       → Device diagnostics (optional)
  - POST /api/remote-command/     → Remote feed trigger (automatic button path)
  - POST /api/stop-feeding/       → Stop current feeding
  - POST /api/calibrate/          → Calibration endpoint

- REST Resources (DRF)
  - GET/POST /api/logs/           → Feeding logs
    - Query params: start_date, end_date, search, feed_type
      - feed_type values:
        - manual → sources [manual_button, button, manual]
        - automatic → [automatic_button, remote_command, web, esp, serial_command]
        - scheduled → [schedule, scheduled]
      - Legacy synonyms also supported: button, remote, esp, web
  - GET/POST /api/schedules/      → Feeding schedules (CRUD)
  - GET/POST /api/commands/       → Pending commands (CRUD)

Response example (FeedingLog via serializer):
```json
{
  "id": 123,
  "timestamp": "2025-09-23T21:35:00Z",
  "source": "manual_button",
  "portion_dispensed": 12.5,
  "amount": 12.5,
  "action": "feed",
  "success": true,
  "feed_type": "manual"
}
```

 Frontend (Templates + Vanilla JS)
- History
  - Feed Type filter options: Manual Button, Automatic Button, Schedule
  - Badges/icons derived from feed_type
  - Search, date range, pagination, CSV export
- Control Panel
  - Prominent Feed Now button and portion slider
  - Schedules list with enable/disable and time editor
  - Feeding Logs table shows friendly Source labels
- Home
  - Recent Activity shows feed_type labels and icons
  - Stats cards and last-fed time
    
 Firmware (ESP8266 / Arduino)
- Hardware
  - MG996R Servo (D5), Button (D6), RGB LED (D1, D2, D3)
- Software
  - Non‑blocking logic using millis()
  - Keeps a local queue of log entries and flushes to server when online
  - Sources used in logs: manual_button, automatic_button, schedule
  - Critical events are logged via Serial for debugging

 Local Development
Prerequisites
- Python 3.12, pip, and virtualenv (venv)
- Arduino IDE 

Setup
```powershell
# From PETio/project
python -m venv .venv
. .venv\Scripts\activate
pip install -r requirements.txt  # if present; otherwise install Django + djangorestframework
python manage.py migrate
python manage.py runserver
```

Useful Commands
```powershell
# Django checks and migrations
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate

# Collect static (dev)
python manage.py collectstatic --noinput --clear
```

 Testing
- Django
  - Add model and API tests under project/app/tests.py
  - Use pytest or Django test runner
- Firmware
  - Use Serial monitor to validate button press, scheduled trigger, and HTTP sync

 Production Notes
- Use a real WSGI/ASGI server (gunicorn, uvicorn/daphne)
- Switch to PostgreSQL and configure environment-specific settings
- Never commit secrets or Wi‑Fi credentials; use environment variables / EEPROM
