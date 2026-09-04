const MapView = (() => {
    let map;
    let zoneLayer;
    let overlayLayer;
    let selectZone;
    let activeMode = 'risk';
    const layers = {};
    const num = v => Number.isFinite(Number(v)) ? Number(v) : 0;
    const validCoords = z => z && Array.isArray(z.coordinates) && z.coordinates.length === 2 && z.coordinates.every(Number.isFinite);

    // --- Rainfall timeline (weather-radar style) — Rainfall tab only ---
    const RAIN_FRAMES = [{ label: 'Now', h: 0 }, { label: '+6h', h: 6 }, { label: '+24h', h: 24 }];
    let rainFrame = 0;
    let rainPlaying = false;
    let rainTimer = null;
    let liveHazard = {};          // zoneId -> { trajectory }
    let liveHazardAt = 0;
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
            if (activeMode === 'rainfall') { showRainTimeline(); loadLiveHazard(); }
            else { stopRainAnim(); showRainTimeline(false); }
            renderMode(activeMode);
        }));

        // Rainfall timeline control (radar-style play/pause + Now / +6h / +24h scrubber)
        const head = element.closest('.map-shell')?.querySelector('.map-head');
        if (head && !document.getElementById('map-rain-time')) {
            const bar = document.createElement('div');
            bar.className = 'map-rain-time';
            bar.id = 'map-rain-time';
            bar.hidden = true;
            bar.innerHTML =
                '<button id="rain-play" class="rain-play" type="button" aria-label="Play rainfall animation">▶</button>' +
                '<div class="rain-track"><input id="rain-scrub" type="range" min="0" max="2" step="1" value="0" aria-label="Rainfall time">' +
                '<div class="rain-ticks"><span>Now</span><span>+6h</span><span>+24h</span></div></div>' +
                '<span id="rain-frame" class="rain-frame">Now</span>';
            head.appendChild(bar);
            bar.querySelector('#rain-play').addEventListener('click', toggleRainAnim);
            bar.querySelector('#rain-scrub').addEventListener('input', event => {
                stopRainAnim();
                rainFrame = Math.max(0, Math.min(2, parseInt(event.target.value, 10) || 0));
                paintRainFrame();
            });
        }
        window.addEventListener('resize', resize);
        document.addEventListener('codenexus:authenticated', resize);
    }

    function showRainTimeline(on = true) {
        const bar = document.getElementById('map-rain-time');
        if (bar) bar.hidden = !on;
    }
    function loadLiveHazard() {
        if (Date.now() - liveHazardAt < 60000 && Object.keys(liveHazard).length) return Promise.resolve();
        return fetch('/api/live/hazard')
            .then(r => r.json())
            .then(d => {
                (d.zones || []).forEach(z => { if (z && z.zone_id) liveHazard[z.zone_id] = { trajectory: z.trajectory || [] }; });
                liveHazardAt = Date.now();
                if (activeMode === 'rainfall') paintRainFrame();
            })
            .catch(() => { /* fall back to AppState values below */ });
    }
    function toggleRainAnim() {
        rainPlaying ? stopRainAnim() : startRainAnim();
    }
    function startRainAnim() {
        rainPlaying = true;
        const btn = document.getElementById('rain-play');
        if (btn) { btn.textContent = '⏸'; btn.classList.add('playing'); }
        clearInterval(rainTimer);
        rainTimer = setInterval(() => {
            rainFrame = (rainFrame + 1) % RAIN_FRAMES.length;
            paintRainFrame();
        }, 1500);
    }
    function stopRainAnim() {
        rainPlaying = false;
        clearInterval(rainTimer);
        rainTimer = null;
        const btn = document.getElementById('rain-play');
        if (btn) { btn.textContent = '▶'; btn.classList.remove('playing'); }
    }
    // rainfall (mm/hr) at frame `h` hours ahead, from the Live-Forecast trajectory
    // (trailing 3 h mean); falls back to the 6 h browser forecast, then the current value.
    function rainValueForZone(zone, hAhead) {
        const traj = liveHazard[zone.id] && liveHazard[zone.id].trajectory;
        if (traj && traj.length) {
            let nowIdx = 0;
            for (let i = 0; i < traj.length; i++) if (traj[i].kind === 'observed') nowIdx = i;
            const idx = Math.min(traj.length - 1, nowIdx + hAhead);
            const win = traj.slice(Math.max(0, idx - 2), idx + 1).map(s => num(s.rain)).filter(Number.isFinite);
            if (win.length) return win.reduce((a, b) => a + b, 0) / win.length;
        }
        const fc = zone.forecastRainfall;
        if (hAhead > 0 && Array.isArray(fc) && fc.length) {
            const idx = Math.min(fc.length - 1, hAhead - 1);
            const win = fc.slice(Math.max(0, idx - 2), idx + 1).map(num).filter(Number.isFinite);
            if (win.length) return win.reduce((a, b) => a + b, 0) / win.length;
        }
        return num(zone.rainfall);
    }
    function paintRainFields(zones) {
        const frame = RAIN_FRAMES[rainFrame];
        (zones || []).filter(validCoords).forEach(z => drawRainfall(z, rainValueForZone(z, frame.h), frame.label));
        const lbl = document.getElementById('rain-frame');
        if (lbl) lbl.textContent = frame.label;
        const scr = document.getElementById('rain-scrub');
        if (scr && +scr.value !== rainFrame) scr.value = String(rainFrame);
    }
    function paintRainFrame() {
        if (activeMode !== 'rainfall' || !map || !overlayLayer) return;
        if (document.querySelector('.view.active') && document.querySelector('.view.active').dataset.section !== 'dashboard') return;
        overlayLayer.clearLayers();
        paintRainFields(window.AppState && window.AppState.zones);
    }

    function resize() { if (map) requestAnimationFrame(() => map.invalidateSize({ animate:false })); }

    // --- Rainfall map: a filled radial rain field per zone, coloured on a
    //     rainfall-intensity ramp. `value` is mm/hr at the current timeline frame. ---
    function rainRamp(v) {
        if (v >= 50) return '#d34438';
        if (v >= 30) return '#e07b38';
        if (v >= 15) return '#d9a441';
        if (v >= 5)  return '#4dae8f';
        if (v >= 1)  return '#5aa9c9';
        return '#8fb9c9';
    }
    function drawRainfall(zone, value, frameLabel) {
        value = Math.max(0, num(value));
        const dry = value < 1;
        // outer radius 9 km (dry) -> ~40 km (torrential); visible at region zoom
        const outer = 9000 + Math.min(value, 60) * 520;
        const col = rainRamp(value);
        const tag = (frameLabel && frameLabel !== 'Now' ? ` (${frameLabel})` : '') + (dry ? ' · no rain' : '');
        const label = `${zone.name}: ${value.toFixed(1)} mm/hr${tag}`;
        [[1, 0.10], [0.7, 0.16], [0.44, 0.24], [0.22, 0.34]].forEach((ring, i) => {
            const c = L.circle(zone.coordinates, {
                radius: outer * ring[0], stroke: i === 0, color: col, weight: 1.5, opacity: 0.5,
                fillColor: col, fillOpacity: ring[1] * (dry ? 0.55 : 1), className: 'rain-field'
            }).addTo(overlayLayer);
            if (i === 0) c.bindTooltip(label, { sticky: true });
        });
    }

    // --- Exposure map: a choropleth-style circle per zone sized/coloured by the
    //     exposure index (+ population when known), with the individual assets
    //     drawn as diamonds on top. ---
    function expoRamp(v) {
        if (v >= 80) return '#c94f43';
        if (v >= 60) return '#e07b38';
        if (v >= 40) return '#d9a441';
        return '#8ab07a';
    }
    function drawExposure(state) {
        (state.zones || [])
            .filter(z => Array.isArray(z.coordinates) && z.coordinates.length === 2 && z.coordinates.every(Number.isFinite))
            .forEach(z => {
                const ex = num(z.exposure);
                const R = Math.max(1400, Math.min(6500, num(z.population) || ex * 70));
                const col = expoRamp(ex);
                const label = `${z.name}: exposure ${Math.round(ex)}/100` + (z.population ? ` · ≈${Number(z.population).toLocaleString()} people` : '');
                [[1, 0.06], [0.62, 0.11], [0.32, 0.18]].forEach((ring, i) => {
                    const c = L.circle(z.coordinates, {
                        radius: R * ring[0], stroke: i === 0, color: col, weight: 1, opacity: 0.3,
                        fillColor: col, fillOpacity: ring[1], className: 'expo-field'
                    }).addTo(overlayLayer);
                    if (i === 0) c.bindTooltip(label, { sticky: true });
                });
            });
        (state.exposure && state.exposure.features || [])
            .filter(f => f.properties && f.properties.feature_type === 'infrastructure')
            .forEach(f => {
                const co = f.geometry.coordinates;
                L.marker([co[1], co[0]], { icon: L.divIcon({ className: 'expo-asset', html: '◆', iconSize: [16, 16] }) })
                    .addTo(overlayLayer)
                    .bindTooltip((f.properties.name || 'Exposed asset') + (f.properties.type ? ' · ' + f.properties.type : ''));
            });
    }

    // --- Roads & evacuation: three animated "marching ants" routes radiating
    //     from the selected zone to assembly points, over the bright road tiles. ---
    function drawEvacuationRoutes(zone) {
        const lat = zone.coordinates[0], lng = zone.coordinates[1];
        const routes = [
            [[lat, lng], [lat - 0.028, lng - 0.04], [lat - 0.066, lng - 0.088]],
            [[lat, lng], [lat + 0.022, lng - 0.03], [lat + 0.05, lng - 0.082]],
            [[lat, lng], [lat - 0.04, lng + 0.028], [lat - 0.078, lng + 0.06]]
        ];
        routes.forEach((pts, i) => {
            L.polyline(pts, { color: '#4db0a6', weight: 4, opacity: 0.95, className: 'evac-flow', lineCap: 'round' })
                .addTo(overlayLayer)
                .bindTooltip('Prototype evacuation route ' + (i + 1));
            L.circleMarker(pts[pts.length - 1], { radius: 5, color: '#2f8b6f', fillColor: '#e2f4ef', fillOpacity: 1, weight: 2 })
                .addTo(overlayLayer).bindTooltip('Assembly point');
        });
    }

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
        if (activeMode === 'rainfall') paintRainFields(state.zones);
        if (activeMode === 'exposure') drawExposure(state);
        if (activeMode === 'roads') drawEvacuationRoutes(selected);
        if (activeMode === 'terrain') { map.removeLayer(layers.satellite); layers.terrain.addTo(map); } else { map.removeLayer(layers.terrain); layers.satellite.addTo(map); }
        layers.roads.setOpacity(activeMode === 'roads' ? .9 : .35);
        if (selected.id !== map._selectedZone) map._selectedZone = selected.id;
    }

    function renderLocationSwitcher(state) { const switcher = document.getElementById('map-location-switcher'); if (!switcher) return; switcher.innerHTML = state.zones.map(zone => `<button class="map-place ${zone.id === state.selectedZoneId ? 'active' : ''}" data-map-zone="${zone.id}"><i class="place-dot" style="background:${color(zone)}"></i><span>${zone.name || '—'}</span><b>${Math.round(num(zone.score))}</b></button>`).join(''); switcher.querySelectorAll('[data-map-zone]').forEach(button => button.addEventListener('click', () => selectZone(button.dataset.mapZone))); }
    const MODE_LABELS = { risk: 'RISK OVERLAY', rainfall: 'RAINFALL MAP', terrain: 'TERRAIN BASEMAP', exposure: 'EXPOSURE MAP', roads: 'ROADS & EVACUATION' };
    function renderMode(mode) { const label = document.getElementById('active-layer'); if (label) label.textContent = MODE_LABELS[mode] || `${mode.toUpperCase()} OVERLAY`; if (window.AppState) render(window.AppState); }
    return { init, render };
})();
