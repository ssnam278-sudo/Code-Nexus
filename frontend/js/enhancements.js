(() => {
    const zoneIds = { 'Tawang Corridor':'tawang', 'East Siang Valley':'siang', 'Churachandpur Ridge':'chura', 'South Garo Hills':'garo', 'Bomdila Pass':'bomdila', 'Ziro Valley':'ziro', 'Roing Foothills':'roing', 'Ukhrul Ridge':'ukhrul' };
    async function refreshComparison() {
        const panel = document.getElementById('ai-comparison-body');
        const name = document.getElementById('selected-zone-name')?.textContent;
        const zoneId = zoneIds[name];
        if (!panel || !zoneId) return;
        try {
            const zone = await fetch(`/api/risk?zone_id=${zoneId}`).then(response => response.json());
            const comparison = await fetch('/api/ml/compare', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(zone) }).then(response => response.json());
            const model = comparison.model;
            const baseline = comparison.baseline;
            const badge = document.getElementById('ai-review-badge');
            badge.textContent = comparison.comparison.agrees ? 'AGREEMENT' : 'REVIEW REQUIRED';
            badge.className = `comparison-badge ${comparison.comparison.agrees ? 'agree' : 'review'}`;
            panel.innerHTML = `<div class="comparison-scores"><span>BASELINE <b>${baseline.risk_score} · ${baseline.risk_level}</b></span><span>AI MODEL <b>${model.prediction} · ${model.confidence}%</b></span></div><p>${model.explanation}</p><div class="ai-drivers">${model.top_drivers.map(driver => `<span>${driver.name}<b>${driver.importance}%</b></span>`).join('')}</div>`;
        } catch (error) { panel.innerHTML = '<p>AI comparison unavailable. Baseline remains active.</p>'; }
    }
    document.addEventListener('DOMContentLoaded', () => { setTimeout(refreshComparison, 1200); setInterval(refreshComparison, 7000); });
})();
