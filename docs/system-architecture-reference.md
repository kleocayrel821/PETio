# PETio System Architecture Reference

This document is the definitive reference for designing, communicating, and maintaining PETio's system architecture across device firmware and Django-based backend applications. It is structured to help generate consistent architecture diagrams (C4Context, C4Container, Mermaid architecture-beta, and block diagrams) and serve as onboarding material.

## System Overview
- ESP8266 Feeder Device (Firmware)
  - Modules: NetworkingManager, HTTPClientManager, LedController, MotorController
  - Interfaces: WiFi (STA/AP), HTTP (device endpoints), NTP (time sync)
  - Inputs: Manual Feed Button, Portion Adjust Buttons, Serial CAL commands
  - Outputs: Servo Motor (MG996R), RGB LEDs
  - Behavior: Small/medium/large portion strategies, anti-jam, post-feed clearing

- Django Backend
  - Controller App
    - Device APIs: status, logs, commands, schedule
    - Web UI: schedules, pending commands, history, status
    - Data: FeedingSchedule, PendingCommand, FeedingLog, DeviceStatus
  - Marketplace App
    - Catalog, Listing Detail, Requests, Messaging, Transactions
    - Admin dashboards and analytics
    - Data: Category, Listing, PurchaseRequest, MessageThread/Message, Transaction, Report
  - Social App
    - Profiles, Posts, Reactions, Follows, Notifications
    - Moderation features
  - Infrastructure
    - Channels (real-time dispatch), Celery (background tasks), PostgreSQL (DB), Redis (broker), SMTP (email)

## External Dependencies
- WiFi network (device connectivity)
- NTP server (time synchronization)
- SMTP server (email notifications)
- Redis broker (task queue)

## Data Flows (Core)
- Device → Controller
  - Poll GET /api/device/command/; POST /api/device/command/ack/
  - Poll GET /api/check-schedule/
  - POST /api/device/status/ (heartbeat)
  - POST /api/device/logs/ (feeding logs)
  - Requires X-API-Key header; dev/prod keys must match firmware DEFAULT_API_KEY

- Controller UI → Models
  - Schedule creation and management
  - Feed-now command creation
  - History and status dashboards

- Marketplace
  - Requests lifecycle: pending → negotiate/accept/reject/cancel → meetup → payment → completed
  - Messaging threads between buyer and seller
  - Quick sell API for dashboard: /api/listings/<id>/sell/

- Social
  - Private follow decisions (request/approve/pending)
  - Notifications for interactions

## Decision Logic (Highlights)
- Schedule decision:
  - Local time (Asia/Manila) with tolerance window
  - Duplicate prevention via cache and recent logs
- Device feeding strategies:
  - Normal continuous feed for small portions
  - Chunked feeding with mini-agitation for medium portions
  - Reverse-clear cycles for large portions; post-feed clearing runs after all feeds
- Network resilience:
  - Short HTTP timeouts, single retry
  - Backoff (e.g., 60s) on failures to avoid loop blocking

## Security & Environment
- Dev
  - ALLOWED_HOSTS: 127.0.0.1, localhost, 192.168.18.9
  - PETIO_DEVICE_API_KEY configured in dev.py; match firmware
  - Runserver bound to 0.0.0.0:8000; firewall allowed
- Prod
  - HTTPS domain (petio.site); TLS verification recommended (CA pinning on device)
  - ALLOWED_HOSTS includes production domains only

## Diagram Templates

