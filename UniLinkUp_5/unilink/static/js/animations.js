/* animations.js
 * Small, dependency-free interaction layer shared across every page:
 *   1. Shrinks the navbar slightly once the page is scrolled (adds
 *      .sb-navbar-scrolled, purely a CSS hook).
 *   2. Fades cards / sections up into place as they enter the viewport
 *      (elements carrying .sb-animate / .sb-animate-up, or automatically
 *      every .sb-card that opts in via [data-animate]).
 *   3. Shows a full-page loading overlay with a spinner the moment an
 *      "auth" form (login / register) is submitted, so there's visible
 *      motion while the browser waits on the server round-trip. The form
 *      still submits natively — this never blocks or delays submission,
 *      it just gives the wait a visual.
 */
(function () {
  'use strict';

  // ---- 1. Navbar shrink on scroll ----
  var navbar = document.getElementById('sbNavbar');
  if (navbar) {
    var onScroll = function () {
      navbar.classList.toggle('sb-navbar-scrolled', window.scrollY > 12);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  // ---- 2. Entrance animation on scroll into view ----
  var animated = document.querySelectorAll('.sb-card, .sb-animate, [data-animate]');
  if ('IntersectionObserver' in window && animated.length) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('sb-in-view');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    animated.forEach(function (el, idx) {
      el.classList.add('sb-pre-animate');
      el.style.transitionDelay = Math.min(idx * 40, 240) + 'ms';
      io.observe(el);
    });
  } else {
    animated.forEach(function (el) { el.classList.add('sb-in-view'); });
  }

  // ---- 3. Loading overlay on auth form submit ----
  var overlay = document.createElement('div');
  overlay.className = 'sb-loading-overlay';
  overlay.innerHTML =
    '<div class="sb-loading-box">' +
    '  <div class="sb-loading-spinner"></div>' +
    '  <div class="sb-loading-text">Just a moment...</div>' +
    '</div>';
  document.body.appendChild(overlay);

  function armLoadingOverlay(form, label) {
    form.addEventListener('submit', function (e) {
      if (form.checkValidity && !form.checkValidity()) return; // let native validation show first
      var textEl = overlay.querySelector('.sb-loading-text');
      if (textEl && label) textEl.textContent = label;
      overlay.classList.add('sb-loading-visible');
      var btn = form.querySelector('button[type="submit"]');
      if (btn) {
        btn.dataset.originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="sb-btn-spinner"></span> Please wait...';
      }
    });
  }

  document.querySelectorAll('form[data-loading]').forEach(function (form) {
    armLoadingOverlay(form, form.dataset.loading);
  });

  // Safety net: if the page is restored from bfcache (e.g. user hits Back
  // after a failed login), make sure the overlay isn't stuck visible.
  window.addEventListener('pageshow', function (evt) {
    if (evt.persisted) overlay.classList.remove('sb-loading-visible');
  });
})();
