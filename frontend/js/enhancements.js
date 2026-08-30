/* Keeps AppState.mlComparison current for the selected zone. The panel itself is
 * rendered by Dashboard.renderComparison (single renderer) so there is only ever
 * one source of truth. If /api/ml/compare is unreachable the last known result
 * stays on screen (never a blank dash). */
(() => {
    const nameToId = {
        'Tawang Corridor': 'tawang', 'East Siang Valley': 'siang', 'Churachandpur Ridge': 'chura',
        'South Garo Hills': 'garo', 'Bomdila Pass': 'bomdila', 'Ziro Valley': 'ziro',
        'Roing Foothills': 'roing', 'Ukhrul Ridge': 'ukhrul'
    };
    let lastZone = null;

    async function refresh() {
        const S = window.AppState;
        const name = document.getElementById('selected-zone-name')?.textContent;
        const zoneId = nameToId[name] || (S && S.selectedZoneId);
        if (!zoneId) return;
        try {
            const zone = await fetch(`/api/risk?zone_id=${encodeURIComponent(zoneId)}`).then(r => r.json());
            const cmp = await fetch('/api/ml/compare', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(zone)
            }).then(r => r.json());
            if (cmp && cmp.model && S) {
                S.mlComparison = cmp;
                lastZone = zoneId;
                if (window.Dashboard && typeof Dashboard.render === 'function') Dashboard.render(S);
            }
        } catch (e) { /* keep last known result */ }
    }

    window.refreshMlCheck = refresh;   // app.js calls this on zone select
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(refresh, 1500);
        setInterval(refresh, 12000);
    });
})();
