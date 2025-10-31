# Unified Navigation – Template Scan and view_name Mapping

This document lists Social and Marketplace templates to update, with the recommended `view_name` to pass into the sidebar include for active highlighting.

## Social Templates

- `social/templates/social/home.html` → `view_name='feed'`
- `social/templates/social/feed.html` → `view_name='feed'`
- `social/templates/social/dashboard.html` → `view_name='dashboard'`
- `social/templates/social/notifications.html` → `view_name='notifications'`
- `social/templates/social/create_post.html` → `view_name='create_post'`
- `social/templates/social/post_detail.html` → `view_name='feed'` (detail page; highlight Feed)
- `social/templates/social/edit_post.html` → `view_name='dashboard'` (editing; highlight Dashboard)
- `social/templates/social/edit_profile.html` → `view_name='dashboard'`
- `social/templates/social/profile.html` → `view_name='feed'`

Notes:
- Sidebar items for Social are exactly: Feed/Home (`feed`), Dashboard (`dashboard`), Notifications (`notifications`), Create Post (`create_post`).
- Pages without a direct sidebar item use the closest relevant item for highlighting, as indicated above.

## Marketplace Templates

- `marketplace/templates/marketplace/403.html` → `view_name='browse'`
- `marketplace/templates/marketplace/buyer_dashboard.html` → `view_name='transactions'`
- `marketplace/templates/marketplace/catalog.html` → `view_name='browse'`
- `marketplace/templates/marketplace/create_listing.html` → `view_name='my_listings'`
- `marketplace/templates/marketplace/dashboard.html` → `view_name='my_listings'`
- `marketplace/templates/marketplace/detail.html` → `view_name='browse'`
- `marketplace/templates/marketplace/messages.html` → `view_name='messages'`
- `marketplace/templates/marketplace/moderator_dashboard.html` → `view_name='notifications'` (closest fit)
- `marketplace/templates/marketplace/notifications.html` → `view_name='notifications'`
- `marketplace/templates/marketplace/report_listing.html` → `view_name='my_listings'`
- `marketplace/templates/marketplace/request_detail.html` → `view_name='transactions'`
- `marketplace/templates/marketplace/reset.html` → `view_name='browse'`
- `marketplace/templates/marketplace/seller_dashboard.html` → `view_name='my_listings'`
- `marketplace/templates/marketplace/transactions.html` → `view_name='transactions'`

Notes:
- Marketplace sidebar items are: Browse (`browse`), My Listings (`my_listings`), Messages (`messages`), Transactions (`transactions`), Notifications (`notifications`).
- Where a precise URL name is unclear, pages still receive a `view_name` for highlighting; links use known URL names or `#` placeholders per safety guidelines.