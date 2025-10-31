# PETio System Analysis

Scope: End-to-end overview of entities, endpoints, background tasks, and data flows across firmware, controller, marketplace, social, and shared project services. Based on repository structure under d:\PETio.

## Project Structure
- Apps: `accounts`, `controller`, `marketplace`, `social`
- Firmware: `firmware/Firmware.ino`
- Project config: `project/settings`, `project/celery.py`, `project/context_processors.py`
- Docs: `docs/petio-firmware-and-ui-guide.md`, `docs/app-controller-improvements.md`

## Key Entities (Textual ERD)
- Accounts
  - `User` extends Django `AbstractUser`; adds `mobile_number`, `age`, `marketing_opt_in` and preference flags: `email_marketplace_notifications`, `email_on_messages`, `email_on_request_updates`; parallel notification flags also present (`notify_*`).
  - `Profile` stores additional per-user info.
- Controller
  - `PetProfile` basic pet metadata used by UI.
  - `FeedingSchedule` has `time`, `portion_size`, `enabled`, optional `days_of_week`, `label`.
  - `FeedingLog` records feed events; serializer exposes `action`, `success` for UI.
  - `PendingCommand` queues firmware commands (e.g., manual feed, stop feeding).
  - `DeviceStatus` tracks heartbeat: `device_id`, `status`, `last_seen`, `wifi_rssi`, `uptime`, `daily_feeds`, `last_feed`, `error_message`.
- Marketplace
  - `Category` taxonomy for listings.
  - `Listing` includes seller, price, quantity, status, category; moderation fields include `rejected_at`, `rejected_by`, `rejected_reason_code`.
  - Messaging: `MessageThread` (listing, buyer, seller, status, last_message_at), `Message` (thread content, author).
  - Commerce lifecycle: `PurchaseRequest` (buyer, seller, listing, status, accepted/completed timestamps; one-to-one `Transaction`), `Transaction` (status, amount), `TransactionLog` with indexes (`request`, `action`; `actor`).
  - Moderation: `Report` with status and reason; threshold handling.
  - Ratings: `SellerRating` constraints ensure `score` in [1–5].
  - `Notification` captures events (`type` in request_created, status_changed, message_posted), `title`, `body`, `unread`, `email_sent`, optional `related_listing` or `related_request`.
- Social
  - `Post` (title, content, author, category, image, likes, pinned).
  - `Follow` (follower, following).
  - `UserProfile` (bio, avatar, location, website, birth_date, privacy).
  - `Announcement` (active window, content, link).
  - Social notifications exist separately within `social` views for user-level notices.

### Relationship Summary (3NF reasoning)
- `Listing` → `Category` (many-to-one). Non-key attributes describe listing only.
- `MessageThread` → `Listing`, `buyer`, `seller`; `Message` → `MessageThread`, `author`. Messages depend only on thread and author; no transitive dependencies.
- `PurchaseRequest` → `Listing`, `buyer`, `seller`; one-to-one `Transaction`. Request status timestamps depend solely on request key; transaction depends solely on transaction key.
- `TransactionLog` → `Transaction`, `actor`; each log entry depends only on its key.
- `Notification` → `User`, optional `Listing` or `PurchaseRequest`. Email flags live on `User` and are not duplicated in `Notification`.
- `FeedingSchedule` and `FeedingLog` are independent entities; logs reference action context but not duplication of schedule data.
- Enumerated status values are modeled as domain constants; acceptable for 3NF when values are atomic and not duplicating attributes.

## Endpoints Inventory
- Controller UI
  - `GET /` name `home` → Control Panel (`app/home.html`).
  - `GET /schedules-ui/` name `schedules_ui` → Schedules management UI.
  - `GET /history/` name `history` → Feeding logs UI.
- Controller DRF and function views
  - Router exposes `/logs/`, `/schedules/`, `/pets/`, `/commands/` and `/api/...` variants.
  - `GET check_schedule` named route returns `{ should_feed, portion_size, current_time, schedules[], triggered_schedule_* }` and uses cache guard to deduplicate within a 180-second window.
