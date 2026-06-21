(function () {
  'use strict';

  var LEVEL      = window.PLC_LEVEL || 'level1';
  var BANNER_ID  = document.getElementById('complete-banner') ? 'complete-banner' : 'done-banner';
  var startTime  = Date.now();

  /* ── Inject modal HTML ── */
  var MODAL_HTML = [
    '<div id="assess-overlay" role="dialog" aria-modal="true" aria-labelledby="assess-modal-title">',
    '  <div id="assess-modal">',
    '    <div id="assess-modal-header">',
    '      <h2 id="assess-modal-title">Manager\'s Competency Review</h2>',
    '      <button id="assess-close-x" aria-label="Close review">&times;</button>',
    '    </div>',
    '    <div id="assess-score-row">',
    '      <div id="assess-score-num" aria-label="Score">--</div>',
    '      <div id="assess-grade-badge" aria-label="Grade">-</div>',
    '      <div id="assess-score-meta">',
    '        <div id="assess-tier-label"></div>',
    '        <div id="assess-summary-line"></div>',
    '      </div>',
    '    </div>',
    '    <div id="assess-body">',
    '      <p id="assess-p1"></p>',
    '      <p id="assess-p2"></p>',
    '      <p id="assess-p3"></p>',
    '    </div>',
    '    <table id="assess-breakdown" aria-label="Score breakdown">',
    '      <thead><tr>',
    '        <th scope="col">Criterion</th>',
    '        <th scope="col">Result</th>',
    '        <th scope="col">Pts</th>',
    '      </tr></thead>',
    '      <tbody id="assess-breakdown-body"></tbody>',
    '    </table>',
    '    <div id="assess-error" role="alert">',
    '      Could not connect to the assessment server. Make sure serve.py is running.',
    '    </div>',
    '    <div id="assess-footer">',
    '      <button id="assess-close-btn">Close Review</button>',
    '    </div>',
    '  </div>',
    '</div>'
  ].join('\n');

  document.body.insertAdjacentHTML('beforeend', MODAL_HTML);

  /* ── Inject "Get Manager's Review" button into the completion banner ── */
  var banner = document.getElementById(BANNER_ID);
  if (banner) {
    var btn = document.createElement('button');
    btn.id        = 'assess-btn';
    btn.className = 'assess-btn';
    btn.innerHTML = '&#128203; Get Manager\'s Review';
    btn.setAttribute('aria-label', 'Submit performance data and receive a manager\'s competency review');
    banner.appendChild(btn);
  }

  /* ── Collect submission data from the DOM ── */
  function getPayload() {
    var milestonesDone = Array.from(document.querySelectorAll('[id^="m"]'))
      .filter(function (el) { return /^m\d+$/.test(el.id) && el.classList.contains('done'); })
      .map(function (el) { return el.id; });

    var scanEl    = document.getElementById('scan-num');
    var scanCount = scanEl ? (parseInt(scanEl.textContent, 10) || 0) : 0;
    var elapsedMs = Date.now() - startTime;

    var bonusFlags = {};
    if (LEVEL === 'level2') bonusFlags.fault_tested = milestonesDone.indexOf('m5') !== -1;
    if (LEVEL === 'level3') bonusFlags.all_fc = milestonesDone.length >= 7;
    if (LEVEL === 'level4') bonusFlags.wire_break = milestonesDone.indexOf('m7') !== -1;
    if (LEVEL === 'level5') bonusFlags.estop_mid  = milestonesDone.indexOf('m4') !== -1;
    if (LEVEL === 'level6') {
      bonusFlags.estop_abort = milestonesDone.indexOf('m5') !== -1;
      bonusFlags.autocycle   = milestonesDone.indexOf('m7') !== -1;
    }

    return {
      level:          LEVEL,
      milestones_done: milestonesDone,
      scan_count:     scanCount,
      elapsed_ms:     elapsedMs,
      bonus_flags:    bonusFlags
    };
  }

  /* ── Populate and show modal ── */
  function showModal(data) {
    var overlay = document.getElementById('assess-overlay');
    var scoreEl = document.getElementById('assess-score-num');
    var gradeEl = document.getElementById('assess-grade-badge');
    var tierEl  = document.getElementById('assess-tier-label');
    var summEl  = document.getElementById('assess-summary-line');
    var p1      = document.getElementById('assess-p1');
    var p2      = document.getElementById('assess-p2');
    var p3      = document.getElementById('assess-p3');
    var tbody   = document.getElementById('assess-breakdown-body');
    var errEl   = document.getElementById('assess-error');

    errEl.style.display = 'none';

    scoreEl.textContent = data.score + '/100';
    scoreEl.className   = 'assess-tier-' + data.tier;

    gradeEl.textContent = data.grade;
    gradeEl.className   = 'assess-grade-' + data.grade;

    tierEl.textContent  = data.tier_label;
    tierEl.className    = 'assess-tier-' + data.tier;

    summEl.textContent  = data.summary_line;
    p1.textContent      = data.paragraph_1;
    p2.textContent      = data.paragraph_2;
    p3.textContent      = data.paragraph_3;

    /* Breakdown table */
    tbody.innerHTML = '';

    /* Milestone rows */
    (data.milestone_detail || []).forEach(function (m) {
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + escHtml(m.label) + '</td>' +
        '<td>' + (m.done ? '<span class="assess-tick" aria-label="Passed">&#10003;</span>' : '<span class="assess-cross" aria-label="Not met">&#10007;</span>') + '</td>' +
        '<td class="assess-pts">' + (m.done ? m.weight : 0) + '/' + m.weight + '</td>';
      tbody.appendChild(tr);
    });

    /* Efficiency row */
    var effRow = document.createElement('tr');
    effRow.innerHTML =
      '<td>Operational Efficiency (' + escHtml(data.efficiency_label) + ')</td>' +
      '<td><span class="assess-tick">&#10003;</span></td>' +
      '<td class="assess-pts">' + data.efficiency_score + '/15</td>';
    tbody.appendChild(effRow);

    /* Bonus rows */
    (data.bonus_detail || []).forEach(function (b) {
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + escHtml(b.label) + '</td>' +
        '<td>' + (b.earned ? '<span class="assess-tick">&#10003;</span>' : '<span class="assess-cross">&#10007;</span>') + '</td>' +
        '<td class="assess-pts">' + (b.earned ? b.points : 0) + '/' + b.points + '</td>';
      tbody.appendChild(tr);
    });

    overlay.classList.add('open');
    document.getElementById('assess-close-x').focus();
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* ── Submit handler ── */
  document.addEventListener('click', function (e) {
    if (e.target && e.target.id === 'assess-btn') {
      var btn = e.target;
      btn.disabled    = true;
      btn.textContent = 'Analysing\u2026';

      fetch('/api/assess/', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(getPayload())
      })
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(function (data) {
          showModal(data);
          btn.disabled    = false;
          btn.innerHTML   = '&#128203; Get Manager\'s Review';
        })
        .catch(function () {
          document.getElementById('assess-error').style.display = 'block';
          document.getElementById('assess-overlay').classList.add('open');
          btn.disabled    = false;
          btn.innerHTML   = '&#128203; Get Manager\'s Review';
        });
    }
  });

  /* ── Close handlers ── */
  function closeModal() {
    document.getElementById('assess-overlay').classList.remove('open');
    var ab = document.getElementById('assess-btn');
    if (ab) ab.focus();
  }
  document.addEventListener('click', function (e) {
    if (e.target.id === 'assess-close-x' || e.target.id === 'assess-close-btn') closeModal();
    if (e.target.id === 'assess-overlay') closeModal();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeModal();
  });

  /* ── Trap focus inside modal ── */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Tab') return;
    var overlay = document.getElementById('assess-overlay');
    if (!overlay.classList.contains('open')) return;
    var focusable = Array.from(overlay.querySelectorAll('button, [tabindex]:not([tabindex="-1"])'));
    if (!focusable.length) return;
    var first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault(); first.focus();
    }
  });

}());
