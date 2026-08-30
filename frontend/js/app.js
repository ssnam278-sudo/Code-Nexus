// Every displayed/derived numeric value is coerced through this: undefined / null
// / NaN / non-finite -> the supplied default (0 unless stated).
function num(value, fallback = 0) { const n = Number(value); return Number.isFinite(n) ? n : fallback; }

/* ============================================================================
 * CodeNexusRisk — the ONE risk formula.
 * A byte-for-byte port of backend/risk_engine.py calculate_risk():
 *   risk = 0.35·rainfall_pressure + 0.25·soil_saturation
 *        + 0.25·terrain_susceptibility + 0.15·historical_susceptibility
 * every term normalised to 0–100, bands 35 / 55 / 75.
 * Used for offline scoring; when the API is connected the identical Python
 * version is authoritative and this is not called for the score.
 * ==========================================================================*/
window.CodeNexusRisk = (() => {
	const WEIGHTS = { 'Rainfall pressure': 0.35, 'Soil saturation': 0.25, 'Terrain susceptibility': 0.25, 'Historical susceptibility': 0.15 };
	const REF_INTENSITY_MM_H = 50, REF_ACCUM_MM_24H = 200;
	const FORMULA = 'risk = 0.35·rainfall_pressure + 0.25·soil_saturation + 0.25·terrain_susceptibility + 0.15·historical_susceptibility  (each term normalised to 0–100)';
	const clamp = (v, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v));

	function factors(zone) {
		const rain = Math.max(0, num(zone.rainfall));
		const accum = Math.max(0, num(zone.accumulated ?? zone.accumulated_rainfall));
		const rainfallPressure = 100 * clamp(0.6 * (rain / REF_INTENSITY_MM_H) + 0.4 * (accum / REF_ACCUM_MM_24H), 0, 1);
		const soil = clamp(num(zone.moisture ?? zone.soil_moisture));
		const terrain = clamp(0.5 * num(zone.slope) + 0.5 * num(zone.susceptibility));
		const hist = clamp(num(zone.history));
		const rows = [
			{ name: 'Rainfall pressure', value: +rainfallPressure.toFixed(1), input: +rain.toFixed(1), input_unit: 'mm/hr + 24h accum', input_detail: `${rain.toFixed(1)} mm/hr now, ${Math.round(accum)} mm/24h` },
			{ name: 'Soil saturation', value: +soil.toFixed(1), input: +soil.toFixed(1), input_unit: '%' },
			{ name: 'Terrain susceptibility', value: +terrain.toFixed(1), input: +terrain.toFixed(1), input_unit: 'slope+suscept index', input_detail: `slope ${Math.round(num(zone.slope))}, susceptibility ${Math.round(num(zone.susceptibility))}` },
			{ name: 'Historical susceptibility', value: +hist.toFixed(1), input: +hist.toFixed(1), input_unit: 'index' }
		];
		return rows.map(f => ({ ...f, weight: WEIGHTS[f.name], contribution: +(f.value * WEIGHTS[f.name]).toFixed(2) }));
	}
	function level(score) { const s = num(score); return s >= 75 ? 'Critical' : s >= 55 ? 'High' : s >= 35 ? 'Advisory' : 'Monitoring'; }
	function score(zone) {
		const cf = factors(zone);
		const s = Math.round(clamp(cf.reduce((a, f) => a + f.contribution, 0)));
		return { risk_score: s, risk_level: level(s), contributing_factors: cf, formula: FORMULA, weights: { ...WEIGHTS } };
	}
	return { score, level, factors, WEIGHTS, FORMULA };
})();

// canonical threshold ladder (35 / 55 / 75) — one function, used everywhere
function levelFor(score) { return window.CodeNexusRisk.level(score); }

/* Real static baseline per zone. slope / susceptibility / history are the
 * SRTM-DEM + GSI-derived values from backend/data/zone_profile_cache (identical
 * to what the API serves); coordinates + exposure from backend/data/zones.json;
 * seed telemetry from backend/data/sensors.json for the pre-first-pull state.
 * No score is stored — it is always computed by CodeNexusRisk, so the offline
 * build produces the same number as the API. */
