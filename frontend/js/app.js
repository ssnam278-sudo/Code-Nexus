const MockAPI = (() => {
	const zones = [
		{ id:'tawang', name:'Tawang Corridor', district:'Tawang, Arunachal Pradesh', score:67, base:46, slope:72, susceptibility:82, history:68, exposure:86, rainfall:42.6, moisture:76, temperature:19.4, accumulated:184, confidence:84, coordinates:[27.4728,94.9120] },
		{ id:'siang', name:'East Siang Valley', district:'Pasighat, Arunachal Pradesh', score:52, base:38, slope:61, susceptibility:64, history:54, exposure:72, rainfall:29.8, moisture:64, temperature:22.1, accumulated:138, confidence:79, coordinates:[28.0667,95.3267] },
		{ id:'chura', name:'Churachandpur Ridge', district:'Churachandpur, Manipur', score:41, base:31, slope:55, susceptibility:59, history:48, exposure:63, rainfall:18.4, moisture:51, temperature:24.7, accumulated:96, confidence:76, coordinates:[24.3333,93.6833] },
		{ id:'garo', name:'South Garo Hills', district:'Baghmara, Meghalaya', score:28, base:24, slope:43, susceptibility:42, history:35, exposure:51, rainfall:11.2, moisture:39, temperature:25.8, accumulated:67, confidence:73, coordinates:[25.4969,90.6036] },
		{ id:'bomdila', name:'Bomdila Pass', district:'West Kameng, Arunachal Pradesh', score:19, base:16, slope:38, susceptibility:34, history:25, exposure:32, rainfall:7.4, moisture:29, temperature:14.8, accumulated:42, confidence:78, coordinates:[27.2648,92.4246] },
		{ id:'ziro', name:'Ziro Valley', district:'Lower Subansiri, Arunachal Pradesh', score:34, base:27, slope:48, susceptibility:47, history:31, exposure:58, rainfall:14.6, moisture:46, temperature:20.6, accumulated:81, confidence:75, coordinates:[27.5444,93.8197] },
		{ id:'roing', name:'Roing Foothills', district:'Lower Dibang Valley, Arunachal Pradesh', score:47, base:34, slope:64, susceptibility:68, history:52, exposure:61, rainfall:22.7, moisture:58, temperature:21.2, accumulated:119, confidence:77, coordinates:[28.1397,95.8400] },
		{ id:'ukhrul', name:'Ukhrul Ridge', district:'Ukhrul, Manipur', score:31, base:25, slope:51, susceptibility:45, history:38, exposure:44, rainfall:13.1, moisture:43, temperature:22.8, accumulated:74, confidence:74, coordinates:[25.0968,94.3614] }
	];
	let reports = [{ location:'Tawang Corridor', observation:'Fresh tension cracks observed near km marker 14.2.', severity:'High', time:'14:18 IST', status:'Under review' }, { location:'East Siang Valley', observation:'Drainage channel clear after morning inspection.', severity:'Advisory', time:'13:42 IST', status:'Verified' }];
	return { zones:() => structuredClone(zones), reports:() => structuredClone(reports), addReport:report => { reports.unshift(report); return structuredClone(report); }, submitSimulation:payload => payload };
})();

const AppState = { baseline:MockAPI.zones(), zones:MockAPI.zones(), reports:MockAPI.reports(), selectedZoneId:'tawang', scenario:'Normal', rainfallBoost:0, moistureBoost:0, lastUpdated:new Date(), previousZones:MockAPI.zones() };

function calculateZone(zone) {
	const rainfall = zone.rainfall + AppState.rainfallBoost * (zone.id === 'tawang' ? 1 : .78);
	const moisture = Math.min(98, zone.moisture + AppState.moistureBoost * (zone.id === 'tawang' ? 1 : .72));
	const rainPressure = Math.min(100, rainfall * 1.08 + (zone.accumulated + AppState.rainfallBoost * 1.7) * .08);
	const score = Math.round(Math.min(100, zone.base + rainPressure * .22 + moisture * .16 + zone.slope * .12 + zone.susceptibility * .16 + zone.history * .08));
	const level = score >= 75 ? 'Critical' : score >= 55 ? 'High' : score >= 35 ? 'Advisory' : 'Monitoring';
	return { ...zone, rainfall, moisture, score, level, confidence:Math.min(94, zone.confidence + (level === 'Critical' ? 3 : 0)) };
}
function selectedZone() { return AppState.zones.find(zone => zone.id === AppState.selectedZoneId) || AppState.zones[0]; }
function recalculateState() { AppState.previousZones = AppState.zones.map(zone => ({ ...zone })); AppState.zones = AppState.baseline.map(calculateZone); AppState.lastUpdated = new Date(); Dashboard.render(AppState); MapView.render(AppState); }
function selectZone(id) { AppState.selectedZoneId = id; Dashboard.render(AppState); MapView.render(AppState); }
function applyScenario(scenario) { const values = { Normal:[0,0], 'Heavy Rain':[18,9], 'Extreme Rain':[42,18] }; const [rainfallBoost, moistureBoost] = values[scenario] || values.Normal; AppState.scenario = scenario; AppState.rainfallBoost = rainfallBoost; AppState.moistureBoost = moistureBoost; MockAPI.submitSimulation({ scenario, rainfallBoost, moistureBoost }); recalculateState(); showToast(`${scenario} conditions applied. Risk engine recalculated.`); }
function showToast(message) { const toast = document.getElementById('toast'); toast.textContent = message; toast.classList.add('show'); clearTimeout(showToast.timer); showToast.timer = setTimeout(() => toast.classList.remove('show'), 3000); }
function switchView(view) { document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === view)); document.querySelectorAll('.view').forEach(item => item.classList.toggle('active', item.dataset.section === view)); if (view === 'intelligence') Dashboard.renderIntelligence(AppState); if (view === 'alerts') Dashboard.renderAlertsPage(AppState); if (view === 'reports') Dashboard.renderReports(AppState); }
document.addEventListener('DOMContentLoaded', () => { Dashboard.init({ selectZone, applyScenario, switchView, showToast }); MapView.init(selectZone); recalculateState(); setInterval(() => { if (AppState.scenario === 'Normal') { AppState.baseline = AppState.baseline.map(zone => ({ ...zone, rainfall:Math.max(0, zone.rainfall + (Math.random() - .5) * .8), moisture:Math.max(0, zone.moisture + (Math.random() - .5) * .25) })); recalculateState(); } }, 7000); });