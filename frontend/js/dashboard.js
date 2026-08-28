const Dashboard = (() => {
	let actions;
	const $ = id => document.getElementById(id);
	const current = state => (state && state.zones || []).find(zone => zone.id === state.selectedZoneId) || (state && state.zones || [])[0] || null;
	const levelClass = level => String(level || 'monitoring').toLowerCase();
	function init(callbacks) {
		actions = callbacks;
		document.querySelectorAll('.nav-item').forEach(item => item.addEventListener('click', () => actions.switchView(item.dataset.view)));
		document.querySelectorAll('[data-view-target]').forEach(item => item.addEventListener('click', () => actions.switchView(item.dataset.viewTarget)));
		$('demo-button').addEventListener('click', runDemo); $('refresh-button').addEventListener('click', () => actions.applyScenario('Normal')); $('zone-details-button').addEventListener('click', () => actions.switchView('intelligence')); $('report-form').addEventListener('submit', submitReport); if (!$('report-media')) { const label = document.createElement('label'); label.textContent = 'EVIDENCE PHOTO / VIDEO'; label.innerHTML += '<input id="report-media" type="file" accept="image/*,video/*">'; $('report-form').insertBefore(label, $('report-form').querySelector('.brief-action')); } if (!$('ai-comparison')) { const panel = document.createElement('section'); panel.id = 'ai-comparison'; panel.className = 'ai-comparison panel'; panel.innerHTML = '<div class="section-head"><div><p class="kicker">DECISION SUPPORT</p><h2>AI vs baseline</h2></div><span id="ai-review-badge" class="comparison-badge">SYNCING</span></div><div id="ai-comparison-body"></div>'; document.querySelector('.incident-brief')?.after(panel); }
	}
	function runDemo() { const button = $('demo-button'); button.disabled = true; button.innerHTML = '<span>●</span> Monitoring escalation'; actions.applyScenario('Normal'); setTimeout(() => actions.applyScenario('Heavy Rain'), 1500); setTimeout(() => actions.applyScenario('Extreme Rain'), 3300); setTimeout(() => { button.disabled = false; button.innerHTML = '<span>▶</span> Run escalation demo'; }, 5100); }
	const num = (v, d = 0) => { const n = Number(v); return Number.isFinite(n) ? n : d; };
	function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, num(v))); }
	function levelOf(score) { const s = num(score); return s >= 75 ? 'Critical' : s >= 55 ? 'High' : s >= 36 ? 'Advisory' : 'Monitoring'; }
	function safeLevel(zone) { return zone && typeof zone.level === 'string' ? zone.level : levelOf(zone && zone.score); }
	function animateNumber(element, value, decimals = 0) { if (!element) return; const start = num(element.dataset.value ?? String(element.textContent).replace(/[^0-9.-]/g, '')); const end = num(value); if (!Number.isFinite(end)) { element.textContent = decimals ? (0).toFixed(decimals) : '0'; element.dataset.value = 0; return; } if (Math.abs(start - end) < .01) { element.textContent = decimals ? end.toFixed(decimals) : Math.round(end); element.dataset.value = end; return; } const began = performance.now(); element.classList.add('changing'); const tick = now => { const progress = Math.min(1, (now - began) / 600); const eased = 1 - Math.pow(1 - progress, 3); element.textContent = decimals ? (start + (end - start) * eased).toFixed(decimals) : Math.round(start + (end - start) * eased); element.dataset.value = end; if (progress < 1) requestAnimationFrame(tick); else element.classList.remove('changing'); }; requestAnimationFrame(tick); }
	function animateGauge(element, score) { if (!element) return; const target = clamp(score, 0, 100); const start = num(element.dataset.score); const began = performance.now(); const tick = now => { const progress = Math.min(1, (now - began) / 700); const eased = 1 - Math.pow(1 - progress, 3); const value = clamp(start + (target - start) * eased, 0, 100); element.style.background = `conic-gradient(${target >= 75 ? 'var(--red)' : target >= 55 ? 'var(--orange)' : 'var(--amber)'} 0 ${value}%, #e2ebea ${value}% 100%)`; element.dataset.score = value; if (progress < 1) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }
	function render(state) {
		const zones = (state.zones || []).map(z => ({ ...z, score: num(z && z.score), confidence: num(z && z.confidence, 75), level: safeLevel(z) }));
		const zone = zones.find(z => z.id === state.selectedZoneId) || zones[0] || { name:'—', district:'—', score:0, confidence:0, level:'Monitoring', coordinates:[0,0] };
		const previous = (state.previousZones || []).find(item => item.id === zone.id) || zone;
		const regional = zones.length ? Math.round(zones.reduce((sum, item) => sum + num(item.score), 0) / zones.length) : 0;
		const activeAlerts = (state.alerts && state.alerts.length) ? state.alerts.length : zones.filter(item => item.level === 'High' || item.level === 'Critical').length;
		$('updated-time').textContent = state.lastUpdated.toLocaleTimeString('en-IN', { hour12:false });
		$('clock').textContent = `${state.lastUpdated.toLocaleTimeString('en-IN', { hour12:false })} IST`;
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
		animateNumber($('rainfall-value'), num(zone.rainfall), 1);
		animateNumber($('moisture-value'), num(zone.moisture));
		animateNumber($('temperature-value'), num(zone.temperature), 1);
		animateNumber($('accumulated-value'), num(zone.accumulated) + num(state.rainfallBoost) * 1.7);
		$('forecast-now').textContent = Math.round(num(zone.score));
		const co = Array.isArray(zone.coordinates) ? zone.coordinates : [0, 0];
		$('coordinates').textContent = `${num(co[0]).toFixed(4)}° N, ${num(co[1]).toFixed(4)}° E`;
		$('risk-explanation').textContent = explanation(zone);
		renderBreakdown(zone); renderSparklines(zone); renderTelemetryMeta(zone, state); renderForecast(zone); renderFieldVerify(zone); renderComparison({ ...state, zones });
		const feed = document.querySelector('.nav-feed'); if (feed) feed.innerHTML = `<i class="dot ${state.backendConnected ? 'green' : 'cyan'}"></i> ${state.backendConnected ? 'Flask API connected' : 'Offline prototype mode'}`;
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
	function renderBreakdown(zone) {
		const el = $('factor-list'); if (!el) return;
		el.className = 'factors risk-breakdown';
		const parts = breakdownParts(zone);
		const rows = parts.map(p => `<div class="rb-row"><span class="rb-label">${p.label}</span><span class="rb-val">${p.pts} pts</span><i class="rb-bar"><em style="width:${clamp(p.pts / 40 * 100, 2, 100)}%;background:${p.color}"></em></i></div>`).join('');
		const bands = [['0–35', 'Monitoring'], ['36–54', 'Advisory'], ['55–74', 'High'], ['75–100', 'Critical']];
		const mark = clamp(zone && zone.score, 0, 100);
		const scale = `<div class="rb-scale"><div class="rb-track"><span class="mon"></span><span class="adv"></span><span class="hi"></span><span class="cr"></span><b class="rb-marker" style="left:${mark}%"><i>${Math.round(mark)}</i></b></div><div class="rb-bands">${bands.map(b => `<span><b>${b[0]}</b> ${b[1]}</span>`).join('')}</div></div>`;
		el.innerHTML = `<p class="rb-head">SCORE BREAKDOWN <b>${parts.reduce((a, p) => a + p.pts, 0)} / 100</b></p>${rows}${scale}`;
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
	function renderTelemetryMeta(zone, state) {
		const live = !!(zone && zone._live);
		if (live) {
			const s = sparkSeries(zone);
			const badges = [pctBadge(s.rain), pctBadge(s.soil), pctBadge(s.temp), pctBadge(s.acc)];
			document.querySelectorAll('.telemetry-item').forEach((it, i) => {
				const b = it.querySelector('b'); if (!b || !badges[i]) return;
				b.textContent = badges[i].text;
				b.className = badges[i].cls;
			});
		}
		const feed = document.querySelector('.telemetry .feed-state');
		if (feed) {
			if (live && state && state.weatherFetchedAt) {
				const t = new Date(state.weatherFetchedAt).toLocaleTimeString('en-IN', { hour12:false, hour:'2-digit', minute:'2-digit' });
				feed.innerHTML = `<i class="dot green"></i> LIVE · Open-Meteo · Last fetched ${t}`;
			} else {
				feed.innerHTML = `<i class="dot green"></i> FEED HEALTHY`;
			}
		}
		const srcStatus = $('src-telemetry-status'), srcSub = $('src-telemetry-sub');
		if (srcStatus) srcStatus.textContent = live ? 'LIVE' : 'SIMULATED';
		if (srcSub) srcSub.textContent = live ? 'Open-Meteo Weather API — updated hourly' : 'Rainfall, moisture, temperature';
	}
	function renderForecast(zone) {
		const cells = document.querySelectorAll('.forecast-values strong');
		if (zone && zone._live && Array.isArray(zone.forecastRainfall) && zone.forecastRainfall.length) {
			const f = zone.forecastRainfall.map(num);
			const soilNow = num(zone.moisture);
			const f0 = zone.factors0 || {};
			const staticPts = Math.round(num(f0.slope, 12)) + Math.round(num(f0.historical, 6));
			const at = h => {
				const w = f.slice(0, h);
				const peak = w.length ? Math.max(...w, num(zone.rainfall)) : num(zone.rainfall);
				const soilBump = Math.min(12, w.reduce((a, b) => a + b, 0) * 0.35);
				const rp = Math.round(typeof rainfallPoints === 'function' ? rainfallPoints(peak) : 0);
				const sp = Math.round(typeof soilPoints === 'function' ? soilPoints(Math.min(100, soilNow + soilBump)) : 0);
				return clamp(rp + sp + staticPts, 0, 100);
			};
			const proj = [at(1), at(3), at(6)];
			cells.forEach((cell, i) => { if (i > 0 && proj[i - 1] != null) cell.textContent = Math.round(proj[i - 1]); });
			return;
		}
		const proj = [4, 9, 14];
		cells.forEach((cell, i) => { if (i > 0 && proj[i - 1] != null) cell.textContent = Math.round(clamp(num(zone && zone.score) + proj[i - 1], 0, 100)); });
	}
	function renderFieldVerify(zone) {
		const fv = $('field-verify'); if (!fv) return;
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
			if ($('ai-review-badge')) { $('ai-review-badge').textContent = 'BASELINE'; $('ai-review-badge').className = 'comparison-badge agree'; }
			body.innerHTML = `<div class="comparison-scores"><span>BASELINE ENGINE <b>${Math.round(num(z.score))} · ${safeLevel(z)}</b></span><span>MODEL CONFIDENCE <b>${Math.round(num(z.confidence, 0))}%</b></span></div><p>Explainable rainfall-trigger engine is active. The learned comparison model runs when the API backend is connected.</p>`;
			return;
		}
		const model = comparison.model; const baseline = comparison.baseline;
		$('ai-review-badge').textContent = comparison.comparison.agrees ? 'AGREEMENT' : 'REVIEW REQUIRED';
		$('ai-review-badge').className = `comparison-badge ${comparison.comparison.agrees ? 'agree' : 'review'}`;
		body.innerHTML = `<div class="comparison-scores"><span>BASELINE <b>${baseline.risk_score} · ${baseline.risk_level}</b></span><span>AI MODEL <b>${model.prediction} · ${model.confidence}%</b></span></div><p>${model.explanation}</p><div class="ai-drivers">${model.top_drivers.map(driver => `<span>${driver.name}<b>${driver.importance}%</b></span>`).join('')}</div>`;
	}
	function factors(zone) { return [{ label:'Rainfall pressure', value:`${Math.min(100, Math.round(num(zone.rainfall) * 1.7))}%`, weight:'+22%' }, { label:'Soil saturation', value:`${Math.round(num(zone.moisture))}%`, weight:'+16%' }, { label:'Terrain susceptibility', value:`${Math.round(num(zone.susceptibility))}%`, weight:'+16%' }, { label:'Historical susceptibility', value:`${Math.round(num(zone.history))}%`, weight:'+8%' }]; }
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
	function renderExposure(zone) { const exposure = num(zone && zone.exposure); const assets = (AppState.infrastructure || []).filter(asset => asset.zone_id === (zone && zone.id)); $('exposed-population').textContent = assets.length ? `${(assets.reduce((sum, asset) => sum + num(asset.population_served), 0) / 1000).toFixed(1)}K` : `${(exposure * .15).toFixed(1)}K`; $('roads-at-risk').textContent = String(assets.filter(asset => asset.type === 'road').length || Math.max(1, Math.round(exposure / 28))).padStart(2,'0'); $('villages-count').textContent = String(assets.filter(asset => asset.type === 'village').length || Math.max(2, Math.round(exposure / 12))).padStart(2,'0'); $('infrastructure-count').textContent = String(assets.filter(asset => asset.criticality === 'Critical' || asset.type === 'bridge').length || Math.max(1, Math.round(exposure / 22))).padStart(2,'0'); }
	function renderZones(state) { const list = document.getElementById('zone-list'); if (!list) return; list.innerHTML = (state.zones || []).map(zone => `<div class="zone-row ${zone.id === state.selectedZoneId ? 'selected' : ''}" data-zone="${zone.id}"><i class="dot ${levelClass(safeLevel(zone))}"></i><span>${zone.name || '—'}</span><strong>${Math.round(num(zone.score))}</strong></div>`).join(''); document.querySelectorAll('[data-zone]').forEach(item => item.addEventListener('click', () => actions.selectZone(item.dataset.zone))); }
	function renderAlerts(state) {
		state.acks = state.acks || {};
		const alerts = (state.alerts && state.alerts.length) ? state.alerts : (state.zones || []).filter(zone => safeLevel(zone) === 'High' || safeLevel(zone) === 'Critical').map(zone => ({ zone_id:zone.id, level:safeLevel(zone), title:`${safeLevel(zone)} risk detected`, reason:zone.name, risk_score:Math.round(num(zone.score)) }));
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
			renderAlerts(state);
			if (actions && actions.showToast) actions.showToast('Alert acknowledged by Duty Officer.');
		}));
	}
	function renderPriority(state) { const priority = [...(state.zones || [])].sort((a,b) => (num(b.score) * .65 + num(b.exposure) * .35) - (num(a.score) * .65 + num(a.exposure) * .35)); $('priority-list').innerHTML = priority.slice(0,3).map((zone,index) => { const lvl = safeLevel(zone); return `<div class="priority-row"><strong>0${index + 1}</strong><div><b>${zone.name || '—'}</b><small>${lvl.toUpperCase()} · ${Math.round(num(zone.exposure))}% exposure</small></div><em>${lvl === 'Critical' || lvl === 'High' ? 'VERIFY NOW' : 'MONITOR'}</em></div>`; }).join(''); }
	function renderIntelligence(state) { $('intelligence-zone-list').innerHTML = (state.zones || []).map(zone => `<div class="intelligence-zone" data-zone-intel="${zone.id}"><i class="dot ${levelClass(safeLevel(zone))}"></i><span>${zone.name || '—'}</span><b>${Math.round(num(zone.score))}</b></div>`).join(''); document.querySelectorAll('[data-zone-intel]').forEach(item => item.addEventListener('click', () => actions.selectZone(item.dataset.zoneIntel))); const zone = current(state) || {}; $('intelligence-detail').innerHTML = `<p class="kicker">SELECTED ZONE / ${String(zone.district || '—').toUpperCase()}</p><h2>${zone.name || '—'}</h2><p>${explanation(zone)}</p><div class="factor-list">${factors(zone).map(item => `<div class="factor"><span>${item.label}</span><strong>${item.value}<b>${item.weight}</b></strong></div>`).join('')}</div>`; }
	function renderAlertsPage(state) { $('all-alerts').innerHTML = (state.zones || []).map(zone => `<div class="all-alert-row"><i class="dot ${levelClass(safeLevel(zone))}"></i><div><strong>${zone.name || '—'}</strong><small>Risk ${Math.round(num(zone.score))} · ${num(zone.rainfall).toFixed(1)} mm/hr · ${Math.round(num(zone.moisture))}% soil moisture</small></div><b>${safeLevel(zone).toUpperCase()}</b></div>`).join(''); $('all-priority').innerHTML = (state.zones || []).slice().sort((a,b) => num(b.score) - num(a.score)).map((zone,index) => { const lvl = safeLevel(zone); return `<div class="all-alert-row"><strong>0${index+1}</strong><div><strong>${zone.name || '—'}</strong><small>${Math.round(num(zone.exposure))}% exposure</small></div><b>${lvl === 'Critical' || lvl === 'High' ? 'IMMEDIATE VERIFICATION' : 'MONITOR'}</b></div>`; }).join(''); }
	function renderReports(state) { $('report-list').innerHTML = (state.reports || []).map(report => `<div class="report-row"><div><strong>${report.location || '—'}</strong><small>${report.observation || ''}</small><small>${report.time || '—'} · ${report.status || 'Submitted'}</small></div><select class="report-status" data-report-id="${report.id || ''}" aria-label="Update report status"><option ${report.status === 'Submitted' ? 'selected' : ''}>Submitted</option><option ${report.status === 'Under review' ? 'selected' : ''}>Under review</option><option ${report.status === 'Verified' ? 'selected' : ''}>Verified</option><option ${report.status === 'Rejected' ? 'selected' : ''}>Rejected</option></select><b>${String(report.severity || 'Advisory').toUpperCase()}</b></div>`).join(''); document.querySelectorAll('.report-status[data-report-id]').forEach(select => select.addEventListener('change', () => actions.updateReport(Number(select.dataset.reportId), select.value))); }
	async function submitReport(event) { event.preventDefault(); const media = $('report-media').files[0]; const report = { zone_id:AppState.selectedZoneId, location:$('report-location').value, observation:$('report-observation').value || 'Ground observation submitted for review.', severity:$('report-severity').value, timestamp:new Date().toISOString(), status:'Under review', media_type:media ? media.type : null, media_name:media ? media.name : null }; if (navigator.geolocation) await new Promise(resolve => navigator.geolocation.getCurrentPosition(position => { report.latitude = position.coords.latitude; report.longitude = position.coords.longitude; report.accuracy_m = position.coords.accuracy; resolve(); }, resolve, { enableHighAccuracy:true, timeout:5000, maximumAge:60000 })); await actions.submitReport(report); $('report-form').reset(); renderReports(AppState); actions.showToast('Field report entered into the verification queue.'); }
	return { init, render, renderIntelligence, renderAlertsPage, renderReports };
})();