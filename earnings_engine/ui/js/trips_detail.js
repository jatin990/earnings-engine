// trips_detail.js — Task 6 render functions (auto-generated)

let trekMap = null;
let trekPolyline = null;

// ---- Trek Route Map (Leaflet + OpenStreetMap) ----
function initTrekMap() {
    const mapEl = document.getElementById('trekMap');
    if (!mapEl) return;
    if (trekMap) { trekMap.remove(); trekMap = null; }

    // Trek waypoints: [lat, lng, label, day]
    const waypoints = [
        [28.2096, 83.9855, "Pokhara (Start)", 1],
        [28.3667, 83.7333, "Nayapul Trailhead", 2],
        [28.4972, 83.7378, "Tikhedhunga", 2],
        [28.5397, 83.7208, "Ghorepani", 3],
        [28.5333, 83.7167, "Poon Hill (3210m)", 4],
        [28.5583, 83.7167, "Tadapani", 4],
        [28.5833, 83.7500, "Chhomrong", 5],
        [28.6333, 83.7833, "Bamboo", 6],
        [28.6667, 83.8167, "Deurali", 7],
        [28.7089, 83.9583, "Machhapuchhre BC (MBC)", 8],
        [28.7167, 84.0833, "Annapurna Base Camp (4130m)", 8],
        [28.6333, 83.7833, "Bamboo (Return)", 9],
        [28.3667, 83.7333, "Nayapul (Return)", 10],
        [28.2096, 83.9855, "Pokhara", 10],
        [28.4167, 83.7000, "Kushma Bungee (228m)", 11],
    ];

    // Remove old map container content and rebuild
    mapEl.innerHTML = '';

    // Add title above map
    const title = document.createElement('p');
    title.className = 'text-xs text-slate-400 mb-2 px-1';
    title.textContent = 'Trek route — OpenStreetMap (click markers for day info)';
    mapEl.appendChild(title);

    const mapDiv = document.createElement('div');
    mapDiv.style.height = '350px';
    mapDiv.style.borderRadius = '12px';
    mapEl.appendChild(mapDiv);

    trekMap = L.map(mapDiv).setView([28.55, 83.88], 12);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 17,
    }).addTo(trekMap);

    const routeCoords = waypoints.map(w => [w[0], w[1]]);

    // Draw route polyline
    trekPolyline = L.polyline(routeCoords, {
        color: '#0ea5e9',
        weight: 3,
        opacity: 0.85,
        dashArray: '6 4',
    }).addTo(trekMap);

    // Add numbered day markers
    waypoints.forEach((w, i) => {
        const isStart = i === 0;
        const isEnd = i === waypoints.length - 1;
        const isABC = w[2].includes('ABC');
        const isBungee = w[2].includes('Bungee');
        const color = isABC ? '#ef4444' : isBungee ? '#22c55e' : isStart || isEnd ? '#3b82f6' : '#6366f1';
        const radius = isABC || isBungee ? 9 : 6;

        L.circleMarker([w[0], w[1]], {
            radius, color, fillColor: color, fillOpacity: 0.9, weight: 2,
        }).addTo(trekMap)
          .bindPopup(`<b>Day ${w[3]}:</b> ${w[2]}`);
    });

    trekMap.fitBounds(trekPolyline.getBounds(), { padding: [20, 20] });
}

