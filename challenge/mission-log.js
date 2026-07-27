/* ═══════════════════════════════════════════════
   MISSION LOG — shared progress journal
   challenge/mission-log.js
════════════════════════════════════════════════ */
(function () {
  'use strict';

  var panel = document.getElementById('ml-panel');
  if (!panel) return;

  var LEVEL    = panel.dataset.level || 'unknown';
  var HINT     = panel.dataset.hint  || '';
  var SK       = 'plc-ml-' + LEVEL;

  var toggle    = document.getElementById('ml-toggle');
  var body      = document.getElementById('ml-body');
  var starsEl   = document.getElementById('ml-stars');
  var skillIn   = document.getElementById('ml-skill');
  var notesIn   = document.getElementById('ml-notes');
  var saveBtn   = document.getElementById('ml-save');
  var clearBtn  = document.getElementById('ml-clear');
  var entriesEl = document.getElementById('ml-entries');
  var countEl   = document.getElementById('ml-count');

  var rating = 0;

  /* ── storage helpers ── */
  function load() {
    try { return JSON.parse(localStorage.getItem(SK) || '[]'); }
    catch (e) { return []; }
  }
  function persist(entries) {
    try { localStorage.setItem(SK, JSON.stringify(entries)); }
    catch (e) {}
  }

  /* ── formatting ── */
  function fmtDate(ts) {
    var d = new Date(ts);
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) +
      '  ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  }
  function starStr(n) {
    var s = '';
    for (var i = 1; i <= 5; i++) { s += (i <= n ? '★' : '☆'); }
    return s;
  }
  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* ── toast ── */
  function toast(msg) {
    var t = document.getElementById('ml-toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'ml-toast';
      t.className = 'ml-toast';
      t.setAttribute('role', 'status');
      t.setAttribute('aria-live', 'polite');
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(function () { t.classList.remove('show'); }, 1800);
  }

  /* ── update badge count ── */
  function updateCount() {
    var n = load().length;
    countEl.textContent = n + (n === 1 ? ' ENTRY' : ' ENTRIES');
  }

  /* ── render entry list ── */
  function render() {
    updateCount();
    var entries = load();
    if (!entries.length) {
      entriesEl.innerHTML = '<div class="ml-empty">NO LOG ENTRIES YET — COMPLETE THE CHALLENGE AND RECORD WHAT YOU LEARNED</div>';
      return;
    }
    entriesEl.innerHTML = '';
    for (var i = entries.length - 1; i >= 0; i--) {
      var e = entries[i];
      var el = document.createElement('article');
      el.className = 'ml-entry';
      el.innerHTML =
        '<div class="ml-entry-top">' +
          '<span class="ml-entry-ts">' + fmtDate(e.ts) + '</span>' +
          (e.skill ? '<span class="ml-entry-skill">' + esc(e.skill) + '</span>' : '') +
          '<span class="ml-entry-stars" aria-label="Difficulty: ' + e.rating + ' out of 5">' +
            starStr(e.rating) +
          '</span>' +
        '</div>' +
        '<div class="ml-entry-notes">' + esc(e.notes) + '</div>' +
        '<button class="ml-entry-del" data-idx="' + i + '" type="button" ' +
          'aria-label="Delete this log entry">✕</button>';
      entriesEl.appendChild(el);
    }
  }

  /* ── toggle open/close ── */
  toggle.addEventListener('click', function () {
    var isOpen = panel.classList.toggle('open');
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    body.hidden = !isOpen;
    if (isOpen) {
      if (!skillIn.value && HINT) { skillIn.placeholder = HINT; }
      render();
    }
  });
  body.hidden = true;

  /* ── star rating ── */
  var starBtns = starsEl.querySelectorAll('.ml-star');
  Array.prototype.forEach.call(starBtns, function (btn) {
    btn.addEventListener('mouseenter', function () {
      var v = parseInt(btn.dataset.v, 10);
      Array.prototype.forEach.call(starBtns, function (s) {
        s.classList.toggle('lit', parseInt(s.dataset.v, 10) <= v);
      });
    });
    btn.addEventListener('mouseleave', function () {
      Array.prototype.forEach.call(starBtns, function (s) {
        s.classList.toggle('lit', parseInt(s.dataset.v, 10) <= rating);
      });
    });
    btn.addEventListener('click', function () {
      rating = parseInt(btn.dataset.v, 10);
      Array.prototype.forEach.call(starBtns, function (s) {
        s.classList.toggle('lit', parseInt(s.dataset.v, 10) <= rating);
      });
    });
  });

  /* ── save entry ── */
  saveBtn.addEventListener('click', function () {
    var notes = notesIn.value.trim();
    if (!notes) {
      notesIn.focus();
      notesIn.style.borderColor = 'var(--red, #ef4444)';
      setTimeout(function () { notesIn.style.borderColor = ''; }, 1400);
      return;
    }
    var entries = load();
    entries.push({
      ts:     Date.now(),
      skill:  skillIn.value.trim(),
      rating: rating,
      notes:  notes
    });
    persist(entries);
    notesIn.value = '';
    skillIn.value = '';
    rating = 0;
    Array.prototype.forEach.call(starBtns, function (s) { s.classList.remove('lit'); });
    render();
    toast('ENTRY LOGGED ✓');
  });

  /* ── delete single entry ── */
  entriesEl.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('.ml-entry-del') : null;
    if (!btn) return;
    var idx = parseInt(btn.dataset.idx, 10);
    var entries = load();
    entries.splice(idx, 1);
    persist(entries);
    render();
  });

  /* ── clear all ── */
  clearBtn.addEventListener('click', function () {
    if (!load().length) return;
    if (!confirm('Clear all mission log entries for this level? This cannot be undone.')) return;
    localStorage.removeItem(SK);
    render();
    toast('LOG CLEARED');
  });

  /* ── init badge count on page load ── */
  updateCount();

}());
