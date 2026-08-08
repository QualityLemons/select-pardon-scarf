/**
 * prereq-notice.js
 * Injects a non-blocking prerequisite recommendation banner on level pages
 * (Level 2–6) when the learner has not yet submitted a result for the
 * immediately preceding level.
 *
 * Expects:
 *   window.PLC_LEVEL  — already set by each level template (e.g. 'level3')
 *   #prereq-notice-wrap — an empty <div> injected just before .main/.workspace
 *
 * Dismissal persistence:
 *   - Authenticated users: stored server-side via POST /api/prereq-dismissals/
 *     so the dismissal persists across browsers and devices.
 *   - Unauthenticated users: falls back to localStorage (same behaviour as before).
 */
(function () {
  'use strict';

  var levelKey = window.PLC_LEVEL || '';
  var m = levelKey.match(/^level(\d+)$/);
  if (!m) return;

  var levelNum = parseInt(m[1], 10);
  if (levelNum <= 1) return;   // Level 1 has no prerequisite

  var prevNum = levelNum - 1;
  var prevKey = 'level' + prevNum;

  var localDismissKey = 'plec-prereq-dismissed-' + levelKey;

  /* ── dismissal helpers ── */

  function markDismissedLocally() {
    try { localStorage.setItem(localDismissKey, 'true'); } catch (e) {}
  }

  function isDismissedLocally() {
    try { return localStorage.getItem(localDismissKey) === 'true'; } catch (e) { return false; }
  }

  function markDismissedServerSide() {
    fetch('/api/prereq-dismissals/', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
      body: JSON.stringify({ level_key: levelKey }),
    }).catch(function () { /* fire-and-forget; localStorage already set */ });
  }

  function getCsrfToken() {
    var name = 'csrftoken';
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.indexOf(name + '=') === 0) {
        return decodeURIComponent(c.slice(name.length + 1));
      }
    }
    return '';
  }

  /* ── notice UI ── */

  function hideWrap() {
    var w = document.getElementById('prereq-notice-wrap');
    if (w) w.style.display = 'none';
  }

  function dismissNotice(isAuthenticated) {
    markDismissedLocally();
    if (isAuthenticated) markDismissedServerSide();
    hideWrap();
  }

  function injectNotice(wrap, isAuthenticated) {
    wrap.innerHTML =
      '<div id="prereq-notice" role="status" ' +
           'style="display:flex;align-items:center;gap:10px;' +
                  'background:rgba(245,158,11,.07);' +
                  'border-top:1px solid rgba(245,158,11,.2);' +
                  'border-bottom:1px solid rgba(245,158,11,.2);' +
                  'border-left:3px solid #f59e0b;' +
                  'padding:9px 16px;font-size:12px;color:#fbbf24;' +
                  'line-height:1.5;">' +
        '<span aria-hidden="true" style="font-size:15px;flex-shrink:0;">&#8592;</span>' +
        '<span>' +
          '<strong>Recommended:</strong> complete ' +
          '<a href="/challenge/level' + prevNum + '/" ' +
             'style="color:#f59e0b;text-decoration:underline;font-weight:700;">' +
             'Level ' + prevNum + '</a>' +
          ' before this one &mdash; this challenge builds directly on Level ' +
          prevNum + ' concepts.' +
        '</span>' +
        '<button ' +
          'id="prereq-notice-dismiss" ' +
          'aria-label="Dismiss prerequisite recommendation" ' +
          'title="Dismiss" ' +
          'style="margin-left:auto;background:none;border:none;color:#92400e;' +
                 'cursor:pointer;font-size:16px;padding:0 4px;line-height:1;' +
                 'flex-shrink:0;min-height:auto;">' +
          '&#10005;' +
        '</button>' +
      '</div>';
    var btn = document.getElementById('prereq-notice-dismiss');
    if (btn) btn.addEventListener('click', function () { dismissNotice(isAuthenticated); });
  }

  /* ── main logic ── */

  var wrap = document.getElementById('prereq-notice-wrap');
  if (!wrap) return;

  /* Fast path: already dismissed locally — skip all network calls */
  if (isDismissedLocally()) return;

  /* Step 1: check auth state; the /api/me response also tells us if the
     user is authenticated so we can decide which dismissal store to use. */
  fetch('/api/me', { credentials: 'same-origin' })
    .then(function (r) { return r.ok ? r.json() : { authenticated: false }; })
    .catch(function () { return { authenticated: false }; })
    .then(function (me) {
      var isAuthenticated = me && me.authenticated;

      if (!isAuthenticated) {
        /* Unauthenticated — use localStorage only, then check results */
        fetch('/api/results', { credentials: 'same-origin' })
          .then(function (r) {
            if (r.status === 401) { injectNotice(wrap, false); return null; }
            if (!r.ok) return null;
            return r.json();
          })
          .then(function (data) {
            if (!data) return;
            var hasPrev = (data.results || []).some(function (r) {
              return r.level_key === prevKey;
            });
            if (!hasPrev) injectNotice(wrap, false);
          })
          .catch(function () { injectNotice(wrap, false); });
        return;
      }

      /* Authenticated — check server-side dismissals first, then results */
      fetch('/api/prereq-dismissals/', { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : { dismissed: [] }; })
        .catch(function () { return { dismissed: [] }; })
        .then(function (d) {
          var dismissed = d.dismissed || [];
          if (dismissed.indexOf(levelKey) !== -1) {
            /* Also sync localStorage so the fast path fires next time */
            markDismissedLocally();
            return;
          }

          /* Not dismissed server-side — check results */
          fetch('/api/results', { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : { results: [] }; })
            .catch(function () { return { results: [] }; })
            .then(function (data) {
              var hasPrev = (data.results || []).some(function (r) {
                return r.level_key === prevKey;
              });
              if (!hasPrev) injectNotice(wrap, true);
            });
        });
    });
}());