// ---- Block 4 ----
function renderItinerary() {
    const container = document.getElementById('detail-tab-itinerary');
    if (!container) return;

    // Init Leaflet trek map
    initTrekMap();

    // Day table
    const diffColors = {
        'Rest': 'bg-slate-700 text-slate-300',
        'Easy': 'bg-green-900 text-green-300',
        'Moderate': 'bg-yellow-900 text-yellow-300',
        'Hard': 'bg-red-900 text-red-300'
    };

    let tableRows = currentItinerary.map(day => {
        const diff = diffColors[day.difficulty] || 'bg-slate-700 text-slate-300';
        const alert = day.trail_alert
            ? `<span class="ml-2 text-xs text-orange-400" title="${day.trail_alert}">⚠️</span>`
            : '';
        const dist = day.distance_km ? `${day.distance_km}km` : '—';
        const alt = day.altitude_meters ? `${day.altitude_meters.toLocaleString()}m` : '—';
        return `
            <tr class="border-t border-slate-700 hover:bg-slate-800/50 cursor-pointer"
                onclick="toggleItineraryDay('${day.day_id}')">
                <td class="py-2 px-3 text-slate-400 text-sm">D${day.day_number}</td>
                <td class="py-2 px-3 text-slate-300 text-sm">${day.date || '—'}</td>
                <td class="py-2 px-3 text-slate-200 text-sm font-medium">
                    ${day.title}${alert}
                </td>
                <td class="py-2 px-3 text-slate-400 text-sm">${alt}</td>
                <td class="py-2 px-3 text-slate-400 text-sm">${dist}</td>
                <td class="py-2 px-3">
                    <span class="text-xs px-2 py-0.5 rounded ${diff}">${day.difficulty}</span>
                </td>
            </tr>
            <tr id="itin-expand-${day.day_id}" class="hidden bg-slate-900/50">
                <td colspan="6" class="px-4 py-3">
                    <div class="text-slate-300 text-sm mb-1">
                        <span class="text-slate-500">Route:</span> ${day.start_point || ''} → ${day.end_point || ''}
                    </div>
                    ${day.accommodation ? `<div class="text-slate-300 text-sm mb-1"><span class="text-slate-500">Stay:</span> ${day.accommodation}</div>` : ''}
                    ${day.meals ? `<div class="text-slate-300 text-sm mb-1"><span class="text-slate-500">Meals:</span> ${day.meals}</div>` : ''}
                    ${day.description ? `<div class="text-slate-300 text-sm mb-1">${day.description}</div>` : ''}
                    ${day.trail_alert ? `<div class="text-orange-400 text-sm mt-2 p-2 bg-orange-900/20 rounded border border-orange-800">${day.trail_alert}</div>` : ''}
                </td>
            </tr>
        `;
    }).join('');

    // SVG elevation profile
    const svgHtml = buildElevationSVG(currentItinerary);

    container.innerHTML = `
        <div class="mb-4">
            <h3 class="text-slate-200 font-semibold mb-3">11-Day Trek Itinerary</h3>
            <div class="overflow-x-auto">
                <table class="w-full text-left">
                    <thead>
                        <tr class="text-xs text-slate-500 uppercase tracking-wide">
                            <th class="py-2 px-3">Day</th>
                            <th class="py-2 px-3">Date</th>
                            <th class="py-2 px-3">Segment</th>
                            <th class="py-2 px-3">Altitude</th>
                            <th class="py-2 px-3">Distance</th>
                            <th class="py-2 px-3">Difficulty</th>
                        </tr>
                    </thead>
                    <tbody>${tableRows}</tbody>
                </table>
            </div>
        </div>
        <div class="mt-6">
            <h4 class="text-slate-400 text-sm font-medium mb-2">Elevation Profile</h4>
            ${svgHtml}
            <p class="text-xs text-slate-500 mt-1">⚠️ Orange markers = flood-affected segments. Verify route with TIMS/ACAP rangers on site.</p>
        </div>
    `;
}

function toggleItineraryDay(dayId) {
    const row = document.getElementById(`itin-expand-${dayId}`);
    if (row) row.classList.toggle('hidden');
}

