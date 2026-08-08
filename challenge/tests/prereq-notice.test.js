/**
 * prereq-notice.test.js
 * Unit tests for challenge/prereq-notice.js dismiss behaviour.
 *
 * Tests:
 *  1. Dismiss button hides the notice immediately.
 *  2. After dismissal the localStorage key is set for the exact level.
 *  3. Re-running the script on the same level (localStorage key present) skips
 *     all fetch calls and never injects the notice.
 *  4. The dismissal key for one level does NOT prevent the notice from showing
 *     on a different level (different key).
 *
 * Environment: jest-environment-jsdom (configured in package.json).
 */

'use strict';

const fs   = require('fs');
const path = require('path');

const SCRIPT_SRC = fs.readFileSync(
  path.resolve(__dirname, '..', 'prereq-notice.js'),
  'utf8'
);

/* ── helpers ─────────────────────────────────────────────────────────────── */

/**
 * Run the IIFE in the current jsdom window context for the given level key.
 * Sets window.PLC_LEVEL before evaluating so the IIFE picks it up.
 */
function runScript(levelKey) {
  window.PLC_LEVEL = levelKey;
  // eslint-disable-next-line no-eval
  eval(SCRIPT_SRC);
}

/**
 * Build a minimal DOM fixture: a single #prereq-notice-wrap div.
 */
function buildDom() {
  document.body.innerHTML = '<div id="prereq-notice-wrap"></div>';
}

/**
 * Return a jest mock for fetch that simulates an unauthenticated visitor
 * with no previous results, so the notice will be injected.
 *
 * Call order driven by prereq-notice.js:
 *   1. GET /api/me          → { authenticated: false }
 *   2. GET /api/results     → 401  (triggers injectNotice for unauth path)
 */
function makeFetchUnauthNoResults() {
  return jest.fn().mockImplementation((url) => {
    if (url === '/api/me') {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ authenticated: false }),
      });
    }
    if (url === '/api/results') {
      return Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve(null) });
    }
    return Promise.reject(new Error('Unexpected fetch: ' + url));
  });
}

/**
 * Flush all pending micro-tasks / promise chains so the async fetch chain
 * inside prereq-notice.js completes before we make assertions.
 */
async function flushPromises() {
  // Resolve the fetch chain: /api/me → /api/results (2 async hops each)
  for (let i = 0; i < 10; i++) {
    await Promise.resolve();
  }
}

/* ── tests ───────────────────────────────────────────────────────────────── */

beforeEach(() => {
  // Reset DOM and localStorage before every test.
  document.body.innerHTML = '';
  localStorage.clear();
  jest.restoreAllMocks();
});

// ── Test 1: clicking dismiss hides the notice ─────────────────────────────

test('dismiss button hides the prereq notice immediately', async () => {
  buildDom();
  global.fetch = makeFetchUnauthNoResults();

  runScript('level3');
  await flushPromises();

  const notice = document.getElementById('prereq-notice');
  expect(notice).not.toBeNull();                        // notice was injected

  const btn = document.getElementById('prereq-notice-dismiss');
  expect(btn).not.toBeNull();

  btn.click();

  const wrap = document.getElementById('prereq-notice-wrap');
  expect(wrap.style.display).toBe('none');              // wrap is hidden
});

// ── Test 2: localStorage key is set after dismiss ─────────────────────────

test('dismissing sets the correct localStorage key for the level', async () => {
  buildDom();
  global.fetch = makeFetchUnauthNoResults();

  runScript('level3');
  await flushPromises();

  expect(localStorage.getItem('plec-prereq-dismissed-level3')).toBeNull(); // not yet

  document.getElementById('prereq-notice-dismiss').click();

  expect(localStorage.getItem('plec-prereq-dismissed-level3')).toBe('true');
});

// ── Test 3: notice stays hidden on re-visit to the same level ────────────

test('notice does not reappear when the localStorage key is already set', async () => {
  // Pre-seed the key as if the user already dismissed on a previous visit.
  localStorage.setItem('plec-prereq-dismissed-level3', 'true');

  buildDom();
  const fetchSpy = jest.fn();
  global.fetch = fetchSpy;  // should never be called

  runScript('level3');
  await flushPromises();

  // fetch must not have been called (fast-path return)
  expect(fetchSpy).not.toHaveBeenCalled();
  // notice must not have been injected
  expect(document.getElementById('prereq-notice')).toBeNull();
});

