const Dashboard = (() => {
	let actions;
	const $ = id => document.getElementById(id);
	const current = state => (state && state.zones || []).find(zone => zone.id === state.selectedZoneId) || (state && state.zones || [])[0] || null;
	const levelClass = level => String(level || 'monitoring').toLowerCase();
	function init(callbacks) {
		actions = callbacks;
		document.querySelectorAll('.nav-item').forEach(item => item.addEventListener('click', () => actions.switchView(item.dataset.view)));
		document.querySelectorAll('[data-view-target]').forEach(item => item.addEventListener('click', () => actions.switchView(item.dataset.viewTarget)));
		$('demo-button').addEventListener('click', runDemo); $('refresh-button').addEventListener('click', () => (actions.resetDemo ? actions.resetDemo() : actions.applyScenario('Normal'))); $('zone-details-button').addEventListener('click', () => actions.switchView('intelligence')); $('report-form').addEventListener('submit', submitReport); if (!$('report-media')) { const label = document.createElement('label'); label.textContent = 'EVIDENCE PHOTO / VIDEO'; label.innerHTML += '<input id="report-media" type="file" accept="image/*,video/*">'; $('report-form').insertBefore(label, $('report-form').querySelector('.brief-action')); } if (!$('ai-comparison')) { const panel = document.createElement('section'); panel.id = 'ai-comparison'; panel.className = 'ai-comparison panel'; panel.innerHTML = '<div class="section-head"><div><p class="kicker">DECISION SUPPORT</p><h2>ML Risk Check</h2></div><span id="ai-review-badge" class="comparison-badge">SYNCING</span></div><div id="ai-comparison-body"></div><p class="ml-disclaimer"><b>Prototype model — not validated.</b> Random Forest (logistic surrogate where scikit-learn is not bundled), trained on <b>synthetic data</b> (<code>historical_training.json</code>), <b>not</b> real disaster records. Shown only as a cross-check on the physics-based score.</p>'; document.querySelector('.incident-brief')?.after(panel); }
	}
	function runDemo() { const button = $('demo-button'); button.disabled = true; button.innerHTML = '<span>●</span> Monitoring escalation'; actions.applyScenario('Normal'); setTimeout(() => actions.applyScenario('Heavy Rain'), 1500); setTimeout(() => actions.applyScenario('Extreme Rain'), 3300); setTimeout(() => { button.disabled = false; button.innerHTML = '<span>▶</span> Run escalation demo'; }, 5100); }
	const num = (v, d = 0) => { const n = Number(v); return Number.isFinite(n) ? n : d; };
	function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, num(v))); }
	// single threshold ladder (35 / 55 / 75) — same as backend risk_engine._level
	function levelOf(score) { return window.CodeNexusRisk.level(score); }
	function safeLevel(zone) { return zone && typeof zone.level === 'string' ? zone.level : levelOf(zone && zone.score); }
	function animateNumber(element, value, decimals = 0) { if (!element) return; const start = num(element.dataset.value ?? String(element.textContent).replace(/[^0-9.-]/g, '')); const end = num(value); if (!Number.isFinite(end)) { element.textContent = decimals ? (0).toFixed(decimals) : '0'; element.dataset.value = 0; return; } if (Math.abs(start - end) < .01) { element.textContent = decimals ? end.toFixed(decimals) : Math.round(end); element.dataset.value = end; return; } const began = performance.now(); element.classList.add('changing'); const tick = now => { const progress = Math.min(1, (now - began) / 600); const eased = 1 - Math.pow(1 - progress, 3); element.textContent = decimals ? (start + (end - start) * eased).toFixed(decimals) : Math.round(start + (end - start) * eased); element.dataset.value = end; if (progress < 1) requestAnimationFrame(tick); else element.classList.remove('changing'); }; requestAnimationFrame(tick); }
	function animateGauge(element, score) { if (!element) return; const target = clamp(score, 0, 100); const start = num(element.dataset.score); const began = performance.now(); const tick = now => { const progress = Math.min(1, (now - began) / 700); const eased = 1 - Math.pow(1 - progress, 3); const value = clamp(start + (target - start) * eased, 0, 100); element.style.background = `conic-gradient(${target >= 75 ? 'var(--red)' : target >= 55 ? 'var(--orange)' : 'var(--amber)'} 0 ${value}%, #e2ebea ${value}% 100%)`; element.dataset.score = value; if (progress < 1) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }
	function render(state) {
		const zones = (state.zones || []).map(z => ({ ...z, score: num(z && z.score), confidence: num(z && z.confidence, 75), level: safeLevel(z) }));
		const zone = zones.find(z => z.id === state.selectedZoneId) || zones[0] || { name:'—', district:'—', score:0, confidence:0, level:'Monitoring', coordinates:[0,0] };
		const previous = (state.previousZones || []).find(item => item.id === zone.id) || zone;
		const regional = zones.length ? Math.round(zones.reduce((sum, item) => sum + num(item.score), 0) / zones.length) : 0;
		const activeAlerts = (state.alerts && state.alerts.length) ? state.alerts.length : zones.filter(item => item.level === 'High' || item.level === 'Critical').length;
		const asOf = dataAsOf(state, zones);
		const asOfText = asOf
			? asOf.toLocaleString('en-IN', { hour12:false, day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' }) + ' IST'
			: 'no live data timestamp';
		if ($('updated-time')) $('updated-time').textContent = asOf ? asOf.toLocaleTimeString('en-IN', { hour12:false }) : '—';
		if ($('clock')) $('clock').textContent = asOfText;
		animateNumber($('regional-risk'), regional);
		animateNumber($('active-alerts'), activeAlerts);
		$('regional-status').textContent = levelOf(regional).toUpperCase();
		const top = zones.slice().sort((a, b) => num(b.score) - num(a.score))[0];
		$('highest-priority').textContent = (top && top.name ? top.name : '—').split(' ')[0].toUpperCase();
		$('selected-zone-name').textContent = zone.name || '—';
		$('selected-location').textContent = zone.district || '—';
		$('selected-level').textContent = zone.level.toUpperCase();
		$('selected-level').className = `level-badge ${levelClass(zone.level)}`;
		animateNumber($('selected-score'), zone.score);
		animateGauge($('score-ring'), zone.score);
		$('risk-reading').textContent = `${zone.level.toUpperCase()} RISK`;
		$('risk-reading').style.color = zone.level === 'Critical' ? 'var(--red)' : zone.level === 'High' ? 'var(--orange)' : 'var(--amber)';
		$('selected-confidence').textContent = `${Math.round(num(zone.confidence, 0))}%`;
		$('confidence-bar-fill').style.width = `${clamp(num(zone.confidence, 0), 0, 100)}%`;
		renderConfidenceBasis(zone);
		animateNumber($('rainfall-value'), num(zone.rainfall), 1);
		animateNumber($('moisture-value'), num(zone.moisture));
		animateNumber($('temperature-value'), num(zone.temperature), 1);
		animateNumber($('accumulated-value'), num(zone.accumulated) + num(state.rainfallBoost) * 1.7);
		$('forecast-now').textContent = Math.round(num(zone.score));
		const co = Array.isArray(zone.coordinates) ? zone.coordinates : [0, 0];
		$('coordinates').textContent = `${num(co[0]).toFixed(4)}° N, ${num(co[1]).toFixed(4)}° E`;
		$('risk-explanation').textContent = explanation(zone);
		renderBreakdown(zone); renderSparklines(zone); renderTelemetryMeta(zone, state); renderForecast(zone); renderFieldVerify(zone); renderComparison({ ...state, zones });

		// ONE honest status indicator, shared by the header badge and the nav feed
		const mode = dataModeBadge(state, zones);
		const flag = document.querySelector('.command-deck .prototype-flag');
		if (flag) { flag.innerHTML = `<i></i> ${mode.label}`; flag.className = `prototype-flag mode-${mode.cls}`; }
		const deckHealth = document.querySelector('.deck-health');
		if (deckHealth) deckHealth.innerHTML = `<i class="dot ${state.backendConnected ? 'green' : 'cyan'}"></i> ${state.backendConnected ? 'API LINKED' : 'LOCAL'}`;
		const feed = document.querySelector('.nav-feed');
		if (feed) {
			const feedText = state.backendConnected
				? mode.label
				: (mode.cls === 'simulated' ? 'Offline · local formula (same weights)' : `${mode.label} · offline scoring`);
			feed.innerHTML = `<i class="dot ${mode.cls === 'simulated' ? 'cyan' : 'green'}"></i> ${feedText}`;
		}
		if ($('health-score')) $('health-score').innerHTML = `${state.backendConnected ? 'OK' : 'LOCAL'} <small>STATUS</small>`;
		if ($('health-feed')) $('health-feed').textContent = mode.label;
		renderSources(state);
		renderChanges(zone, previous, state); renderExposure(zone); renderZones({ ...state, zones }); renderAlerts({ ...state, zones }); renderPriority({ ...state, zones }); renderReports(state);
	}
	function defaultFactors(zone) {
		const s = clamp(zone && zone.score, 0, 100);
		const raw = [
			Math.max(1, num(zone && zone.rainfall)),
			Math.max(1, num(zone && (zone.moisture ?? zone.soil_moisture)) * 0.6),
			Math.max(1, ((num(zone && zone.slope) + num(zone && zone.susceptibility)) / 2) * 0.5),
			Math.max(1, num(zone && zone.history) * 0.4)
		];
		const t = raw.reduce((a, b) => a + b, 0) || 1;
		return { rainfall: raw[0] / t * s, soil: raw[1] / t * s, slope: raw[2] / t * s, historical: raw[3] / t * s };
	}
	function breakdownParts(zone) {
		if (zone && zone.liveFactors) {                         // real Open-Meteo path
			const lf = zone.liveFactors;
			return [
				{ label:'Rainfall intensity', pts:Math.max(0, Math.round(num(lf.rainfall))), color:'var(--orange)' },
				{ label:'Soil saturation', pts:Math.max(0, Math.round(num(lf.soil))), color:'var(--orange)' },
				{ label:'Slope susceptibility', pts:Math.max(0, Math.round(num(lf.slope))), color:'var(--teal)' },
				{ label:'Historical events', pts:Math.max(0, Math.round(num(lf.historical))), color:'var(--teal)' }
			];
		}
		const score = clamp(zone && zone.score, 0, 100);
		const f0 = (zone && zone.factors0) || defaultFactors(zone);
		const rainW = 1 + clamp(num(AppState && AppState.rainfallBoost), 0, 60) / 30;
		const soilW = 1 + clamp(num(AppState && AppState.moistureBoost), 0, 40) / 30;
		const raw = [
			num(f0.rainfall) * rainW,
			num(f0.soil) * soilW,
			num(f0.slope),
			num(f0.historical)
		];
		const total = raw.reduce((a, b) => a + b, 0) || 1;
		const scaled = raw.map(v => v / total * score);
		const ints = scaled.map(v => Math.max(0, Math.round(v)));
		let diff = Math.round(score) - ints.reduce((a, b) => a + b, 0);
		const order = ints.map((_, i) => i).sort((a, b) => scaled[b] - scaled[a]);
		for (let k = 0; diff !== 0 && k < order.length * 6; k++) {
			const i = order[k % order.length];
			if (diff > 0) { ints[i] += 1; diff -= 1; }
			else if (ints[i] > 0) { ints[i] -= 1; diff += 1; }
		}
		return [
			{ label:'Rainfall intensity', pts:ints[0], color:'var(--orange)' },
			{ label:'Soil saturation', pts:ints[1], color:'var(--orange)' },
			{ label:'Slope susceptibility', pts:ints[2], color:'var(--teal)' },
			{ label:'Historical events', pts:ints[3], color:'var(--teal)' }
		];
	}
	// single source of truth for the live/simulated flags, shared by the header
	// badge, the telemetry cards AND the Data Sources transparency page.
	function sourceFlags(state, zones) {
		const list = (zones && zones.length ? zones : (state && state.zones) || []);
		const n = list.length || 1;
		const rainLive = list.filter(z => z && (z.rainfall_data_source === 'open-meteo' || z.data_source === 'open-meteo' || z._live)).length;
		const soilSrcs = new Set(list.map(z => z && z.soil_data_source).filter(Boolean));
		let soil = 'simulated';
		if (list.length && list.every(z => z && z.soil_data_source === 'nasa-power')) soil = 'nasa-power';
		else if (list.length && list.every(z => z && (z.soil_data_source === 'open-meteo' || z.soil_data_source === 'nasa-power'))) soil = 'open-meteo';
		else if (soilSrcs.has('nasa-power') || soilSrcs.has('open-meteo')) soil = 'partial';
		const selected = list.find(z => z && z.id === (state && state.selectedZoneId)) || list[0] || {};
		return {
			rain: rainLive === n && n > 0 ? 'live' : rainLive ? 'partial' : 'simulated',
			soil,
			ageSeconds: feedAge(selected, state)
		};
	}
	// one honest status: LIVE DATA / PARTIAL LIVE DATA / SIMULATED DATA.
	// Derived from what the client actually holds (sourceFlags) — the server's
	// own data_mode can say "simulated" while the browser has a live Open-Meteo
	// pull, and the badge must match what the pages show.
	function dataModeBadge(state, zones) {
		const f = sourceFlags(state, zones);
		const rainOk = f.rain === 'live';
		const soilOk = f.soil === 'nasa-power' || f.soil === 'open-meteo';
		if (rainOk && soilOk) return { label: 'LIVE DATA', cls: 'live' };
		if (rainOk || soilOk || f.rain === 'partial' || f.soil === 'partial') return { label: 'PARTIAL LIVE DATA', cls: 'partial' };
		return { label: 'SIMULATED DATA', cls: 'simulated' };
	}
	// newest real data timestamp — same freshness the Live Forecast tab reports
	function dataAsOf(state, zones) {
		const stamps = (zones || [])
			.map(z => z && (z.observed_at || z.soil_observed_at))
			.filter(Boolean)
			.map(s => Date.parse(s))
			.filter(n => Number.isFinite(n));
		if (state && state.weatherFetchedAt) {
			const w = +new Date(state.weatherFetchedAt);
			if (Number.isFinite(w)) stamps.push(w);
		}
		const age = state && state.health && state.health.data_mode && state.health.data_mode.feed_age_seconds;
		if (Number.isFinite(age)) stamps.push(Date.now() - age * 1000);
		return stamps.length ? new Date(Math.max(...stamps)) : null;
	}
	function thresholdScale(zone) {
		// bands match backend risk_engine._level: 35 Advisory / 55 High / 75 Critical
		const bands = [['0–34', 'Monitoring'], ['35–54', 'Advisory'], ['55–74', 'High'], ['75–100', 'Critical']];
		const mark = clamp(zone && zone.score, 0, 100);
		return `<div class="rb-scale"><div class="rb-track"><span class="mon"></span><span class="adv"></span><span class="hi"></span><span class="cr"></span><b class="rb-marker" style="left:${mark}%"><i>${Math.round(mark)}</i></b></div><div class="rb-bands">${bands.map(b => `<span><b>${b[0]}</b> ${b[1]}</span>`).join('')}</div></div>`;
	}
	function renderConfidenceBasis(zone) {
		const el = $('confidence-basis'); if (!el) return;
		const items = Array.isArray(zone.confidence_basis) ? zone.confidence_basis : [];
		if (!items.length) { el.innerHTML = '<li class="neu">basis unavailable in offline mode</li>'; return; }
		el.innerHTML = items.slice(0, 4).map(it => {
			const e = num(it.effect);
			const cls = e > 0 ? 'pos' : e < 0 ? 'neg' : 'neu';
			const sign = e > 0 ? `+${e}` : e < 0 ? `${e}` : '±0';
			return `<li class="${cls}"><b>${sign}</b> ${it.factor}</li>`;
		}).join('');
	}
	function renderBreakdown(zone) {
		const el = $('factor-list'); if (!el) return;
		el.className = 'factors risk-breakdown';
		const cf = Array.isArray(zone.contributing_factors) ? zone.contributing_factors : null;
		if (cf && cf.length) {
			const maxC = Math.max(...cf.map(f => num(f.contribution)), 1);
			const rows = cf.map(f => {
				const pts = num(f.contribution);
				const col = /rain|soil|moist/i.test(f.name) ? 'var(--orange)' : 'var(--teal)';
				return `<div class="rb-row"><span class="rb-label">${f.name}</span>`
					+ `<span class="rb-val">${Number(f.weight).toFixed(2)} × ${Math.round(num(f.value))} = ${pts.toFixed(1)}</span>`
					+ `<i class="rb-bar"><em style="width:${clamp(pts / maxC * 100, 2, 100)}%;background:${col}"></em></i>`
					+ `<span class="rb-input">input ${num(f.input)} ${f.input_unit || ''}${f.input_unit === 'index' ? ' (0–100)' : ''} → normalised ${Math.round(num(f.value))}</span></div>`;
			}).join('');
			const total = cf.reduce((a, f) => a + num(f.contribution), 0);
			const formula = zone.formula || 'risk = Σ (weightᵢ × inputᵢ),  inputᵢ normalised 0–100';
			el.innerHTML = `<p class="rb-head">RISK SCORE FORMULA <b>${Math.round(num(zone.score))} / 100</b></p>`
				+ `<p class="rb-formula">${formula}</p>`
				+ `<p class="rb-cols"><span>factor</span><span>weight × input = pts</span></p>`
				+ rows
				+ `<p class="rb-sum">Σ = ${total.toFixed(1)} pts → risk score ${Math.round(num(zone.score))}</p>`
				+ thresholdScale(zone);
			return;
		}
		// offline fallback: heuristic point split (no backend weights available)
		const parts = breakdownParts(zone);
		const rows = parts.map(p => `<div class="rb-row"><span class="rb-label">${p.label}</span><span class="rb-val">${p.pts} pts</span><i class="rb-bar"><em style="width:${clamp(p.pts / 40 * 100, 2, 100)}%;background:${p.color}"></em></i></div>`).join('');
		el.innerHTML = `<p class="rb-head">SCORE BREAKDOWN <b>${parts.reduce((a, p) => a + p.pts, 0)} / 100</b></p>`
			+ `<p class="rb-formula">offline estimate — connect the API for the full weighted formula (risk = Σ wᵢ·xᵢ)</p>`
			+ rows + thresholdScale(zone);
	}
	function sparkSeries(zone) {
		const live = zone && zone._live;
		const arr = k => (live && Array.isArray(zone[k]) && zone[k].length >= 2) ? zone[k].map(num) : null;
		const rain = arr('hourlyRainfall'), soil = arr('hourlySoilMoisture'), temp = arr('hourlyTemperature');
		const acc = rain ? rain.map((_, i) => rain.slice(Math.max(0, i - 23), i + 1).reduce((a, b) => a + b, 0)) : null;
		return { rain, soil, temp, acc };
	}
	function renderSparklines(zone) {
		const items = document.querySelectorAll('.telemetry-item');
		const s = sparkSeries(zone);
		const cfg = [
			{ el:items[0], series:s.rain, now:Math.max(0.1, num(zone.rainfall)), vol:0.20, color:'#c87422' },
			{ el:items[1], series:s.soil, now:Math.max(0.1, num(zone.moisture)), vol:0.08, color:'#c87422' },
			{ el:items[2], series:s.temp, now:Math.max(0.1, num(zone.temperature)), vol:0.05, color:'#378b5b' },
			{ el:items[3], series:s.acc, now:Math.max(0.1, num(zone.accumulated)), vol:0.05, color:'#c87422' }
		];
		cfg.forEach(c => {
			if (!c.el) return;
			const spark = c.el.querySelector('.sparkline'); if (!spark) return;
			let pts;
			if (Array.isArray(c.series) && c.series.length >= 2) {
				pts = c.series.slice(-24);
			} else {
				pts = [];
				for (let i = 0; i < 24; i++) { const t = i / 23; pts.push(Math.max(0, c.now * (0.72 + 0.28 * t) + Math.sin(i * 1.7 + c.now) * c.now * c.vol * (0.35 + 0.65 * t))); }
			}
			const min = Math.min(...pts), max = Math.max(...pts), rng = (max - min) || 1;
			const W = 100, H = 17;
			const d = pts.map((v, i) => `${(i / (pts.length - 1) * W).toFixed(1)},${(H - (num(v) - min) / rng * (H - 3) - 1.5).toFixed(1)}`).join(' ');
			spark.classList.add('spark-svg');
			spark.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><polyline points="${d}" fill="none" stroke="${c.color}" stroke-width="1.3" vector-effect="non-scaling-stroke"/></svg>`;
		});
	}
	function pctBadge(series) {
		if (!Array.isArray(series) || series.length < 7) return null;
		const now = num(series[series.length - 1]), past = num(series[series.length - 7]);
		const pct = past === 0 ? (now === 0 ? 0 : 100) : (now - past) / Math.abs(past) * 100;
		if (Math.abs(pct) < 2) return { text:'Stable', cls:'steady' };
		const up = pct > 0;
		return { text:`${up ? '↑' : '↓'} ${Math.abs(Math.round(pct))}%`, cls: up ? 'up' : 'steady' };
	}
	function feedAge(zone, state) {
		if (zone && Number.isFinite(num(zone.feed_age_seconds, NaN))) return num(zone.feed_age_seconds);
		const stamp = (zone && zone.observed_at) || (state && state.weatherFetchedAt);
		const ms = stamp ? Date.parse(stamp) : NaN;
		return Number.isFinite(ms) ? Math.max(0, Math.round((Date.now() - ms) / 1000)) : null;
	}
	function ageText(seconds) {
		if (seconds == null) return '';
		if (seconds < 90) return `${seconds}s ago`;
		if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
		return `${(seconds / 3600).toFixed(1)} h ago`;
	}
	function renderTelemetryMeta(zone, state) {
		// use the SAME flags the Data Sources page and the header badge use
		const flags = sourceFlags(state);
		const rainLive = flags.rain !== 'simulated';
		const soilLive = flags.soil !== 'simulated';
		if (zone && zone._live) {
			const s = sparkSeries(zone);
			const badges = [pctBadge(s.rain), pctBadge(s.soil), pctBadge(s.temp), pctBadge(s.acc)];
			document.querySelectorAll('.telemetry-item').forEach((it, i) => {
				const b = it.querySelector('b'); if (!b || !badges[i]) return;
				b.textContent = badges[i].text;
				b.className = badges[i].cls;
			});
		}
		const tags = [
			rainLive ? { t: 'LIVE', c: 'live' } : { t: 'SIM', c: 'sim' },
			soilLive ? { t: flags.soil === 'nasa-power' ? 'POWER' : 'LIVE', c: 'live' } : { t: 'SIM', c: 'sim' },
			rainLive ? { t: 'LIVE', c: 'live' } : { t: 'SIM', c: 'sim' },
			rainLive ? { t: 'LIVE', c: 'live' } : { t: 'SIM', c: 'sim' }
		];
		document.querySelectorAll('.telemetry-item').forEach((it, i) => {
			const label = it.querySelector('label'); if (!label || !tags[i]) return;
			let tag = label.querySelector('.src-tag');
			if (!tag) { tag = document.createElement('span'); tag.className = 'src-tag'; label.appendChild(tag); }
			tag.textContent = tags[i].t;
			tag.className = `src-tag ${tags[i].c}`;
		});
		const feed = document.querySelector('.telemetry .feed-state');
		if (feed) {
			feed.innerHTML = rainLive
				? `<i class="dot green"></i> LIVE${flags.ageSeconds != null ? ' · ' + ageText(flags.ageSeconds) : ''}`
				: `<i class="dot cyan"></i> SIMULATED FEED`;
		}
	}
	// The transparency page — reads the SAME sourceFlags every other view uses.
	function renderSources(state) {
		if (!$('src-telemetry-status')) return;
		const flags = sourceFlags(state);
		const age = flags.ageSeconds != null ? ' · ' + ageText(flags.ageSeconds) : '';
		$('src-telemetry-status').textContent = flags.rain === 'live' ? 'LIVE' : flags.rain === 'partial' ? 'PARTIAL LIVE' : 'SIMULATED';
		if ($('src-telemetry-sub')) $('src-telemetry-sub').textContent = flags.rain !== 'simulated'
			? `Open-Meteo forecast API — keyless${age}`
			: 'Simulated rainfall (no live feed connected)';
		const soilLabel = flags.soil === 'nasa-power' ? 'LIVE · NASA POWER'
			: flags.soil === 'open-meteo' ? 'LIVE · Open-Meteo'
			: flags.soil === 'partial' ? 'PARTIAL LIVE' : 'SIMULATED';
		$('src-soil-status').textContent = soilLabel;
		if ($('src-contract-soil')) $('src-contract-soil').textContent =
			flags.soil === 'nasa-power' ? 'NASA POWER' : flags.soil === 'simulated' ? 'simulated' : 'Open-Meteo';
		if ($('src-soil-sub')) $('src-soil-sub').textContent = flags.soil === 'nasa-power'
			? `NASA POWER GWETTOP (daily, ~2–5 day lag); Open-Meteo cross-check${age}`
			: flags.soil === 'open-meteo' ? `Open-Meteo 0–7 cm soil moisture (live)${age}`
			: flags.soil === 'partial' ? 'Mixed: some zones live, some simulated'
			: 'Simulated soil saturation (no live feed connected)';
		const disp = state && state.health && state.health.alert_dispatch;
		if ($('src-dispatch-status')) {
			const chans = [];
			if (disp && disp.telegram_configured) chans.push('Telegram');
			if (disp && disp.sms_configured) chans.push('SMS');
			$('src-dispatch-status').textContent = !disp ? 'CONFIGURABLE'
				: chans.length ? 'LIVE · ' + chans.join(' + ') : 'NOT CONFIGURED';
		}
		if ($('src-dispatch-sub') && disp) {
			$('src-dispatch-sub').textContent = disp.sms_configured
				? `Telegram Bot API + real SMS (${disp.sms_provider || 'textbelt'}) — env-var keys`
				: 'Telegram Bot API + SMS (Textbelt / Twilio / Fast2SMS) — env-var keys';
		}
	}
	function renderForecast(zone) {
		const cells = document.querySelectorAll('.forecast-values strong');
		// project the SAME formula forward using the Open-Meteo 6 h rainfall forecast
		if (zone && Array.isArray(zone.forecastRainfall) && zone.forecastRainfall.length) {
			const f = zone.forecastRainfall.map(num);
			const at = h => {
				const win = f.slice(0, h);
				const peak = win.length ? Math.max(num(zone.rainfall), ...win) : num(zone.rainfall);
				const rainSum = win.reduce((a, b) => a + b, 0);
				const projected = {
					...zone,
					rainfall: peak,
					accumulated: num(zone.accumulated) + rainSum,
					moisture: Math.min(100, num(zone.moisture) + Math.min(14, rainSum * 0.35))
				};
				return window.CodeNexusRisk.score(projected).risk_score;
			};
			const proj = [at(1), at(3), at(6)];
			cells.forEach((cell, i) => { if (i > 0 && proj[i - 1] != null) cell.textContent = Math.round(proj[i - 1]); });
			return;
		}
		const drift = [4, 9, 14];
		cells.forEach((cell, i) => { if (i > 0 && drift[i - 1] != null) cell.textContent = Math.round(clamp(num(zone && zone.score) + drift[i - 1], 0, 100)); });
	}
	function renderFieldVerify(zone) {
		const fv = $('field-verify'); if (!fv) return;
		// backend ground-truth override (from /api/risk) takes precedence over the
		// client-side offline adjustment.
		const gt = zone.ground_truth;
		if (gt) {
			fv.hidden = false;
			const ds = num(gt.delta_score), dc = num(gt.delta_confidence);
			const verb = gt.overridden ? 'overridden by verified field report' : 'adjusted by field report';
			fv.innerHTML = `<b>GROUND TRUTH — score ${verb}</b> — ${gt.note || 'field observation'}`
				+ ` (${ds >= 0 ? '+' : ''}${ds} to score, ${dc >= 0 ? '+' : ''}${dc} confidence`
				+ `${gt.location ? ' · ' + gt.location : ''})`;
			return;
		}
		if (zone.fieldAdjust) {
			fv.hidden = false;
			const ds = num(zone.fieldAdjust.score), dc = num(zone.fieldAdjust.confidence);
			fv.innerHTML = `<b>Adjusted by field verification at ${zone.fieldAdjust.at || '—'}</b> — ${zone.fieldAdjust.note || 'field observation'} (${ds >= 0 ? '+' : ''}${ds} to score, +${dc} confidence)`;
		} else { fv.hidden = true; }
	}
	function explanation(zone) { if (zone.level === 'Critical') return 'Extreme rainfall and near-saturated soil are pushing this steep, susceptible corridor into critical risk.'; if (zone.level === 'High') return 'Heavy rainfall and rising soil saturation are raising risk on highly susceptible terrain.'; return 'Conditions remain below the high-risk threshold while terrain susceptibility and exposure are monitored.'; }
	function renderComparison(state) {
		const body = $('ai-comparison-body'); if (!body) return;
		const comparison = state.mlComparison;
		if (!comparison) {
			const z = current(state) || {};
			if ($('ai-review-badge')) { $('ai-review-badge').textContent = 'BASELINE ONLY'; $('ai-review-badge').className = 'comparison-badge agree'; }
			body.innerHTML = `<div class="comparison-scores"><span>PHYSICS-BASED SCORE <b>${Math.round(num(z.score))} · ${safeLevel(z)}</b></span><span>CONFIDENCE <b>${Math.round(num(z.confidence, 0))}%</b></span></div><p>The ML cross-check runs when the API is reachable.</p>`;
			return;
		}
		const model = comparison.model; const baseline = comparison.baseline;
		const agrees = comparison.comparison.agrees;
		$('ai-review-badge').textContent = agrees ? 'ML AGREES' : 'ML DISAGREES — REVIEW';
		$('ai-review-badge').className = `comparison-badge ${agrees ? 'agree' : 'review'}`;
		body.innerHTML =
			`<div class="comparison-scores">`
			+ `<span>PHYSICS-BASED <b>${baseline.risk_score} · ${baseline.risk_level}</b></span>`
			+ `<span>ML PREDICTION <b>${model.prediction} · ${model.confidence}% conf</b></span>`
			+ `</div>`
			+ `<p><b>${model.name || 'ML model'}:</b> ${model.explanation}</p>`
			+ `<p class="ai-drivers-head">Top ML factors</p>`
			+ `<div class="ai-drivers">${(model.top_drivers || []).slice(0, 3).map(driver => `<span>${driver.name}<b>${driver.importance}%</b></span>`).join('')}</div>`;
	}
	// the SAME four factors and weights the score is built from
	function factors(zone) {
		const cf = Array.isArray(zone.contributing_factors) && zone.contributing_factors.length
			? zone.contributing_factors
			: window.CodeNexusRisk.factors(zone);
		return cf.map(f => ({
			label: f.name,
			value: `${Math.round(num(f.value))}/100`,
			weight: `w ${Number(f.weight).toFixed(2)} → ${num(f.contribution).toFixed(1)} pts`
		}));
	}
	function renderChanges(zone, previous, state) {
		const now = (state && state.lastUpdated) || new Date();
		const since = new Date(now.getTime() - 15 * 60000).toLocaleTimeString('en-IN', { hour12:false, hour:'2-digit', minute:'2-digit' });
		const score = Math.round(num(zone && zone.score));
		const rainfall = num(zone && zone.rainfall);
		const prevScore = (previous && Number.isFinite(num(previous.score)) && Math.round(num(previous.score)) !== score) ? Math.round(num(previous.score)) : Math.max(0, score - 6);
		const prevRain = (previous && num(previous.rainfall) > 0 && num(previous.rainfall) !== rainfall) ? num(previous.rainfall) : (rainfall / 1.18) || 1;
		const rainPct = prevRain > 0 ? Math.round((rainfall - prevRain) / prevRain * 100) : 0;
		const reports = (state && state.reports) || [];
		const line3 = zone.fieldAdjust
			? { text:`1 new field report from ${zone.fieldAdjust.location} — ${String(zone.fieldAdjust.severity || '').toLowerCase()} severity`, tone:'up' }
			: { text:`${reports.length} field report${reports.length === 1 ? '' : 's'} in the verification queue`, tone:'steady' };
		const lines = [
			{ text:`Risk score ${prevScore} to ${score} since ${since}`, tone: score > prevScore ? 'risk' : (score < prevScore ? 'down' : 'steady') },
			{ text: rainPct >= 0 ? `Rainfall up ${rainPct} percent in the last hour` : `Rainfall down ${Math.abs(rainPct)} percent in the last hour`, tone: rainPct > 0 ? 'up' : 'steady' },
			line3
		];
		$('changes-list').innerHTML = lines.map(l => `<div class="change-line ${l.tone}"><span>▸</span> ${l.text}</div>`).join('');
	}
	// people, rounded and labelled as an estimate — never a spurious-precision figure
	function roundK(people) {
		const k = num(people) / 1000;
		if (k >= 10) return `≈${Math.round(k)}K`;
		if (k >= 1) return `≈${(Math.round(k * 2) / 2).toFixed(1)}K`;
		return `≈${Math.max(0, Math.round(people / 100) * 100)}`;
	}
	function renderExposure(zone) {
		const exposure = num(zone && zone.exposure);
		const assets = (AppState.infrastructure || []).filter(asset => asset.zone_id === (zone && zone.id));
		const assetPop = assets.reduce((sum, asset) => sum + num(asset.population_served), 0);
		// per-zone census-based estimate (zones.json), then asset registry, then index
		const zonePop = num(zone && zone.population);
		const exposedEl = $('exposed-population');
		if (exposedEl) {
			const val = zonePop || assetPop || exposure * 150;
			exposedEl.textContent = roundK(val);
			const label = exposedEl.nextElementSibling;
			if (label) label.textContent = zonePop ? 'People · census estimate (Phase 2: WorldPop)'
				: assets.length ? 'People · from asset registry' : 'People · index-based estimate';
		}
		$('roads-at-risk').textContent = String(assets.filter(asset => asset.type === 'road').length || Math.max(1, Math.round(exposure / 28))).padStart(2,'0');
		$('villages-count').textContent = String(assets.filter(asset => asset.type === 'village').length || Math.max(2, Math.round(exposure / 12))).padStart(2,'0');
		$('infrastructure-count').textContent = String(assets.filter(asset => asset.criticality === 'Critical' || asset.type === 'bridge').length || Math.max(1, Math.round(exposure / 22))).padStart(2,'0');
		const headline = $('exposed-headline');
		if (headline) {
			const zoneSum = (AppState.zones || []).reduce((s, z) => s + num(z.population), 0);
			const assetSum = (AppState.infrastructure || []).reduce((sum, asset) => sum + num(asset.population_served), 0);
			const idxSum = (AppState.zones || []).reduce((s, z) => s + num(z.exposure) * 150, 0);
			headline.textContent = roundK(zoneSum || assetSum || idxSum);
			const em = headline.nextElementSibling;
			if (em) em.textContent = zoneSum ? 'Census estimate · Phase 2: WorldPop / OSM'
				: assetSum ? 'Modelled · asset registry' : 'Modelled · exposure index';
		}
	}
	function renderZones(state) { const list = document.getElementById('zone-list'); if (!list) return; list.innerHTML = (state.zones || []).map(zone => `<div class="zone-row ${zone.id === state.selectedZoneId ? 'selected' : ''}" data-zone="${zone.id}"><i class="dot ${levelClass(safeLevel(zone))}"></i><span>${zone.name || '—'}</span><strong>${Math.round(num(zone.score))}</strong></div>`).join(''); document.querySelectorAll('[data-zone]').forEach(item => item.addEventListener('click', () => actions.selectZone(item.dataset.zone))); }
	// ONE definition of "an active alert", used by the nav badge, the Situation
	// Room event stream AND the Alert register — always derived from state.zones
	// (the single source of truth for scores), enriched with the server's alert
	// detail where available. Guarantees the badge count == register row count.
	const ALERT_LEVELS = ['Advisory', 'High', 'Critical'];
	function activeAlerts(state) {
		const byZone = {};
		(state.alerts || []).forEach(a => { if (a && a.zone_id) byZone[a.zone_id] = a; });
		return (state.zones || [])
			.filter(zone => ALERT_LEVELS.includes(safeLevel(zone)))
			.sort((a, b) => num(b.score) - num(a.score))
			.map(zone => {
				const level = safeLevel(zone);
				const server = byZone[zone.id];
				return {
					zone_id: zone.id,
					level,
					title: (server && server.title) || `${level} risk detected`,
					reason: (server && server.reason) || zone.name,
					recommended_action: server && server.recommended_action,
					risk_score: Math.round(num(zone.score))
				};
			});
	}
	function renderAlerts(state) {
		state.acks = state.acks || {};
		const alerts = activeAlerts(state);
		$('alert-count').textContent = String(alerts.length).padStart(2, '0');
		$('alert-list').innerHTML = (alerts.length ? alerts : [{ title:'No active escalation', level:'Monitoring', risk_score:0 }]).slice(0, 3).map(alert => {
			const key = `${alert.zone_id || alert.title}|${alert.level}`;
			const ack = state.acks[key];
			const control = alert.risk_score
				? (ack
					? `<button class="ack-btn done" disabled>ACK · ${ack.by} · ${ack.at}</button>`
					: `<button class="ack-btn" data-ack="${key}">Acknowledge</button>`)
				: '';
			return `<div class="alert-row${ack ? ' acknowledged' : ''}"><i class="dot ${levelClass(alert.level)}"></i><div><strong>${alert.title}</strong><small>${alert.reason || 'All zones remain below threshold'}${alert.risk_score ? ` · Risk ${alert.risk_score}` : ''}</small>${control}</div><b>${alert.risk_score ? alert.level.toUpperCase() : 'CLEAR'}</b></div>`;
		}).join('');
		document.querySelectorAll('#alert-list [data-ack]').forEach(btn => btn.addEventListener('click', () => {
			state.acks[btn.dataset.ack] = { by:'Duty Officer', at:new Date().toLocaleTimeString('en-IN', { hour12:false, hour:'2-digit', minute:'2-digit' }) };
			if (actions && actions.persistAcks) actions.persistAcks();
			renderAlerts(state);
			if (actions && actions.showToast) actions.showToast('Alert acknowledged by Duty Officer.');
		}));
	}
	function renderPriority(state) { const priority = [...(state.zones || [])].sort((a,b) => (num(b.score) * .65 + num(b.exposure) * .35) - (num(a.score) * .65 + num(a.exposure) * .35)); $('priority-list').innerHTML = priority.slice(0,3).map((zone,index) => { const lvl = safeLevel(zone); return `<div class="priority-row"><strong>0${index + 1}</strong><div><b>${zone.name || '—'}</b><small>${lvl.toUpperCase()} · ${Math.round(num(zone.exposure))}% exposure</small></div><em>${lvl === 'Critical' || lvl === 'High' ? 'VERIFY NOW' : 'MONITOR'}</em></div>`; }).join(''); }
	function renderIntelligence(state) { $('intelligence-zone-list').innerHTML = (state.zones || []).map(zone => `<div class="intelligence-zone" data-zone-intel="${zone.id}"><i class="dot ${levelClass(safeLevel(zone))}"></i><span>${zone.name || '—'}</span><b>${Math.round(num(zone.score))}</b></div>`).join(''); document.querySelectorAll('[data-zone-intel]').forEach(item => item.addEventListener('click', () => actions.selectZone(item.dataset.zoneIntel))); const zone = current(state) || {}; $('intelligence-detail').innerHTML = `<p class="kicker">SELECTED ZONE / ${String(zone.district || '—').toUpperCase()}</p><h2>${zone.name || '—'}</h2><p>${explanation(zone)}</p><div class="factor-list">${factors(zone).map(item => `<div class="factor"><span>${item.label}</span><strong>${item.value}<b>${item.weight}</b></strong></div>`).join('')}</div>`; }
	function renderAlertsPage(state) {
		// Same activeAlerts() set as the nav badge and the event stream, so the
		// register row count can never disagree with "Alerts NN".
		const all = (state.zones || []);
		const alertIds = new Set(activeAlerts(state).map(a => a.zone_id));
		const alerting = all.filter(z => alertIds.has(z.id)).sort((a, b) => num(b.score) - num(a.score));
		const belowCount = all.length - alerting.length;
		$('all-alerts').innerHTML = (alerting.length
			? alerting.map(zone => `<div class="all-alert-row"><i class="dot ${levelClass(safeLevel(zone))}"></i><div><strong>${zone.name || '—'}</strong><small>Risk ${Math.round(num(zone.score))} · ${num(zone.rainfall).toFixed(1)} mm/hr · ${Math.round(num(zone.moisture))}% soil moisture</small></div><b>${safeLevel(zone).toUpperCase()}</b></div>`).join('')
			: '<div class="all-alert-row"><i class="dot monitoring"></i><div><strong>No zones at alert level</strong><small>All monitored zones are below the Advisory threshold</small></div><b>CLEAR</b></div>')
			+ (belowCount ? `<div class="all-alert-row" style="opacity:.6"><i class="dot monitoring"></i><div><small>${belowCount} zone${belowCount === 1 ? '' : 's'} below Advisory — not listed</small></div></div>` : '');
		$('all-priority').innerHTML = all.slice().sort((a, b) => num(b.score) - num(a.score)).map((zone, index) => { const lvl = safeLevel(zone); return `<div class="all-alert-row"><strong>0${index + 1}</strong><div><strong>${zone.name || '—'}</strong><small>${Math.round(num(zone.exposure))}% exposure</small></div><b>${lvl === 'Critical' || lvl === 'High' ? 'IMMEDIATE VERIFICATION' : 'MONITOR'}</b></div>`; }).join('');
	}
	// keep the field-report Location dropdown in sync with the real zone list
	function syncReportLocations(state) {
		const sel = $('report-location'); if (!sel) return;
		const zones = (state && state.zones) || [];
		if (!zones.length) return;
		const want = zones.map(z => z.id).join(',');
		if (sel.dataset.zoneKey === want) return;
		const keep = sel.value;
		sel.innerHTML = zones.map(z => `<option value="${z.id}">${z.name}</option>`).join('');
		sel.dataset.zoneKey = want;
		if (zones.some(z => z.id === keep)) sel.value = keep;
		else if (state.selectedZoneId) sel.value = state.selectedZoneId;
	}
	function evidenceHtml(report) {
		const data = report.media_data;
		if (!data || typeof data !== 'string') return '';
		if (String(report.media_type || data.slice(5, 20)).startsWith('image')) {
			return `<a class="report-thumb" href="${data}" target="_blank" rel="noopener" title="${report.media_name || 'evidence'}"><img src="${data}" alt="field evidence"></a>`;
		}
		return `<a class="report-file" href="${data}" download="${report.media_name || 'evidence'}">📎 ${report.media_name || 'evidence file'}</a>`;
	}
	function renderReports(state) {
		syncReportLocations(state);
		$('report-list').innerHTML = (state.reports || []).map(report => {
			const isSeed = report.seed === true || report.is_seed === 1 || report.is_seed === true;
			const tag = isSeed ? ' <span class="seed-tag">DEMO</span>' : '';
			return `<div class="report-row${isSeed ? ' is-seed' : ''}">${evidenceHtml(report)}<div><strong>${report.location || '—'}${tag}</strong><small>${report.observation || ''}</small><small>${report.time || '—'} · ${report.status || 'Submitted'}</small></div><select class="report-status" data-report-id="${report.id ?? ''}" aria-label="Update report status"><option ${report.status === 'Submitted' ? 'selected' : ''}>Submitted</option><option ${report.status === 'Under review' ? 'selected' : ''}>Under review</option><option ${report.status === 'Verified' ? 'selected' : ''}>Verified</option><option ${report.status === 'Rejected' ? 'selected' : ''}>Rejected</option></select><b>${String(report.severity || 'Advisory').toUpperCase()}</b></div>`;
		}).join('');
		document.querySelectorAll('.report-status[data-report-id]').forEach(select => select.addEventListener('change', () => actions.updateReport(select.dataset.reportId, select.value)));
	}
	function readFileAsDataURL(file) {
		return new Promise((resolve, reject) => {
			const fr = new FileReader();
			fr.onload = () => resolve(fr.result);
			fr.onerror = () => reject(fr.error);
			fr.readAsDataURL(file);
		});
	}
	async function submitReport(event) {
		event.preventDefault();
		const media = $('report-media').files[0];
		const sel = $('report-location');
		const zoneId = (sel && sel.value) || AppState.selectedZoneId;
		const locationName = (sel && sel.selectedOptions[0] && sel.selectedOptions[0].textContent) || zoneId;
		let mediaData = null;
		if (media) {
			if (media.size > 2 * 1024 * 1024) { actions.showToast('Evidence file too large (max 2 MB).'); return; }
			try { mediaData = await readFileAsDataURL(media); } catch (e) { mediaData = null; }
		}
		const report = { zone_id: zoneId, location: locationName, observation: $('report-observation').value || 'Ground observation submitted for review.', severity: $('report-severity').value, timestamp: new Date().toISOString(), status: 'Under review', media_type: media ? media.type : null, media_name: media ? media.name : null, media_data: mediaData };
		if (navigator.geolocation) await new Promise(resolve => navigator.geolocation.getCurrentPosition(position => { report.latitude = position.coords.latitude; report.longitude = position.coords.longitude; report.accuracy_m = position.coords.accuracy; resolve(); }, resolve, { enableHighAccuracy: true, timeout: 5000, maximumAge: 60000 }));
		await actions.submitReport(report);
		$('report-observation').value = '';
		if ($('report-media')) $('report-media').value = '';
		renderReports(AppState);
		actions.showToast(`Field report logged for ${locationName}${mediaData ? ' with evidence' : ''}.`);
	}
	return { init, render, renderIntelligence, renderAlertsPage, renderReports, renderSources };
})();