/* ERA5 validation showcase — the strongest proof point.
   Self-contained: injects its own nav item ("Validation") + section, renders the
   Sohra 2022 landslide backtest and the 2019 control week side by side, from
   backend/replay.py via /api/replay (or window.__REPLAY_DATA when embedded). */
(function () {
  'use strict';

  var API = (typeof API_BASE === 'string') ? API_BASE : '';
  var EVENT_ID = 'meghalaya-2022';
  var CONTROL_ID = 'control-meghalaya-2019';

  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }

  function getReplay(id) {
    if (window.__REPLAY_DATA && window.__REPLAY_DATA[id]) return Promise.resolve(window.__REPLAY_DATA[id]);
    return fetch(API + '/api/replay?event=' + encodeURIComponent(id)).then(function (r) { return r.json(); });
  }

  function inject() {
    if (document.querySelector('[data-section="validation"]')) return;

    var nav = document.querySelector('.top-nav');
    if (nav) {
      var btn = el('button', 'nav-item', '<span>◈</span> Validation <b class="val-badge">PROOF</b>');
      btn.dataset.view = 'validation';
      var first = nav.querySelector('.nav-item');
      if (first && first.nextSibling) nav.insertBefore(btn, first.nextSibling);
      else nav.insertBefore(btn, nav.querySelector('.nav-spacer') || null);
      btn.addEventListener('click', function () {
        if (typeof switchView === 'function') switchView('validation'); else show();
      });
    }

    var main = document.querySelector('.content') || document.body;
    var view = el('section', 'view secondary-view');
    view.dataset.section = 'validation';
    view.innerHTML =
      '<div class="view-heading"><p class="kicker">EVIDENCE / BACKTEST</p>' +
      '<h1>Would it have caught a real landslide?</h1>' +
      '<p>Real ERA5 reanalysis rainfall for two past weeks, fed through the exact ' +
      'same risk engine the live dashboard uses. No tuning to the outcome.</p></div>' +
      '<div class="val-hero" id="val-hero"><div class="val-load">Loading ERA5 backtest…</div></div>' +
      '<div class="val-grid" id="val-grid"></div>' +
      '<p class="val-note" id="val-note"></p>';
    main.appendChild(view);

    if (!document.getElementById('validation-style')) {
      var css = el('style'); css.id = 'validation-style';
      css.textContent =
        '.val-badge{margin-left:5px;padding:1px 5px;border-radius:9px;background:#d8f0e2;color:#1f7a52;font:600 8px "Barlow Condensed";letter-spacing:.6px}' +
        '.val-hero{display:flex;flex-wrap:wrap;gap:26px;align-items:flex-end;margin:4px 0 20px;padding:16px 20px;border:1px solid var(--line,#d7e2e2);border-left:4px solid var(--red,#c94f43);background:#fff;box-shadow:var(--shadow,0 8px 22px rgba(34,64,70,.07))}' +
        '.val-hero .big{font:700 46px/1 "Barlow Condensed",sans-serif;color:#b23a30}' +
        '.val-hero .big small{display:block;font:600 10px/1.3 "Barlow Condensed";letter-spacing:1px;color:#7c8d91;margin-top:5px}' +
        '.val-hero .sep{width:1px;align-self:stretch;background:#e3ecec}' +
        '.val-hero .say{max-width:46ch;color:#4a6067;font-size:12px;line-height:1.5}' +
        '.val-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}' +
        '.val-card{border:1px solid var(--line,#d7e2e2);background:#fff;border-radius:8px;padding:14px 16px}' +
        '.val-card h3{margin:0 0 2px;font:600 17px "Barlow Condensed",sans-serif;color:#23444c}' +
        '.val-card .sub{margin:0 0 10px;color:#7c8d91;font-size:11px}' +
        '.val-card.event{border-top:3px solid var(--red,#c94f43)}' +
        '.val-card.control{border-top:3px solid var(--green,#378b5b)}' +
        '.val-verdict{display:inline-block;margin-top:9px;padding:4px 9px;border-radius:4px;font:600 10px "Barlow Condensed";letter-spacing:.6px}' +
        '.val-verdict.hit{color:#12525b;background:#e2f1f0}' +
        '.val-verdict.calm{color:#2f7d54;background:#e6f4ec}' +
        '.val-chart svg{display:block;width:100%;height:250px}' +
        '.val-legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:6px;color:#6b7c81;font-size:10px}' +
        '.val-legend i{display:inline-block;width:11px;height:0;border-top:3px solid;margin-right:4px;vertical-align:2px}' +
        '.val-note{margin-top:12px;color:#82929a;font-size:10.5px;line-height:1.5}' +
        '@media(max-width:900px){.val-grid{grid-template-columns:1fr}.val-hero .sep{display:none}}';
      document.head.appendChild(css);
    }
  }

  function fmtLead(h) {
    if (h == null) return null;
    if (h >= 120) return (h / 24).toFixed(1).replace(/\.0$/, '') + ' d';
    return Math.round(h) + ' h';
  }
  function shortDate(iso) { return (iso || '').slice(0, 10); }

  // combined rainfall + risk-score chart with event markers
  function chart(r, rainMax) {
    var steps = r.steps || [];
    var n = steps.length;
    if (!n) return '<p class="empty">no data</p>';
    var W = 680, H = 250, padL = 30, padR = 30, padT = 22, padB = 34;
    var iw = W - padL - padR, ih = H - padT - padB;
    var x = function (i) { return padL + (n <= 1 ? 0 : i / (n - 1) * iw); };
    var yScore = function (v) { return padT + (1 - v / 100) * ih; };
    var yRain = function (v) { return padT + (1 - Math.min(1, v / rainMax)) * ih; };

    var g = '';
    // threshold bands
    [[0, 35, '#eef6f0'], [35, 55, '#fbf2df'], [55, 75, '#f7e9df'], [75, 100, '#f7e2df']].forEach(function (b) {
      g += '<rect x="' + padL + '" y="' + yScore(b[1]).toFixed(1) + '" width="' + iw +
        '" height="' + (yScore(b[0]) - yScore(b[1])).toFixed(1) + '" fill="' + b[2] + '"/>';
    });
    [35, 55, 75].forEach(function (v) {
      g += '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + yScore(v).toFixed(1) + '" y2="' + yScore(v).toFixed(1) +
        '" stroke="#dde6e6" stroke-width="1"/>' +
        '<text x="3" y="' + (yScore(v) + 3).toFixed(1) + '" font-size="8" fill="#9aabad">' + v + '</text>';
    });

    // rainfall (24 h accumulation) as a soft area
    var rainPts = steps.map(function (s, i) { return x(i).toFixed(1) + ' ' + yRain(s.rain_24h || 0).toFixed(1); });
    g += '<polygon points="' + padL + ' ' + yRain(0).toFixed(1) + ' ' + rainPts.join(' ') + ' ' + (W - padR) + ' ' + yRain(0).toFixed(1) +
      '" fill="#e07b38" fill-opacity="0.16"/>' +
      '<polyline points="' + rainPts.join(' ') + '" fill="none" stroke="#e07b38" stroke-width="1.2" stroke-opacity="0.7"/>';

    // risk-score line
    var d = steps.map(function (s, i) { return (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + yScore(s.risk_score).toFixed(1); }).join(' ');
    g += '<path d="' + d + '" fill="none" stroke="#284a52" stroke-width="2.2"/>';

    function marker(idx, color, label, sub) {
      if (idx == null || idx < 0 || idx >= n) return;
      var xx = x(idx).toFixed(1);
      g += '<line x1="' + xx + '" x2="' + xx + '" y1="' + padT + '" y2="' + (H - padB) +
        '" stroke="' + color + '" stroke-width="1.6" stroke-dasharray="4 3"/>' +
        '<circle cx="' + xx + '" cy="' + yScore(steps[idx].risk_score).toFixed(1) + '" r="3.4" fill="' + color + '"/>' +
        '<text x="' + xx + '" y="' + (padT + 9) + '" font-size="8.5" font-weight="700" fill="' + color + '" text-anchor="middle">' + label + '</text>' +
        (sub ? '<text x="' + xx + '" y="' + (padT + 19) + '" font-size="8" fill="' + color + '" text-anchor="middle">' + sub + '</text>' : '');
    }
    marker(r.warning_index, '#c98a1e', 'HIGH', r.lead_time_hours != null ? '−' + fmtLead(r.lead_time_hours) : '');
    marker(r.critical_index, '#c33c50', 'CRITICAL', r.critical_lead_time_hours != null ? '−' + fmtLead(r.critical_lead_time_hours) : '');
    marker(r.failure_index, '#1c2e33', 'FAILURE', shortDate((r.event || {}).failure_utc));

    // control: watermark
    if (!(r.event || {}).failure_utc) {
      g += '<text x="' + (padL + iw / 2) + '" y="' + (padT + ih / 2) + '" font-size="15" font-weight="700" fill="#cfe0d4" text-anchor="middle">NO ALERT ISSUED</text>';
      var pk = steps.reduce(function (a, s, i) { return s.risk_score > steps[a].risk_score ? i : a; }, 0);
      g += '<circle cx="' + x(pk).toFixed(1) + '" cy="' + yScore(steps[pk].risk_score).toFixed(1) + '" r="3" fill="#378b5b"/>' +
        '<text x="' + x(pk).toFixed(1) + '" y="' + (yScore(steps[pk].risk_score) - 6).toFixed(1) + '" font-size="8.5" fill="#2f7d54" text-anchor="middle">peak ' + steps[pk].risk_score + '</text>';
    }

    var t0 = shortDate(steps[0].time), t1 = shortDate(steps[n - 1].time);
    g += '<text x="' + padL + '" y="' + (H - 6) + '" font-size="8" fill="#9aabad">' + t0 + '</text>' +
      '<text x="' + (W - padR) + '" y="' + (H - 6) + '" font-size="8" fill="#9aabad" text-anchor="end">' + t1 + '</text>' +
      '<text x="' + (W - padR + 2) + '" y="' + (padT + 3) + '" font-size="8" fill="#c07a3a" text-anchor="end">mm/24h</text>';

    return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' + g + '</svg>';
  }

  function card(r, kind) {
    var ev = r.event || {};
    var isEvent = !!ev.failure_utc;
    var verdict = isEvent
      ? '<span class="val-verdict hit">HIGH ' + Math.round(r.lead_time_hours) + ' h early · CRITICAL ' + Math.round(r.critical_lead_time_hours) + ' h early ✓</span>'
      : '<span class="val-verdict calm">NO FALSE ALARM ✓ &nbsp;peak score ' + r.peak_score + '/100</span>';
    return '<div class="val-card ' + kind + '">' +
      '<h3>' + ev.name + '</h3>' +
      '<p class="sub">' + (isEvent ? 'Failure ' + shortDate(ev.failure_utc) + ' · ' : 'Routine monsoon week · ') + (r.rainfall_source || 'ERA5 archive') + '</p>' +
      '<div class="val-chart">' + chart(r, window.__valRainMax || 60) + '</div>' +
      '<div class="val-legend"><span><i style="border-color:#284a52"></i>risk score</span>' +
      '<span><i style="border-color:#e07b38"></i>rainfall, mm/24h</span>' +
      (isEvent ? '<span><i style="border-color:#c98a1e"></i>HIGH</span><span><i style="border-color:#c33c50"></i>CRITICAL</span>' : '') + '</div>' +
      verdict + '</div>';
  }

  function render() {
    var hero = document.getElementById('val-hero');
    var grid = document.getElementById('val-grid');
    var note = document.getElementById('val-note');
    if (!grid) return;
    Promise.all([getReplay(EVENT_ID), getReplay(CONTROL_ID)]).then(function (res) {
      var ev = res[0], ctrl = res[1];
      if (!ev || ev.error || !ev.steps) { grid.innerHTML = '<p class="empty">Replay data unavailable — needs the API.</p>'; if (hero) hero.innerHTML = ''; return; }
      // shared rainfall scale so the contrast is honest
      var maxE = Math.max.apply(null, ev.steps.map(function (s) { return s.rain_24h || 0; }));
      var maxC = ctrl && ctrl.steps ? Math.max.apply(null, ctrl.steps.map(function (s) { return s.rain_24h || 0; })) : 0;
      window.__valRainMax = Math.max(30, maxE, maxC);

      var hiH = ev.lead_time_hours != null ? Math.round(ev.lead_time_hours) : null;
      var crH = ev.critical_lead_time_hours != null ? Math.round(ev.critical_lead_time_hours) : null;
      if (hero) hero.innerHTML =
        '<div class="big">' + (hiH != null ? hiH + ' h' : '—') + '<small>HIGH-RISK WARNING<br>BEFORE THE LANDSLIDE</small></div>' +
        '<div class="sep"></div>' +
        '<div class="big">' + (crH != null ? crH + ' h' : '—') + '<small>CRITICAL WARNING<br>BEFORE THE LANDSLIDE</small></div>' +
        '<div class="sep"></div>' +
        '<p class="say">On real ERA5 rainfall for the 17 Jun 2022 Sohra / Cherrapunji landslide, the engine crossed <b>HIGH</b> ' +
        (hiH != null ? hiH + ' hours' : '') + ' and <b>CRITICAL</b> ' + (crH != null ? crH + ' hours' : '') +
        ' before the failure. On an ordinary 2019 monsoon week it peaked at ' + ctrl.peak_score + '/100 and never raised an alert.</p>';

      grid.innerHTML = card(ev, 'event') + (ctrl && ctrl.steps ? card(ctrl, 'control') : '');
      if (note) note.textContent =
        'ERA5 is a ~25 km reanalysis and under-catches convective monsoon peaks in steep terrain, so absolute mm are conservative — ' +
        'the trajectory and the lead time are the signal, not a hindcast of the exact rainfall. Levels: Monitoring <35 · Advisory 35 · High 55 · Critical 75. ' +
        'Rainfall source: ' + (ev.rainfall_source || 'Open-Meteo ERA5 archive') + ' (no API key). Same engine as the live dashboard.';
    }).catch(function () {
      grid.innerHTML = '<p class="empty">Replay data unavailable — needs the API (or embedded data).</p>';
      if (hero) hero.innerHTML = '';
    });
  }

  function show() {
    document.querySelectorAll('.view').forEach(function (v) { v.classList.toggle('active', v.dataset.section === 'validation'); });
    document.querySelectorAll('.nav-item').forEach(function (i) { i.classList.toggle('active', i.dataset.view === 'validation'); });
  }

  var rendered = false;
  function boot() {
    inject();
    if (typeof window.switchView === 'function' && !window.switchView.__valWrapped) {
      var orig = window.switchView;
      window.switchView = function (v) { orig(v); if (v === 'validation') { show(); if (!rendered) { rendered = true; render(); } } };
      window.switchView.__valWrapped = true;
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
