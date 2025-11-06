/**
 * PETio Marketplace Admin JavaScript Utilities
 * Purpose: Provide cohesive interactions, helpers, and UI micro-interactions for the admin UI.
 * Scope: Loaded on admin pages to unify toasts, sidebar, formatting, and optional chart loading.
 */

/* global lucide */

/**
 * Get CSRF token from cookies for POST requests.
 * @returns {string|null} CSRF token value
 */
function getCSRFToken() {
  const name = 'csrftoken';
  const cookies = document.cookie ? document.cookie.split(';') : [];
  for (let i = 0; i < cookies.length; i++) {
    const cookie = cookies[i].trim();
    if (cookie.startsWith(name + '=')) {
      return decodeURIComponent(cookie.substring(name.length + 1));
    }
  }
  return null;
}

/**
 * Debounce a function to prevent rapid calls.
 * @param {Function} fn - The function to debounce
 * @param {number} delayMs - Delay in milliseconds
 * @returns {Function} Debounced wrapper
 */
function debounce(fn, delayMs) {
  let t = null;
  return function debounced(...args) {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), delayMs);
  };
}

/**
 * Format a numeric PHP currency value (₱) consistently.
 * @param {number|string} value - Numeric value to format
 * @returns {string} Formatted string like "₱1,234.56"
 */
function formatCurrencyPHP(value) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency', currency: 'PHP', minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(Number(value) || 0);
  } catch (e) {
    const v = Number(value) || 0;
    return `₱${v.toFixed(2)}`;
  }
}

/**
 * Human-friendly relative time (e.g., "2 hours ago").
 * @param {string|Date|number} dateInput - Date, timestamp, or string
 * @returns {string} Relative time label
 */
function timeAgo(dateInput) {
  const d = typeof dateInput === 'string' ? new Date(dateInput) : new Date(dateInput);
  const diff = Date.now() - d.getTime();
  const s = Math.floor(diff / 1000);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  const dday = Math.floor(h / 24);
  if (s < 60) return `${s}s ago`;
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  if (dday < 30) return `${dday}d ago`;
  const mo = Math.floor(dday / 30);
  if (mo < 12) return `${mo}mo ago`;
  return `${Math.floor(mo / 12)}y ago`;
}

/**
 * Show a toast notification using DaisyUI styles, positioned top-right.
 * Creates a container if it does not exist; auto-dismisses after 5 seconds.
 * @param {string} message - Message to display
 * @param {('info'|'success'|'warning'|'error')} level - Visual style level
 */
function showMarketplaceToast(message, level = 'info') {
  let container = document.getElementById('marketplaceToastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'marketplaceToastContainer';
    container.className = 'toast toast-top toast-end fixed right-4 top-4 z-50';
    document.body.appendChild(container);
  }
  const alert = document.createElement('div');
  alert.className = `alert alert-${level} shadow-md flex items-center gap-3`;
  const icon = document.createElement('span');
  icon.innerHTML = {
    success: '<i class="fas fa-check-circle"></i>',
    error: '<i class="fas fa-exclamation-circle"></i>',
    warning: '<i class="fas fa-exclamation-triangle"></i>',
    info: '<i class="fas fa-info-circle"></i>'
  }[level] || '<i class="fas fa-info-circle"></i>';
  const text = document.createElement('span');
  text.textContent = message || '';
  const closeBtn = document.createElement('button');
  closeBtn.className = 'btn btn-ghost btn-xs ml-2';
  closeBtn.setAttribute('aria-label', 'Close notification');
  closeBtn.innerHTML = '<i class="fas fa-times"></i>';
  closeBtn.addEventListener('click', () => alert.remove());
  alert.appendChild(icon); alert.appendChild(text); alert.appendChild(closeBtn);
  container.appendChild(alert);
  setTimeout(() => { alert.remove(); }, 5000);
}

/**
 * Lazy-load Chart.js (UMD build) with robust CDN fallback.
 * Ensures `window.Chart` is present for non-module script usage.
 * @returns {Promise<void>} Resolves only when Chart is available on window
 */
