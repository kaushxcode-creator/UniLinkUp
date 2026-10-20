/* notifications.js
 * Drives the bell icon in the navbar for students, college staff, and faculty.
 * Students: bell = notifications their college has sent them (manual
 * messages + drive reminders); opening the dropdown marks them read.
 * College staff: bell = open Help Desk queries raised by their students;
 * opening the dropdown just lets them jump to the Help Desk, no server
 * write happens (resolving a query is a deliberate action on that page).
 * Faculty: bell = their own upcoming 1-on-1 mentoring classes.
 *
 * Polls /api/notifications/summary every 45s so a badge count updates
 * without needing a page reload.
 */
(function () {
  'use strict';

  var toggle = document.getElementById('sbBellToggle');
  if (!toggle) return; // not logged in / no bell on this page

  var badge = document.getElementById('sbBellBadge');
  var menu = document.getElementById('sbBellMenu');
  var role = toggle.dataset.role;
  var opened = false;

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
  }

  function timeAgo(iso) {
    if (!iso) return '';
    var then = new Date(iso.replace(' ', 'T') + 'Z');
    if (isNaN(then.getTime())) return iso.slice(0, 16);
    var mins = Math.round((Date.now() - then.getTime()) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + 'm ago';
    var hrs = Math.round(mins / 60);
    if (hrs < 24) return hrs + 'h ago';
    return Math.round(hrs / 24) + 'd ago';
  }

  function render(data) {
    var count = data.count || 0;
    if (count > 0) {
      badge.hidden = false;
      badge.textContent = count > 9 ? '9+' : String(count);
    } else {
      badge.hidden = true;
    }

    var items = data.items || [];
    if (!items.length) {
      menu.innerHTML = '<li class="sb-bell-empty text-muted small px-3 py-2">No notifications yet.</li>';
      return;
    }

    var html = items.map(function (item) {
      return (
        '<li class="sb-bell-item-row' + (item.unread ? ' sb-bell-unread' : '') + '">' +
        '  <div class="sb-bell-item-title">' + escapeHtml(item.title) + '</div>' +
        '  <div class="sb-bell-item-msg">' + escapeHtml(item.message) + '</div>' +
        '  <div class="sb-bell-item-time">' + timeAgo(item.created_at) + '</div>' +
        '</li>'
      );
    }).join('<li><hr class="dropdown-divider my-1"></li>');

    if (role === 'employee') {
      html += '<li><hr class="dropdown-divider my-1"></li>' +
              '<li><a class="dropdown-item small text-center fw-semibold" href="/college/helpdesk">Open Help Desk &rarr;</a></li>';
    }
    if (role === 'faculty') {
      html += '<li><hr class="dropdown-divider my-1"></li>' +
              '<li><a class="dropdown-item small text-center fw-semibold" href="/faculty/home">View All Classes &rarr;</a></li>';
    }

    menu.innerHTML = html;
  }

  function refresh() {
    fetch('/api/notifications/summary', { headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { return r.ok ? r.json() : { count: 0, items: [] }; })
      .then(render)
      .catch(function () { /* fail silently — bell just stays as-is */ });
  }

  refresh();
  setInterval(refresh, 45000);

  if (role === 'student') {
    toggle.addEventListener('shown.bs.dropdown', function () {
      if (opened) return;
      opened = true;
      fetch('/api/notifications/mark_read', { method: 'POST' })
        .then(function () {
          badge.hidden = true;
          badge.textContent = '0';
        })
        .catch(function () {});
    });
    // Reset so the next batch of new notifications gets marked read again too.
    toggle.addEventListener('hidden.bs.dropdown', function () { opened = false; });
  }
})();