const BASELINE_ZONES = [
	{ id: 'tawang', name: 'Tawang Corridor', district: 'Tawang, Arunachal Pradesh', coordinates: [27.5861, 91.8594], slope: 61.9, susceptibility: 81.8, history: 55.0, exposure: 86, rainfall: 42.6, moisture: 76, temperature: 19.4, accumulated: 184, population: 14000 },
	{ id: 'siang', name: 'East Siang Valley', district: 'Pasighat, Arunachal Pradesh', coordinates: [28.0667, 95.3267], slope: 27.5, susceptibility: 36.1, history: 27.0, exposure: 72, rainfall: 29.8, moisture: 64, temperature: 22.1, accumulated: 138, population: 24000 },
	{ id: 'chura', name: 'Churachandpur Ridge', district: 'Churachandpur, Manipur', coordinates: [24.3333, 93.6833], slope: 32.5, susceptibility: 41.9, history: 36.1, exposure: 63, rainfall: 18.4, moisture: 51, temperature: 24.7, accumulated: 96, population: 19000 },
	{ id: 'garo', name: 'South Garo Hills', district: 'Baghmara, Meghalaya', coordinates: [25.1980, 90.6300], slope: 20.8, susceptibility: 21.8, history: 17.5, exposure: 51, rainfall: 11.2, moisture: 39, temperature: 25.8, accumulated: 67, population: 9000 },
	{ id: 'bomdila', name: 'Bomdila Pass', district: 'West Kameng, Arunachal Pradesh', coordinates: [27.2648, 92.4246], slope: 47.2, susceptibility: 61.0, history: 15.5, exposure: 32, rainfall: 7.4, moisture: 29, temperature: 14.8, accumulated: 42, population: 7000 },
	{ id: 'ziro', name: 'Ziro Valley', district: 'Lower Subansiri, Arunachal Pradesh', coordinates: [27.5444, 93.8197], slope: 29.1, susceptibility: 34.3, history: 27.9, exposure: 58, rainfall: 14.6, moisture: 46, temperature: 20.6, accumulated: 81, population: 14000 },
	{ id: 'roing', name: 'Roing Foothills', district: 'Lower Dibang Valley, Arunachal Pradesh', coordinates: [28.1397, 95.8400], slope: 41.9, susceptibility: 50.6, history: 26.0, exposure: 61, rainfall: 22.7, moisture: 58, temperature: 21.2, accumulated: 119, population: 12000 },
	{ id: 'ukhrul', name: 'Ukhrul Ridge', district: 'Ukhrul, Manipur', coordinates: [25.0968, 94.3614], slope: 38.3, susceptibility: 44.1, history: 39.0, exposure: 44, rainfall: 13.1, moisture: 43, temperature: 22.8, accumulated: 74, population: 11000 }
];

/* Demo baseline for the Verification log so it is never blank. The backend
 * seeds the same three rows into its DB (backend/data/seed_reports.json); these
 * are the offline / backend-unreachable fallback. Marked seed:true — real
 * submissions always sort above them and are what feed the risk engine. */
const SeedReports = (() => {
	const stamp = hoursAgo => {
		const dt = new Date(Date.now() - hoursAgo * 3600 * 1000);
		return dt.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }) + ' IST';
	};
	const reports = [
		{ zone_id: 'roing', location: 'Roing Foothills', observation: 'Field team confirmed rising water level near stream crossing, no immediate road blockage', severity: 'High', status: 'Under review', time: stamp(5), seed: true },
		{ zone_id: 'tawang', location: 'Tawang Corridor', observation: 'Minor soil slippage observed near km marker 12, road shoulder showing cracks after continuous rainfall', severity: 'Advisory', status: 'Verified', time: stamp(18), seed: true },
		{ zone_id: 'siang', location: 'East Siang Valley', observation: 'Local resident reported small debris on approach road, cleared by afternoon', severity: 'Advisory', status: 'Verified', time: stamp(48), seed: true }
	];
	return { list: () => structuredClone(reports), add: () => {} };
})();

/* Small localStorage layer. On Vercel the serverless SQLite in /tmp is wiped
 * between requests, so field reports, their score effect, and acknowledgements
 * are also kept client-side and restored on load. On Render the backend DB is
 * authoritative and these are merged in (deduped). */
const Persist = window.Persist = {
	get(key, fallback) {
		try { const v = localStorage.getItem('codenexus.' + key); return v ? JSON.parse(v) : fallback; }
		catch (e) { return fallback; }
	},
	set(key, value) { try { localStorage.setItem('codenexus.' + key, JSON.stringify(value)); } catch (e) {} },
	clear(key) { try { localStorage.removeItem('codenexus.' + key); } catch (e) {} }
};