// ── Test 4: dismissal key for one level does not suppress a different level

test('notice reappears on a different level despite same-level dismissal', async () => {
  // level3 is dismissed, but now we visit level4 — different key.
  localStorage.setItem('plec-prereq-dismissed-level3', 'true');

  buildDom();
  global.fetch = makeFetchUnauthNoResults();

  runScript('level4');
  await flushPromises();

  // The level4 key is absent so the notice SHOULD appear.
  expect(document.getElementById('prereq-notice')).not.toBeNull();
  // And the level4 dismiss key is not yet set.
  expect(localStorage.getItem('plec-prereq-dismissed-level4')).toBeNull();
});

// ── Test 5: unauthenticated — /api/results includes prev level → no notice ─

test('notice is not shown to an unauthenticated visitor who already has a result for the previous level', async () => {
  buildDom();

  // /api/me → not authenticated; /api/results → 200 with a result for level2
  global.fetch = jest.fn().mockImplementation((url) => {
    if (url === '/api/me') {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ authenticated: false }),
      });
    }
    if (url === '/api/results') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ results: [{ level_key: 'level2' }] }),
      });
    }
    return Promise.reject(new Error('Unexpected fetch: ' + url));
  });

  runScript('level3');   // prevKey === 'level2'
  await flushPromises();

  // hasPrev is true → notice must NOT be injected
  expect(document.getElementById('prereq-notice')).toBeNull();
});

// ── Test 7: Level 1 — early exit, fetch never called, no notice injected ──

test('Level 1 never calls fetch and never injects a prereq notice', async () => {
  buildDom();
  const fetchSpy = jest.fn();
  global.fetch = fetchSpy;

  runScript('level1');
  await flushPromises();

  // The levelNum <= 1 guard must fire before any network call.
  expect(fetchSpy).not.toHaveBeenCalled();
  // No notice element must be present.
  expect(document.getElementById('prereq-notice')).toBeNull();
  // The wrap must remain untouched (not hidden, not populated).
  const wrap = document.getElementById('prereq-notice-wrap');
  expect(wrap).not.toBeNull();
  expect(wrap.innerHTML).toBe('');
});

// ── Test 8: invalid / missing PLC_LEVEL — early exit, fetch never called ──

test('missing PLC_LEVEL never calls fetch and never injects a prereq notice', async () => {
  buildDom();
  const fetchSpy = jest.fn();
  global.fetch = fetchSpy;

  // Simulate a page where PLC_LEVEL was not set.
  runScript('');
  await flushPromises();

  expect(fetchSpy).not.toHaveBeenCalled();
  expect(document.getElementById('prereq-notice')).toBeNull();
});

test('invalid PLC_LEVEL format never calls fetch and never injects a prereq notice', async () => {
  buildDom();
  const fetchSpy = jest.fn();
  global.fetch = fetchSpy;

  // Simulate a bogus key that does not match /^level(\d+)$/.
  runScript('levelX');
  await flushPromises();

  expect(fetchSpy).not.toHaveBeenCalled();
  expect(document.getElementById('prereq-notice')).toBeNull();
});

// ── Test 6: authenticated — /api/results includes prev level → no notice ──

test('notice is not shown to an authenticated learner who already has a result for the previous level', async () => {
  buildDom();

  // /api/me → authenticated; /api/prereq-dismissals/ → not dismissed;
  // /api/results → 200 with a result for level2
  global.fetch = jest.fn().mockImplementation((url) => {
    if (url === '/api/me') {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ authenticated: true }),
      });
    }
    if (url === '/api/prereq-dismissals/') {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ dismissed: [] }),
      });
    }
    if (url === '/api/results') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ results: [{ level_key: 'level2' }] }),
      });
    }
    return Promise.reject(new Error('Unexpected fetch: ' + url));
  });

  runScript('level3');   // prevKey === 'level2'
  await flushPromises();

  // hasPrev is true → notice must NOT be injected
  expect(document.getElementById('prereq-notice')).toBeNull();
});