// ---- Block 5 ----
function buildElevationSVG(days) {
    const W = 600, H = 180, PAD = { top: 20, right: 20, bottom: 40, left: 50 };
    const innerW = W - PAD.left - PAD.right;
    const innerH = H - PAD.top - PAD.bottom;
    const maxAlt = 4500, minAlt = 0;
    const n = days.length;
    if (n === 0) return '';

    const xScale = i => PAD.left + (i / (n - 1)) * innerW;
    const yScale = alt => PAD.top + innerH - ((alt - minAlt) / (maxAlt - minAlt)) * innerH;

    // Build path and dots
    const pts = days.map((d, i) => ({ x: xScale(i), y: yScale(d.altitude_meters || 0), day: d }));
    const pathD = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
    
    // Area fill (closed path)
    const areaD = pathD + ` L ${pts[n-1].x.toFixed(1)} ${(PAD.top + innerH).toFixed(1)} L ${pts[0].x.toFixed(1)} ${(PAD.top + innerH).toFixed(1)} Z`;

    // Y axis labels
    const yLabels = [0, 1000, 2000, 3000, 4000].map(alt => {
        const y = yScale(alt);
        return `<text x="${PAD.left - 6}" y="${y}" text-anchor="end" font-size="9" fill="#64748b">${alt}m</text>`;
    }).join('');

    // X axis (day numbers)
    const xLabels = pts.map((p, i) => {
        return `<text x="${p.x}" y="${PAD.top + innerH + 14}" text-anchor="middle" font-size="9" fill="#64748b">D${i+1}</text>`;
    }).join('');

    // Dots — flood days get orange
    const dots = pts.map(p => {
        const isFlood = !!p.day.trail_alert;
        const color = isFlood ? '#f97316' : '#38bdf8';
        const r = isFlood ? 5 : 4;
        return `
            <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${r}" fill="${color}" stroke="#0f172a" stroke-width="1.5">
                <title>${p.day.title} (${p.day.altitude_meters}m)</title>
            </circle>
        `;
    }).join('');

    return `
        <svg viewBox="0 0 ${W} ${H}" class="w-full h-auto" style="background:#0f172a; border-radius:8px; border:1px solid #1e293b" aria-label="ABC Trek elevation profile">
            <defs>
                <linearGradient id="elevGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#0ea5e9" stop-opacity="0.3"/>
                    <stop offset="100%" stop-color="#0ea5e9" stop-opacity="0.02"/>
                </linearGradient>
            </defs>
            <!-- Grid lines -->
            ${[1000,2000,3000,4000].map(alt => {
                const y = yScale(alt);
                return `<line x1="${PAD.left}" y1="${y}" x2="${PAD.left + innerW}" y2="${y}" stroke="#1e293b" stroke-width="1"/>`;
            }).join('')}
            <!-- Area fill -->
            <path d="${areaD}" fill="url(#elevGrad)"/>
            <!-- Line -->
            <path d="${pathD}" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linejoin="round"/>
            <!-- Dots -->
            ${dots}
            <!-- Y axis labels -->
            ${yLabels}
            <!-- X axis labels -->
            ${xLabels}
            <!-- Axis lines -->
            <line x1="${PAD.left}" y1="${PAD.top}" x2="${PAD.left}" y2="${PAD.top + innerH}" stroke="#334155" stroke-width="1"/>
            <line x1="${PAD.left}" y1="${PAD.top + innerH}" x2="${PAD.left + innerW}" y2="${PAD.top + innerH}" stroke="#334155" stroke-width="1"/>
        </svg>
    `;
}

