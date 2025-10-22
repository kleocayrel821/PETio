# Marketplace App and Controller Improvements

This document outlines proposed improvements for the PETio Marketplace app, with a focus on the UI (templates) and controllers (Django views/endpoints). The goal is to improve user experience, correctness, performance, security, and maintainability.

## Summary
- Clarify and enforce request state transitions across controllers.
- Make meetup flows uniformly JSON-first with friendly inline UX.
- Integrate payments for transactions and surface payment state consistently.
- Optimize catalog and detail queries; add indexes where needed.
- Strengthen validation, error handling, and observability across endpoints.

## Scope & References
- Controllers: `marketplace/views.py`, `marketplace/urls.py`
- Templates: `marketplace/templates/marketplace/*.html`
- Models: `marketplace/models.py`
- Tasks: `marketplace/tasks.py`
- Existing docs: `docs/marketplace-improvements.md`, `docs/marketplace-user-and-admin-guide.md`

## App (UI) Improvements
- Catalog (`marketplace/templates/marketplace/catalog.html`)
  - Add filters: category, price range, status, distance.
  - Implement sort options: price, date, popularity.
  - Add pagination or infinite scroll; handle empty states clearly.
  - Show quick stats via `global_stats`; cache for performance.
- Listing Detail (`marketplace/templates/marketplace/detail.html`)
  - Multiple images and media support; image carousel and zoom.
  - Seller trust badges, ratings, and “similar listings”.
  - Replace remaining hardcoded placeholders; ensure `{{ listing.title }}` used everywhere.
- Request Detail (`marketplace/templates/marketplace/request_detail.html`)
  - Inline validation and progress feedback for offer and meetup forms.
  - Disable submit buttons while submitting; surface server errors without full reload.
  - Prominent “Mark Completed” button gated by payment + meetup confirmed (implemented; continue refining visibility rules).
  - Show condensed timeline: negotiate, meetup, completion, cancellation.
- Messages (`marketplace/templates/marketplace/messages.html`)
  - Real-time updates (WebSocket or polling) and long-thread virtualization.
  - Rich text formatting restrictions; quoting and threading for clarity.

## Controllers / Views Improvements
- State machine enforcement
  - Centralize `PurchaseRequestStatus` transitions; validate allowed actions per state.
  - Deduplicate acceptance/cancellation logic between seller actions and negotiation endpoints.
- Meetup JSON-first flows
  - Ensure `propose_meetup`, `update_meetup`, `confirm_meetup` return JSON consistently using `wants_json(request)`.
  - Standardize success and error payloads with `json_ok` and `json_error`.
  - Add timezone normalization and validation (already seeded; enforce consistently).
- Completion flow
  - Gate `mark_request_completed` by payment `TransactionStatus.PAID` and presence of `MEETUP_CONFIRMED` log.
  - Idempotency: prevent double completion; return specific error codes for invalid transitions.
- Payments integration
  - Add provider (Stripe/Adyen) for holds/escrow and refunds.
  - Map transaction states to provider intents; handle webhooks.
  - Reflect payment state in controllers and templates consistently.
- Access control and permissions
  - Consolidate checks (buyer/seller/moderator) into shared helpers.
  - Add tests to verify unauthorized access is denied for all sensitive endpoints.
- Rate limiting
  - Apply `rate_limit` to message posting and meetup actions to curb abuse.

## Validation & Error Handling
- Forms and inputs
  - Enforce numeric ranges and required fields server-side; mirror client-side hints.
  - Use `sanitize_text` for free text inputs; cap lengths and reject control characters.
- Error responses
  - Use `HttpResponseBadRequest` for HTML flows and `json_error` for JSON requests.
  - Add error codes and field-level details to improve client handling.
- Messaging
  - Persist and surface meaningful error messages via `django_messages` without full page reload.

## Performance & Scaling
- Query optimization
  - Use `select_related`/`prefetch_related` in catalog/detail and request threads.
  - Add DB indexes for frequently filtered fields (category, status, price).
- Caching
  - Cache `global_stats` with sensible TTL; invalidate on listing changes.
  - Consider caching catalog filters/options.
- N+1 audits
  - Evaluate `RequestDetailView` and message rendering for N+1 issues.

## Security & Compliance
- CSRF and authentication
  - Ensure CSRF tokens present and validated in all POST forms.
- Authorization
  - Centralize permission checks; audit admin/moderator powers and logging.
- Data sanitization
  - Confirm templating auto-escaping; sanitize user inputs with `sanitize_text`.
- Secrets & configuration
  - Store provider secrets securely; support environment-based configs.
- Audit trails
  - Ensure `TransactionLog` captures all critical actions; add moderator/admin actions.

## Testing & Observability
- Unit tests
  - Add tests for `RequestDetailView.get_context_data` flags and flows.
  - Cover meetup propose/update/confirm (HTML + JSON) and error paths.
  - Test `mark_request_completed` gating and idempotency.
- Integration/E2E
  - Simulate negotiation and meetup lifecycle, including ratings.
- Observability
  - Add structured logging for controllers; tag by request ID and user.
  - Integrate error monitoring (e.g., Sentry) and performance traces.

## Internationalization & Accessibility
- i18n
  - Wrap user-visible strings in translation functions; add locale files.
- a11y
  - Add labels/aria attributes; ensure keyboard navigation and contrast.
  - Announce dynamic changes (e.g., form submit success/error) for screen readers.

## Background Tasks (`marketplace/tasks.py`)
- Email delivery
  - Add HTML emails and templates; include deep links to `request_detail`.
  - Batch notifications; avoid sending too frequently to the same user.
  - Add exponential backoff with jitter for `self.retry`; log failures with context.
  - Instrument task execution (timings, success/failure counters).

## Developer Experience
- Tooling
  - Add linters (`flake8`), formatters (`black`), type hints (`mypy`).
  - Pre-commit hooks and CI checks for tests/formatting.
- Migrations
  - Validate and document migrations; avoid risky status renames without guards.
- Documentation
  - Keep `docs/marketplace-improvements.md` and this roadmap in sync; add diagrams for flows.

## Prioritized Roadmap
- P0 (Correctness & UX)
  - Enforce state machine; unify meetup JSON flows; payment+completion gating; consistent error payloads.
- P1 (Performance & Features)
  - Catalog filters/pagination; query optimizations; caching; richer listing detail.
- P2 (Polish & Scale)
  - i18n/a11y; observability; dev tooling; email enhancements.

## Acceptance Criteria Examples
- Meetups: Propose/Update/Confirm endpoints return consistent JSON with success/error codes; templates use inline feedback.
- Completion: Button visible only when buyer/moderator, payment is PAID, meetup confirmed, status is ACCEPTED; double-submits prevented.
- Catalog: Filters and pagination operate without N+1 queries; page renders within target response time.
- Tests: 90%+ coverage of critical controllers; passing CI; clear logs on failure.

---

Maintainers can use this as the living plan to prioritize work. Tie each improvement to specific issues and PRs, and update acceptance criteria as flows evolve.