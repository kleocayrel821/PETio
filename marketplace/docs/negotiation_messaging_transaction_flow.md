# Marketplace Negotiation, Messaging, Notifications, and Transaction Flow

This document explains how negotiation, messaging, notifications, and the overall transaction lifecycle work in the marketplace. It summarizes the key models, view handlers, JSON APIs, state transitions, and side effects such as logs and notifications.

> Note: Route names and paths may differ between HTML and JSON endpoints. Refer to `marketplace/urls.py` for exact URL patterns.

## Core Models and Status Enums

- `PurchaseRequestStatus`:
  - `pending` → initial request created by buyer
  - `negotiating` → an offer is in progress (buyer offer or seller counter)
  - `accepted` → seller accepted terms; transaction exists
  - `rejected` → seller rejected
  - `canceled` → buyer or seller canceled (context-dependent rules)
  - `completed` → buyer marked completed post-meetup and payment

- `TransactionStatus`:
  - `proposed` → default record when created (some flows set directly to `confirmed`)
  - `confirmed` → seller accepted request terms
  - `awaiting_payment` → optional phase to reflect off-platform payment expectation
  - `paid` → payment recorded (precondition for completion)
  - `completed` → after meetup confirmed and buyer marks completed
  - `canceled` → transaction canceled

- `ListingStatus` (selected highlights):
  - `active` → available for requests
  - `reserved` → set upon acceptance to prevent double-selling
  - `sold` → set upon completion

- `LogAction` important entries:
  - `buyer_request`, `seller_accept`, `seller_reject`, `seller_negotiate`
  - `offer_submitted`, `offer_countered`, `offer_accepted`, `offer_rejected`
  - `meetup_proposed`, `meetup_updated`, `meetup_confirmed`
  - `request_canceled`, `request_completed`

## High-Level Flow Overview

```
Buyer -> creates PurchaseRequest (pending)
      -> optionally submits offer (negotiating)

Seller -> responds: accept | reject | counter
  - accept: PR=accepted, Listing=reserved, Transaction=confirmed
  - reject: PR=rejected
  - counter: PR=negotiating with counter_offer

Meetup logistics (accepted requests only):
  - propose -> update -> confirm (time in future)

Payment + Completion:
  - once Transaction=paid and meetup confirmed, buyer can mark PR completed
    => PR=completed, Transaction=completed, Listing=sold

Cancellation:
  - buyer/seller can cancel depending on state; listing restored if reserved

Throughout:
  - Messages in thread/request, unread counts, notifications, transaction logs
```

## Negotiation Logic

- Buyer `submit_offer` (HTML form):
  - Preconditions: user is buyer, request is `pending` or `negotiating`, listing is `active`.
  - Effects:
    - Set `PurchaseRequest.status = negotiating`
    - Update `offer_price` and optional `quantity`
    - Create `TransactionLog(action=offer_submitted)`
    - Notify seller (`NotificationType.STATUS_CHANGED`)

- Seller `respond_offer` (HTML form) supports three actions:
  - Accept:
    - Set `PurchaseRequest.status = accepted`
    - Create `Transaction` and set `Transaction.status = confirmed`
    - Set `Listing.status = reserved`
    - Create `TransactionLog(action=offer_accepted)`
    - Notify buyer (`STATUS_CHANGED`)
  - Reject:
    - Set `PurchaseRequest.status = rejected`
    - Create `TransactionLog(action=offer_rejected)`
    - Notify buyer
  - Counter:
    - Keep `PurchaseRequest.status = negotiating`
    - Set `counter_offer` amount
    - Create `TransactionLog(action=offer_countered)`
    - Notify buyer

Guards and validation exist to prevent invalid transitions (e.g., only seller can respond; listing must be active to accept).

## Request Accept/Reject/Cancel (Non-offer flows)

- `seller_accept_request` (HTML):
  - Preconditions: seller owns listing; PR is `pending`.
  - Effects:
    - `PR.status = accepted`
    - Create `Transaction` and set `status = confirmed`
    - `Listing.status = reserved`
    - Log `seller_accept`
    - Notify buyer (`STATUS_CHANGED`)

- `seller_reject_request` (HTML):
  - `PR.status = rejected`
  - Log `seller_reject`
  - Notify buyer

- `buyer_cancel_request` / `seller_cancel_request` (HTML):
  - Cancels active request(s) according to rules:
    - Pending/Negotiating: typically buyer can cancel
    - Accepted: seller may cancel prior to completion
  - Effects:
    - `PR.status = canceled`
    - `Transaction.status = canceled` (if exists)
    - `Listing.status = active` if previously `reserved`
    - Log `request_canceled`
    - Notify both parties

## Messaging

Two messaging scopes exist:

- Thread messages (`Message`) tied to a listing/thread between buyer and seller:
  - Start or get thread: `api_start_or_get_thread`
  - Post message: `api_post_message`
  - Fetch messages: `api_fetch_messages` supports pagination via `after_id` and `limit`

- Request messages (`RequestMessage`) tied to a specific `PurchaseRequest`:
  - HTML form handler: `post_request_message`
  - Unread logic includes both thread and request messages.

Unread criteria used by `messages_count`:
- `Message.read_at IS NULL` and message is from the other party in a thread the user participates in
- `RequestMessage.read_at IS NULL` and authored by the other party in a `PurchaseRequest` where user is buyer or seller

## Notifications

- `_notify(user, notif_type, ...)` creates in-app notifications and may send email depending on preferences and availability.
- Key types: `REQUEST_CREATED`, `STATUS_CHANGED`, `MESSAGE_POSTED`.
- Used throughout negotiation, accept/reject, meetup proposal/update/confirm, cancellation, and completion to alert the other party.
- `notifications_count` returns unread in-app notification count: `{ "count": <number> }`.

