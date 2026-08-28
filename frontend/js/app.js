// Every displayed/derived numeric value is coerced through this: undefined / null
// / NaN / non-finite -> the supplied default (0 unless stated).
function num(value, fallback = 0) { const n = Number(value); return Number.isFinite(n) ? n : fallback; }
function levelFor(score) { const s = num(score); return s >= 75 ? 'Critical' : s >= 55 ? 'High' : s >= 36 ? 'Advisory' : 'Monitoring'; }
// Live-data band scale (Open-Meteo path): 0-30 Monitoring / 31-50 Advisory / 51-75 High / 76-100 Critical
function levelForLive(score) { const s = num(score); return s > 75 ? 'Critical' : s > 50 ? 'High' : s > 30 ? 'Advisory' : 'Monitoring'; }
function seg(x, x0, x1, y0, y1) { const t = (num(x) - x0) / ((x1 - x0) || 1); return y0 + (y1 - y0) * Math.max(0, Math.min(1, t)); }
// Real rainfall (mm/hr) -> rainfall factor points
function rainfallPoints(mm) {
	const m = Math.max(0, num(mm));
	if (m <= 5) return seg(m, 0, 5, 0, 8);
	if (m <= 15) return seg(m, 5, 15, 8, 16);
	if (m <= 30) return seg(m, 15, 30, 16, 22);
	if (m <= 50) return seg(m, 30, 50, 22, 28);
	return Math.min(35, seg(m, 50, 120, 28, 35));
}
// Real soil moisture (%) -> saturation factor points
function soilPoints(pct) {
	const p = Math.max(0, Math.min(100, num(pct)));
	if (p <= 30) return seg(p, 0, 30, 0, 6);
	if (p <= 50) return seg(p, 30, 50, 6, 12);
	if (p <= 70) return seg(p, 50, 70, 12, 18);
	if (p <= 85) return seg(p, 70, 85, 18, 24);
	return seg(p, 85, 100, 24, 30);
}

const MockAPI = (() => {
	// Each zone carries a full, real numeric shape. factors0 is the baseline point
	// breakdown and always sums to score; the live breakdown scales from it.
	const zones = [
		{ id:'tawang', name:'Tawang Corridor', district:'Tawang, Arunachal Pradesh', score:67, level:'High', confidence:84, base:46, slope:72, susceptibility:82, history:68, exposure:86, rainfall:42.6, moisture:76, temperature:19.4, accumulated:184, coordinates:[27.58,91.86], factors0:{ rainfall:24, soil:19, slope:15, historical:9 } },
		{ id:'siang', name:'East Siang Valley', district:'Pasighat, Arunachal Pradesh', score:53, level:'Advisory', confidence:71, base:38, slope:61, susceptibility:64, history:54, exposure:72, rainfall:29.8, moisture:64, temperature:22.1, accumulated:138, coordinates:[28.12,95.35], factors0:{ rainfall:18, soil:14, slope:13, historical:8 } },
		{ id:'chura', name:'Churachandpur Ridge', district:'Churachandpur, Manipur', score:41, level:'Advisory', confidence:68, base:31, slope:55, susceptibility:59, history:48, exposure:63, rainfall:18.4, moisture:51, temperature:24.7, accumulated:96, coordinates:[24.33,93.68], factors0:{ rainfall:12, soil:11, slope:12, historical:6 } },
		{ id:'garo', name:'South Garo Hills', district:'Baghmara, Meghalaya', score:35, level:'Monitoring', confidence:65, base:24, slope:43, susceptibility:42, history:35, exposure:51, rainfall:11.2, moisture:39, temperature:25.8, accumulated:67, coordinates:[25.47,90.62], factors0:{ rainfall:10, soil:9, slope:11, historical:5 } },
		{ id:'bomdila', name:'Bomdila Pass', district:'West Kameng, Arunachal Pradesh', score:19, level:'Monitoring', confidence:78, base:16, slope:38, susceptibility:34, history:25, exposure:32, rainfall:7.4, moisture:29, temperature:14.8, accumulated:42, coordinates:[27.26,92.40], factors0:{ rainfall:6, soil:5, slope:5, historical:3 } },
		{ id:'ziro', name:'Ziro Valley', district:'Lower Subansiri, Arunachal Pradesh', score:28, level:'Monitoring', confidence:73, base:27, slope:48, susceptibility:47, history:31, exposure:58, rainfall:14.6, moisture:46, temperature:20.6, accumulated:81, coordinates:[27.63,93.83], factors0:{ rainfall:8, soil:7, slope:9, historical:4 } },
		{ id:'roing', name:'Roing Foothills', district:'Lower Dibang Valley, Arunachal Pradesh', score:47, level:'Advisory', confidence:77, base:34, slope:64, susceptibility:68, history:52, exposure:61, rainfall:22.7, moisture:58, temperature:21.2, accumulated:119, coordinates:[28.14,95.83], factors0:{ rainfall:16, soil:12, slope:12, historical:7 } },
		{ id:'ukhrul', name:'Ukhrul Ridge', district:'Ukhrul, Manipur', score:31, level:'Monitoring', confidence:74, base:25, slope:51, susceptibility:45, history:38, exposure:44, rainfall:13.1, moisture:43, temperature:22.8, accumulated:74, coordinates:[25.05,94.36], factors0:{ rainfall:10, soil:8, slope:9, historical:4 } }
	];
	let reports = [{ location:'Tawang Corridor', observation:'Fresh tension cracks observed near km marker 14.2.', severity:'High', time:'14:18 IST', status:'Under review' }, { location:'East Siang Valley', observation:'Drainage channel clear after morning inspection.', severity:'Advisory', time:'13:42 IST', status:'Verified' }];
	return { zones:() => structuredClone(zones), reports:() => structuredClone(reports), addReport:report => { reports.unshift(report); return structuredClone(report); } };
})();

