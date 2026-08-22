/**
 * progress-bar.test.js
 * Unit tests for the updateProgressStat / #intel-prog-fill width logic
 * defined inside templates/challenge/index.html.
 *
 * Tests:
 *  1. 0 results  → bar at 0 %
 *  2. 1 result   → bar at 16.7 % (1/6 × 100, rounded to 1 dp)
 *  3. 3 results  → bar at 50 %
 *  4. 6 results  → bar at 100 %
 *  5. Duplicate level_key entries are deduplicated before the percentage
 *     is calculated (same level attempted multiple times counts once).
 *  6. #intel-progress-val text content reflects the distinct-level count.
 *  7. #intel-progress-stat is made visible after an update.
 *  8. The aria-label on #intel-progress-stat reflects the correct count.
 *
 * Environment: jest-environment-jsdom (configured in package.json).
 */

'use strict';

const fs   = require('fs');
const path = require('path');

/* ── Extract updateProgressStat from the template ───────────────────────── */

const html = fs.readFileSync(
  path.resolve(__dirname, '..', '..', 'templates', 'challenge', 'index.html'),
  'utf8'
);

const MARKER = 'function updateProgressStat(results)';
const startIdx = html.indexOf(MARKER);
if (startIdx === -1) {
  throw new Error(
    'updateProgressStat not found in templates/challenge/index.html – ' +
    'update the extraction logic if the function was renamed or moved.'
  );
}

/* Walk forward counting braces to locate the function's closing } */
let depth = 0;
let pos   = startIdx;
let opened = false;
while (pos < html.length) {
  if (html[pos] === '{') { depth++;  opened = true; }
  if (html[pos] === '}') { depth--; }
  pos++;
  if (opened && depth === 0) break;
}

const FN_SRC = html.slice(startIdx, pos); // e.g. "function updateProgressStat(results) { … }"

/* ── Helpers ─────────────────────────────────────────────────────────────── */

/**
 * Evaluate FN_SRC in the current jsdom window scope and return the function.
 * We wrap it so it's accessible without polluting the global forever.
 */
// eslint-disable-next-line no-new-func
const getUpdateFn = () => new Function(`${FN_SRC}; return updateProgressStat;`)();

/**
 * Build the minimal DOM that updateProgressStat references.
 */
function buildDom() {
  document.body.innerHTML = `
    <div id="intel-grid">
      <div id="intel-progress-stat" style="display:none;">
        <span id="intel-progress-val">0</span>
        <div class="intel-prog-track">
          <div class="intel-prog-fill" id="intel-prog-fill" style="width:0%;"></div>
        </div>
      </div>
    </div>
  `;
}

/**
 * Construct a results array with the given level_key strings.
 * Duplicates are intentionally supported to verify deduplication.
 */
function makeResults(...levelKeys) {
  return levelKeys.map(k => ({ level_key: k }));
}

/**
 * Call updateProgressStat with the given results array, flush the
 * requestAnimationFrame callback, and return the #intel-prog-fill width.
 */
function runUpdate(results) {
  getUpdateFn()(results);
  // Flush the rAF callback that sets style.width
  window.__rAFCallbacks.forEach(cb => cb());
  window.__rAFCallbacks = [];
  return document.getElementById('intel-prog-fill').style.width;
}

/* ── Setup / teardown ────────────────────────────────────────────────────── */

beforeEach(() => {
  // Replace requestAnimationFrame with a synchronous-flush stub so tests
  // don't depend on the browser's rendering pipeline.
  window.__rAFCallbacks = [];
  window.requestAnimationFrame = cb => window.__rAFCallbacks.push(cb);

  buildDom();
});

afterEach(() => {
  document.body.innerHTML = '';
  delete window.__rAFCallbacks;
  delete window.requestAnimationFrame;
});

/* ── Tests ───────────────────────────────────────────────────────────────── */

// 1. Empty results ──────────────────────────────────────────────────────────

test('progress bar stays at 0% when no results are returned', () => {
  const width = runUpdate([]);
  expect(width).toBe('0%');
});

// 2. One level completed ────────────────────────────────────────────────────

test('progress bar shows 16.7% after 1 of 6 levels is completed', () => {
  const width = runUpdate(makeResults('level1'));
  expect(width).toBe('16.7%');
});

// 3. Three levels completed ────────────────────────────────────────────────

test('progress bar shows 50% after 3 of 6 levels are completed', () => {
  const width = runUpdate(makeResults('level1', 'level2', 'level3'));
  expect(width).toBe('50%');
});

// 4. All six levels completed ──────────────────────────────────────────────

test('progress bar reaches 100% when all 6 levels are completed', () => {
  const width = runUpdate(
    makeResults('level1', 'level2', 'level3', 'level4', 'level5', 'level6')
  );
  expect(width).toBe('100%');
});

// 5. Duplicate entries are deduplicated ────────────────────────────────────

test('duplicate level_key entries count as one distinct level', () => {
  // level1 appears three times (e.g. the learner retook it) – still counts as 1/6
  const width = runUpdate(makeResults('level1', 'level1', 'level1'));
  expect(width).toBe('16.7%');
});

test('multiple duplicates across different levels deduplicate correctly', () => {
  // level1 × 2, level2 × 2 → 2 distinct → 2/6 ≈ 33.3 %
  const width = runUpdate(makeResults('level1', 'level1', 'level2', 'level2'));
  expect(width).toBe('33.3%');
});

// 6. #intel-progress-val reflects the distinct count ──────────────────────

test('#intel-progress-val displays the correct distinct-level count', () => {
  runUpdate(makeResults('level1', 'level3', 'level5'));
  const val = document.getElementById('intel-progress-val').textContent;
  expect(val).toBe('3');
});

// 7. #intel-progress-stat becomes visible ────────────────────────────────

test('#intel-progress-stat is made visible after the first update', () => {
  runUpdate(makeResults('level1'));
  const stat = document.getElementById('intel-progress-stat');
  expect(stat.style.display).not.toBe('none');
});

test('#intel-progress-stat is made visible even when result count is 0', () => {
  runUpdate([]);
  const stat = document.getElementById('intel-progress-stat');
  expect(stat.style.display).not.toBe('none');
});

// 8. aria-label reflects the count ────────────────────────────────────────

test('aria-label on #intel-progress-stat reflects the distinct level count', () => {
  runUpdate(makeResults('level1', 'level2'));
  const stat = document.getElementById('intel-progress-stat');
  expect(stat.getAttribute('aria-label')).toBe('2 of 6 levels attempted');
});

// 9. Bar resets to 0% after all results are deleted ───────────────────────

test('progress bar resets to 0% after the last result is deleted', () => {
  // Simulate a learner who had one completed level (16.7%)…
  runUpdate(makeResults('level1'));
  // …then deletes it; the next API response is an empty array
  const width = runUpdate([]);
  expect(width).toBe('0%');
});

// 10. Partial delete: 3 → 2 levels (50% → 33.3%) ─────────────────────────

test('progress bar drops from 50% to 33.3% when one of three completed levels is deleted', () => {
  // Learner has three levels completed → 50%
  runUpdate(makeResults('level1', 'level2', 'level3'));
  // Learner deletes one result; now only two distinct levels remain
  const width = runUpdate(makeResults('level1', 'level2'));
  expect(width).toBe('33.3%');
});