- Device REST API (firmware)
  - `GET /api/device/config/` → runtime config like poll interval.
  - `GET /api/device/feed-command/` → pending manual feed: `{ id, command, portion_size }`.
  - `POST /api/device/logs/` → telemetry logs batch.
  - `POST /api/device/status/` → heartbeat with RSSI, uptime, etc.
  - `POST /api/device/acknowledge/` → marks `PendingCommand` processed.
  - All require header `X-API-Key` with `PETIO_DEVICE_API_KEY`.
- Marketplace pages and JSON endpoints
  - `GET /marketplace/` home, listing browse; `GET /marketplace/listing/<id>/` detail; `GET /marketplace/listing/new/` create.
  - Purchase flow: `GET /marketplace/listing/<id>/request/`; `GET /marketplace/request/<id>/` detail, `GET /marketplace/request/<id>/meetup.ics` calendar embed.
  - Messaging: `POST /marketplace/request/<id>/message/` post messages; additional JSON APIs exist for thread creation and message fetch/post.
  - Ratings: `POST /marketplace/request/<request_id>/rate/`.
  - Notifications: `GET /marketplace/notifications/` and utility actions to mark all or toggle read.
- Social
  - `GET /social/` home, `GET /social/feed`, post create/edit/detail/delete, AJAX `toggle_like`, `toggle_follow`.
  - Profile pages, edit, and social notifications management.

## Background Tasks and Integrations
- Celery
  - `project/celery.py` configures app, autodiscover tasks.
  - Base settings: `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` default to `redis://localhost:6379/0`.
  - Task routing example: `marketplace.tasks.send_notification_email` → `notifications` queue.
  - Dev settings: tasks run eagerly (`CELERY_TASK_ALWAYS_EAGER=True`) for local testing.
- Email
  - Dev email backend: console (`django.core.mail.backends.console.EmailBackend`).
  - Async email task `marketplace/tasks.py::send_notification_email` respects user prefs and marks `Notification.email_sent` on success; retries with backoff.
- Cache
  - Default cache: `LocMemCache` with `LOCATION` override in dev.
  - Controller `check_schedule` uses cache key `sched_triggered:<id>:<date>:<HHMM>` with 180s TTL to prevent duplicate feeds.
- Channels
  - Channel layers configured with in-memory backend. No active websockets flows documented; available for future real-time features.

## Data Flows (Textual)
- Firmware ↔ Controller
  - Firmware polls `GET /api/device/config/` for operational hints.
  - Firmware periodically calls `GET /api/device/feed-command/` to fetch pending manual feed; executes and `POST /api/device/acknowledge/`.
  - Firmware sends `POST /api/device/status/` heartbeats updating `DeviceStatus` and `POST /api/device/logs/` telemetry/feeding logs.
  - Scheduled feeds: server-side `check_schedule` determines due feeds using local timezone, recent logs within 10 minutes, and a cache guard to avoid duplicates.
- Controller UI
  - Control Panel queries `/api/logs/?limit=N` for recent activity (expects `action`, `success`).
  - Schedules UI uses CRUD endpoints to manage `FeedingSchedule` entries; PUT treated as partial update for toggle convenience.
- Marketplace
  - Buyer initiates `PurchaseRequest`; status transitions recorded; ratings posted after completion.
  - Messaging threads and messages facilitate buyer–seller negotiation; notifications created per event.
  - `Notification` creation may dispatch async email via Celery according to `User` preferences.
- Social
  - Users interact via posts, likes, follows; social notifications managed within the app.

## DFDs (Textual)
- Level 0
  - External entities: `User`, `Device`.
  - System: `PETio` with major processes: Device API, Controller UI/API, Marketplace, Social.
  - Data stores: `DB` (Accounts, Controller, Marketplace, Social), `Cache`.
  - Flows: Device telemetry/commands, user actions (feed, schedule, commerce), notifications/email.