function resolveApiBase() {
	const configured = (window.CODENEXUS_CONFIG?.apiBaseUrl || '').replace(/\/$/, '');
	if (!configured) return '';
	try {
		const url = new URL(configured, window.location.href);
		const localTargets = ['localhost', '127.0.0.1', '0.0.0.0'];
		const localPage = ['localhost', '127.0.0.1', ''].includes(window.location.hostname);
		if (localTargets.includes(url.hostname) && !localPage) return window.location.origin;
		return url.toString().replace(/\/$/, '');
	} catch (error) {
		return configured;
	}
}
const configuredApiBase = resolveApiBase();
const API_BASE = configuredApiBase || (window.location.protocol === 'file:' ? 'http://127.0.0.1:5000' : '');
const ApiClient = {
	async request(path, options) { const response = await fetch(`${API_BASE}${path}`, { headers:{ 'Content-Type':'application/json', ...(options && options.headers) }, ...options }); if (!response.ok) throw new Error(`API ${response.status}`); return response.json(); },
	async zones() { return this.request('/api/zones'); },
	async sensors() { return this.request('/api/sensors'); },
	async syncOpenMeteo() { return this.request('/api/live/open-meteo', { method:'POST' }); },
	async risk(zoneId, scenario = 'Normal') { return this.request(`/api/risk?zone_id=${encodeURIComponent(zoneId)}&scenario=${encodeURIComponent(scenario)}`); },
	async mlCompare(zone) { return this.request('/api/ml/compare', { method:'POST', body:JSON.stringify(zone) }); },
	async updateReport(id, status) { return this.request(`/api/reports/${id}`, { method:'PATCH', body:JSON.stringify({ status }) }); },
	async alerts() { return this.request('/api/alerts'); },
	async reports() { return this.request('/api/reports'); },
	async infrastructure() { return this.request('/api/infrastructure'); },
	async exposure(zoneId) { return this.request(`/api/exposure${zoneId ? `?zone_id=${encodeURIComponent(zoneId)}` : ''}`); },
	async riskHistory() { return this.request('/api/risk-history'); },
	async simulationHistory() { return this.request('/api/simulation'); },
	async simulation(scenario, zoneId) { return this.request('/api/simulation', { method:'POST', body:JSON.stringify({ scenario, zone_id:zoneId }) }); },
	async createReport(report) { return this.request('/api/reports', { method:'POST', body:JSON.stringify(report) }); }
};

