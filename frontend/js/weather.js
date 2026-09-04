/* Live weather from Open-Meteo (free, no key, no auth).
   Fetched once per zone on load, cached in localStorage for 10 minutes.
   Every failure path is silent -> the dashboard falls back to its simulated
   values without a console error. */
const WeatherService = (() => {
	'use strict';

	const CACHE_KEY = 'codenexus.weather.v2';
	const TTL_MS = 10 * 60 * 1000;               // do not poll more than once / 10 min
	const store = {};                            // zoneId -> parsed shape
	let lastFetched = null;
	let ok = false;

	const n = (v, d = 0) => { const x = Number(v); return Number.isFinite(x) ? x : d; };

	function url(lat, lng) {
		return 'https://api.open-meteo.com/v1/forecast'
			+ '?latitude=' + encodeURIComponent(lat)
			+ '&longitude=' + encodeURIComponent(lng)
			+ '&current=temperature_2m,rain,relative_humidity_2m,soil_moisture_0_to_7cm'
			+ '&hourly=rain,soil_moisture_0_to_7cm,temperature_2m'
			+ '&past_hours=24&forecast_hours=48&timezone=Asia%2FKolkata';
	}

	function parse(json) {
		const cur = json.current || {};
		const h = json.hourly || {};
		const times = Array.isArray(h.time) ? h.time : [];
		const rain = (h.rain || []).map(v => Math.max(0, n(v)));
		const soil = (h.soil_moisture_0_to_7cm || []).map(v => n(v) * 100);   // m3/m3 -> %
		const temp = (h.temperature_2m || []).map(v => n(v));

		// locate "now" in the hourly array
		let nowIdx = -1;
		if (cur.time && times.length) {
			const key = String(cur.time).slice(0, 13);
			nowIdx = times.findIndex(t => String(t).slice(0, 13) === key);
		}
		if (nowIdx < 0) nowIdx = Math.min(24, Math.max(0, rain.length - 7));

		const from = Math.max(0, nowIdx - 23);
		const last24Rain = rain.slice(from, nowIdx + 1);

		return {
			rainfall: Math.max(0, n(cur.rain)),
			soilMoisture: Math.max(0, Math.min(100, n(cur.soil_moisture_0_to_7cm) * 100)),
			temperature: n(cur.temperature_2m),
			humidity: n(cur.relative_humidity_2m),
			accumulatedRain24h: last24Rain.reduce((a, b) => a + b, 0),
			hourlyRainfall: last24Rain,
			hourlySoilMoisture: soil.slice(from, nowIdx + 1),
			hourlyTemperature: temp.slice(from, nowIdx + 1),
			forecastRainfall: rain.slice(nowIdx + 1, nowIdx + 49),   // next 48 h
			_fullRain: rain,
			_nowIdx: nowIdx
		};
	}

	async function fetchZone(zone) {
		const co = zone.coordinates || [zone.lat, zone.lng];
		const res = await fetch(url(n(co[0]), n(co[1])), { mode: 'cors', cache: 'no-store' });
		if (!res.ok) throw new Error('open-meteo ' + res.status);
		return parse(await res.json());
	}

	function readCache() {
		try {
			const raw = localStorage.getItem(CACHE_KEY);
			if (!raw) return null;
			const c = JSON.parse(raw);
			if (!c || !c.at || !c.data || (Date.now() - c.at) > TTL_MS) return null;
			return c;
		} catch (e) { return null; }
	}
	function writeCache() {
		try { localStorage.setItem(CACHE_KEY, JSON.stringify({ at: Date.now(), data: store })); } catch (e) {}
	}

	async function loadAll(zones) {
		const cached = readCache();
		if (cached) {
			Object.keys(cached.data).forEach(id => { store[id] = cached.data[id]; });
			lastFetched = new Date(cached.at);
			ok = Object.keys(store).length > 0;
			return { ok, cached: true, lastFetched };
		}
		try {
			const results = await Promise.allSettled((zones || []).map(z => fetchZone(z).then(d => [z.id, d])));
			let any = false;
			results.forEach(r => { if (r.status === 'fulfilled' && r.value) { store[r.value[0]] = r.value[1]; any = true; } });
			if (!any) return { ok: false };
			lastFetched = new Date();
			ok = true;
			writeCache();
			return { ok: true, cached: false, lastFetched };
		} catch (e) {
			return { ok: false };
		}
	}

	function pctChange(series, hoursBack = 6) {
		const arr = Array.isArray(series) ? series : [];
		if (arr.length < hoursBack + 1) return null;
		const now = n(arr[arr.length - 1]);
		const past = n(arr[arr.length - 1 - hoursBack]);
		if (!Number.isFinite(now) || !Number.isFinite(past)) return null;
		if (past === 0) return now === 0 ? 0 : 100;
		return (now - past) / Math.abs(past) * 100;
	}

	return {
		loadAll,
		get: id => store[id] || null,
		hasData: () => ok && Object.keys(store).length > 0,
		lastFetched: () => lastFetched,
		pctChange
	};
})();
if (typeof window !== 'undefined') window.WeatherService = WeatherService;
