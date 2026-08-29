const MapView = (() => {
    let map;
    let zoneLayer;
    let overlayLayer;
    let selectZone;
    let activeMode = 'risk';
    const layers = {};
    const num = v => Number.isFinite(Number(v)) ? Number(v) : 0;
    const color = zone => (zone && zone.level) === 'Critical' ? '#d34438' : (zone && zone.level) === 'High' ? '#d36c36' : (zone && zone.level) === 'Advisory' ? '#d5a03b' : '#4d9d69';

    function init(selectCallback) {
        selectZone = selectCallback;
        const element = document.getElementById('risk-map');
        if (!window.L || !element) return;
        map = L.map(element, { zoomControl:false, attributionControl:true, minZoom:5, maxZoom:18, zoomSnap:.25, scrollWheelZoom:true }).setView([26.85, 93.7], 6);
        L.control.zoom({ position:'bottomright' }).addTo(map);
        layers.terrain = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', { maxZoom:17, attribution:'OpenTopoMap' });
        layers.satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom:19, attribution:'Esri World Imagery' }).addTo(map);
        layers.roads = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom:19, opacity:.45, attribution:'OpenStreetMap' }).addTo(map);
        zoneLayer = L.layerGroup().addTo(map);
        overlayLayer = L.layerGroup().addTo(map);
        document.querySelectorAll('.map-control').forEach(button => button.addEventListener('click', () => {
            document.querySelectorAll('.map-control').forEach(item => item.classList.remove('active'));
            button.classList.add('active');
            activeMode = button.dataset.mapMode;
            renderMode(activeMode);
        }));
        const head = element.closest('.map-shell')?.querySelector('.map-head');
        if (head && !document.getElementById('map-time-range')) {
            const control = document.createElement('label');
            control.className = 'map-time-control';
            control.innerHTML = 'RAINFALL <select id="map-time-range"><option value="now">Now (mm/hr)</option><option value="24h">24-h total (mm)</option></select>';
            head.appendChild(control);
            control.querySelector('select').addEventListener('change', event => { map._timeWindow = event.target.value; renderMode(activeMode); });
        }
        window.addEventListener('resize', resize);
        document.addEventListener('codenexus:authenticated', resize);
    }

    function resize() { if (map) requestAnimationFrame(() => map.invalidateSize({ animate:false })); }
    function drawRainfall(zone, windowName) {
        // both driven by real Open-Meteo values on the zone record
        const is24 = windowName === '24h';
        const value = Math.max(0, num(is24 ? zone.accumulated : zone.rainfall));
        const radius = is24
            ? Math.max(400, Math.min(3200, value * 7))
            : Math.max(400, Math.min(2600, value * 34));
        L.circle(zone.coordinates, { radius, color:'#e07b38', weight:2, dashArray:'6 7', fillColor:'#e07b38', fillOpacity:.11, className:'rainfall-ring' })
            .bindTooltip(`${zone.name}: ${value.toFixed(1)} ${is24 ? 'mm / 24 h' : 'mm / hr'}`)
            .addTo(overlayLayer);
    }
    function drawExposure(state) { (state.exposure?.features || []).filter(feature => feature.properties?.feature_type === 'infrastructure').forEach(feature => { const [longitude, latitude] = feature.geometry.coordinates; L.circleMarker([latitude, longitude], { radius:7, color:'#f0a33c', fillColor:'#fff4c2', fillOpacity:.95, weight:2 }).bindTooltip(feature.properties.name || 'Exposed asset').addTo(overlayLayer); }); }
    function drawEvacuationRoutes(zone) { const [latitude, longitude] = zone.coordinates; L.polyline([[latitude - .06, longitude - .08], [latitude - .025, longitude - .025], [latitude, longitude]], { color:'#4b9f91', weight:4, dashArray:'10 8', opacity:.9 }).bindTooltip('Prototype evacuation route').addTo(overlayLayer); }

    function render(state) {
        const selected = state.zones.find(zone => zone.id === state.selectedZoneId) || state.zones[0];
        if (!selected || !Array.isArray(selected.coordinates) || selected.coordinates.some(value => !Number.isFinite(value))) return;
        document.getElementById('coordinates').textContent = `${selected.coordinates[0].toFixed(4)}° N, ${selected.coordinates[1].toFixed(4)}° E`;
        renderLocationSwitcher(state);
        if (!map) return;
        zoneLayer.clearLayers();
        overlayLayer.clearLayers();
        (state.zones || []).filter(zone => Array.isArray(zone.coordinates) && zone.coordinates.length === 2 && zone.coordinates.every(Number.isFinite)).forEach(zone => {
            const selectedZone = zone.id === state.selectedZoneId;
            const marker = L.circleMarker(zone.coordinates, { radius:selectedZone ? 10 : 7, color:color(zone), fillColor:color(zone), fillOpacity:.9, weight:selectedZone ? 3 : 2, className: zone.level === 'Critical' || zone.level === 'High' ? 'risk-pulse' : '' });
            marker.bindTooltip(`<strong>${zone.name}</strong><br>${zone.level || 'Monitoring'} · Score ${Math.round(num(zone.score))}`);
            marker.on('click', () => selectZone(zone.id));
            marker.addTo(zoneLayer);
        });
        if (activeMode === 'rainfall') state.zones.filter(zone => Array.isArray(zone.coordinates) && zone.coordinates.length === 2 && zone.coordinates.every(Number.isFinite)).forEach(zone => drawRainfall(zone, map._timeWindow || 'now'));
        if (activeMode === 'exposure') drawExposure(state);
        if (activeMode === 'roads') drawEvacuationRoutes(selected);
        if (activeMode === 'terrain') { map.removeLayer(layers.satellite); layers.terrain.addTo(map); } else { map.removeLayer(layers.terrain); layers.satellite.addTo(map); }
        layers.roads.setOpacity(activeMode === 'roads' ? .9 : .35);
        if (selected.id !== map._selectedZone) map._selectedZone = selected.id;
    }

    function renderLocationSwitcher(state) { const switcher = document.getElementById('map-location-switcher'); if (!switcher) return; switcher.innerHTML = state.zones.map(zone => `<button class="map-place ${zone.id === state.selectedZoneId ? 'active' : ''}" data-map-zone="${zone.id}"><i class="place-dot" style="background:${color(zone)}"></i><span>${zone.name || '—'}</span><b>${Math.round(num(zone.score))}</b></button>`).join(''); switcher.querySelectorAll('[data-map-zone]').forEach(button => button.addEventListener('click', () => selectZone(button.dataset.mapZone))); }
    function renderMode(mode) { const label = document.getElementById('active-layer'); if (label) label.textContent = `${mode.toUpperCase()} OVERLAY`; if (window.AppState) render(window.AppState); }
    return { init, render };
})();