const SCENARIO_BOOSTS = { Normal:[0,0], 'Heavy Rain':[18,9], 'Extreme Rain':[42,18], Recovery:[-8,-6] };
const AppState = window.AppState = { baseline:MockAPI.zones(), zones:MockAPI.zones(), sensors:[], alerts:[], infrastructure:[], exposure:{ type:'FeatureCollection', features:[] }, riskHistory:[], simulationEvents:[], reports:MockAPI.reports(), selectedZoneId:'tawang', scenario:'Normal', rainfallBoost:0, moistureBoost:0, lastUpdated:new Date(), previousZones:MockAPI.zones(), backendConnected:false, mlComparison:null, fieldAdjust:{}, acks:{} };
// A submitted field report nudges its zone's risk score and model confidence.
function registerFieldAdjust(report) {
	const sev = String(report.severity || '').toLowerCase();
	const obs = String(report.observation || '').toLowerCase();
	const noMovement = /(no|nil|not any|without)\s+(observed\s+|visible\s+|fresh\s+|sign\s+of\s+)?(movement|slippage|slip|cracks?|displacement|subsidence|settlement)|slope (is )?stable|nothing observed|no change/.test(obs);
	let dScore, dConf, note;
	if (noMovement) { dScore = -4; dConf = 8; note = 'no slope movement observed on the ground'; }
	else if (sev === 'critical') { dScore = 13; dConf = 12; note = 'critical ground observation confirmed by field team'; }
	else if (sev === 'high') { dScore = 8; dConf = 10; note = 'high-severity ground observation confirmed'; }
	else { dScore = 3; dConf = 6; note = 'field observation logged'; }
	const at = new Date().toLocaleTimeString('en-IN', { hour12:false, hour:'2-digit', minute:'2-digit' });
	AppState.fieldAdjust = AppState.fieldAdjust || {};
	const prev = AppState.fieldAdjust[report.zone_id] || { score:0, confidence:0 };
	AppState.fieldAdjust[report.zone_id] = {
		score: Math.max(-15, Math.min(30, prev.score + dScore)),
		confidence: Math.min(18, prev.confidence + dConf),
		at, note, severity: report.severity, location: report.location
	};
}
function normalizeZone(zone) {
	const score = num(zone.score ?? zone.risk_score, 0);
	const confidence = num(zone.confidence ?? zone.model_confidence ?? zone.confidence_pct, 75);
	return {
		...zone,
		score,
		level: zone.level ?? zone.risk_level ?? levelFor(score),
		confidence,
		moisture: num(zone.moisture ?? zone.soil_moisture, 0),
		rainfall: num(zone.rainfall, 0),
		accumulated: num(zone.accumulated ?? zone.accumulated_rainfall, 0),
		temperature: num(zone.temperature, 0),
		slope: num(zone.slope, 0),
		susceptibility: num(zone.susceptibility, 0),
		history: num(zone.history, 0),
		exposure: num(zone.exposure, 0)
	};
}
function normalizeReport(report) { return { ...report, time:report.time || (report.timestamp ? new Date(report.timestamp).toLocaleTimeString('en-IN', { hour12:false }) : 'Unknown time') }; }
function localRisk(zone) {
	const rBoost = num(AppState.rainfallBoost), mBoost = num(AppState.moistureBoost);
	const rainfall = Math.max(0, num(zone.rainfall) + rBoost);
	const moisture = Math.min(100, Math.max(0, num(zone.moisture) + mBoost));
	const adj = (AppState.fieldAdjust || {})[zone.id];
	const f0 = zone.factors0 || {};

	if (zone._live) {
		// Score = real-rainfall points + real-soil points + static terrain points.
		const rp = Math.max(0, Math.round(rainfallPoints(rainfall)));
		const sp = Math.max(0, Math.round(soilPoints(moisture)));
		const slp = Math.max(0, Math.round(num(f0.slope, 12)));
		const hp = Math.max(0, Math.round(num(f0.historical, 6)));
		let score = rp + sp + slp + hp;
		let confidence = num(zone.confidence, 82);
		if (adj) { score += num(adj.score); confidence = Math.min(99, Math.round(confidence + num(adj.confidence))); }
		score = Math.max(0, Math.min(100, score));
		return {
			...zone, rainfall, moisture,
			accumulated: Math.max(0, num(zone.accumulated) + rBoost * 1.7),
			score, confidence, level: levelForLive(score),
			liveFactors: { rainfall: rp, soil: sp, slope: slp, historical: hp },
			fieldAdjust: adj || null
		};
	}

	const anchor = num(zone.score);
	let score = Math.round(Math.min(100, Math.max(0, anchor + rBoost * (0.38 + num(zone.susceptibility) / 500) + mBoost * 0.35)));
	let confidence = num(zone.confidence, 75);
	if (adj) { score = Math.max(0, Math.min(100, score + num(adj.score))); confidence = Math.min(99, Math.round(confidence + num(adj.confidence))); }
	return { ...zone, rainfall, moisture, accumulated: Math.max(0, num(zone.accumulated) + rBoost * 1.7), score, confidence, level: levelFor(score), fieldAdjust: adj || null };
}
function renderState() { AppState.lastUpdated = new Date(); Dashboard.render(AppState); MapView.render(AppState); }