### Mermaid C4Context (System Context)
```mermaid
C4Context
title PETio System Context

Person(user, "User", "Pet owner via web UI")
Person(admin, "Admin", "Administrator")

System_Ext(device, "ESP8266 Feeder", "Firmware device")
System_Ext(wifi, "WiFi", "Connectivity")
System_Ext(ntp, "NTP Server", "Time sync")
System_Ext(redis, "Redis", "Broker")
System_Ext(smtp, "SMTP", "Email server")

Enterprise_Boundary(e1, "Django Backend") {
  System(controller, "Controller App", "Device APIs + UI")
  System(marketplace, "Marketplace App", "Catalog/Requests/Transactions")
  System(social, "Social App", "Profiles/Posts/Reactions/Notifications")
  System(channels, "Channels", "Real-time layer")
  System(celery, "Celery", "Background tasks")
  SystemDb(postgres, "PostgreSQL", "DB")
}

Rel(user, controller, "Uses Controller UI", "HTTPS")
Rel(user, marketplace, "Uses Marketplace UI", "HTTPS")
Rel(user, social, "Uses Social UI", "HTTPS")
Rel(admin, controller, "Manage schedules/commands", "HTTPS")
Rel(device, controller, "Poll/POST device endpoints", "HTTP")
Rel(device, wifi, "Connects", "")
Rel(device, ntp, "Sync time", "NTP")
Rel(controller, postgres, "Persist schedules/logs/status", "SQL")
Rel(marketplace, postgres, "Persist marketplace data", "SQL")
Rel(social, postgres, "Persist social data", "SQL")
Rel(controller, channels, "Push events", "WS")
Rel(marketplace, channels, "Push events", "WS")
Rel(social, channels, "Push events", "WS")
Rel(celery, redis, "Broker", "Redis")
Rel(celery, smtp, "Emails", "SMTP")
```

### Mermaid block (Subsystem View)
```mermaid
block
  columns 3
  block:Device:3
    columns 3
    ESP8266(("ESP8266 Feeder"))
    Buttons["Manual Feed"] LEDs["Status LEDs"] Motor["Servo"]
    NetworkingManager HTTPClientManager LedController MotorController
  end
  block:Connectivity:2
    columns 2
    WiFi(("WiFi")) NTP(("NTP"))
  end
  block:Backend:3
    columns 3
    block:Controller:2
      columns 2
      ControllerUI["Controller UI"] DeviceAPIs["Device APIs"] Schedules["Schedules"]
    end
    block:Marketplace:2
      columns 2
      MarketplaceUI["Marketplace UI"] Listings Requests Messaging Transactions
    end
    block:Social:2
      columns 2
      SocialUI["Social UI"] Profiles Posts Reactions Notifications
    end
    Channels(("Channels")) Celery["Celery"] Redis[("Redis")] PostgreSQL[("PostgreSQL")] SMTP["SMTP"]
  end
  ESP8266 --> WiFi
  ESP8266 --> NTP
  HTTPClientManager -- "HTTP GET/POST" --> DeviceAPIs
  ControllerUI --> Schedules
  ControllerUI --> DeviceAPIs
  MarketplaceUI --> Listings
  MarketplaceUI --> Requests
  MarketplaceUI --> Messaging
  MarketplaceUI --> Transactions
  SocialUI --> Profiles
  SocialUI --> Posts
  SocialUI --> Reactions
  SocialUI --> Notifications
  DeviceAPIs --> PostgreSQL
  Schedules --> PostgreSQL
  Listings --> PostgreSQL
  Requests --> PostgreSQL
  Messaging --> PostgreSQL
  Transactions --> PostgreSQL
  Profiles --> PostgreSQL
  Posts --> PostgreSQL
  Reactions --> PostgreSQL
  Notifications --> PostgreSQL
  ControllerUI --> Channels
  MarketplaceUI --> Channels
  SocialUI --> Channels
  Celery --> Redis
  Celery --> SMTP
```

## Code References
- Firmware: [Firmware.ino](file:///d:/PETio/controller/firmware/Firmware/Firmware.ino)
- Controller URLs/API: [urls.py](file:///d:/PETio/controller/urls.py#L1-L59), [device_api.py](file:///d:/PETio/controller/device_api.py#L1-L298)
- Marketplace: [urls.py](file:///d:/PETio/marketplace/urls.py#L33-L142), [views.py](file:///d:/PETio/marketplace/views.py), [test_app.py](file:///d:/PETio/marketplace/test_app.py)
- Social: app views/models
- Settings: [dev.py](file:///d:/PETio/project/settings/dev.py), [base.py](file:///d:/PETio/project/settings/base.py), [prod.py](file:///d:/PETio/project/settings/prod.py)
