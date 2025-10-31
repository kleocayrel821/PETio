# PETio Controller App

This repository contains the PETio Controller web application built with Django and Django Channels, providing a real-time UI for device status and feeding events, plus progressive-web-app (PWA) support.

## Run (ASGI / Channels)

- Ensure dependencies are installed (including `channels` and `daphne`).
- Start the server with Daphne:
  
  ```bash
  python -m daphne project.asgi:application -b 127.0.0.1 -p 8000
  ```
  
- ASGI app: `project.asgi:application` (configured via `ProtocolTypeRouter`).
- WebSocket routing is defined in `project/routing.py`.

## Real-time UI

- WebSocket endpoints:
  - `ws://<host>/ws/device-status/` — broadcasts device status updates.
  - `ws://<host>/ws/feeding-logs/` — broadcasts feeding log events.
- Frontend integration lives in `controller/templates/app/base.html`:
  - Connects to both WebSocket endpoints.
  - Fallback to HTTP polling for status when WebSocket is unavailable.
  - Displays toast notifications for feeding events.

## Error Reporting

- Global error boundary captures window errors and unhandled promise rejections.
- Client errors are POSTed to `POST /api/client-errors/` with JSON payload:
  - `message`, `stack`, `timestamp`, `url`, `userAgent`, and `type`.

## PWA / Service Worker

- Service worker: `sw.js` is served at `/sw.js`.
- Offline fallback page: `/offline/`.
- Registration is triggered from the base template (`base.html`), if not already registered.

## Useful URLs

- Home UI: `/`
- Schedules UI: `/schedules-ui/`
- History UI: `/history/`
- Health: `/api/health/`