// Merge cached Open-Meteo readings onto the baseline zones; localRisk then scores
// them from real rainfall + soil moisture. Silent no-op if nothing was fetched.
function applyWeather() {
	if (typeof WeatherService === 'undefined' || !WeatherService.hasData()) return false;
	const merge = z => {
		const w = WeatherService.get(z.id);
		if (!w) return z;
		return {
			...z,
			rainfall: num(w.rainfall),
			moisture: num(w.soilMoisture),
			temperature: num(w.temperature),
			accumulated: num(w.accumulatedRain24h),
			humidity: num(w.humidity),
			hourlyRainfall: Array.isArray(w.hourlyRainfall) ? w.hourlyRainfall : [],
			hourlySoilMoisture: Array.isArray(w.hourlySoilMoisture) ? w.hourlySoilMoisture : [],
			hourlyTemperature: Array.isArray(w.hourlyTemperature) ? w.hourlyTemperature : [],
			forecastRainfall: Array.isArray(w.forecastRainfall) ? w.forecastRainfall : [],
			_live: true
		};
	};
	AppState.baseline = (AppState.baseline || []).map(merge);
	AppState.zones = AppState.baseline.map(localRisk);
	return true;
}
async function loadWeather() {
	if (typeof WeatherService === 'undefined') return;
	// The claude.ai artifact sandbox blocks external fetch via CSP; skip cleanly
	// so the console stays error-free. Real deployments (Render/Vercel/localhost) fetch normally.
	const host = (typeof location !== 'undefined' && location.hostname) || '';
	if (/claude|usercontent|anthropic/i.test(host)) return;
	try {
		const result = await WeatherService.loadAll((AppState.baseline || []).map(z => ({ id: z.id, coordinates: z.coordinates })));
		if (!result || !result.ok) return;          // silent fallback -> simulated values stay
		AppState.liveWeather = true;
		AppState.weatherFetchedAt = WeatherService.lastFetched();
		if (applyWeather()) renderState();
	} catch (error) { /* silent: keep simulated values */ }
}
async function bootstrap() { let weatherSyncFailed = false; try { try { await ApiClient.syncOpenMeteo(); } catch (error) { weatherSyncFailed = true; console.warn('Live weather sync unavailable; loading API data without refresh.', error); } const [zones, sensors, alertPayload, reports, infrastructure, exposure, riskHistory, simulation] = await Promise.all([ApiClient.zones(), ApiClient.sensors(), ApiClient.alerts(), ApiClient.reports(), ApiClient.infrastructure(), ApiClient.exposure(), ApiClient.riskHistory(), ApiClient.simulationHistory()]); AppState.baseline = zones.map(normalizeZone); AppState.zones = await Promise.all(AppState.baseline.map(async zone => normalizeZone(await ApiClient.risk(zone.id, AppState.scenario)))); const selected = AppState.zones.find(zone => zone.id === AppState.selectedZoneId) || AppState.zones[0]; AppState.mlComparison = await ApiClient.mlCompare(selected); AppState.sensors = sensors; AppState.alerts = alertPayload.alerts || []; AppState.reports = reports.map(normalizeReport); AppState.infrastructure = infrastructure; AppState.exposure = exposure; AppState.riskHistory = riskHistory; AppState.simulationEvents = simulation.events || []; AppState.backendConnected = true; showToast(weatherSyncFailed ? 'Connected to Flask API; live weather sync unavailable.' : 'Connected to Flask monitoring API.'); } catch (error) { AppState.backendConnected = false; AppState.zones = AppState.baseline.map(localRisk); showToast('Offline prototype mode: using local fallback data.'); } renderState(); }
async function selectZone(id) { AppState.previousZones = AppState.zones.map(zone => ({ ...zone })); AppState.selectedZoneId = id; if (AppState.backendConnected) { try { const [result, exposure] = await Promise.all([ApiClient.risk(id, AppState.scenario), ApiClient.exposure(id)]); AppState.zones = AppState.zones.map(zone => zone.id === id ? { ...zone, ...normalizeZone(result) } : zone); AppState.exposure = exposure; } catch (error) { AppState.zones = AppState.zones.map(localRisk); } } renderState(); }
async function applyScenario(scenario) { const [rainfallBoost, moistureBoost] = SCENARIO_BOOSTS[scenario] || SCENARIO_BOOSTS.Normal; AppState.previousZones = AppState.zones.map(zone => ({ ...zone })); AppState.scenario = scenario; AppState.rainfallBoost = rainfallBoost; AppState.moistureBoost = moistureBoost; if (AppState.backendConnected) { try { const result = await ApiClient.simulation(scenario); AppState.zones = result.results.map(normalizeZone); AppState.riskHistory = await ApiClient.riskHistory(); AppState.alerts = (await ApiClient.alerts()).alerts || []; AppState.simulationEvents = (await ApiClient.simulationHistory()).events || []; renderState(); showToast(`${scenario} loaded from Flask risk engine.`); return; } catch (error) { AppState.backendConnected = false; } } AppState.zones = AppState.baseline.map(localRisk); renderState(); showToast(`${scenario} applied in offline prototype mode.`); }
async function submitReport(report) {
	if (AppState.backendConnected) {
		try {
			await ApiClient.createReport(report);
			AppState.reports = (await ApiClient.reports()).map(normalizeReport);
			registerFieldAdjust(report);
			AppState.previousZones = AppState.zones.map(z => ({ ...z }));
			AppState.zones = AppState.zones.map(localRisk);
			AppState._fieldPending = true;
			return;
		} catch (error) { AppState.backendConnected = false; }
	}
	report.time = report.time || (new Date().toLocaleTimeString('en-IN', { hour12:false }) + ' IST');
	MockAPI.addReport(report);
	AppState.reports = MockAPI.reports();
	registerFieldAdjust(report);
	AppState.previousZones = AppState.zones.map(z => ({ ...z }));
	AppState.zones = AppState.baseline.map(localRisk);
	AppState._fieldPending = true;
	AppState._skipJitterUntil = Date.now() + 9000;
}
function showToast(message) { const toast = document.getElementById('toast'); toast.textContent = message; toast.classList.add('show'); clearTimeout(showToast.timer); showToast.timer = setTimeout(() => toast.classList.remove('show'), 3000); }
let realtimeFailures = 0;
function connectRealtimeStream() { if (typeof EventSource === 'undefined') return; const source = new EventSource(`${API_BASE}/api/events`); source.onopen = () => { realtimeFailures = 0; }; source.addEventListener('telemetry', () => bootstrap()); source.onerror = () => { source.close(); realtimeFailures += 1; if (realtimeFailures <= 4) setTimeout(connectRealtimeStream, 5000); else console.info('Live event stream unavailable on this host; using periodic polling instead.'); }; }
function switchView(view) { document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === view)); document.querySelectorAll('.view').forEach(item => item.classList.toggle('active', item.dataset.section === view)); if (view === 'dashboard') { AppState._fieldPending = false; Dashboard.render(AppState); } if (view === 'intelligence') Dashboard.renderIntelligence(AppState); if (view === 'alerts') Dashboard.renderAlertsPage(AppState); if (view === 'reports') Dashboard.renderReports(AppState); }
document.addEventListener('DOMContentLoaded', () => { Dashboard.init({ selectZone, applyScenario, switchView, showToast, submitReport, updateReport: async (id, status) => { await ApiClient.updateReport(id, status); AppState.reports = (await ApiClient.reports()).map(normalizeReport); renderState(); showToast(`Report marked ${status}.`); } }); MapView.init(selectZone); bootstrap(); loadWeather(); connectRealtimeStream(); setInterval(() => { if (AppState.backendConnected) bootstrap(); else if (!AppState.liveWeather && AppState.scenario === 'Normal' && Date.now() > (AppState._skipJitterUntil || 0)) { AppState.previousZones = AppState.zones.map(z => ({ ...z })); AppState.baseline = AppState.baseline.map(zone => ({ ...zone, rainfall:Math.max(0, zone.rainfall + (Math.random() - .5) * .8), moisture:Math.max(0, zone.moisture + (Math.random() - .5) * .25) })); AppState.zones = AppState.baseline.map(localRisk); renderState(); } }, 7000); });