- Level 1 (Controller)
  - Processes: `Schedule Evaluator` (check_schedule), `Command Queue` (PendingCommand), `Logs API`, `Status Heartbeat`.
  - Flows: UI enqueues commands → Device fetch/ack; Device posts logs/status → UI displays; Schedule evaluator reads schedules/logs/cache → feed decision.
- Level 1 (Marketplace)
  - Processes: `Listing & Requests`, `Messaging`, `Transactions & Logs`, `Notifications`.
  - Flows: Buyer creates request → seller responds; messages exchanged; transaction created; logs maintained; notifications generated and optionally emailed.
- Level 2 (Schedule Evaluator)
  - Inputs: `FeedingSchedule`, recent `FeedingLog`, `Cache`, current local time.
  - Logic: window tolerance (180s), day-of-week filtering, duplicate prevention via logs and cache; outputs: feed decision (`should_feed`, `portion_size`).

## Process Flow Narrative (Firmware → Web UI)
- Startup
  - Firmware reads config from controller and sets poll intervals.
- Manual feed
  - User triggers feed in Control Panel → backend creates `PendingCommand`.
  - Firmware polls feed-command → executes motor feed → posts `acknowledge` → posts logs and status.
  - UI polls logs and shows success/failure events.
- Scheduled feed
  - `FeedingSchedule` entries managed via Schedules UI.
  - Device can consult `check_schedule` or rely on server-sent commands; evaluator uses timezone-aware checks and cache guard to prevent duplicates.
- Observability
  - Heartbeat updates `DeviceStatus`; UI shows connectivity and recent feeds; logs paginated and refreshed with debounced polling.

## Layered System Architecture
- Firmware layer: ESP8266/Arduino (`Firmware.ino`) with `NetworkingManager`, `HTTPClientManager`, `MotorController`, `LedController`, NTP-based timing.
- Device API gateway: Controller `device_api.py` endpoints authenticated via `X-API-Key`.
- Controller app: Django views (Control Panel, Schedules, History), DRF viewsets for logs/schedules; cache-backed schedule evaluator; models for device state and actions.
- Marketplace app: Django views and JSON endpoints for listings, requests, messaging; Celery tasks for email notifications; admin dashboards and moderation.
- Social app: Community features with posts, follows, profiles, notifications.
- Shared services: Django settings with caches, Celery (Redis default), Channels; console email in dev.

## Settings and Security Notes
- `project/settings/base.py`: `CACHES` locmem default; `CHANNEL_LAYERS` in-memory; Celery broker/result default Redis; task routing for notification emails.
- `project/settings/dev.py`: console email backend, Celery eager mode; `PETIO_DEVICE_API_KEY` configurable via env.
- Device API uses `X-API-Key`; ensure env var set and matches firmware.
- Controller `check_schedule` uses server-side cache to prevent repeat triggers; recent logs cross-check to avoid time skew duplication.

## Gaps and Alignment Notes
- Firmware schedule processing expects a `{ schedule: { schedule_id, scheduled_time_utc, portion_g } }` payload in some code paths, while controller `check_schedule` returns `{ should_feed, portion_size, current_time, schedules[] }`. Align firmware/controller by either switching firmware to device endpoints (`/api/device/...`) or adding a compat response on the server.
- Channels are configured but not actively used; potential for real-time notifications.
- Background tasks currently centered on email; future work in docs suggests batching, HTML templates, metrics.

## References
- Controller: `controller/urls.py`, `controller/views.py` (check_schedule, viewsets), templates under `controller/templates/app`.
- Firmware: `firmware/Firmware.ino` (polling, schedule processing, grace period, ISO parsing).
- Marketplace: `marketplace/urls.py`, `marketplace/views.py`, `marketplace/tasks.py`, migrations for `Notification`, `TransactionLog` indexes, moderation fields.
- Social: `social/views.py`, `social/urls.py`, admin and models.
- Settings: `project/settings/base.py`, `project/settings/dev.py`; Celery: `project/celery.py`.

---
This document summarizes current repository state and data flows to support planning and alignment across firmware, controller, marketplace, and social features.