// ---- Block 6 ----
function renderPackingList() {
    const container = document.getElementById('detail-tab-packing');
    if (!container) return;

    // Determine member columns
    const members = currentTripMembers.length > 0
        ? currentTripMembers.map(m => m.name)
        : ['Owner'];

    // Group items by category
    const grouped = {};
    currentPackingItems.forEach(item => {
        if (!grouped[item.category]) grouped[item.category] = [];
        grouped[item.category].push(item);
    });

    const statusIcon = s => s === 'confirmed' ? '✅' : s === 'packed' ? '📦' : '🔲';
    const statusNext = {'pending':'packed','packed':'confirmed','confirmed':'pending'};

    const memberHeaders = members.map(m =>
        `<th class="py-2 px-2 text-center text-xs text-slate-500 font-normal">${m}</th>`
    ).join('');

    let rows = '';
    const categoryOrder = ['Clothing','Gear','Documents','Medicine','Nutrition','Misc'];
    const orderedCats = [...categoryOrder.filter(c => grouped[c]), ...Object.keys(grouped).filter(c => !categoryOrder.includes(c))];

    orderedCats.forEach(cat => {
        rows += `<tr><td colspan="${3 + members.length}" class="pt-4 pb-1 px-3 text-xs text-slate-500 uppercase tracking-wide font-semibold">${cat}</td></tr>`;
        grouped[cat].forEach(item => {
            const memberCells = members.map(memberName => {
                const st = (item.statuses && item.statuses[memberName]) || 'pending';
                const icon = statusIcon(st);
                const next = statusNext[st];
                return `<td class="py-2 px-2 text-center">
                    <button onclick="togglePackingStatus('${item.item_id}','${memberName}','${next}')"
                        class="text-lg hover:scale-110 transition-transform" title="${st}">
                        ${icon}
                    </button>
                </td>`;
            }).join('');
            const deleteBtn = isOwner
                ? `<button onclick="deletePackingItem('${item.item_id}')" class="text-slate-600 hover:text-red-400 ml-2 text-xs">×</button>`
                : '';
            rows += `
                <tr id="pack-row-${item.item_id}" class="border-t border-slate-800 hover:bg-slate-800/30">
                    <td class="py-2 px-3 text-slate-200 text-sm">${item.name}${deleteBtn}</td>
                    <td class="py-2 px-3 text-slate-500 text-xs">${item.added_by}</td>
                    ${memberCells}
                </tr>
            `;
        });
    });

    container.innerHTML = `
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-slate-200 font-semibold">Packing Checklist</h3>
            <button onclick="openAddPackingItemModal()" 
                class="text-xs px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors">
                + Add Item
            </button>
        </div>
        <div class="overflow-x-auto">
            <table class="w-full text-left">
                <thead>
                    <tr class="text-xs text-slate-500 uppercase tracking-wide">
                        <th class="py-2 px-3">Item</th>
                        <th class="py-2 px-3">Added by</th>
                        ${memberHeaders}
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
        <p class="text-xs text-slate-600 mt-3">🔲 Pending → 📦 Packed → ✅ Confirmed. Click your column to toggle.</p>
    `;
}

async function togglePackingStatus(itemId, memberName, newStatus) {
    // Optimistic update
    const item = currentPackingItems.find(i => i.item_id === itemId);
    if (item) {
        if (!item.statuses) item.statuses = {};
        item.statuses[memberName] = newStatus;
        renderPackingList();
    }
    // Background PATCH
    await fetch(`/api/v1/trips/${selectedTripId}/packing/${itemId}/status`, {
        method: 'PATCH',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({member_name: memberName, status: newStatus})
    });
}

async function deletePackingItem(itemId) {
    if (!confirm('Remove this packing item?')) return;
    currentPackingItems = currentPackingItems.filter(i => i.item_id !== itemId);
    renderPackingList();
    await fetch(`/api/v1/trips/${selectedTripId}/packing/${itemId}`, {method: 'DELETE'});
}

function openAddPackingItemModal() {
    // Show a simple inline prompt or a small modal
    // Use the existing modal pattern in the template for consistency
    document.getElementById('addPackingModal').classList.remove('hidden');
}

// ---- Block 7 ----
async function submitAddPackingItem() {
    const name = document.getElementById('newPackItemName').value.trim();
    const category = document.getElementById('newPackItemCategory').value;
    const addedBy = currentUserName || 'owner';
    if (!name) return;

    const res = await fetch(`/api/v1/trips/${selectedTripId}/packing`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({name, category, added_by: addedBy})
    });
    const data = await res.json();
    if (data.item) {
        data.item.statuses = {};
        currentPackingItems.push(data.item);
        renderPackingList();
    }
    document.getElementById('addPackingModal').classList.add('hidden');
    document.getElementById('newPackItemName').value = '';
}
