// Navigation interactions for PETio unified navbar/sidebar

(function() {
  function $(selector) { return document.querySelector(selector); }
  function on(el, evt, handler) { if (el) el.addEventListener(evt, handler); }

  // Badge utilities
  function updateBadge(el, count, max) {
    if (!el) return;
    const cap = typeof max === 'number' ? max : 99;
    const val = typeof count === 'number' ? count : 0;
    if (val > 0) {
      el.textContent = String(val > cap ? cap + '+' : val);
      el.style.display = '';
      el.setAttribute('aria-live', 'polite');
    } else {
      el.style.display = 'none';
    }
  }

  function toggleMenu(btn, menu) {
    if (!btn || !menu) return;
    const expanded = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!expanded));
    menu.classList.toggle('show', !expanded);
  }

  function closeMenu(btn, menu) {
    if (!btn || !menu) return;
    btn.setAttribute('aria-expanded', 'false');
    menu.classList.remove('show');
  }

  function initNotificationBadgePolling() {
    const badge = $('#notificationBadge');
    const appSwitcher = $('.app-switcher');
    if (!badge) return;

    // Initialize display from data-count
    try {
      const initial = parseInt(badge.getAttribute('data-count') || '0', 10);
      updateBadge(badge, isNaN(initial) ? 0 : initial);
    } catch (e) {}

    const currentApp = (appSwitcher && appSwitcher.getAttribute('data-current-app')) || '';
    const urlAttr = badge.getAttribute('data-badge-count-url');
    const appAttr = badge.getAttribute('data-app') || '';
    // Gate by app: if a specific app is set on the badge, require match; else default to social-only for global badge
    const shouldPoll = appAttr ? (currentApp === appAttr) : (currentApp === 'social');
    if (!shouldPoll) return;

    const url = urlAttr || '/social/notifications/count/';
    const max = parseInt(badge.getAttribute('data-badge-max') || '99', 10);

    function refresh() {
      fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }})
        .then(r => r.json())
        .then(data => {
          const count = (data && typeof data.count === 'number') ? data.count : 0;
          updateBadge(badge, count, max);
          // Mirror Social local badge if present
          const local = document.getElementById('notifBadge');
          if (local) updateBadge(local, count, max);
        })
        .catch(() => {});
    }
    // Initial and interval
    refresh();
    setInterval(refresh, 60000);
  }

  // Generic badge polling for any element with data-badge-count-url
  function initGenericBadgePolling() {
    window.PETIO = window.PETIO || {};
    window.PETIO.badgeIntervals = window.PETIO.badgeIntervals || new Map();
    const appSwitcher = $('.app-switcher');
    const currentApp = (appSwitcher && appSwitcher.getAttribute('data-current-app')) || '';
    const badges = document.querySelectorAll('[data-badge-count-url]');
    badges.forEach(function(el){
      // Skip the global notificationBadge; it is handled separately
      if (el.id === 'notificationBadge') return;
      const url = el.getAttribute('data-badge-count-url');
      const intervalMs = parseInt(el.getAttribute('data-badge-interval') || '60000', 10);
      const max = parseInt(el.getAttribute('data-badge-max') || '99', 10);
      const appAttr = el.getAttribute('data-app') || '';
      if (appAttr && appAttr !== currentApp) return;

      function doRefresh(){
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }})
          .then(r => r.json())
          .then(data => {
            const count = (data && typeof data.count === 'number') ? data.count : 0;
            updateBadge(el, count, max);
          })
          .catch(() => {});
      }
      // Initial
      doRefresh();
      // Clear existing interval if any
      const existing = window.PETIO.badgeIntervals.get(el);
      if (existing) clearInterval(existing);
      const handle = setInterval(doRefresh, intervalMs);
      window.PETIO.badgeIntervals.set(el, handle);
    });
  }

  function initNavigation() {
    // App switcher
    const appToggle = $('#appSwitcherToggle');
    const appDropdown = $('#appSwitcherDropdown');
    on(appToggle, 'click', function(e) {
      e.stopPropagation();
      toggleMenu(appToggle, appDropdown);
    });

    // Profile dropdown
    const profileToggle = $('#profileToggle');
    const profileDropdown = $('#profileDropdown');
    const profileMenu = document.querySelector('.profile-menu');

    // Click toggle (mobile/keyboard accessibility)
    on(profileToggle, 'click', function(e) {
      e.stopPropagation();
      toggleMenu(profileToggle, profileDropdown);
    });

    // Hover-driven open/close for a smooth UX
    on(profileMenu, 'mouseenter', function() {
      if (!profileDropdown) return;
      profileDropdown.classList.add('show');
      if (profileToggle) profileToggle.setAttribute('aria-expanded', 'true');
    });
    on(profileMenu, 'mouseleave', function() {
      if (!profileDropdown) return;
      profileDropdown.classList.remove('show');
      if (profileToggle) profileToggle.setAttribute('aria-expanded', 'false');
    });

    // Close menus on outside click
    on(document, 'click', function(e) {
      if (appDropdown && appDropdown.classList.contains('show')) {
        const withinApp = appDropdown.contains(e.target) || (appToggle && appToggle.contains(e.target));
        if (!withinApp) closeMenu(appToggle, appDropdown);
      }
      if (profileDropdown && profileDropdown.classList.contains('show')) {
        const withinProf = profileDropdown.contains(e.target) || (profileToggle && profileToggle.contains(e.target));
        if (!withinProf) closeMenu(profileToggle, profileDropdown);
      }
    });

    // Esc closes open menus
    on(document, 'keydown', function(e) {
      if (e.key === 'Escape') {
        if (appDropdown && appDropdown.classList.contains('show')) closeMenu(appToggle, appDropdown);
        if (profileDropdown && profileDropdown.classList.contains('show')) closeMenu(profileToggle, profileDropdown);
      }
    });

    // Keyboard shortcuts: Alt+1/2/3 to switch apps
    on(document, 'keydown', function(e) {
      if (!e.altKey) return;
      if (e.code === 'Digit1') { window.location.href = '/'; }
      if (e.code === 'Digit2') { window.location.href = '/social/'; }
      if (e.code === 'Digit3') { window.location.href = '/marketplace/'; }
    });

    // CSRF helper
    window.PETIO = window.PETIO || {};
    window.PETIO.getCsrfToken = function() {
      const meta = document.querySelector('meta[name="csrf-token"]');
      if (meta && meta.content && meta.content !== 'NOTPROVIDED') return meta.content;
      const match = document.cookie.match(/csrftoken=([^;]+)/);
      return match ? match[1] : '';
    };

    initNotificationBadgePolling();
    initGenericBadgePolling();
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNavigation);
  } else {
    initNavigation();
  }

  // Expose init in case of dynamic page injections
  window.PETIO = window.PETIO || {};
  window.PETIO.initNavigation = initNavigation;
})();