## Meetup and Logistics

Meetup details live on `Transaction`:
- Fields: `meetup_time`, `meetup_place`, `meetup_timezone`, optional `reschedule_reason`.

Flow:
- `propose_meetup` (HTML): create initial `meetup_time`, `meetup_place`, and optional `timezone`.
- `update_meetup` (HTML): modify existing details and optionally set `reschedule_reason`.
- `confirm_meetup` (HTML): confirms details; validates that `meetup_time` is in the future at confirmation time.
- ICS export: `meetup_ics` generates a calendar invite from the confirmed details.

Each step logs `meetup_proposed`, `meetup_updated`, or `meetup_confirmed` and notifies the counterpart.

## Completion

- `mark_request_completed` (HTML): allows buyer (or moderator) to mark a request completed.
  - Preconditions:
    - `PurchaseRequest.status = accepted`
    - `Transaction.status = paid`
    - `meetup_confirmed` log exists
  - Effects:
    - `PR.status = completed`
    - `Transaction.status = completed`
    - `Listing.status = sold`
    - Log `request_completed`
    - Notify both parties

## JSON API Reference (Selected)

> Use `urls.py` to confirm exact paths. Below are logical handlers and sample payloads/returns.

- Create request: `api_request_create`
```json
{
  "listing_id": 123,
  "message": "Interested in this item",
  "offer_price": 45.00,
  "quantity": 1
}
```
Returns `request` record with `status = "pending"` and basic listing details.

- Accept request: `api_request_accept`
```json
{
  "request_id": 456
}
```
Effects mirror `seller_accept_request` and return `transaction` object and updated `listing` summary.

- Reject request: `api_request_reject`
```json
{ "request_id": 456 }
```
Sets request to `rejected` and logs/notifications.

- Negotiate (counter): `api_request_negotiate`
```json
{
  "request_id": 456,
  "counter_offer": 50.00
}
```
Keeps request in `negotiating` and notifies buyer.

- Cancel: `api_request_cancel`
```json
{ "request_id": 456, "reason": "Change of plans" }
```
Cancels request and transaction; restores listing if reserved.

- Meetup set/update: `api_request_meetup_set`
```json
{
  "request_id": 456,
  "meetup_time": "2025-12-01T18:00:00",
  "meetup_place": "Central Park",
  "meetup_timezone": "US/Eastern"
}
```
Creates or updates `Transaction` meetup details and logs `meetup_proposed`/`meetup_updated`.

- Meetup confirm: `api_request_meetup_confirm`
```json
{ "request_id": 456 }
```
Validates future time and logs `meetup_confirmed`.

- Complete: `api_request_complete`
```json
{ "request_id": 456, "note": "All good" }
```
Transitions request and transaction to `completed`; listing to `sold`.

- Messaging:
  - Start/get thread: `api_start_or_get_thread` with `listing_id`
  - Post: `api_post_message` with `{ "thread_id": ..., "text": "..." }`
  - Fetch: `api_fetch_messages?thread_id=...&after_id=...&limit=50`

## Guards, Permissions, and Validation

- Only authenticated users; endpoints often use `@login_required` or DRF `IsAuthenticatedOrReadOnly`.
- Buyer vs. seller role checks for actions (e.g., only seller can accept/reject; only buyer can mark completed).
- State guards prevent illegal transitions (e.g., cannot confirm meetup without details, cannot accept when listing inactive).
- Input sanitation: text fields pass through `sanitize_text` and forms validate lengths/formats.
- Timezone-aware date handling for meetups and future-time validation on confirmation.

## Logging and Audit Trail

- `TransactionLog` records every significant state change with `request`, `actor`, `action`, and optional `note`.
- UI surfaces negotiation and meetup logs in request detail, and helper flags like `meetup_confirmed`.
- Logs underpin permissions like `can_mark_completed` (derived from `Transaction.status == paid`, `meetup_confirmed`, and roles).

## Unread Counts and Badges

- `notifications_count` → returns unread notification count for header badges.
- `messages_count` → combines unread thread messages and request messages.

## Side Effects Summary

- On every action, consider:
  - Status transitions on `PurchaseRequest`, `Transaction`, `Listing`
  - Logging via `TransactionLog`
  - Notifications via `_notify`
  - Potential email dispatch (when enabled)

## Where to Look in Code

- View functions: `marketplace/views.py`
  - Negotiation: `submit_offer`, `respond_offer`
  - Request actions: `seller_accept_request`, `seller_reject_request`, `buyer_cancel_request`, `seller_cancel_request`, `mark_request_completed`
  - Meetup: `propose_meetup`, `update_meetup`, `confirm_meetup`, `meetup_ics`
  - Messaging (JSON): `api_start_or_get_thread`, `api_post_message`, `api_fetch_messages`
  - Request (JSON): `api_request_create`, `api_request_accept`, `api_request_reject`, `api_request_negotiate`, `api_request_cancel`, `api_request_meetup_set`, `api_request_meetup_confirm`, `api_request_complete`
  - Notifications and counts: `_notify`, `notifications_count`, `messages_count`

## Appendix: ASCII State Diagrams

PurchaseRequest:
```
pending -> negotiating -> accepted -> completed
   \           \           \-> canceled
    \           \-> rejected
     \-> canceled
```

Transaction:
```
confirmed -> paid -> completed
    \           \-> canceled
     \-> canceled
```

Listing:
```
active -> reserved -> sold
   \           \-> active (if request canceled)
```

This documentation should give you a clear, end-to-end understanding of how negotiation, messaging, notifications, and transaction flows operate within the marketplace.