/* motion.js
 * Site-wide animation layer added in the v4 redesign. Loaded on every page.
 *   1. Page curtain: links marked [data-transition] play a wipe before
 *      navigating; the next page wipes back in.
 *   2. Scroll reveal for [data-scroll], .sb-meter and .sb-stack.
 *   3. Count-up numbers ([data-count]).
 *   4. 3D tilt on .sb-tilt / .sb-role-card (mouse only).
 * Everything respects prefers-reduced-motion.
 */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var body = document.body;
  var curtain = document.getElementById('sbPageCurtain');

  // ---- 1. Page curtain ----
  if (body.classList.contains('sb-page-enter')) {
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { body.classList.add('sb-page-entered'); });
    });
    setTimeout(function () { body.classList.remove('sb-page-enter', 'sb-page-entered'); }, 900);
  }

  function leaveTo(href) {
    try { sessionStorage.setItem('sbTransit', '1'); } catch (e) {}
    var auth = document.querySelector('.sb-auth-wrap');
    if (auth) auth.classList.add('is-leaving');
    if (curtain) curtain.classList.add('is-in');
    setTimeout(function () { window.location.href = href; }, reduce ? 0 : 460);
  }
  window.sbLeaveTo = leaveTo;

  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[data-transition]');
    if (!a) return;
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (a.target && a.target !== '_self') return;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#') return;
    e.preventDefault();
    leaveTo(a.href);
  });

  // Login | Register switch: slide the pill first, then wipe to the other page
  document.querySelectorAll('[data-auth-switch]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      if (a.classList.contains('is-current')) { e.preventDefault(); return; }
      if (e.metaKey || e.ctrlKey || e.shiftKey) return;
      e.preventDefault();
      var sw = a.parentElement;
      sw.setAttribute('data-current', a.getAttribute('data-auth-switch'));
      sw.querySelectorAll('a').forEach(function (x) { x.classList.toggle('is-current', x === a); });
      setTimeout(function () { leaveTo(a.href); }, reduce ? 0 : 280);
    });
  });

  window.addEventListener('pageshow', function (evt) {
    if (evt.persisted && curtain) curtain.classList.remove('is-in');
    var auth = document.querySelector('.sb-auth-wrap.is-leaving');
    if (auth) auth.classList.remove('is-leaving');
  });

  // ---- 2. Scroll reveal ----
  var revealables = document.querySelectorAll('[data-scroll], .sb-meter, .sb-stack, .sb-timeline-item');
  if ('IntersectionObserver' in window && !reduce) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
    revealables.forEach(function (el) { io.observe(el); });
  } else {
    revealables.forEach(function (el) { el.classList.add('is-visible'); });
  }

  // ---- 3. Count-up numbers ----
  function countUp(el) {
    var target = parseFloat(el.getAttribute('data-count')) || 0;
    var decimals = (el.getAttribute('data-count').split('.')[1] || '').length;
    var suffix = el.getAttribute('data-suffix') || '';
    if (reduce || target === 0) { el.textContent = target.toFixed(decimals) + suffix; return; }
    var start = null, dur = 1600;
    function step(ts) {
      if (!start) start = ts;
      var p = Math.min((ts - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 4);
      el.textContent = (target * eased).toFixed(decimals) + suffix;
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  var counters = document.querySelectorAll('[data-count]');
  if ('IntersectionObserver' in window) {
    var cio = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { countUp(entry.target); cio.unobserve(entry.target); }
      });
    }, { threshold: 0.4 });
    counters.forEach(function (el) { cio.observe(el); });
  } else {
    counters.forEach(countUp);
  }

  // ---- 4. Tilt ----
  if (!reduce && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    document.querySelectorAll('.sb-tilt, .sb-role-card').forEach(function (card) {
      card.addEventListener('mousemove', function (e) {
        var r = card.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width - 0.5;
        var y = (e.clientY - r.top) / r.height - 0.5;
        card.style.transform = 'perspective(800px) rotateY(' + (x * 10) + 'deg) rotateX(' + (-y * 10) + 'deg) translateY(-6px)';
      });
      card.addEventListener('mouseleave', function () {
        card.style.transform = '';
      });
    });
  }
})();
