/* landing.js — only loaded on the home page.
 *   1. Intro splash (once per browser session)
 *   2. "Live network" canvas behind the hero
 *   3. Typed rotating word (Students / Faculty / Colleges / Companies)
 *   4. "What is UniLinkUp?" slideshow: autoplay, arrows, dots, keys, swipe
 *   5. How-it-works timeline line that fills as you scroll
 */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var body = document.body;

  // ---- 1. Intro splash ----
  var pre = document.getElementById('sbPreloader');
  var seen = false;
  try { seen = sessionStorage.getItem('sbIntroSeen') === '1'; } catch (e) {}
  if (pre) {
    if (seen || reduce || body.classList.contains('sb-page-enter')) {
      pre.classList.add('is-gone');
    } else {
      body.classList.add('sb-preloading');
      body.style.overflow = 'hidden';
      setTimeout(function () {
        pre.classList.add('is-done');
        body.classList.remove('sb-preloading');
        body.style.overflow = '';
      }, 2000);
      setTimeout(function () { pre.classList.add('is-gone'); }, 3100);
      try { sessionStorage.setItem('sbIntroSeen', '1'); } catch (e) {}
    }
  }

  // ---- 2. Network canvas ----
  var canvas = document.getElementById('sbNetCanvas');
  if (canvas && canvas.getContext && !reduce) {
    var ctx = canvas.getContext('2d');
    var hero = canvas.parentElement;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var W = 0, H = 0, nodes = [], mouse = { x: -9999, y: -9999 }, running = true;
    var colors = ['rgba(111,224,196,', 'rgba(232,130,60,', 'rgba(255,255,255,'];

    function resize() {
      W = hero.clientWidth; H = hero.clientHeight;
      canvas.width = W * dpr; canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var count = Math.max(28, Math.min(90, Math.round(W * H / 16000)));
      nodes = [];
      for (var i = 0; i < count; i++) {
        nodes.push({
          x: Math.random() * W, y: Math.random() * H,
          vx: (Math.random() - 0.5) * 0.45, vy: (Math.random() - 0.5) * 0.45,
          r: Math.random() * 2 + 1, c: colors[i % 7 === 0 ? 1 : (i % 5 === 0 ? 2 : 0)]
        });
      }
    }
    function frame() {
      if (!running) return;
      ctx.clearRect(0, 0, W, H);
      var maxD = 130;
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        var dxm = mouse.x - n.x, dym = mouse.y - n.y, dm = Math.sqrt(dxm * dxm + dym * dym);
        if (dm < 180) { n.vx += dxm * 0.00006; n.vy += dym * 0.00006; }
        n.x += n.vx; n.y += n.vy;
        if (n.x < 0 || n.x > W) n.vx *= -1;
        if (n.y < 0 || n.y > H) n.vy *= -1;
        n.vx *= 0.999; n.vy *= 0.999;
        for (var j = i + 1; j < nodes.length; j++) {
          var m = nodes[j], dx = n.x - m.x, dy = n.y - m.y, d = dx * dx + dy * dy;
          if (d < maxD * maxD) {
            ctx.strokeStyle = 'rgba(111,224,196,' + (0.22 * (1 - Math.sqrt(d) / maxD)) + ')';
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(n.x, n.y); ctx.lineTo(m.x, m.y); ctx.stroke();
          }
        }
        if (dm < 160) {
          ctx.strokeStyle = 'rgba(232,130,60,' + (0.35 * (1 - dm / 160)) + ')';
          ctx.beginPath(); ctx.moveTo(n.x, n.y); ctx.lineTo(mouse.x, mouse.y); ctx.stroke();
        }
        ctx.fillStyle = n.c + '0.85)';
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill();
      }
      requestAnimationFrame(frame);
    }
    resize();
    window.addEventListener('resize', function () { clearTimeout(resize._t); resize._t = setTimeout(resize, 150); });
    hero.addEventListener('mousemove', function (e) {
      var r = hero.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top;
    });
    hero.addEventListener('mouseleave', function () { mouse.x = mouse.y = -9999; });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (en) {
        var vis = en[0].isIntersecting;
        if (vis && !running) { running = true; requestAnimationFrame(frame); }
        running = vis;
      }).observe(hero);
    }
    requestAnimationFrame(frame);
  }

  // ---- 3. Typed word ----
  var typed = document.querySelector('.sb-typed');
  if (typed && !reduce) {
    var words = (typed.getAttribute('data-words') || '').split('|');
    var wi = 0, ci = words[0].length, deleting = true;
    function tick() {
      var w = words[wi];
      if (deleting) {
        ci--;
        typed.textContent = w.slice(0, ci);
        if (ci <= 0) { deleting = false; wi = (wi + 1) % words.length; }
        setTimeout(tick, 55);
      } else {
        w = words[wi]; ci++;
        typed.textContent = w.slice(0, ci);
        if (ci >= w.length) { deleting = true; setTimeout(tick, 1800); return; }
        setTimeout(tick, 95);
      }
    }
    setTimeout(tick, 3200);
  }

  // ---- 4. Slideshow ----
  var show = document.getElementById('sbShow');
  if (show) {
    var slides = show.querySelectorAll('.sb-slide');
    var dots = show.querySelectorAll('.sb-show-dot');
    var DURATION = 6000;
    show.style.setProperty('--sb-show-ms', DURATION + 'ms');
    var current = 0, timer = null, remaining = DURATION, startedAt = 0, paused = false;

    function go(i) {
      i = (i + slides.length) % slides.length;
      slides[current].classList.remove('is-active');
      // restart CSS animations on the incoming slide
      void slides[i].offsetWidth;
      slides[i].classList.add('is-active');
      dots.forEach(function (d, k) {
        d.classList.toggle('is-active', k === i);
        d.classList.toggle('is-done', k < i);
        var bar = d.querySelector('span');
        if (bar) { bar.style.animation = 'none'; void bar.offsetWidth; bar.style.animation = ''; }
      });
      current = i;
      remaining = DURATION;
      schedule();
    }
    function schedule() {
      clearTimeout(timer);
      if (paused || reduce) return;
      startedAt = Date.now();
      timer = setTimeout(function () { go(current + 1); }, remaining);
    }
    function pause() {
      if (paused) return;
      paused = true; show.classList.add('is-paused');
      clearTimeout(timer);
      remaining = Math.max(400, remaining - (Date.now() - startedAt));
    }
    function resume() {
      if (!paused) return;
      paused = false; show.classList.remove('is-paused');
      schedule();
    }
    show.querySelectorAll('.sb-show-arrow').forEach(function (b) {
      b.addEventListener('click', function () { go(current + parseInt(b.getAttribute('data-dir'), 10)); });
    });
    dots.forEach(function (d) {
      d.addEventListener('click', function () { go(parseInt(d.getAttribute('data-go'), 10)); });
    });
    show.addEventListener('mouseenter', pause);
    show.addEventListener('mouseleave', resume);
    show.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight') go(current + 1);
      if (e.key === 'ArrowLeft') go(current - 1);
    });
    var tx = null;
    show.addEventListener('touchstart', function (e) { tx = e.touches[0].clientX; }, { passive: true });
    show.addEventListener('touchend', function (e) {
      if (tx === null) return;
      var dx = e.changedTouches[0].clientX - tx;
      if (Math.abs(dx) > 45) go(current + (dx < 0 ? 1 : -1));
      tx = null;
    });
    document.addEventListener('visibilitychange', function () { document.hidden ? pause() : resume(); });

    // Wait for the intro splash before starting the clock
    var delay = (pre && !pre.classList.contains('is-gone')) ? 2000 : 0;
    setTimeout(function () {
      dots[0] && dots[0].querySelector('span') && (function (s) { s.style.animation = 'none'; void s.offsetWidth; s.style.animation = ''; })(dots[0].querySelector('span'));
      schedule();
    }, delay);
  }

  // ---- 5. Timeline progress ----
  var tl = document.getElementById('sbTimeline');
  if (tl) {
    var line = tl.querySelector('.sb-timeline-line span');
    var onScroll = function () {
      var r = tl.getBoundingClientRect();
      var vh = window.innerHeight;
      var p = (vh * 0.7 - r.top) / r.height;
      p = Math.max(0, Math.min(1, p));
      line.style.setProperty('--progress', (p * 100).toFixed(1) + '%');
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }
})();
