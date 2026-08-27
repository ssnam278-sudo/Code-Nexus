/* Historical event replay view.
   Self-contained: injects its own nav item + section, hooks the app's switchView,
   and renders from either the live API (/api/replay) or embedded data
   (window.__REPLAY_DATA / window.__REPLAY_EVENTS) when there is no backend. */
(function () {
  'use strict';

  var API = (typeof API_BASE === 'string') ? API_BASE : '';
  var LEVEL_COLOR = { Monitoring: '#4d9d69', Advisory: '#d5a03b', High: '#d36c36', Critical: '#d34438' };

  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }

  function inject() {
    if (document.querySelector('[data-section="replay"]')) return;

    var nav = document.querySelector('.top-nav');
    if (nav) {
      var btn = el('button', 'nav-item', '<span>↺</span> Event replay');
      btn.dataset.view = 'replay';
      var spacer = nav.querySelector('.nav-spacer');
      nav.insertBefore(btn, spacer || null);
      btn.addEventListener('click', function () {
        if (typeof switchView === 'function') switchView('replay');
        else show();
      });
    }

    var main = document.querySelector('.content') || document.body;
    var view = el('section', 'view secondary-view');
    view.dataset.section = 'replay';
    view.innerHTML =
      '<div class="view-heading"><p class="kicker">VALIDATION / EVIDENCE</p>' +
      '<h1>Historical event replay</h1>' +
      '<p>Real past rainfall (ERA5) fed through the hazard model &mdash; how many hours of ' +
      'warning it would have produced before a real landslide.</p></div>' +
      '<div class="replay-pick" id="replay-pick"></div>' +
      '<div class="replay-body" id="replay-body"><p class="empty">Loading&hellip;</p></div>';
    main.appendChild(view);

    if (!document.getElementById('replay-style')) {
      var css = el('style'); css.id = 'replay-style';
      css.textContent =
        '.replay-pick{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}' +
        '.replay-pick button{padding:9px 13px;border:1px solid var(--line,#d7e2e2);background:var(--white,#fff);' +
        'color:#3a565c;border-radius:6px;font-size:12px;cursor:pointer}' +
        '.replay-pick button.active{border-color:var(--teal,#167c87);background:#eef7f6;color:#12525b;font-weight:600}' +
        '.replay-head{display:flex;flex-wrap:wrap;gap:22px;align-items:baseline;margin:6px 0 14px}' +
        '.replay-lead{font:700 40px/1 "Barlow Condensed",sans-serif;color:#c05a2b}' +
        '.replay-lead small{display:block;font:600 10px/1 "Barlow Condensed";letter-spacing:1px;color:#7c8d91}' +
        '.replay-lead.crit{color:#b23a30}.replay-lead.calm{color:#2f8b57}' +
        '.replay-meta{color:#5f7379;font-size:12px;max-width:60ch}' +
        '.replay-chart{border:1px solid var(--line,#d7e2e2);background:var(--white,#fff);border-radius:8px;padding:10px}' +
        '.replay-chart svg{display:block;width:100%;height:230px}' +
        '.replay-note{margin-top:8px;color:#82929a;font-size:10.5px}';
      document.head.appendChild(css);
    }
  }

  var events = [], loaded = {}, current = null;

  function getEvents() {
    if (window.__REPLAY_EVENTS) return Promise.resolve(window.__REPLAY_EVENTS);
    return fetch(API + '/api/replay/events').then(function (r) { return r.json(); });
  }
  function getReplay(id) {
    if (loaded[id]) return Promise.resolve(loaded[id]);
    if (window.__REPLAY_DATA && window.__REPLAY_DATA[id]) return Promise.resolve(window.__REPLAY_DATA[id]);
    return fetch(API + '/api/replay?event=' + encodeURIComponent(id)).then(function (r) { return r.json(); });
  }

  function renderPicker() {
    var box = document.getElementById('replay-pick');
    if (!box) return;
    box.innerHTML = '';
    events.forEach(function (ev) {
      var b = el('button', ev.id === current ? 'active' : '', ev.name + (ev.is_control ? '  (control)' : ''));
      b.addEventListener('click', function () { current = ev.id; renderPicker(); renderEvent(ev.id); });
      box.appendChild(b);
    });
  }

  function fmtLead(h) {
    if (h == null) return null;
    if (h >= 48) return (h / 24).toFixed(1).replace(/\.0$/, '') + ' days';
    return Math.round(h) + ' h';
  }

  function renderEvent(id) {
    var body = document.getElementById('replay-body');
    if (body) body.innerHTML = '<p class="empty">Running replay&hellip;</p>';
    getReplay(id).then(function (r) {
      loaded[id] = r;
      if (!body) return;
      if (r.error) { body.innerHTML = '<p class="empty">' + r.error + '</p>'; return; }

      var ev = r.event, steps = r.steps || [];
      var isControl = !ev.failure_utc;
      var leadCls = isControl ? 'calm' : (r.critical_lead_time_hours != null ? 'crit' : '');
      var leadNum, leadLbl;
      if (isControl) { leadNum = 'No alert'; leadLbl = 'peak score ' + r.peak_score + ' · no false alarm'; }
      else if (r.lead_time_hours != null) {
        leadNum = fmtLead(r.lead_time_hours);
        leadLbl = 'of warning at HIGH before failure' +
          (r.critical_lead_time_hours != null ? '  ·  CRITICAL ' + fmtLead(r.critical_lead_time_hours) + ' before' : '');
      } else { leadNum = 'Missed'; leadLbl = 'no warning before failure'; }

      body.innerHTML =
        '<div class="replay-head"><div class="replay-lead ' + leadCls + '">' + leadNum +
        '<small>' + leadLbl + '</small></div>' +
        '<div class="replay-meta">' + ev.description +
        '<br><b>Terrain:</b> slope ' + ev.terrain.slope + ' · susceptibility ' + ev.terrain.susceptibility +
        ' · history ' + ev.terrain.history +
        '<br><b>Rainfall:</b> ' + (r.rainfall_source || 'ERA5 archive') + ' · <b>Source:</b> ' + ev.source + '</div></div>' +
        '<div class="replay-chart">' + chart(r) + '</div>' +
        '<p class="replay-note">Levels: Monitoring &lt;35 · Advisory 35 · High 55 · Critical 75. ' +
        'ERA5 is a ~25 km reanalysis and under-catches convective peaks &mdash; the trajectory and lead time are the signal, not the exact mm.</p>';
    });
  }

  function chart(r) {
    var steps = r.steps, n = steps.length;
    if (!n) return '';
    var W = 900, H = 230, padL = 34, padR = 10, padT = 12, padB = 22;
    var iw = W - padL - padR, ih = H - padT - padB;
    var x = function (i) { return padL + (n <= 1 ? 0 : i / (n - 1) * iw); };
    var y = function (v) { return padT + (1 - v / 100) * ih; };

    var bands = [[0, 35, '#eef6f0'], [35, 55, '#fbf2df'], [55, 75, '#f7e9df'], [75, 100, '#f7e2df']];
    var g = '';
    bands.forEach(function (b) {
      g += '<rect x="' + padL + '" y="' + y(b[1]).toFixed(1) + '" width="' + iw +
        '" height="' + (y(b[0]) - y(b[1])).toFixed(1) + '" fill="' + b[2] + '"/>';
    });
    [35, 55, 75].forEach(function (v) {
      g += '<line x1="' + padL + '" x2="' + (W - padR) + '" y1="' + y(v).toFixed(1) + '" y2="' + y(v).toFixed(1) +
        '" stroke="#d9e2e2" stroke-width="1"/>' +
        '<text x="4" y="' + (y(v) + 3).toFixed(1) + '" font-size="9" fill="#8a999b">' + v + '</text>';
    });

    var d = steps.map(function (s, i) { return (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(s.risk_score).toFixed(1); }).join(' ');
    g += '<path d="' + d + '" fill="none" stroke="#31525a" stroke-width="2"/>';

    function vline(idx, color, label) {
      if (idx == null || idx < 0 || idx >= n) return;
      var xx = x(idx).toFixed(1);
      g += '<line x1="' + xx + '" x2="' + xx + '" y1="' + padT + '" y2="' + (H - padB) +
        '" stroke="' + color + '" stroke-width="1.5" stroke-dasharray="4 3"/>' +
        '<text x="' + xx + '" y="' + (padT + 9) + '" font-size="9" fill="' + color + '" text-anchor="middle">' + label + '</text>';
    }
    vline(r.warning_index, '#c98a1e', 'HIGH');
    vline(r.critical_index, '#c33c50', 'CRITICAL');
    vline(r.failure_index, '#1c2e33', 'FAILURE');

    // endpoints
    steps.forEach(function (s, i) {
      if (i % Math.ceil(n / 60) !== 0 && i !== n - 1) return;
      g += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(s.risk_score).toFixed(1) + '" r="1.6" fill="' +
        (LEVEL_COLOR[s.risk_level] || '#31525a') + '"/>';
    });

    var t0 = (steps[0].time || '').slice(0, 10), t1 = (steps[n - 1].time || '').slice(0, 10);
    g += '<text x="' + padL + '" y="' + (H - 6) + '" font-size="9" fill="#8a999b">' + t0 + '</text>' +
      '<text x="' + (W - padR) + '" y="' + (H - 6) + '" font-size="9" fill="#8a999b" text-anchor="end">' + t1 + '</text>';

    return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' + g + '</svg>';
  }

  function show() {
    document.querySelectorAll('.view').forEach(function (v) { v.classList.toggle('active', v.dataset.section === 'replay'); });
    document.querySelectorAll('.nav-item').forEach(function (i) { i.classList.toggle('active', i.dataset.view === 'replay'); });
  }

  function boot() {
    inject();
    // extend the app's switchView so the nav integrates cleanly
    if (typeof window.switchView === 'function' && !window.switchView.__replayWrapped) {
      var orig = window.switchView;
      window.switchView = function (v) { orig(v); if (v === 'replay') show(); };
      window.switchView.__replayWrapped = true;
    }
    getEvents().then(function (list) {
      events = list || [];
      if (!events.length) return;
      current = events[0].id;
      renderPicker();
      renderEvent(current);
    }).catch(function () {
      var b = document.getElementById('replay-body');
      if (b) b.innerHTML = '<p class="empty">Replay needs the API (or embedded data).</p>';
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
