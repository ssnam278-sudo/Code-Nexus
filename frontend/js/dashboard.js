const Dashboard = (() => {
	let actions;
	const $ = id => document.getElementById(id);
	const current = state => state.zones.find(zone => zone.id === state.selectedZoneId) || state.zones[0];
	const levelClass = level => level.toLowerCase();
	function init(callbacks) {
		actions = callbacks;
		document.querySelectorAll('.nav-item').forEach(item => item.addEventListener('click', () => actions.switchView(item.dataset.view)));
		document.querySelectorAll('[data-view-target]').forEach(item => item.addEventListener('click', () => actions.switchView(item.dataset.viewTarget)));
		$('demo-button').addEventListener('click', runDemo); $('refresh-button').addEventListener('click', () => actions.applyScenario('Normal')); $('zone-details-button').addEventListener('click', () => actions.switchView('intelligence')); $('report-form').addEventListener('submit', submitReport); if (!$('report-media')) { const label = document.createElement('label'); label.textContent = 'EVIDENCE PHOTO / VIDEO'; label.innerHTML += '<input id="report-media" type="file" accept="image/*,video/*">'; $('report-form').insertBefore(label, $('report-form').querySelector('.brief-action')); } if (!$('ai-comparison')) { const panel = document.createElement('section'); panel.id = 'ai-comparison'; panel.className = 'ai-comparison panel'; panel.innerHTML = '<div class="section-head"><div><p class="kicker">DECISION SUPPORT</p><h2>AI vs baseline</h2></div><span id="ai-review-badge" class="comparison-badge">SYNCING</span></div><div id="ai-comparison-body"></div>'; document.querySelector('.incident-brief')?.after(panel); }
	}
	function runDemo() { const button = $('demo-button'); button.disabled = true; button.innerHTML = '<span>●</span> Monitoring escalation'; actions.applyScenario('Normal'); setTimeout(() => actions.applyScenario('Heavy Rain'), 1500); setTimeout(() => actions.applyScenario('Extreme Rain'), 3300); setTimeout(() => { button.disabled = false; button.innerHTML = '<span>▶</span> Run escalation demo'; }, 5100); }
	function animateNumber(element, value, decimals = 0) { const start = Number(element.dataset.value || element.textContent.replace(/[^0-9.-]/g, '')) || 0; const end = Number(value); if (Math.abs(start - end) < .01) return; const began = performance.now(); element.classList.add('changing'); const tick = now => { const progress = Math.min(1, (now - began) / 600); const eased = 1 - Math.pow(1 - progress, 3); element.textContent = decimals ? (start + (end - start) * eased).toFixed(decimals) : Math.round(start + (end - start) * eased); element.dataset.value = end; if (progress < 1) requestAnimationFrame(tick); else element.classList.remove('changing'); }; requestAnimationFrame(tick); }
	function animateGauge(element, score) { const start = Number(element.dataset.score || 0); const began = performance.now(); const tick = now => { const progress = Math.min(1, (now - began) / 700); const eased = 1 - Math.pow(1 - progress, 3); const value = start + (score - start) * eased; element.style.background = `conic-gradient(${score >= 75 ? 'var(--red)' : score >= 55 ? 'var(--orange)' : 'var(--amber)'} 0 ${value}%, #e2ebea ${value}% 100%)`; element.dataset.score = value; if (progress < 1) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }
	function render(state) { const zone = current(state); const previous = (state.previousZones || []).find(item => item.id === zone.id) || zone; const regional = Math.round(state.zones.reduce((sum, item) => sum + item.score, 0) / state.zones.length); $('updated-time').textContent = state.lastUpdated.toLocaleTimeString('en-IN', { hour12:false }); $('clock').textContent = `${state.lastUpdated.toLocaleTimeString('en-IN', { hour12:false })} IST`; animateNumber($('regional-risk'), regional); animateNumber($('active-alerts'), state.alerts.length || state.zones.filter(item => item.score >= 55).length); $('regional-status').textContent = regional >= 75 ? 'CRITICAL' : regional >= 55 ? 'HIGH' : regional >= 35 ? 'ADVISORY' : 'MONITORING'; $('highest-priority').textContent = state.zones.slice().sort((a,b) => b.score - a.score)[0].name.split(' ')[0].toUpperCase(); $('selected-zone-name').textContent = zone.name; $('selected-location').textContent = zone.district; $('selected-level').textContent = zone.level.toUpperCase(); $('selected-level').className = `level-badge ${levelClass(zone.level)}`; animateNumber($('selected-score'), zone.score); animateGauge($('score-ring'), zone.score); $('risk-reading').textContent = `${zone.level.toUpperCase()} RISK`; $('risk-reading').style.color = zone.level === 'Critical' ? 'var(--red)' : zone.level === 'High' ? 'var(--orange)' : 'var(--amber)'; $('selected-confidence').textContent = `${zone.confidence}%`; $('confidence-bar-fill').style.width = `${zone.confidence}%`; animateNumber($('rainfall-value'), zone.rainfall, 1); animateNumber($('moisture-value'), zone.moisture); animateNumber($('temperature-value'), zone.temperature, 1); animateNumber($('accumulated-value'), zone.accumulated + state.rainfallBoost * 1.7); $('forecast-now').textContent = zone.score; $('coordinates').textContent = `${zone.coordinates[0].toFixed(4)}° N, ${zone.coordinates[1].toFixed(4)}° E`; $('risk-explanation').textContent = explanation(zone); renderBreakdown(zone); renderSparklines(zone); renderForecast(zone); renderFieldVerify(zone); renderComparison(state); const feed = document.querySelector('.nav-feed'); if (feed) feed.innerHTML = `<i class="dot ${state.backendConnected ? 'green' : 'cyan'}"></i> ${state.backendConnected ? 'Flask API connected' : 'Offline prototype mode'}`; renderChanges(zone, previous, state); renderExposure(zone); renderZones(state); renderAlerts(state); renderPriority(state); renderReports(state); }
	function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
	function breakdownParts(zone) {
		const raw = [
			Math.min(72, zone.rainfall) * 1.15,
			zone.moisture * 0.62,
			((zone.slope + zone.susceptibility) / 2) * 0.42,
			zone.history * 0.34
		];
		const total = raw.reduce((a, b) => a + b, 0) || 1;
		const scaled = raw.map(v => v / total * zone.score);
		const ints = scaled.map(Math.round);
		let diff = Math.round(zone.score) - ints.reduce((a, b) => a + b, 0);
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
		const bands = [['0–30', 'Monitoring'], ['31–50', 'Advisory'], ['51–75', 'High'], ['76–100', 'Critical']];
		const mark = clamp(Math.round(zone.score), 0, 100);
		const scale = `<div class="rb-scale"><div class="rb-track"><span class="mon"></span><span class="adv"></span><span class="hi"></span><span class="cr"></span><b class="rb-marker" style="left:${mark}%"><i>${Math.round(zone.score)}</i></b></div><div class="rb-bands">${bands.map(b => `<span><b>${b[0]}</b> ${b[1]}</span>`).join('')}</div></div>`;
		el.innerHTML = `<p class="rb-head">SCORE BREAKDOWN <b>${parts.reduce((a, p) => a + p.pts, 0)} / 100</b></p>${rows}${scale}`;
	}
	function renderSparklines(zone) {
		const items = document.querySelectorAll('.telemetry-item');
		const cfg = [
			{ el:items[0], now:zone.rainfall, vol:0.20, color:'#c87422' },
			{ el:items[1], now:zone.moisture, vol:0.08, color:'#c87422' },
			{ el:items[2], now:zone.temperature, vol:0.05, color:'#378b5b' },
			{ el:items[3], now:zone.accumulated, vol:0.05, color:'#c87422' }
		];
		cfg.forEach(s => {
			if (!s.el) return;
			const spark = s.el.querySelector('.sparkline'); if (!spark) return;
			const n = 24, pts = [];
			for (let i = 0; i < n; i++) {
				const t = i / (n - 1);
				const base = s.now * (0.72 + 0.28 * t);
				const noise = Math.sin(i * 1.7 + s.now) * s.now * s.vol * (0.35 + 0.65 * t);
				pts.push(Math.max(0, base + noise));
			}
			const min = Math.min(...pts), max = Math.max(...pts), rng = (max - min) || 1;
			const W = 100, H = 17;
			const d = pts.map((v, i) => `${(i / (n - 1) * W).toFixed(1)},${(H - (v - min) / rng * (H - 3) - 1.5).toFixed(1)}`).join(' ');
			spark.classList.add('spark-svg');
			spark.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><polyline points="${d}" fill="none" stroke="${s.color}" stroke-width="1.3" vector-effect="non-scaling-stroke"/></svg>`;
		});
	}
	function renderForecast(zone) {
		const cells = document.querySelectorAll('.forecast-values strong');
		const proj = [4, 9, 14];
		cells.forEach((cell, i) => { if (i > 0 && proj[i - 1] != null) cell.textContent = clamp(Math.round(zone.score) + proj[i - 1], 0, 100); });
	}
	function renderFieldVerify(zone) {
		const fv = $('field-verify'); if (!fv) return;
		if (zone.fieldAdjust) {
			fv.hidden = false;
			const sign = zone.fieldAdjust.score >= 0 ? '+' : '';
			fv.innerHTML = `<b>Adjusted by field verification at ${zone.fieldAdjust.at}</b> — ${zone.fieldAdjust.note} (${sign}${zone.fieldAdjust.score} to score, +${zone.fieldAdjust.confidence} confidence)`;
		} else { fv.hidden = true; }
	}
	function explanation(zone) { if (zone.level === 'Critical') return 'Extreme rainfall and near-saturated soil are pushing this steep, susceptible corridor into critical risk.'; if (zone.level === 'High') return 'Heavy rainfall and rising soil saturation are raising risk on highly susceptible terrain.'; return 'Conditions remain below the high-risk threshold while terrain susceptibility and exposure are monitored.'; }
	function renderComparison(state) {
		const body = $('ai-comparison-body'); if (!body) return;
		const comparison = state.mlComparison;
		if (!comparison) {
			const z = current(state);
			if ($('ai-review-badge')) { $('ai-review-badge').textContent = 'BASELINE'; $('ai-review-badge').className = 'comparison-badge agree'; }
			body.innerHTML = `<div class="comparison-scores"><span>BASELINE ENGINE <b>${Math.round(z.score)} · ${z.level}</b></span><span>MODEL CONFIDENCE <b>${z.confidence}%</b></span></div><p>Explainable rainfall-trigger engine is active. The learned comparison model runs when the API backend is connected.</p>`;
			return;
		}
		const model = comparison.model; const baseline = comparison.baseline;
		$('ai-review-badge').textContent = comparison.comparison.agrees ? 'AGREEMENT' : 'REVIEW REQUIRED';
		$('ai-review-badge').className = `comparison-badge ${comparison.comparison.agrees ? 'agree' : 'review'}`;
		body.innerHTML = `<div class="comparison-scores"><span>BASELINE <b>${baseline.risk_score} · ${baseline.risk_level}</b></span><span>AI MODEL <b>${model.prediction} · ${model.confidence}%</b></span></div><p>${model.explanation}</p><div class="ai-drivers">${model.top_drivers.map(driver => `<span>${driver.name}<b>${driver.importance}%</b></span>`).join('')}</div>`;
	}
	function factors(zone) { return [{ label:'Rainfall pressure', value:`${Math.min(100, Math.round(zone.rainfall * 1.7))}%`, weight:'+22%' }, { label:'Soil saturation', value:`${Math.round(zone.moisture)}%`, weight:'+16%' }, { label:'Terrain susceptibility', value:`${zone.susceptibility}%`, weight:'+16%' }, { label:'Historical susceptibility', value:`${zone.history}%`, weight:'+8%' }]; }
	function renderChanges(zone, previous, state) {
		const now = (state && state.lastUpdated) || new Date();
		const since = new Date(now.getTime() - 15 * 60000).toLocaleTimeString('en-IN', { hour12:false, hour:'2-digit', minute:'2-digit' });
		const prevScore = (previous && previous.score !== zone.score) ? previous.score : Math.max(0, Math.round(zone.score) - 6);
		const prevRain = (previous && previous.rainfall && previous.rainfall !== zone.rainfall) ? previous.rainfall : zone.rainfall / 1.18;
		const rainPct = prevRain > 0 ? Math.round((zone.rainfall - prevRain) / prevRain * 100) : 0;
		const reports = (state && state.reports) || [];
		const line3 = zone.fieldAdjust
			? { text:`1 new field report from ${zone.fieldAdjust.location} — ${String(zone.fieldAdjust.severity || '').toLowerCase()} severity`, tone:'up' }
			: { text:`${reports.length} field report${reports.length === 1 ? '' : 's'} in the verification queue`, tone:'steady' };
		const lines = [
			{ text:`Risk score ${prevScore} to ${Math.round(zone.score)} since ${since}`, tone: Math.round(zone.score) > prevScore ? 'risk' : (Math.round(zone.score) < prevScore ? 'down' : 'steady') },
			{ text: rainPct >= 0 ? `Rainfall up ${rainPct} percent in the last hour` : `Rainfall down ${Math.abs(rainPct)} percent in the last hour`, tone: rainPct > 0 ? 'up' : 'steady' },
			line3
		];
		$('changes-list').innerHTML = lines.map(l => `<div class="change-line ${l.tone}"><span>▸</span> ${l.text}</div>`).join('');
	}
	function renderExposure(zone) { const assets = AppState.infrastructure.filter(asset => asset.zone_id === zone.id); $('exposed-population').textContent = assets.length ? `${(assets.reduce((sum, asset) => sum + asset.population_served, 0) / 1000).toFixed(1)}K` : `${(zone.exposure * .15).toFixed(1)}K`; $('roads-at-risk').textContent = String(assets.filter(asset => asset.type === 'road').length || Math.max(1, Math.round(zone.exposure / 28))).padStart(2,'0'); $('villages-count').textContent = String(assets.filter(asset => asset.type === 'village').length || Math.max(2, Math.round(zone.exposure / 12))).padStart(2,'0'); $('infrastructure-count').textContent = String(assets.filter(asset => asset.criticality === 'Critical' || asset.type === 'bridge').length || Math.max(1, Math.round(zone.exposure / 22))).padStart(2,'0'); }
	function renderZones(state) { const list = document.getElementById('zone-list'); if (!list) return; list.innerHTML = state.zones.map(zone => `<div class="zone-row ${zone.id === state.selectedZoneId ? 'selected' : ''}" data-zone="${zone.id}"><i class="dot ${levelClass(zone.level)}"></i><span>${zone.name}</span><strong>${zone.score}</strong></div>`).join(''); document.querySelectorAll('[data-zone]').forEach(item => item.addEventListener('click', () => actions.selectZone(item.dataset.zone))); }
	function renderAlerts(state) {
		state.acks = state.acks || {};
		const alerts = state.alerts.length ? state.alerts : state.zones.filter(zone => zone.score >= 55).map(zone => ({ zone_id:zone.id, level:zone.level, title:`${zone.level} risk detected`, reason:zone.name, risk_score:Math.round(zone.score) }));
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
	function renderPriority(state) { const priority = [...state.zones].sort((a,b) => b.score * .65 + b.exposure * .35 - (a.score * .65 + a.exposure * .35)); $('priority-list').innerHTML = priority.slice(0,3).map((zone,index) => `<div class="priority-row"><strong>0${index + 1}</strong><div><b>${zone.name}</b><small>${zone.level.toUpperCase()} · ${zone.exposure}% exposure</small></div><em>${zone.level === 'Critical' || zone.level === 'High' ? 'VERIFY NOW' : 'MONITOR'}</em></div>`).join(''); }
	function renderIntelligence(state) { $('intelligence-zone-list').innerHTML = state.zones.map(zone => `<div class="intelligence-zone" data-zone-intel="${zone.id}"><i class="dot ${levelClass(zone.level)}"></i><span>${zone.name}</span><b>${zone.score}</b></div>`).join(''); document.querySelectorAll('[data-zone-intel]').forEach(item => item.addEventListener('click', () => actions.selectZone(item.dataset.zoneIntel))); const zone = current(state); $('intelligence-detail').innerHTML = `<p class="kicker">SELECTED ZONE / ${zone.district.toUpperCase()}</p><h2>${zone.name}</h2><p>${explanation(zone)}</p><div class="factor-list">${factors(zone).map(item => `<div class="factor"><span>${item.label}</span><strong>${item.value}<b>${item.weight}</b></strong></div>`).join('')}</div>`; }
	function renderAlertsPage(state) { $('all-alerts').innerHTML = state.zones.map(zone => `<div class="all-alert-row"><i class="dot ${levelClass(zone.level)}"></i><div><strong>${zone.name}</strong><small>Risk ${zone.score} · ${zone.rainfall.toFixed(1)} mm/hr · ${Math.round(zone.moisture)}% soil moisture</small></div><b>${zone.level.toUpperCase()}</b></div>`).join(''); $('all-priority').innerHTML = state.zones.slice().sort((a,b) => b.score - a.score).map((zone,index) => `<div class="all-alert-row"><strong>0${index+1}</strong><div><strong>${zone.name}</strong><small>${zone.exposure}% exposure</small></div><b>${zone.level === 'Critical' || zone.level === 'High' ? 'IMMEDIATE VERIFICATION' : 'MONITOR'}</b></div>`).join(''); }
	function renderReports(state) { $('report-list').innerHTML = state.reports.map(report => `<div class="report-row"><div><strong>${report.location}</strong><small>${report.observation}</small><small>${report.time} · ${report.status}</small></div><select class="report-status" data-report-id="${report.id || ''}" aria-label="Update report status"><option ${report.status === 'Submitted' ? 'selected' : ''}>Submitted</option><option ${report.status === 'Under review' ? 'selected' : ''}>Under review</option><option ${report.status === 'Verified' ? 'selected' : ''}>Verified</option><option ${report.status === 'Rejected' ? 'selected' : ''}>Rejected</option></select><b>${report.severity.toUpperCase()}</b></div>`).join(''); document.querySelectorAll('.report-status[data-report-id]').forEach(select => select.addEventListener('change', () => actions.updateReport(Number(select.dataset.reportId), select.value))); }
	async function submitReport(event) { event.preventDefault(); const media = $('report-media').files[0]; const report = { zone_id:AppState.selectedZoneId, location:$('report-location').value, observation:$('report-observation').value || 'Ground observation submitted for review.', severity:$('report-severity').value, timestamp:new Date().toISOString(), status:'Under review', media_type:media ? media.type : null, media_name:media ? media.name : null }; if (navigator.geolocation) await new Promise(resolve => navigator.geolocation.getCurrentPosition(position => { report.latitude = position.coords.latitude; report.longitude = position.coords.longitude; report.accuracy_m = position.coords.accuracy; resolve(); }, resolve, { enableHighAccuracy:true, timeout:5000, maximumAge:60000 })); await actions.submitReport(report); $('report-form').reset(); renderReports(AppState); actions.showToast('Field report entered into the verification queue.'); }
	return { init, render, renderIntelligence, renderAlertsPage, renderReports };
})();