/* chatbot.js
 * Floating "Ask UniLinkUp" assistant widget. Talks to /api/chat (see
 * chatbot.py + the /api/chat route in app.py). Pure vanilla JS, no
 * dependencies, works on every page because it's included from base.html.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'sb_chat_history_v1';
  var history = [];
  try {
    var saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) history = JSON.parse(saved);
  } catch (e) { history = []; }

  function persist() {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(-20))); } catch (e) {}
  }

  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // Turn **bold** and newlines from bot replies into simple HTML.
  function formatReply(text) {
    var safe = escapeHtml(text);
    safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    safe = safe.replace(/\n/g, '<br>');
    return safe;
  }

  function build() {
    var wrap = el('div', 'sb-chat-widget');

    var bubble = el('button', 'sb-chat-bubble', '<i class="bi bi-robot"></i>');
    bubble.setAttribute('aria-label', 'Open UniLinkUp assistant');
    bubble.type = 'button';

    var panel = el('div', 'sb-chat-panel sb-chat-hidden');
    panel.innerHTML =
      '<div class="sb-chat-header">' +
      '  <div class="sb-chat-header-title"><i class="bi bi-stars"></i> Ask UniLinkUp</div>' +
      '  <button type="button" class="sb-chat-close" aria-label="Close">&times;</button>' +
      '</div>' +
      '<div class="sb-chat-messages"></div>' +
      '<div class="sb-chat-quick"></div>' +
      '<form class="sb-chat-input-row">' +
      '  <input type="text" class="sb-chat-input" placeholder="Type your question..." autocomplete="off">' +
      '  <button type="submit" class="sb-chat-send" aria-label="Send"><i class="bi bi-send-fill"></i></button>' +
      '</form>';

    wrap.appendChild(panel);
    wrap.appendChild(bubble);
    document.body.appendChild(wrap);

    var messagesEl = panel.querySelector('.sb-chat-messages');
    var quickEl = panel.querySelector('.sb-chat-quick');
    var formEl = panel.querySelector('.sb-chat-input-row');
    var inputEl = panel.querySelector('.sb-chat-input');
    var closeEl = panel.querySelector('.sb-chat-close');

    var QUICK_PROMPTS = [
      'How is my eligibility % calculated?',
      'How do I apply to a drive?',
      "What's my progress?",
    ];
    QUICK_PROMPTS.forEach(function (q) {
      var chip = el('button', 'sb-chat-chip', escapeHtml(q));
      chip.type = 'button';
      chip.addEventListener('click', function () { send(q); });
      quickEl.appendChild(chip);
    });

    function addMessage(role, text) {
      var row = el('div', 'sb-chat-msg sb-chat-msg-' + role);
      var bubbleEl = el('div', 'sb-chat-bubble-text', role === 'bot' ? formatReply(text) : escapeHtml(text));
      row.appendChild(bubbleEl);
      messagesEl.appendChild(row);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function addTyping() {
      var row = el('div', 'sb-chat-msg sb-chat-msg-bot sb-chat-typing');
      row.innerHTML = '<div class="sb-chat-bubble-text"><span></span><span></span><span></span></div>';
      messagesEl.appendChild(row);
      messagesEl.scrollTop = messagesEl.scrollHeight;
      return row;
    }

    function send(text) {
      text = (text || inputEl.value).trim();
      if (!text) return;
      inputEl.value = '';
      addMessage('user', text);
      history.push({ role: 'user', content: text });
      persist();

      var typingRow = addTyping();

      fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: history.slice(-8) })
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          typingRow.remove();
          var reply = (data && data.reply) || "Sorry, I couldn't reach the assistant just now.";
          addMessage('bot', reply);
          history.push({ role: 'bot', content: reply });
          persist();
        })
        .catch(function () {
          typingRow.remove();
          addMessage('bot', "I couldn't reach the server just now — please try again in a moment.");
        });
    }

    formEl.addEventListener('submit', function (e) {
      e.preventDefault();
      send();
    });

    function openPanel() {
      panel.classList.remove('sb-chat-hidden');
      bubble.classList.add('sb-chat-bubble-active');
      if (messagesEl.children.length === 0) {
        addMessage('bot', "Hi! I'm the UniLinkUp assistant 👋 Ask me about eligibility %, applying to a drive, your progress, or anything else on the portal.");
      }
      inputEl.focus();
    }
    function closePanel() {
      panel.classList.add('sb-chat-hidden');
      bubble.classList.remove('sb-chat-bubble-active');
    }

    bubble.addEventListener('click', function () {
      if (panel.classList.contains('sb-chat-hidden')) openPanel(); else closePanel();
    });
    closeEl.addEventListener('click', closePanel);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
})();