function loadChartJs() {
  // If already loaded, resolve immediately
  if (window.Chart) return Promise.resolve();

  /**
   * Load a script from the given src and return a Promise.
   * @param {string} src - Script URL
   * @returns {Promise<void>}
   */
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = src;
      s.async = true;
      s.crossOrigin = 'anonymous';
      s.referrerPolicy = 'no-referrer';
      s.onload = () => resolve();
      s.onerror = () => reject(new Error('Failed to load ' + src));
      document.head.appendChild(s);
    });
  }

  // Prefer UMD build that attaches `window.Chart`; try multiple CDNs
  const candidates = [
    'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js',
    'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js',
    'https://unpkg.com/chart.js@4.4.1/dist/chart.umd.min.js',
    'https://unpkg.com/chart.js@4.4.1/dist/chart.umd.js'
  ];

  // Attempt to load sequentially until one succeeds and exposes window.Chart
  let chain = Promise.reject();
  for (const url of candidates) {
    chain = chain.catch(() => loadScript(url).then(() => {
      if (!window.Chart) throw new Error('Chart.js loaded but global Chart missing');
    }));
  }

  return chain.then(() => {
    if (!window.Chart) throw new Error('Chart.js unavailable');
  });
}

/**
 * Export a dataset to CSV.
 * @param {string} filename - Desired filename
 * @param {string[]} headers - CSV header labels
 * @param {Array<Array<string|number>>} rows - Data rows
 */
function exportCsv(filename, headers, rows) {
  const csv = [headers.join(','), ...rows.map(r => r.map(v => `${String(v).replace(/"/g, '""')}`).join(','))].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = filename || 'export.csv';
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

/**
 * Initialize admin sidebar interactions, including mobile drawer and swipe-to-close.
 */
function initAdminSidebar() {
  const sidebar = document.getElementById('admin-sidebar');
  const openBtn = document.getElementById('mobile-nav-toggle');
  const closeBtn = document.getElementById('sidebar-close');
  const overlay = document.getElementById('mobile-overlay');
  const open = () => { if (!sidebar) return; sidebar.classList.add('open'); if (overlay) overlay.classList.remove('hidden'); document.body.style.overflow = 'hidden'; };
  const close = () => { if (!sidebar) return; sidebar.classList.remove('open'); if (overlay) overlay.classList.add('hidden'); document.body.style.overflow = ''; };
  openBtn && openBtn.addEventListener('click', open);
  closeBtn && closeBtn.addEventListener('click', close);
  overlay && overlay.addEventListener('click', close);
  // Simple swipe-to-close for mobile
  let startX = null;
  (overlay || document).addEventListener('touchstart', (e) => { startX = e.touches[0].clientX; }, { passive: true });
  (overlay || document).addEventListener('touchmove', (e) => {
    if (startX == null) return;
    const dx = e.touches[0].clientX - startX;
    // Swipe left threshold
    if (dx < -50) close();
  }, { passive: true });
}

/**
 * Initialize Lucide icons if available.
 */
function initIcons() {
  try { if (window.lucide && typeof window.lucide.createIcons === 'function') { window.lucide.createIcons(); } } catch (_) {}
}

/**
 * Attach minor micro-interactions to buttons and cards for hover/active states.
 */
function initMicroInteractions() {
  document.querySelectorAll('.btn').forEach((btn) => {
    btn.addEventListener('mousedown', () => btn.classList.add('active'));
    btn.addEventListener('mouseup', () => btn.classList.remove('active'));
    btn.addEventListener('mouseleave', () => btn.classList.remove('active'));
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initAdminSidebar();
  initIcons();
  initMicroInteractions();
  // Expose helpers globally for reuse in tab scripts
  window.AdminUtils = { getCSRFToken, debounce, formatCurrencyPHP, timeAgo, loadChartJs, exportCsv, showMarketplaceToast };
});