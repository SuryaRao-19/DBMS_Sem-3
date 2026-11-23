/* ============================================================
   Tata Power EZ Charge — EV Network Management Demo
   Client Interactions, Zero-Flicker Sidebar, CSRF Sync & Helpers
   ============================================================ */

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

function applyCsrfTokenToDom(token) {
  if (!token) return;
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) {
    meta.setAttribute('content', token);
  }
  document.querySelectorAll('input[name="csrf_token"]').forEach((input) => {
    input.value = token;
  });
}

async function refreshCsrfToken() {
  try {
    const res = await fetch('/auth/csrf-token', {
      method: 'GET',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (data && data.csrf_token) {
      applyCsrfTokenToDom(data.csrf_token);
      return data.csrf_token;
    }
  } catch (e) { /* network offline or blocked */ }
  return null;
}

async function csrfFetch(url, options = {}) {
  const buildHeaders = (tok) => ({
    ...(options.headers || {}),
    'X-CSRFToken': tok || getCsrfToken(),
  });
  let res = await fetch(url, {
    credentials: 'same-origin',
    ...options,
    headers: buildHeaders(),
  });
  if (res.status === 400) {
    const fresh = await refreshCsrfToken();
    if (fresh) {
      res = await fetch(url, {
        credentials: 'same-origin',
        ...options,
        headers: buildHeaders(fresh),
      });
    }
  }
  return res;
}

function togglePasswordVisibility(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const reveal = input.type === 'password';
  input.type = reveal ? 'text' : 'password';
  if (btn) {
    btn.textContent = reveal ? 'Hide' : 'Show';
    btn.setAttribute('aria-pressed', reveal ? 'true' : 'false');
    btn.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
  }
}

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.style.display = 'none';
  }
}

function toggleProfileMenu(btn) {
  const wrap = btn.closest('.profile-menu-wrap');
  if (!wrap) return;
  const menu = wrap.querySelector('.profile-dropdown');
  if (menu) {
    menu.classList.toggle('open');
  }
}

function toggleAdminSidebar() {
  if (window.innerWidth <= 1120) {
    document.body.classList.toggle('sidebar-mobile-open');
  } else {
    document.documentElement.classList.remove('sidebar-preload');
    const isCollapsed = !(
      document.body.classList.contains('sidebar-collapsed')
      || document.documentElement.classList.contains('sidebar-is-collapsed')
    );
    document.body.classList.toggle('sidebar-collapsed', isCollapsed);
    document.documentElement.classList.toggle('sidebar-is-collapsed', isCollapsed);
    try {
      localStorage.setItem('ev_sidebar_collapsed', isCollapsed ? '1' : '0');
    } catch (e) { /* storage disabled */ }
  }
}

function closeMobileSidebar() {
  document.body.classList.remove('sidebar-mobile-open');
}

// Refresh CSRF tokens automatically when browser restores page from bfcache
window.addEventListener('pageshow', (event) => {
  if (event.persisted) {
    refreshCsrfToken();
  }
});

// Close modals & profile dropdowns when clicking outside
window.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.style.display = 'none';
  }
  if (!e.target.closest('.profile-menu-wrap')) {
    document.querySelectorAll('.profile-dropdown.open').forEach((el) => el.classList.remove('open'));
  }
});

// Finalize pre-paint sidebar state cleanly and wire submit feedback & alerts
document.addEventListener('DOMContentLoaded', () => {
  try {
    const shouldCollapse = localStorage.getItem('ev_sidebar_collapsed') === '1' && window.innerWidth > 1120;
    document.body.classList.toggle('sidebar-collapsed', shouldCollapse);
    document.documentElement.classList.toggle('sidebar-is-collapsed', shouldCollapse);
  } catch (e) { /* ignore */ }

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      document.documentElement.classList.remove('sidebar-preload');
    });
  });

  // Subtle single-click loading indicator for opt-in auth/action forms
  document.querySelectorAll('form[data-loading-form]').forEach((form) => {
    form.addEventListener('submit', () => {
      const btn = form.querySelector('button[type="submit"]');
      if (btn && !btn.disabled) {
        btn.disabled = true;
        btn.setAttribute('aria-busy', 'true');
        const label = btn.getAttribute('data-loading-label') || 'Please wait...';
        btn.dataset.originalLabel = btn.textContent;
        btn.textContent = label;
      }
    });
  });

  const alerts = document.querySelectorAll('.alert');
  alerts.forEach((alert) => {
    setTimeout(() => {
      alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-10px)';
      setTimeout(() => alert.remove(), 400);
    }, 6000);
  });
});
