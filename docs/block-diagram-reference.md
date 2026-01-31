# PETio Block Diagram Reference

This document provides the canonical breakdown of PETio into blocks (systems, subsystems, interfaces) and the relationships needed to create consistent block diagrams across contexts (device, backend, apps). Use this as the input when authoring diagrams in Mermaid (C4Context/C4Container) or architecture-beta.

## Top-Level Blocks
- ESP8266 Feeder Device
  - Inputs: Manual Feed Button, Portion +/− Buttons, Serial (CAL commands)
  - Controllers/Modules: NetworkingManager, HTTPClientManager, LedController, MotorController
  - Actuators: Servo Motor (MG996R)
  - Indicators: RGB LEDs (red/blue states)
  - External Interfaces: WiFi (STA/AP), NTP, HTTP (device endpoints)

- Django Backend
  - Controller App
    - Device APIs: status, logs, commands, schedule
    - Controller UI: schedules, history, pending commands, device status
    - Data: FeedingSchedule, PendingCommand, FeedingLog, DeviceStatus
  - Marketplace App
    - Catalog, Listing Detail
    - Purchase Requests, Messaging Threads, Transactions
    - Marketplace UI and Admin Views
  - Social App
    - Profiles, Posts, Reactions, Follows, Notifications
    - Social UI and Moderation
  - Shared Infrastructure
    - Channels Layer (real-time)
    - Celery Workers (background tasks)
    - PostgreSQL (primary DB)
    - Redis (broker) and SMTP (email)

## Device Subsystem Blocks
- NetworkingManager: WiFi connect, AP config portal, device ID
- HTTPClientManager: REST calls (GET/POST), API key header, scheme-aware client
- LedController: state handling (ready, feeding, error), overlay feedback
- MotorController: feed execution (normal, chunked, reverse-clear), post-feed clearing, anti-jam
- Time Sync: NTP client and periodic refresh

## Controller Subsystem Blocks
- DeviceAPIs
  - GET /api/device/command/, POST /api/device/command/ack/
  - GET /api/check-schedule/
  - POST /api/device/status/
  - POST /api/device/logs/
- Controller UI
  - Schedule management
  - Pending command control (feed_now)
  - History (logs) and Device Status dashboard
- Data Models
  - FeedingSchedule, PendingCommand, FeedingLog, DeviceStatus
- Schedule Decision
  - Local time (Asia/Manila), window tolerance
  - Duplicate prevention via cache + recent logs

## Marketplace Subsystem Blocks
- Views/API: Catalog, Listing Detail, Requests, Messaging, Transactions
- Data Models: Category, Listing, PurchaseRequest, MessageThread/Message, Transaction, Report
- Admin: dashboards, analytics, approvals, moderation

## Social Subsystem Blocks
- Views: Feed, Profile, Post Create/Interact
- Data Models: Profile, Post, Comment, Reaction, Follow, Notification
- Decisions: private follow approvals, notification delivery

## Interfaces & Edges
- Device → Controller (HTTP)
  - Status heartbeat, feeding logs, command poll, schedule check
- Device ↔ WiFi (connectivity), Device ↔ NTP (time sync)
- Controller → Channels (WebSocket/event dispatch)
- Apps → PostgreSQL (ORM)
- Celery → Redis (broker), Celery → SMTP (email)

## Diagram Guidance
- C4Context (recommended for system overview)
  - Person(User/Admin) → Systems (Controller/Marketplace/Social)
  - System_Ext(Device, WiFi, NTP, Redis, SMTP)
  - Enterprise_Boundary for Django Backend
  - Relations labeled with protocol (“HTTP”, “HTTPS”, “SQL”, “WS”, “NTP”)

- C4Container (for component-level views)
  - Container(Controller UI, Device API, Schedule Engine, Models/ORM) within Controller App
  - Container(Marketplace UI, Catalog API, Request/Transaction Engine) within Marketplace
  - Container(Social UI, Posts API, Notification Engine) within Social
  - Container(DB), Container(Channels), Container(Celery), Container(Redis), Container(SMTP)

- Mermaid architecture-beta (optional)
  - Use group blocks for apps/infrastructure
  - Use service blocks for components and interfaces
  - Edges with explicit side directions (L/R/T/B) and arrows (<, >)

## Block Diagram Checklist
- Include device blocks (controllers, actuators, indicators) and their edges to WiFi/NTP/HTTP.
- Show Controller App APIs and UI, plus data models behind them.
- Represent Marketplace/Social with UI/API/engine blocks and their persistence.
- Add infrastructure blocks: Channels, Celery, DB, Redis, SMTP.
- Label edges with protocols and intent (e.g., “Polls/POST: status, logs, commands”).

## References (Code)
- Firmware: [Firmware.ino](file:///d:/PETio/controller/firmware/Firmware/Firmware.ino)
- Controller: [device_api.py](file:///d:/PETio/controller/device_api.py#L1-L298), [views/urls](file:///d:/PETio/controller/urls.py#L1-L59)
- Marketplace: [urls.py](file:///d:/PETio/marketplace/urls.py#L33-L142), [views.py](file:///d:/PETio/marketplace/views.py), [test_app.py](file:///d:/PETio/marketplace/test_app.py)
- Social: app views/models (in social module)
- Settings: [dev.py](file:///d:/PETio/project/settings/dev.py), [base.py](file:///d:/PETio/project/settings/base.py), [prod.py](file:///d:/PETio/project/settings/prod.py)
