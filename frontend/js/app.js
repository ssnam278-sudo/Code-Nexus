/* API boundary: replace these mock providers with Flask fetch calls later. */
const MockAPI = (() => {
	const zones = [
		{ id:'tawang', name:'Tawang Corridor', district:'Tawang, Arunachal Pradesh', score:67, base:46, slope:72, susceptibility:82, history:68, exposure:86, rainfall:42.6, moisture:76, temperature:19.4, accumulated:184, confidence:84, level:'High', coordinates:[27.4728,94.9120] },
		{ id:'siang', name:'East Siang Valley', district:'Pasighat, Arunachal Pradesh', score:52, base:38, slope:61, susceptibility:64, history:54, exposure:72, rainfall:29.8, moisture:64, temperature:22.1, accumulated:138, confidence:79, level:'Advisory', coordinates:[28.0667,95.3267] },
		{ id:'chura', name:'Churachandpur Ridge', district:'Churachandpur, Manipur', score:41, base:31, slope:55, susceptibility:59, history:48, exposure:63, rainfall:18.4, moisture:51, temperature:24.7, accumulated:96, confidence:76, level:'Advisory', coordinates:[24.3333,93.6833] },
		{ id:'garo', name:'South Garo Hills', district:'Baghmara, Meghalaya', score:28, base:24, slope:43, susceptibility:42, history:35, exposure:51, rainfall:11.2, moisture:39, temperature:25.8, accumulated:67, confidence:73, level:'Monitoring', coordinates:[25.4969,90.6036] }
	];
	let reports = [{ location:'Tawang Corridor', observation:'Fresh tension cracks observed near km marker 14.2.', severity:'High', time:'14:18 IST', status:'Under review' }, { location:'East Siang Valley', observation:'Drainage channel clear after morning inspection.', severity:'Advisory', time:'13:42 IST', status:'Verified' }];
	return { getZones:() => structuredClone(zones), getReports:() => structuredClone(reports), addReport:report => { reports.unshift(report); return structuredClone(report); }, submitSimulation:({ rainfall, moisture, scenario }) => ({ rainfall, moisture, scenario }) };
})();

const AppState = { zones:MockAPI.getZones(), reports:MockAPI.getReports(), selectedZoneId:'tawang', scenario:'Normal', rainfallBoost:0, moistureBoost:0, lastUpdated:new Date() };

function calculateZone(zone) {
	const rainfall = zone.rainfall + AppState.rainfallBoost * (zone.id === 'tawang' ? 1 : .78);
	const moisture = Math.min(98, zone.moisture + AppState.moistureBoost * (zone.id === 'tawang' ? 1 : .72));
	const rainFactor = Math.min(100, rainfall * 1.08 + zone.accumulated * .08);
	const score = Math.round(Math.min(100, zone.base + rainFactor * .22 + moisture * .16 + zone.slope * .12 + zone.susceptibility * .16 + zone.history * .08));
	const level = score >= 75 ? 'Critical' : score >= 55 ? 'High' : score >= 35 ? 'Advisory' : 'Monitoring';
	return { ...zone, rainfall, moisture, score, level, confidence:Math.min(94, zone.confidence + (level === 'Critical' ? 3 : 0)) };
}

function recalculateState() { AppState.zones = AppState.zones.map(calculateZone); AppState.lastUpdated = new Date(); Dashboard.render(AppState); MapView.render(AppState); }
function selectZone(id) { AppState.selectedZoneId = id; Dashboard.render(AppState); MapView.render(AppState); }
function applyScenario(scenario) { const values = { Normal:[0,0], 'Heavy Rain':[18,9], 'Extreme Rain':[42,18] }; const [rainfall, moisture] = values[scenario]; AppState.scenario = scenario; AppState.rainfallBoost = rainfall; AppState.moistureBoost = moisture; MockAPI.submitSimulation({ rainfall, moisture, scenario }); recalculateState(); showToast(`${scenario} scenario applied. Risk engine recalculated.`); }
function showToast(message) { const toast = document.getElementById('toast'); toast.textContent = message; toast.classList.add('show'); clearTimeout(showToast.timer); showToast.timer = setTimeout(() => toast.classList.remove('show'), 3200); }
function switchView(view) { document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === view)); document.querySelectorAll('.view').forEach(section => section.classList.toggle('active-view', section.dataset.section === view)); if (view === 'intelligence') Dashboard.renderIntelligence(AppState); if (view === 'alerts') Dashboard.renderAlertsPage(AppState); if (view === 'reports') Dashboard.renderReports(AppState); }

document.addEventListener('DOMContentLoaded', () => { Dashboard.init({ selectZone, applyScenario, switchView, showToast }); MapView.init(selectZone); recalculateState(); setInterval(() => { if (!AppState.rainfallBoost) { AppState.zones = AppState.zones.map(zone => ({ ...zone, rainfall:Math.max(0, zone.rainfall + (Math.random() - .5) * .8), moisture:Math.max(0, zone.moisture + (Math.random() - .5) * .25) })); recalculateState(); } }, 7000); });
