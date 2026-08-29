/* Live forecast view — real-time hazard from /api/live/hazard.
   Self-contained: injects its own nav item + section and polls the API.
   If the API is absent (static hosting) the tab quietly shows a hint. */
(function () {
  'use strict';

  var API = (typeof API_BASE === 'string') ? API_BASE : '';
  var LC = { Monitoring: '#4d9d69', Advisory: '#d5a03b', High: '#d36c36', Critical: '#d34438' };
  var POLL_MS = 60000;
  var timer = null;

  function el(t, c, h) { var n = document.createElement(t); if (c) n.className = c; if (h != null) n.innerHTML = h; return n; }
  function ago(iso) {
    if (!iso) return 'n/a';
    var s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 90) return Math.round(s) + 's ago';
    if (s < 5400) return Math.round(s / 60) + ' min ago';
    return Math.round(s / 3600) + ' h ago';
  }

  function inject() {
    if (document.querySelector('[data-section="live"]')) return;
    var nav = document.querySelector('.top-nav');
    if (nav) {
      var b = el('button', 'nav-item', '<span>◉</span> Live forecast');
      b.dataset.view = 'live';
      nav.insertBefore(b, nav.querySelector('.nav-spacer') || null);
      b.addEventListener('click', function () {
        if (typeof switchView === 'function') switchView('live'); else show();
        load();
      });
    }
    var main = document.querySelector('.content') || document.body;
    var v = el('section', 'view secondary-view');
    v.dataset.section = 'live';
    v.innerHTML =
      '<div class="view-heading"><p class="kicker">REAL-TIME</p><h1>Live rainfall forecast</h1>' +
      '<p>Observed rainfall (last 16 days) + a 7-day forecast from Open-Meteo, run through the ' +
      'hazard model every 15 min. Lead time is when the <em>forecast</em> first crosses a level.</p></div>' +
      '<div class="live-status" id="live-status">Loading&hellip;</div>' +
      '<div class="live-dispatch" id="live-dispatch">Alert dispatch: checking&hellip;</div>' +
      '<div id="live-list"></div>';
    main.appendChild(v);

    if (!document.getElementById('live-style')) {
      var s = el('style'); s.id = 'live-style';
      s.textContent =
        '.live-status{font-size:12px;color:#5f7379;margin-bottom:12px}' +
        '.live-status b{color:#12525b}' +
        '.live-row{border:1px solid var(--line,#d7e2e2);background:var(--white,#fff);border-radius:8px;' +
        'padding:12px 14px;margin-bottom:10px;display:grid;grid-template-columns:1fr auto;gap:6px 16px;align-items:center}' +
        '.live-row h3{margin:0;font:600 15px "Barlow Condensed",sans-serif;letter-spacing:.3px}' +
        '.live-row .sub{grid-column:1/-1;font-size:11px;color:#7c8d91}' +
        '.live-badge{font:700 10px "Barlow Condensed";letter-spacing:1px;padding:3px 8px;border-radius:4px;color:#fff}' +
        '.live-now{font:700 26px "Barlow Condensed";line-height:1}' +
        '.live-lead{font-size:12px;color:#c0562b;font-weight:600}' +
        '.live-spark{grid-column:1/-1;width:100%;height:44px}' +
        '.live-hz{display:flex;gap:10px;font-size:10.5px;color:#6b7c81;margin-top:2px}' +
        '.live-dispatch{font-size:11px;color:#5f7379;margin:-4px 0 14px;padding:8px 10px;border:1px solid var(--line,#d7e2e2);border-radius:6px;background:#fbfdfd}' +
        '.live-dispatch b{color:#12525b}' +
        '.live-dispatch button{margin-left:8px}';
      document.head.appendChild(s);
    }
  }

  function dispatchStatus() {
    var box = document.getElementById('live-dispatch');
    if (!box) return;
    fetch(API + '/api/health').then(function (r) { return r.json(); }).then(function (h) {
      var d = (h && h.alert_dispatch) || {};
      var tg = !!d.telegram_configured;
      box.innerHTML = 'Telegram alert dispatch: <b>' + (tg ? 'configured' : 'not configured') + '</b>' +
        (tg
          ? ' <button id="live-test-alert" class="ack-btn">Send test alert</button>'
          : ' &mdash; set <code>TELEGRAM_BOT_TOKEN</code> + <code>TELEGRAM_CHAT_ID</code> (see TELEGRAM_SETUP.md)');
      var btn = document.getElementById('live-test-alert');
      if (btn) btn.addEventListener('click', function () {
        btn.disabled = true; btn.textContent = 'Sending…';
        var zid = (window.AppState && window.AppState.selectedZoneId) || '';
        fetch(API + '/api/alerts/dispatch-test' + (zid ? '?zone_id=' + encodeURIComponent(zid) : ''), { method: 'POST' })
          .then(function (r) { return r.json(); })
          .then(function (res) {
            btn.textContent = res.telegram === 'sent'
              ? 'Sent ✓ ' + (res.zone || '') + ' (' + res.risk_score + ')'
              : (res.telegram || 'failed');
          })
          .catch(function () { btn.textContent = 'failed'; });
      });
    }).catch(function () { box.textContent = 'Alert dispatch status needs the backend API.'; });
  }

  function spark(traj, nowIdx) {
    var n = traj.length; if (!n) return '';
    var W = 760, H = 44, x = function (i) { return i / (n - 1) * W; }, y = function (v) { return H - v / 100 * H; };
    var obs = traj.slice(0, nowIdx + 1), fut = traj.slice(nowIdx);
    function path(arr, off) { return arr.map(function (s, i) { return (i ? 'L' : 'M') + x(i + off).toFixed(1) + ' ' + y(s.risk_score).toFixed(1); }).join(' '); }
    var g = '';
    [55, 75].forEach(function (t) { g += '<line x1="0" x2="' + W + '" y1="' + y(t) + '" y2="' + y(t) + '" stroke="#e6ecec"/>'; });
    g += '<path d="' + path(obs, 0) + '" fill="none" stroke="#31525a" stroke-width="2"/>';
    g += '<path d="' + path(fut, nowIdx) + '" fill="none" stroke="#c0562b" stroke-width="2" stroke-dasharray="4 3"/>';
    g += '<line x1="' + x(nowIdx).toFixed(1) + '" x2="' + x(nowIdx).toFixed(1) + '" y1="0" y2="' + H + '" stroke="#9fb0b3" stroke-dasharray="2 2"/>';
    return '<svg class="live-spark" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' + g + '</svg>';
  }

  function render(data) {
    var st = document.getElementById('live-status');
    if (st) {
      var li = data.last_ingest;
      st.innerHTML = 'Source <b>Open-Meteo</b> &middot; last pull <b>' + ago(li && li.ran_at) + '</b> &middot; ' +
        (data.warning_count ? '<b style="color:#c0562b">' + data.warning_count + ' zone(s) in or heading to warning</b>'
          : 'no zones in warning');
    }
    var list = document.getElementById('live-list');
    if (!list) return;
    list.innerHTML = '';
    (data.zones || []).forEach(function (z) {
      if (!z.now) { return; }
      var lvl = z.now.risk_level, fc = z.forecast;
      var nowIdx = 0, traj = z.trajectory || [];
      for (var i = 0; i < traj.length; i++) { if (traj[i].kind === 'observed') nowIdx = i; }
      var lead = '';
      if (fc.lead_time_to_critical_h) lead = 'Critical in ~' + fc.lead_time_to_critical_h + ' h';
      else if (fc.lead_time_to_high_h) lead = 'High in ~' + fc.lead_time_to_high_h + ' h';
      else if (lvl === 'Critical' || lvl === 'High') lead = 'in warning now';

      var row = el('div', 'live-row');
      row.innerHTML =
        '<h3>' + z.name + ' &nbsp;<span class="live-badge" style="background:' + (LC[lvl] || '#888') + '">' + lvl + '</span></h3>' +
        '<div style="text-align:right"><span class="live-now" style="color:' + (LC[lvl] || '#333') + '">' + z.now.risk_score + '</span>' +
        (lead ? '<br><span class="live-lead">' + lead + '</span>' : '') + '</div>' +
        '<div class="live-hz">' + (fc.horizon || []).map(function (h) {
          return '+' + h.h + 'h: <b style="color:' + (LC[h.risk_level] || '#333') + '">' + h.risk_score + '</b>';
        }).join(' &nbsp; ') + '</div>' +
        spark(traj, nowIdx) +
        '<div class="sub">Antecedent rain ' + z.now.api_mm + ' mm &middot; 24 h ' + z.now.rain_24h +
        ' mm &middot; projected peak ' + fc.projected_peak_score + ' (' + fc.projected_peak_level + ') &middot; ' + (z.district || '') + '</div>';
      list.appendChild(row);
    });
    if (!list.children.length) list.innerHTML = '<p class="empty">No live data yet — the first rainfall pull is running.</p>';
  }

  function load() {
    fetch(API + '/api/live/hazard').then(function (r) { return r.json(); }).then(function (d) {
      if (d.status === 'warming_up') {
        var st = document.getElementById('live-status');
        if (st) st.textContent = 'Warming up — fetching the first rainfall pull…';
        return;
      }
      render(d);
    }).catch(function () {
      var st = document.getElementById('live-status');
      if (st) st.innerHTML = 'Live forecast needs the backend API (Render deployment). Not available on static hosting.';
    });
  }

  function show() {
    document.querySelectorAll('.view').forEach(function (v) { v.classList.toggle('active', v.dataset.section === 'live'); });
    document.querySelectorAll('.nav-item').forEach(function (i) { i.classList.toggle('active', i.dataset.view === 'live'); });
  }

  function boot() {
    inject();
    dispatchStatus();
    if (typeof window.switchView === 'function' && !window.switchView.__liveWrapped) {
      var orig = window.switchView;
      window.switchView = function (v) {
        orig(v);
        if (v === 'live') { show(); load(); dispatchStatus(); clearInterval(timer); timer = setInterval(load, POLL_MS); }
        else { clearInterval(timer); timer = null; }
      };
      window.switchView.__liveWrapped = true;
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
