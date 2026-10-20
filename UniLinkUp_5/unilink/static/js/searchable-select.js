/* searchable-select.js
 * Turns any <select> (typically the "College / University" dropdown, which
 * can have 40+ entries) into a type-to-filter combobox — no external
 * library, no CDN dependency. The original <select> stays in the DOM (just
 * visually tucked away) so normal form submission / `required` validation
 * keeps working exactly as before.
 *
 * Usage: <select id="college_id" ...>...</select>
 *        <script>initSearchableSelect(document.getElementById('college_id'));</script>
 */
function initSearchableSelect(selectEl, opts) {
  if (!selectEl || selectEl.dataset.sbEnhanced) return;
  selectEl.dataset.sbEnhanced = '1';
  opts = opts || {};
  var placeholder = opts.placeholder || 'Type to search...';

  var options = Array.prototype.map.call(selectEl.options, function (o) {
    return { value: o.value, label: o.textContent, selected: o.selected };
  });

  selectEl.classList.add('sb-hidden-select');

  var wrap = document.createElement('div');
  wrap.className = 'sb-searchselect';

  var input = document.createElement('input');
  input.type = 'text';
  input.className = 'form-control sb-searchselect-input';
  input.placeholder = placeholder;
  input.autocomplete = 'off';

  var current = options.find(function (o) { return o.selected && o.value; });
  if (current) input.value = current.label;

  var list = document.createElement('div');
  list.className = 'sb-searchselect-list sb-hidden';

  wrap.appendChild(input);
  wrap.appendChild(list);
  selectEl.parentNode.insertBefore(wrap, selectEl.nextSibling);

  var activeIndex = -1;
  var filtered = options;

  function render(filterText) {
    var q = (filterText || '').trim().toLowerCase();
    filtered = options.filter(function (o) {
      return !q || o.label.toLowerCase().indexOf(q) !== -1;
    });
    list.innerHTML = '';
    activeIndex = -1;

    if (filtered.length === 0) {
      var empty = document.createElement('div');
      empty.className = 'sb-searchselect-empty';
      empty.textContent = 'No matches — you can still type your own.';
      list.appendChild(empty);
      return;
    }

    filtered.slice(0, 100).forEach(function (o, idx) {
      var item = document.createElement('div');
      item.className = 'sb-searchselect-item';
      item.textContent = o.label;
      item.dataset.value = o.value;
      item.addEventListener('mousedown', function (e) {
        e.preventDefault();
        choose(o);
      });
      list.appendChild(item);
    });
  }

  function choose(o) {
    selectEl.value = o.value;
    input.value = o.value ? o.label : '';
    selectEl.dispatchEvent(new Event('change', { bubbles: true }));
    close();
  }

  function open() {
    render(input.value);
    list.classList.remove('sb-hidden');
  }
  function close() {
    list.classList.add('sb-hidden');
  }

  input.addEventListener('focus', open);
  input.addEventListener('input', function () {
    if (selectEl.value && input.value !== (options.find(function (o) { return o.value === selectEl.value; }) || {}).label) {
      selectEl.value = '';
      selectEl.dispatchEvent(new Event('change', { bubbles: true }));
    }
    open();
  });

  input.addEventListener('keydown', function (e) {
    var items = list.querySelectorAll('.sb-searchselect-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
      updateActive(items);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      updateActive(items);
    } else if (e.key === 'Enter') {
      if (activeIndex >= 0 && filtered[activeIndex]) {
        e.preventDefault();
        choose(filtered[activeIndex]);
      }
    } else if (e.key === 'Escape') {
      close();
    }
  });

  function updateActive(items) {
    items.forEach(function (el, idx) {
      el.classList.toggle('sb-searchselect-active', idx === activeIndex);
    });
    if (items[activeIndex]) items[activeIndex].scrollIntoView({ block: 'nearest' });
  }

  document.addEventListener('click', function (e) {
    if (!wrap.contains(e.target)) close();
  });
}

// Auto-enhance every <select data-searchable> on the page.
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('select[data-searchable]').forEach(function (sel) {
    initSearchableSelect(sel);
  });
});