// Merge: operator's local submissions first, then whatever the backend has,
// then the demo seed rows so the log is never blank. Deduped by observation
// text (backend-seeded rows share text with the client seeds -> not doubled).
function mergeLocalReports(backendReports) {
	const seen = new Set();
	const out = [];
	const key = r => String(r.observation || '').trim().toLowerCase().slice(0, 120);
	const push = r => { const k = key(r); if (k && seen.has(k)) return; if (k) seen.add(k); out.push(r); };
	(AppState._localReports || []).forEach(push);
	(backendReports || []).forEach(push);
	SeedReports.list().forEach(push);
	return out;
}

// Apply the client-side field-report score effect to any zone the backend did
// NOT already adjust (idempotent — offline computeRisk has usually done it).
function mergeGroundTruth(zones) {
	const adj = AppState.fieldAdjust || {};
	return (zones || []).map(z => {
		const a = adj[z.id];
		if (!a || z.ground_truth) return z;
		const score = Math.max(0, Math.min(100, num(z.score) + num(a.score)));
		return {
			...z,
			score, risk_score: score,
			level: levelFor(score), risk_level: levelFor(score),
			confidence: Math.min(99, Math.round(num(z.confidence, 75) + num(a.confidence))),
			ground_truth: { delta_score: num(a.score), delta_confidence: num(a.confidence), note: a.note, location: a.location, severity: a.severity, status: 'field report' }
		};
	});
}

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
	async request(path, options) { const response = await fetch(`${API_BASE}${path}`, { headers: { 'Content-Type': 'application/json', ...(options && options.headers) }, ...options }); if (!response.ok) throw new Error(`API ${response.status}`); return response.json(); },
	async zones() { return this.request('/api/zones'); },
	async health() { return this.request('/api/health'); },
	async syncOpenMeteo() { return this.request('/api/live/open-meteo', { method: 'POST' }); },
	async mlCompare(zone) { return this.request('/api/ml/compare', { method: 'POST', body: JSON.stringify(zone) }); },
	async updateReport(id, status) { return this.request(`/api/reports/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }); },
	async alerts() { return this.request('/api/alerts'); },
	async reports() { return this.request('/api/reports'); },
	async infrastructure() { return this.request('/api/infrastructure'); },
	async exposure(zoneId) { return this.request(`/api/exposure${zoneId ? `?zone_id=${encodeURIComponent(zoneId)}` : ''}`); },
	async riskHistory() { return this.request('/api/risk-history'); },
	async simulationHistory() { return this.request('/api/simulation'); },
	async simulation(scenario, zoneId) { return this.request('/api/simulation', { method: 'POST', body: JSON.stringify({ scenario, zone_id: zoneId }) }); },
	async createReport(report) { return this.request('/api/reports', { method: 'POST', body: JSON.stringify(report) }); },
	async clearReports() { return this.request('/api/reports/clear', { method: 'POST' }); }
};

const SCENARIO_BOOSTS = { Normal: [0, 0], 'Heavy Rain': [18, 9], 'Extreme Rain': [42, 18], Recovery: [-8, -6] };
const AppState = window.AppState = {
	baseline: structuredClone(BASELINE_ZONES), zones: [], sensors: [], alerts: [], infrastructure: [],
	exposure: { type: 'FeatureCollection', features: [] }, riskHistory: [], simulationEvents: [],
	reports: SeedReports.list(), selectedZoneId: 'tawang', scenario: 'Normal', rainfallBoost: 0, moistureBoost: 0,
	lastUpdated: new Date(), previousZones: [], backendConnected: false, health: null, mlComparison: null,
	fieldAdjust: Persist.get('fieldAdjust', {}),
	acks: Persist.get('acks', {}),
	_localReports: Persist.get('reports', [])
};

// A submitted field report nudges its zone's risk score and model confidence
// (offline mirror of backend/simulator.py apply_ground_truth).
function registerFieldAdjust(report) {
	const sev = String(report.severity || '').toLowerCase();
	const obs = String(report.observation || '').toLowerCase();
	const noMovement = /(no|nil|not any|without)\s+(observed\s+|visible\s+|fresh\s+|sign\s+of\s+)?(movement|slippage|slip|cracks?|displacement|subsidence|settlement)|slope (is )?stable|nothing observed|no change/.test(obs);
	let dScore, dConf, note;
	if (noMovement) { dScore = -4; dConf = 8; note = 'no slope movement observed on the ground'; }
	else if (sev === 'critical') { dScore = 13; dConf = 12; note = 'critical ground observation confirmed by field team'; }
	else if (sev === 'high') { dScore = 8; dConf = 10; note = 'high-severity ground observation confirmed'; }
	else { dScore = 3; dConf = 6; note = 'field observation logged'; }
	const at = new Date().toLocaleTimeString('en-IN', { hour12: false, hour: '2-digit', minute: '2-digit' });
	AppState.fieldAdjust = AppState.fieldAdjust || {};
	const prev = AppState.fieldAdjust[report.zone_id] || { score: 0, confidence: 0 };
	AppState.fieldAdjust[report.zone_id] = {
		score: Math.max(-15, Math.min(30, prev.score + dScore)),
		confidence: Math.min(18, prev.confidence + dConf),
		at, note, severity: report.severity, location: report.location
	};
	Persist.set('fieldAdjust', AppState.fieldAdjust);
}

function normalizeZone(zone) {
	const score = num(zone.score ?? zone.risk_score, 0);
	return {
		...zone,
		score,
		level: zone.level ?? zone.risk_level ?? levelFor(score),
		confidence: num(zone.confidence ?? zone.model_confidence ?? zone.confidence_pct, 75),
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
function normalizeReport(report) { return { ...report, time: report.time || (report.timestamp ? new Date(report.timestamp).toLocaleTimeString('en-IN', { hour12: false }) : 'Unknown time') }; }

function offlineConfidenceBasis(zone) {
	const basis = [];
	const rainLive = zone.data_source === 'open-meteo' || zone._live;
	basis.push(rainLive ? { factor: 'live Open-Meteo rainfall', effect: 12 } : { factor: 'simulated rainfall (offline)', effect: 0 });
	const soilLive = zone.soil_data_source === 'nasa-power' || zone.soil_data_source === 'open-meteo';
	basis.push(soilLive ? { factor: `soil moisture from ${zone.soil_data_source === 'nasa-power' ? 'NASA POWER' : 'Open-Meteo'}`, effect: 5 } : { factor: 'soil moisture simulated', effect: -6 });
	basis.push({ factor: 'all inputs within expected range', effect: 4 });
	return basis;
}

// The offline scorer: same formula as the backend, plus the scenario boosts and
// the field-report adjustment.
function computeRisk(zone) {
	const rBoost = num(AppState.rainfallBoost), mBoost = num(AppState.moistureBoost);
	const rainfall = Math.max(0, num(zone.rainfall) + rBoost);
	const moisture = Math.min(100, Math.max(0, num(zone.moisture ?? zone.soil_moisture) + mBoost));
	const accumulated = Math.max(0, num(zone.accumulated ?? zone.accumulated_rainfall) + rBoost * 1.7);
	const merged = { ...zone, rainfall, moisture, accumulated };
	const r = window.CodeNexusRisk.score(merged);

	let score = r.risk_score;
	let confidence = 72 + offlineConfidenceBasis(zone).reduce((a, b) => a + b.effect, 0);
	confidence = Math.max(40, Math.min(97, Math.round(confidence)));
	let groundTruth = null;
	const adj = (AppState.fieldAdjust || {})[zone.id];
	if (adj) {
		score = Math.max(0, Math.min(100, score + num(adj.score)));
		confidence = Math.min(99, Math.round(confidence + num(adj.confidence)));
		groundTruth = { delta_score: num(adj.score), delta_confidence: num(adj.confidence), note: adj.note, location: adj.location, status: 'offline', severity: adj.severity };
	}
	return {
		...merged,
		...r,
		risk_score: score, score,
		risk_level: levelFor(score), level: levelFor(score),
		confidence,
		confidence_basis: offlineConfidenceBasis(zone),
		ground_truth: groundTruth,
		data_source: zone.data_source || 'simulated',
		rainfall_data_source: zone.rainfall_data_source || zone.data_source || 'simulated',
		soil_data_source: zone.soil_data_source || 'simulated'
	};
}

// Re-render EVERY view from the current state so no page can drift.
function renderState() {
	AppState.lastUpdated = new Date();
	Dashboard.render(AppState);
	MapView.render(AppState);
	Dashboard.renderIntelligence(AppState);
	Dashboard.renderAlertsPage(AppState);
	Dashboard.renderReports(AppState);
	Dashboard.renderSources(AppState);
}

// Browser Open-Meteo pull. If the backend already scored from its own live sync
// we just attach the hourly series. If the backend is on simulated inputs (e.g.
// its server-side sync timed out on a serverless host) but the browser has live
// Open-Meteo, we score from the browser data with the SAME formula and label the
// source honestly — so every page, including Data Sources, agrees.
function applyWeather() {
	if (typeof WeatherService === 'undefined' || !WeatherService.hasData()) return false;
	const series = z => {
		const w = WeatherService.get(z.id);
		if (!w) return {};
		return {
			hourlyRainfall: Array.isArray(w.hourlyRainfall) ? w.hourlyRainfall : [],
			hourlySoilMoisture: Array.isArray(w.hourlySoilMoisture) ? w.hourlySoilMoisture : [],
			hourlyTemperature: Array.isArray(w.hourlyTemperature) ? w.hourlyTemperature : [],
			forecastRainfall: Array.isArray(w.forecastRainfall) ? w.forecastRainfall : []
		};
	};
	const mergeLive = z => {
		const w = WeatherService.get(z.id);
		if (!w) return z;
		const merged = {
			...z, rainfall: num(w.rainfall), moisture: num(w.soilMoisture), temperature: num(w.temperature),
			accumulated: num(w.accumulatedRain24h), humidity: num(w.humidity), ...series(z),
			_live: true, data_source: 'open-meteo', rainfall_data_source: 'open-meteo',
			soil_data_source: 'open-meteo', observed_at: new Date().toISOString()
		};
		return computeRisk(merged);
	};

	if (AppState.backendConnected) {
		AppState.zones = AppState.zones.map(z =>
			z.data_source === 'open-meteo'
				? { ...z, ...series(z), _live: true }   // backend already live -> just decorate
				: mergeLive(z)                          // backend simulated -> use the browser feed
		);
		return true;
	}
	AppState.baseline = (AppState.baseline || []).map(z => {
		const w = WeatherService.get(z.id);
		if (!w) return z;
		return {
			...z, rainfall: num(w.rainfall), moisture: num(w.soilMoisture), temperature: num(w.temperature),
			accumulated: num(w.accumulatedRain24h), humidity: num(w.humidity), ...series(z),
			_live: true, data_source: 'open-meteo', rainfall_data_source: 'open-meteo', soil_data_source: 'open-meteo', observed_at: new Date().toISOString()
		};
	});
	AppState.zones = AppState.baseline.map(computeRisk);
	AppState.liveWeather = true;
	return true;
}
async function loadWeather() {
	if (typeof WeatherService === 'undefined') return;
	const host = (typeof location !== 'undefined' && location.hostname) || '';
	if (/claude|usercontent|anthropic/i.test(host)) return;   // sandbox blocks external fetch
	try {
		const result = await WeatherService.loadAll((AppState.baseline || []).map(z => ({ id: z.id, coordinates: z.coordinates })));
		if (!result || !result.ok) return;
		AppState.weatherFetchedAt = WeatherService.lastFetched();
		if (applyWeather()) renderState();
	} catch (error) { /* silent: keep whatever we have */ }
}

async function bootstrap() {
	try {
		// Kick the server-side pull but DON'T block on it — NASA POWER + Open-Meteo
		// for every zone can take longer than a serverless request budget. The
		// next 7 s cycle picks up the fresh readings; the browser pull covers the
		// gap in the meantime.
		ApiClient.syncOpenMeteo().catch(() => {});
		const [zones, alertPayload, reports, infrastructure, exposure, riskHistory, simulation, health] = await Promise.all([
			ApiClient.zones(), ApiClient.alerts(), ApiClient.reports(), ApiClient.infrastructure(),
			ApiClient.exposure(), ApiClient.riskHistory(), ApiClient.simulationHistory(), ApiClient.health().catch(() => null)
		]);
		AppState.baseline = zones.map(normalizeZone);
		AppState.zones = zones.map(normalizeZone);          // one source: /api/zones bundles the risk record
		AppState.health = health;
		const selected = AppState.zones.find(zone => zone.id === AppState.selectedZoneId) || AppState.zones[0];
		AppState.mlComparison = selected ? await ApiClient.mlCompare(selected).catch(() => null) : null;
		AppState.alerts = alertPayload.alerts || [];
		AppState.reports = mergeLocalReports(reports.map(normalizeReport));
		AppState.infrastructure = infrastructure;
		AppState.exposure = exposure;
		AppState.riskHistory = riskHistory;
		AppState.simulationEvents = simulation.events || [];
		AppState.backendConnected = true;
		showToast('Connected to Code Nexus API.');
	} catch (error) {
		AppState.backendConnected = false;
		AppState.health = null;
		AppState.zones = AppState.baseline.map(computeRisk);
		AppState.reports = mergeLocalReports(SeedReports.list());
		showToast('Offline mode: scores computed locally with the same formula.');
	}
	// Re-merge the browser Open-Meteo pull every cycle. On Vercel the serverless
	// SQLite lives in a per-invocation /tmp, so /api/zones always reads back
	// "simulated" — the browser feed is what makes the dashboard live, and it
	// must survive each bootstrap refresh instead of being clobbered by it.
	applyWeather();
	// Apply any field-report score effect the backend didn't remember (Vercel).
	AppState.zones = mergeGroundTruth(AppState.zones);
	renderState();
}

async function selectZone(id) {
	AppState.previousZones = AppState.zones.map(zone => ({ ...zone }));
	AppState.selectedZoneId = id;
	if (AppState.backendConnected) {
		try { AppState.exposure = await ApiClient.exposure(id); } catch (error) { /* keep prior exposure */ }
		try { AppState.mlComparison = await ApiClient.mlCompare(AppState.zones.find(z => z.id === id) || {}); } catch (error) { /* keep last ML result */ }
	}
	renderState();
	if (typeof window.refreshMlCheck === 'function') window.refreshMlCheck();
}

async function applyScenario(scenario) {
	const [rainfallBoost, moistureBoost] = SCENARIO_BOOSTS[scenario] || SCENARIO_BOOSTS.Normal;
	AppState.previousZones = AppState.zones.map(zone => ({ ...zone }));
	AppState.scenario = scenario;
	AppState.rainfallBoost = rainfallBoost;
	AppState.moistureBoost = moistureBoost;
	if (AppState.backendConnected) {
		try {
			const result = await ApiClient.simulation(scenario);
			AppState.zones = mergeGroundTruth(result.results.map(normalizeZone));
			AppState.riskHistory = await ApiClient.riskHistory();
			AppState.alerts = (await ApiClient.alerts()).alerts || [];
			AppState.simulationEvents = (await ApiClient.simulationHistory()).events || [];
			renderState();
			showToast(`${scenario} loaded from the risk engine.`);
			return;
		} catch (error) { AppState.backendConnected = false; }
	}
	AppState.zones = AppState.baseline.map(computeRisk);
	renderState();
	showToast(`${scenario} applied (offline formula).`);
}

async function submitReport(report) {
	report.time = report.time || (new Date().toLocaleTimeString('en-IN', { hour12: false }) + ' IST');
	report.id = report.id || ('local-' + Date.now());
	// Always keep a client copy + client-side score effect, so a submission and
	// its impact survive a refresh even where the serverless DB forgets it.
	AppState._localReports = [{ ...report, status: report.status || 'Under review' }, ...(AppState._localReports || [])].slice(0, 50);
	// keep the base64 evidence only on the newest few (localStorage is small)
	AppState._localReports.forEach((r, i) => { if (i >= 4 && r.media_data) r.media_data = null; });
	Persist.set('reports', AppState._localReports);
	registerFieldAdjust(report);
	AppState.previousZones = AppState.zones.map(z => ({ ...z }));
	AppState._fieldPending = true;
	AppState._skipJitterUntil = Date.now() + 9000;

	if (AppState.backendConnected) {
		try {
			await ApiClient.createReport(report);
			const backend = (await ApiClient.reports()).map(normalizeReport);
			AppState.reports = mergeLocalReports(backend);
			AppState.zones = mergeGroundTruth((await ApiClient.zones()).map(normalizeZone));
			return;
		} catch (error) { AppState.backendConnected = false; }
	}
	AppState.reports = mergeLocalReports(SeedReports.list());
	AppState.zones = AppState.baseline.map(computeRisk);
}

function showToast(message) { const toast = document.getElementById('toast'); toast.textContent = message; toast.classList.add('show'); clearTimeout(showToast.timer); showToast.timer = setTimeout(() => toast.classList.remove('show'), 3000); }

let realtimeFailures = 0;
function connectRealtimeStream() {
	if (typeof EventSource === 'undefined') return;
	const source = new EventSource(`${API_BASE}/api/events`);
	source.onopen = () => { realtimeFailures = 0; };
	source.addEventListener('telemetry', () => bootstrap());
	source.onerror = () => { source.close(); realtimeFailures += 1; if (realtimeFailures <= 4) setTimeout(connectRealtimeStream, 5000); else console.info('Live event stream unavailable; using periodic polling.'); };
}

function switchView(view) {
	document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === view));
	document.querySelectorAll('.view').forEach(item => item.classList.toggle('active', item.dataset.section === view));
	if (view === 'dashboard') { AppState._fieldPending = false; Dashboard.render(AppState); }
	if (view === 'intelligence') Dashboard.renderIntelligence(AppState);
	if (view === 'alerts') Dashboard.renderAlertsPage(AppState);
	if (view === 'reports') Dashboard.renderReports(AppState);
	if (view === 'sources') Dashboard.renderSources(AppState);
}

function persistAcks() { Persist.set('acks', AppState.acks || {}); }

// The header ↻ button: clear the scenario AND the demo's local state
// (field reports, their score effect, acknowledgements) for a clean run.
async function resetDemo() {
	AppState.fieldAdjust = {}; AppState.acks = {}; AppState._localReports = [];
	Persist.clear('fieldAdjust'); Persist.clear('acks'); Persist.clear('reports');
	AppState.scenario = 'Normal'; AppState.rainfallBoost = 0; AppState.moistureBoost = 0;
	AppState._skipJitterUntil = 0;
	if (AppState.backendConnected) { try { await ApiClient.clearReports(); } catch (e) {} await bootstrap(); }
	else { AppState.reports = SeedReports.list(); AppState.zones = AppState.baseline.map(computeRisk); renderState(); }
	showToast('Demo reset — scenario, field reports and acknowledgements cleared.');
}

async function updateReport(id, status) {
	const local = String(id).startsWith('local-') || !Number.isFinite(Number(id));
	if (local) {
		AppState._localReports = (AppState._localReports || []).map(r => r.id === id ? { ...r, status } : r);
		Persist.set('reports', AppState._localReports);
		AppState.reports = mergeLocalReports(AppState.backendConnected ? await ApiClient.reports().catch(() => []) : SeedReports.list());
	} else {
		try { await ApiClient.updateReport(Number(id), status); } catch (e) {}
		AppState.reports = mergeLocalReports((await ApiClient.reports().catch(() => [])).map(normalizeReport));
		AppState.zones = mergeGroundTruth((await ApiClient.zones().catch(() => AppState.zones)).map(normalizeZone));
	}
	renderState();
	showToast(`Report marked ${status}.`);
}

document.addEventListener('DOMContentLoaded', () => {
	AppState.zones = mergeGroundTruth(AppState.baseline.map(computeRisk));
	AppState.reports = mergeLocalReports(SeedReports.list());
	Dashboard.init({ selectZone, applyScenario, switchView, showToast, submitReport, updateReport, resetDemo, persistAcks });
	MapView.init(selectZone);
	bootstrap();
	loadWeather();
	connectRealtimeStream();
	setInterval(() => {
		loadWeather();   // refresh the browser Open-Meteo pull (cache-backed, cheap within its 10 min TTL)
		if (AppState.backendConnected) { bootstrap(); return; }
		if (AppState.liveWeather || AppState.scenario !== 'Normal' || Date.now() <= (AppState._skipJitterUntil || 0)) return;
		AppState.previousZones = AppState.zones.map(z => ({ ...z }));
		AppState.baseline = AppState.baseline.map(zone => ({
			...zone,
			rainfall: Math.max(0, num(zone.rainfall) + (Math.random() - 0.5) * 0.8),
			moisture: Math.max(0, num(zone.moisture) + (Math.random() - 0.5) * 0.25)
		}));
		AppState.zones = AppState.baseline.map(computeRisk);
		renderState();
	}, 7000);
});
