/* ═══════════════════════════════════════════════
   MISSION LOG — auth-aware learning journal
   challenge/mission-log.js
════════════════════════════════════════════════ */
(function () {
  'use strict';

  var panel = document.getElementById('ml-panel');
  if (!panel) return;

  var LEVEL    = panel.dataset.level || 'unknown';
  var HINT     = panel.dataset.hint  || '';
  var LS_KEY   = 'plc-ml-' + LEVEL;   // localStorage fallback key

  var toggle    = document.getElementById('ml-toggle');
  var body      = document.getElementById('ml-body');
  var starsEl   = document.getElementById('ml-stars');
  var skillIn   = document.getElementById('ml-skill');
  var notesIn   = document.getElementById('ml-notes');
  var saveBtn   = document.getElementById('ml-save');
  var clearBtn  = document.getElementById('ml-clear');
  var entriesEl = document.getElementById('ml-entries');
  var countEl   = document.getElementById('ml-count');

  var rating    = 0;
  var authState = null;   // null = unknown, { authenticated, email }

  /* ── sign-in prompt banner (injected once inside ml-body) ── */
  var signInBanner = null;
  function getOrCreateBanner() {
    if (signInBanner) return signInBanner;
    signInBanner = document.createElement('div');
    signInBanner.className = 'ml-signin-prompt';
    signInBanner.innerHTML =
      '<span class="ml-signin-icon" aria-hidden="true">🔒</span>' +
      '<span class="ml-signin-text">' +
        'Entries are saved to this browser only. ' +
        '<a href="/login/" class="ml-signin-link">Sign in</a> or ' +
        '<a href="/register/" class="ml-signin-link">create an account</a> ' +
        'to save your log to your record.' +
      '</span>';
    body.insertBefore(signInBanner, body.firstChild);
    return signInBanner;
  }

  /* ── localStorage helpers (guest fallback) ── */
  function lsLoad() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '[]'); }
    catch (e) { return []; }
  }
  function lsPersist(entries) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(entries)); }
    catch (e) {}
  }

  /* ── formatting ── */
  function fmtDate(val) {
    var d = (typeof val === 'number') ? new Date(val) : new Date(val + (val.indexOf('Z') === -1 ? 'Z' : ''));
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
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
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

  /* ── render a single entry element ── */
  function makeEntryEl(entryId, skill, notes, ratingVal, dateVal, isServer) {
    var el = document.createElement('article');
    el.className = 'ml-entry';
    el.dataset.entryId  = entryId;
    el.dataset.isServer = isServer ? '1' : '0';
    el.innerHTML =
      '<div class="ml-entry-top">' +
        '<span class="ml-entry-ts">' + fmtDate(dateVal) + '</span>' +
        (skill ? '<span class="ml-entry-skill">' + esc(skill) + '</span>' : '') +
        '<span class="ml-entry-stars" aria-label="Difficulty: ' + ratingVal + ' out of 5">' +
          starStr(ratingVal) +
        '</span>' +
      '</div>' +
      '<div class="ml-entry-notes">' + esc(notes) + '</div>' +
      '<button class="ml-entry-del" data-entry-id="' + esc(String(entryId)) + '" type="button" ' +
        'aria-label="Delete this log entry">✕</button>';
    return el;
  }

  /* ── count badge ── */
  function updateCount(n) {
    countEl.textContent = n + (n === 1 ? ' ENTRY' : ' ENTRIES');
  }

  /* ── SERVER render ── */
  function renderServerEntries(entries) {
    updateCount(entries.length);
    entriesEl.innerHTML = '';
    if (!entries.length) {
      entriesEl.innerHTML = '<div class="ml-empty">NO LOG ENTRIES YET — COMPLETE THE CHALLENGE AND RECORD WHAT YOU LEARNED</div>';
      return;
    }
    for (var i = entries.length - 1; i >= 0; i--) {
      var e = entries[i];
      entriesEl.appendChild(makeEntryEl(e.id, e.skill, e.notes, e.rating, e.created_at, true));
    }
  }

  /* ── GUEST render ── */
  function renderGuestEntries() {
    getOrCreateBanner();
    var entries = lsLoad();
    updateCount(entries.length);
    entriesEl.innerHTML = '';
    if (!entries.length) {
      entriesEl.innerHTML = '<div class="ml-empty">NO LOG ENTRIES YET — COMPLETE THE CHALLENGE AND RECORD WHAT YOU LEARNED</div>';
      return;
    }
    for (var i = entries.length - 1; i >= 0; i--) {
      var e = entries[i];
      entriesEl.appendChild(makeEntryEl(i, e.skill, e.notes, e.rating, e.ts, false));
    }
  }

  /* ── load and render based on auth state ── */
  function loadAndRender() {
    if (authState && authState.authenticated) {
      fetch('/api/mission-log/' + LEVEL + '/', { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : { entries: [] }; })
        .then(function (data) { renderServerEntries(data.entries || []); })
        .catch(function () { renderServerEntries([]); });
    } else {
      renderGuestEntries();
    }
  }

  /* ── check auth, then init ── */
  function initAuth(cb) {
    fetch('/api/me', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : { authenticated: false }; })
      .then(function (me) { authState = me; cb(); })
      .catch(function () { authState = { authenticated: false }; cb(); });
  }

  /* ── toggle open/close ── */
  toggle.addEventListener('click', function () {
    var isOpen = panel.classList.toggle('open');
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    body.hidden = !isOpen;
    if (isOpen) {
      if (!skillIn.value && HINT) skillIn.placeholder = HINT;
      if (authState === null) {
        initAuth(loadAndRender);
      } else {
        loadAndRender();
      }
    }
  });
  body.hidden = true;

  /* initialise count badge without opening the panel */
  initAuth(function () {
    if (authState && authState.authenticated) {
      fetch('/api/mission-log/' + LEVEL + '/', { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : { entries: [] }; })
        .then(function (data) { updateCount((data.entries || []).length); })
        .catch(function () { updateCount(0); });
    } else {
      updateCount(lsLoad().length);
    }
  });

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

    if (authState && authState.authenticated) {
      /* ── save to server ── */
      saveBtn.disabled = true;
      fetch('/api/mission-log/' + LEVEL + '/', {
        method:  'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill: skillIn.value.trim(), notes: notes, rating: rating })
      })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
        .then(function () {
          notesIn.value = '';
          skillIn.value = '';
          rating = 0;
          Array.prototype.forEach.call(starBtns, function (s) { s.classList.remove('lit'); });
          loadAndRender();
          toast('ENTRY SAVED TO YOUR ACCOUNT ✓');
        })
        .catch(function () { toast('Could not save — please try again.'); })
        .finally(function () { saveBtn.disabled = false; });
    } else {
      /* ── guest: localStorage ── */
      var entries = lsLoad();
      entries.push({ ts: Date.now(), skill: skillIn.value.trim(), rating: rating, notes: notes });
      lsPersist(entries);
      notesIn.value = '';
      skillIn.value = '';
      rating = 0;
      Array.prototype.forEach.call(starBtns, function (s) { s.classList.remove('lit'); });
      renderGuestEntries();
      toast('ENTRY LOGGED LOCALLY — sign in to save to your account ✓');
    }
  });

  /* ── delete entry ── */
  entriesEl.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('.ml-entry-del') : null;
    if (!btn) return;
    var entryId = btn.getAttribute('data-entry-id');
    var articleEl = btn.parentNode;

    if (authState && authState.authenticated) {
      fetch('/api/mission-log/' + LEVEL + '/' + entryId + '/', {
        method: 'DELETE',
        credentials: 'same-origin',
      })
        .then(function () { loadAndRender(); })
        .catch(function () { toast('Could not delete — please try again.'); });
    } else {
      var idx = parseInt(entryId, 10);
      var entries = lsLoad();
      entries.splice(idx, 1);
      lsPersist(entries);
      renderGuestEntries();
    }
  });

  /* ── clear all (guest only — server uses per-entry delete) ── */
  clearBtn.addEventListener('click', function () {
    if (authState && authState.authenticated) {
      /* hide the button for server-backed mode — no bulk delete API */
      clearBtn.style.display = 'none';
      return;
    }
    if (!lsLoad().length) return;
    if (!confirm('Clear all mission log entries for this level? This cannot be undone.')) return;
    localStorage.removeItem(LS_KEY);
    renderGuestEntries();
    toast('LOG CLEARED');
  });

}());
