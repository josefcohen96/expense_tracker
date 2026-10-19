// ─── State ────────────────────────────────────────────────────────────────────
const PAGE_DATA = JSON.parse(document.getElementById('seating-data').textContent);
const TABLES   = PAGE_DATA.tables;
const GUESTS   = PAGE_DATA.all_guests;
const ASSIGNS  = PAGE_DATA.assignments;

// build quick lookup maps
const tableMap   = {};   // id -> table obj
const assignMap  = {};   // tableId -> { seatNum -> guestId }
const guestAssign= {};   // guestId -> {table_id, seat_number}
const guestMap   = {};   // guestId -> guest obj

GUESTS.forEach(g => { guestMap[g.id] = g; });
ASSIGNS.forEach(a => {
    assignMap[a.table_id] = assignMap[a.table_id] || {};
    assignMap[a.table_id][a.seat_number] = a.guest_id;
    if (!guestAssign[a.guest_id]) {
        guestAssign[a.guest_id] = { table_id: a.table_id, seat_number: a.seat_number, seats: [a.seat_number] };
    } else {
        guestAssign[a.guest_id].seats.push(a.seat_number);
    }
});
TABLES.forEach(t => { tableMap[t.id] = t; });

let selectedColor = 'rose';
let dragGuestId   = null;   // guest being dragged
let dragTableId   = null;   // table being dragged (repositioning)
let dragOffX = 0, dragOffY = 0;
let panelOpen = true;
let assignTarget = null;    // {table_id, seat_number}

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    TABLES.forEach(t => renderTable(t));
    renderPanel();
    updateStats();
});

// ─── Stats ────────────────────────────────────────────────────────────────────
function personCount(g) { return 1 + (g.plus_one||0) + (g.children_count||0); }

function updateStats() {
    const seatedPeople = Object.keys(guestAssign).reduce((s, gid) => {
        const g = guestMap[parseInt(gid)];
        return g ? s + personCount(g) : s;
    }, 0);
    const totalPeople = GUESTS.reduce((s, g) => s + personCount(g), 0);
    document.getElementById('stat-seated').textContent = seatedPeople;
    document.getElementById('stat-total').textContent = totalPeople;
    document.getElementById('stat-unassigned').textContent = Math.max(0, totalPeople - seatedPeople);
    document.getElementById('stat-tables').textContent = Object.keys(tableMap).length;
    document.getElementById('stat-capacity').textContent = Object.values(tableMap).reduce((s, t) => s + t.capacity, 0);
}

// ─── Panel ────────────────────────────────────────────────────────────────────
function renderPanel(filter) {
    const body = document.getElementById('panel-body');
    const unseated = GUESTS.filter(g => g.status !== 'declined' && !guestAssign[g.id]);
    const list = filter
        ? unseated.filter(g => g.name.includes(filter) || (g.group_name||'').includes(filter) || (g.plus_one_name||'').includes(filter))
        : unseated;
    if (!list.length) {
        body.innerHTML = '<div class="panel-empty">כל המוזמנים מוושבים 🎉</div>';
        return;
    }
    body.innerHTML = list.map(g => {
        const n = personCount(g);
        const plusTag  = g.plus_one ? `<span class="g-plus-tag">+${escHtml(g.plus_one_name || '1')}</span>` : '';
        const childTag = g.children_count > 0 ? `<span class="g-child-tag">${g.children_count} ילד${g.children_count > 1 ? 'ים' : ''}</span>` : '';
        const extrasHtml = (plusTag || childTag) ? `<div class="g-extras">${plusTag}${childTag}</div>` : '';
        return `
        <div class="guest-card" draggable="true"
             data-guest-id="${g.id}"
             ondragstart="guestDragStart(event,${g.id})"
             ondragend="guestDragEnd(event)">
            <div class="g-name">${escHtml(g.name)}${n > 1 ? `<span class="g-badge">👤${n}</span>` : ''}</div>
            ${extrasHtml}
            ${g.group_name ? `<div class="g-group">${escHtml(g.group_name)}</div>` : ''}
        </div>`;
    }).join('');
}

function filterPanelGuests(val) { renderPanel(val || null); }

function toggleGuestsPanel() {
    panelOpen = !panelOpen;
    document.getElementById('guests-panel').classList.toggle('collapsed', !panelOpen);
}

// ─── Table rendering ──────────────────────────────────────────────────────────
function renderTable(t) {
    const existing = document.getElementById('tbl-' + t.id);
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.className = 'table-widget';
    div.id = 'tbl-' + t.id;
    div.dataset.tableId = t.id;
    div.dataset.color = t.color || 'rose';
    div.style.left = (t.x || 100) + 'px';
    div.style.top  = (t.y || 100) + 'px';

    div.innerHTML = `
        <div class="table-label">
            <span class="tbl-name">${escHtml(t.name)}</span>
            <div class="tbl-btns">
                <button title="ערוך" onclick="editTable(${t.id})" onmousedown="event.stopPropagation()">✏️</button>
                <button title="מחק" onclick="deleteTable(${t.id})" onmousedown="event.stopPropagation()">🗑️</button>
            </div>
        </div>
        ${buildTableBody(t)}
    `;

    // Drag-to-reposition
    div.addEventListener('mousedown', tableMouseDown);

    document.getElementById('canvas').appendChild(div);
    tableMap[t.id] = t;
}

function buildTableBody(t) {
    const cap = t.capacity;
    if (t.shape === 'round' || t.shape === 'sweetheart') return buildRound(t, cap);
    if (t.shape === 'head') return buildRect(t, cap, true);
    return buildRect(t, cap, false);
}

function buildRound(t, cap) {
    const R = cap <= 6 ? 58 : cap <= 8 ? 72 : cap <= 10 ? 86 : 98;
    const circleD = cap <= 6 ? 64 : cap <= 8 ? 76 : cap <= 10 ? 88 : 100;
    const wrapSize = (R + 22) * 2;
    const center = wrapSize / 2;

    let seatsHtml = '';
    for (let i = 0; i < cap; i++) {
        const angle = (360 / cap) * i - 90;
        const rad = (angle * Math.PI) / 180;
        const cx = center + R * Math.cos(rad) - 18;
        const cy = center + R * Math.sin(rad) - 18;
        const guestId = (assignMap[t.id] || {})[i];
        const g = guestId ? guestMap[guestId] : null;
        const occupied = !!g;
        const slotIdx = guestId ? seatSlotIdx(guestId, i) : 0;
        const groupCls = guestId ? seatGroupClasses(guestId, i) : '';
        seatsHtml += `
            <div class="seat ${occupied ? 'occupied' : 'empty'}${groupCls}"
                 style="left:${cx}px;top:${cy}px;"
                 data-table-id="${t.id}" data-seat="${i}"
                 data-guest-id="${guestId || ''}"
                 draggable="${occupied}"
                 ondragstart="seatDragStart(event)"
                 ondragend="guestDragEnd(event)"
                 ondragover="seatDragOver(event)"
                 ondragleave="seatDragLeave(event)"
                 ondrop="seatDrop(event)"
                 onclick="seatClick(event,${t.id},${i},${guestId || 0})"
                 title="${seatTitle(g, slotIdx)}"
                 onmousedown="event.stopPropagation()">
                ${seatContent(g, slotIdx)}
            </div>`;
    }

    const seated = Object.keys(assignMap[t.id] || {}).length;
    return `<div class="round-table-wrap" style="width:${wrapSize}px;height:${wrapSize}px;position:relative;">
        <div class="round-table-circle" style="width:${circleD}px;height:${circleD}px;position:absolute;left:${center - circleD/2}px;top:${center - circleD/2}px;">
            <span>${escHtml(t.name)}</span>
            <span class="cnt">${seated}/${cap}</span>
        </div>
        ${seatsHtml}
    </div>`;
}

function buildRect(t, cap, wide) {
    const perSide = Math.floor(cap / 2);
    const extra   = cap - perSide * 2;
    const seatW = 40, seatH = 36, gap = 4;
    const bodyW = wide ? Math.max(perSide * (seatW + gap) - gap, 140) : Math.max(perSide * (seatW + gap) - gap, 100);
    const bodyH = wide ? 28 : 36;

    function rowHtml(indices) {
        return indices.map(i => {
            const guestId = (assignMap[t.id] || {})[i];
            const g = guestId ? guestMap[guestId] : null;
            const slotIdx = guestId ? seatSlotIdx(guestId, i) : 0;
            const groupCls = guestId ? seatGroupClasses(guestId, i) : '';
            return `<div class="seat ${g ? 'occupied' : 'empty'}${groupCls}"
                        style="width:${seatW}px;height:${seatH}px;position:relative;border-radius:.4rem;"
                        data-table-id="${t.id}" data-seat="${i}"
                        data-guest-id="${guestId || ''}"
                        draggable="${!!g}"
                        ondragstart="seatDragStart(event)"
                        ondragend="guestDragEnd(event)"
                        ondragover="seatDragOver(event)"
                        ondragleave="seatDragLeave(event)"
                        ondrop="seatDrop(event)"
                        onclick="seatClick(event,${t.id},${i},${guestId || 0})"
                        title="${seatTitle(g, slotIdx)}"
                        onmousedown="event.stopPropagation()">
                        ${seatContent(g, slotIdx)}
                    </div>`;
        }).join('');
    }

    const topIdx    = Array.from({length: perSide + extra}, (_, k) => k);
    const bottomIdx = Array.from({length: perSide}, (_, k) => perSide + extra + k);
    const seated = Object.keys(assignMap[t.id] || {}).length;

    return `<div class="rect-table-wrap">
        <div class="rect-seats-row">${rowHtml(topIdx)}</div>
        <div class="rect-body" style="width:${bodyW}px;height:${bodyH}px;font-size:.6rem;color:#6b7280;">${escHtml(t.name)}&nbsp;${seated}/${cap}</div>
        <div class="rect-seats-row">${rowHtml(bottomIdx)}</div>
    </div>`;
}

function refreshTable(tableId) {
    const t = tableMap[tableId];
    if (!t) return;
    const div = document.getElementById('tbl-' + tableId);
    if (!div) return;
    // replace only body (keep label + position)
    div.dataset.color = t.color || 'rose';
    div.innerHTML = `
        <div class="table-label">
            <span class="tbl-name">${escHtml(t.name)}</span>
            <div class="tbl-btns">
                <button title="ערוך" onclick="editTable(${t.id})" onmousedown="event.stopPropagation()">✏️</button>
                <button title="מחק" onclick="deleteTable(${t.id})" onmousedown="event.stopPropagation()">🗑️</button>
            </div>
        </div>
        ${buildTableBody(t)}
    `;
    div.removeEventListener('mousedown', tableMouseDown);
    div.addEventListener('mousedown', tableMouseDown);
}

// ─── Table drag-to-reposition ─────────────────────────────────────────────────
function tableMouseDown(e) {
    if (e.target.closest('button') || e.target.closest('.seat')) return;
    dragTableId = parseInt(this.dataset.tableId);
    const rect = this.getBoundingClientRect();
    dragOffX = e.clientX - rect.left;
    dragOffY = e.clientY - rect.top;
    this.classList.add('dragging');
    e.preventDefault();
}

async function endTableDrag() {
    if (!dragTableId) return;
    const id = dragTableId;
    dragTableId = null;  // clear immediately so duplicate fires no-op
    const el = document.getElementById('tbl-' + id);
    if (el) {
        el.classList.remove('dragging');
        const nx = parseFloat(el.style.left), ny = parseFloat(el.style.top);
        if (!Number.isNaN(nx) && !Number.isNaN(ny) && tableMap[id]) {
            tableMap[id].x = nx;
            tableMap[id].y = ny;
            try {
                await api('POST', '/api/wedding/seating/tables/positions', {tables:[{id, x:nx, y:ny}]});
            } catch (err) { /* swallow — UI is already updated */ }
        }
    }
}

document.addEventListener('mousemove', e => {
    if (!dragTableId) return;
    // If primary button no longer held (e.g. mouseup happened outside window), end drag
    if (e.buttons === 0) { endTableDrag(); return; }
    const outer = document.getElementById('canvas-outer');
    const outerRect = outer.getBoundingClientRect();
    const x = e.clientX - outerRect.left + outer.scrollLeft - dragOffX;
    const y = e.clientY - outerRect.top  + outer.scrollTop  - dragOffY;
    const el = document.getElementById('tbl-' + dragTableId);
    if (el) { el.style.left = Math.max(0,x)+'px'; el.style.top = Math.max(0,y)+'px'; }
});
document.addEventListener('mouseup', endTableDrag);
// Belt-and-suspenders: clean up drag state when window loses focus or user leaves the document
window.addEventListener('blur', endTableDrag);
document.addEventListener('mouseleave', endTableDrag);

// ─── Canvas drag-over / drop (for new table placement) ───────────────────────
function canvasDragOver(e) { e.preventDefault(); }
function canvasDrop(e) {
    e.preventDefault();
    if (dragGuestId) {
        dropOnPanel(e);
        dragGuestId = null;
    }
}

// ─── Guest drag-and-drop ──────────────────────────────────────────────────────
function guestDragStart(e, guestId) {
    dragGuestId = guestId;
    e.dataTransfer.setData('text/plain', guestId);
    e.dataTransfer.effectAllowed = 'move';
}
function seatDragStart(e) {
    const guestId = parseInt(e.currentTarget.dataset.guestId);
    if (!guestId) { e.preventDefault(); return; }
    dragGuestId = guestId;
    e.dataTransfer.setData('text/plain', guestId);
    e.dataTransfer.effectAllowed = 'move';
}
function guestDragEnd(e) { dragGuestId = null; }

function seatDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.add('drag-over');
}
function seatDragLeave(e) { e.currentTarget.classList.remove('drag-over'); }

async function seatDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove('drag-over');
    const guestId = parseInt(e.dataTransfer.getData('text/plain'));
    const seatEl = e.currentTarget;
    const tableId = parseInt(seatEl.dataset.tableId);
    const seatNum = parseInt(seatEl.dataset.seat);
    if (!guestId) return;
    await doAssign(guestId, tableId, seatNum);
}

async function dropOnPanel(e) {
    if (!dragGuestId) return;
    const guestId = dragGuestId;
    dragGuestId = null;
    if (!guestAssign[guestId]) return;
    await doUnassign(guestId);
}

// ─── Seat click (assign modal) ────────────────────────────────────────────────
function seatClick(e, tableId, seatNum, guestId) {
    e.stopPropagation();
    openAssignModal(tableId, seatNum, guestId || 0);
}

function openAssignModal(tableId, seatNum, currentGuestId) {
    assignTarget = {table_id: tableId, seat_number: seatNum, current_guest_id: currentGuestId};
    const t = tableMap[tableId];
    const ga = currentGuestId ? guestAssign[currentGuestId] : null;
    const isGroup = ga && ga.seats.length > 1;
    document.getElementById('assign-info').textContent = `שולחן: ${t.name} — מושב ${seatNum + 1}`;
    const clearBtn = document.getElementById('clear-seat-btn');
    clearBtn.style.display = currentGuestId ? '' : 'none';
    clearBtn.textContent = isGroup ? 'הסר קבוצה' : 'הסר מהמושב';
    document.getElementById('guest-search-input').value = '';
    renderAssignList('');
    document.getElementById('assign-modal').style.display = 'flex';
    document.getElementById('guest-search-input').focus();
}
function closeAssignModal() { document.getElementById('assign-modal').style.display='none'; assignTarget=null; }

function renderAssignList(filter) {
    // Show ALL non-declined guests so users can move someone from another table.
    // Guests seated elsewhere are tagged so the user knows the assignment will move them.
    const candidates = GUESTS.filter(g => g.status !== 'declined');
    const list = filter ? candidates.filter(g => g.name.includes(filter)||(g.group_name||'').includes(filter)||(g.plus_one_name||'').includes(filter)) : candidates;
    const scroll = document.getElementById('guest-list-scroll');
    if (!list.length) { scroll.innerHTML = '<div style="text-align:center;color:#9ca3af;padding:1rem;font-size:.8rem">לא נמצאו מוזמנים</div>'; return; }

    // Calculate available seats at this table for each guest
    const tableId = assignTarget.table_id;
    const cap = tableMap[tableId].capacity;

    scroll.innerHTML = list.map(g => {
        const ga = guestAssign[g.id];
        const isCurrentlyHere = ga && ga.table_id === tableId && ga.seats.includes(assignTarget.seat_number);
        const seatedElsewhere = ga && ga.table_id !== tableId;
        const otherTableName = seatedElsewhere && tableMap[ga.table_id] ? tableMap[ga.table_id].name : '';
        const extras = [];
        if (g.plus_one) extras.push(`<span style="color:#be123c;font-weight:600">+${escHtml(g.plus_one_name||'1')}</span>`);
        if (g.children_count > 0) extras.push(`<span style="color:#1d4ed8">${g.children_count} ילד${g.children_count>1?'ים':''}</span>`);
        const n = personCount(g);
        const subLine = [...extras, g.group_name ? `<span>${escHtml(g.group_name)}</span>` : ''].filter(Boolean).join(' · ');

        // Count seats available for this guest (treat their own seats here as available)
        const occupiedByOthers = Object.values(assignMap[tableId] || {}).filter(gid => gid !== g.id).length;
        const available = cap - occupiedByOthers;
        const notEnough = n > available;

        const multiTag = n > 1
            ? `<span style="color:${notEnough?'#dc2626':'#6b7280'};font-size:.65rem;flex-shrink:0;margin-right:.25rem">${notEnough?'⚠️ ':''}👥${n}</span>`
            : '';
        const elsewhereTag = seatedElsewhere
            ? `<span style="color:#a16207;font-size:.65rem;flex-shrink:0;margin-right:.25rem" title="ישוב כעת ב${escHtml(otherTableName)} — בחירה תעביר אותו">↪ ${escHtml(otherTableName)}</span>`
            : '';
        return `<div class="guest-option ${isCurrentlyHere?'bg-rose-50':''}" onclick="pickGuest(${g.id})">
            <div style="flex:1;min-width:0">
                <div class="go-name">${escHtml(g.name)}</div>
                ${subLine ? `<div class="go-group" style="margin-top:.1rem">${subLine}</div>` : ''}
            </div>
            ${elsewhereTag}
            ${multiTag}
            ${isCurrentlyHere ? '<span style="color:#be123c;font-size:.7rem;flex-shrink:0">✓ כאן</span>' : ''}
        </div>`;
    }).join('');
}

function filterAssignGuests(val) { if(assignTarget) renderAssignList(val); }

async function pickGuest(guestId) {
    const { table_id, seat_number } = assignTarget;
    closeAssignModal();
    await doAssign(guestId, table_id, seat_number);
}
async function clearSeat() {
    if (!assignTarget || !assignTarget.current_guest_id) return;
    const guestId = assignTarget.current_guest_id;
    closeAssignModal();
    await doUnassign(guestId);
}

// ─── Core assign/unassign ─────────────────────────────────────────────────────
async function doAssign(guestId, tableId, seatNum) {
    const g = guestMap[guestId];
    const cap = tableMap[tableId].capacity;
    const needed = Math.min(g ? personCount(g) : 1, cap);

    // Build consecutive seats list starting from seatNum (wrapping around for round tables)
    const allSeats = [];
    for (let i = 0; i < needed; i++) {
        allSeats.push((seatNum + i) % cap);
    }

    // Remove previous assignment for this guest (all their seats, possibly another table)
    const prev = guestAssign[guestId];
    if (prev) {
        for (const s of prev.seats) {
            if (assignMap[prev.table_id]) delete assignMap[prev.table_id][s];
        }
        if (prev.table_id !== tableId) refreshTable(prev.table_id);
    }

    // Displace any other guests occupying target seats (including their full groups)
    const displaced = new Set();
    for (const s of allSeats) {
        const occ = (assignMap[tableId] || {})[s];
        if (occ && occ !== guestId) displaced.add(occ);
    }
    for (const dId of displaced) {
        const dp = guestAssign[dId];
        if (dp) {
            for (const s of dp.seats) {
                if (assignMap[dp.table_id]) delete assignMap[dp.table_id][s];
            }
            delete guestAssign[dId];
        }
    }

    // Apply new assignments locally
    assignMap[tableId] = assignMap[tableId] || {};
    for (const s of allSeats) assignMap[tableId][s] = guestId;
    guestAssign[guestId] = { table_id: tableId, seat_number: seatNum, seats: allSeats };

    refreshTable(tableId);
    renderPanel(document.getElementById('panel-search').value || null);
    updateStats();

    // Warn if we couldn't fit everyone (needed was capped at capacity)
    if (g && personCount(g) > cap) {
        const missing = personCount(g) - cap;
        showToast(`⚠️ ${missing} מקומות חסרים בשולחן — הוקצו ${cap} מתוך ${personCount(g)}`);
    }

    // Sync server: unassign each displaced guest BEFORE the new assignment so that
    // their seats — possibly elsewhere on the same table — don't linger server-side.
    for (const dId of displaced) {
        try { await api('DELETE', `/api/wedding/seating/assign/${dId}`); } catch (e) { /* continue */ }
    }

    await api('POST', '/api/wedding/seating/assign', {
        table_id: tableId, seat_number: seatNum, guest_id: guestId,
        extra_seats: allSeats.slice(1)
    });
}

async function doUnassign(guestId) {
    const prev = guestAssign[guestId];
    if (!prev) return;
    for (const s of prev.seats) {
        if (assignMap[prev.table_id]) delete assignMap[prev.table_id][s];
    }
    delete guestAssign[guestId];
    refreshTable(prev.table_id);
    renderPanel(document.getElementById('panel-search').value || null);
    updateStats();
    await api('DELETE', `/api/wedding/seating/assign/${guestId}`);
}

function showToast(msg) {
    let t = document.getElementById('seating-toast');
    if (!t) {
        t = document.createElement('div');
        t.id = 'seating-toast';
        t.style.cssText = 'position:fixed;bottom:1.5rem;left:50%;transform:translateX(-50%);background:#1f2937;color:#fff;padding:.6rem 1.2rem;border-radius:.75rem;font-size:.8rem;z-index:9999;opacity:0;transition:opacity .25s;pointer-events:none;max-width:320px;text-align:center';
        document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.opacity = '1';
    clearTimeout(t._timer);
    t._timer = setTimeout(() => { t.style.opacity = '0'; }, 3500);
}

// ─── Table Add/Edit Modal ─────────────────────────────────────────────────────
function openAddTableModal() {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    document.getElementById('table-modal-title').textContent = 'הוסף שולחן';
    document.getElementById('edit-table-id').value = '';
    document.getElementById('tbl-name').value = 'שולחן ' + (Object.keys(tableMap).length + 1);
    document.getElementById('tbl-shape').value = 'round';
    document.getElementById('tbl-capacity').value = '8';
    document.getElementById('tbl-notes').value = '';
    selectColor('rose', document.querySelector('.color-dot[data-color="rose"]'));
    document.getElementById('table-modal').style.display = 'flex';
    document.getElementById('tbl-name').focus();
    document.getElementById('tbl-name').select();
}

function editTable(tableId) {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    const t = tableMap[tableId];
    document.getElementById('table-modal-title').textContent = 'ערוך שולחן';
    document.getElementById('edit-table-id').value = tableId;
    document.getElementById('tbl-name').value = t.name;
    document.getElementById('tbl-shape').value = t.shape;
    document.getElementById('tbl-capacity').value = t.capacity;
    document.getElementById('tbl-notes').value = t.notes || '';
    selectColor(t.color || 'rose', document.querySelector(`.color-dot[data-color="${t.color||'rose'}"]`));
    document.getElementById('table-modal').style.display = 'flex';
}

function closeTableModal() { document.getElementById('table-modal').style.display='none'; }

function selectColor(color, el) {
    selectedColor = color;
    document.querySelectorAll('.color-dot').forEach(d => d.classList.remove('selected'));
    if (el) el.classList.add('selected');
}

function updateCapacityOptions() {
    const shape = document.getElementById('tbl-shape').value;
    const sel = document.getElementById('tbl-capacity');
    if (shape === 'sweetheart') {
        sel.innerHTML = '<option value="2">2</option>';
    } else if (shape === 'head') {
        sel.innerHTML = [10,12,14,16,18,20].map(v=>`<option value="${v}">${v}</option>`).join('');
        sel.value = '14';
    } else {
        sel.innerHTML = [4,6,8,10,12].map(v=>`<option value="${v}" ${v===8?'selected':''}>${v}</option>`).join('');
        sel.value = '8';
    }
}

async function saveTable() {
    const name     = document.getElementById('tbl-name').value.trim();
    const shape    = document.getElementById('tbl-shape').value;
    const capacity = parseInt(document.getElementById('tbl-capacity').value);
    const notes    = document.getElementById('tbl-notes').value.trim();
    const editId   = document.getElementById('edit-table-id').value;
    if (!name) { alert('נא להזין שם לשולחן'); return; }

    closeTableModal();

    if (editId) {
        const updated = await api('PUT', `/api/wedding/seating/tables/${editId}`,
            {name, shape, capacity, color: selectedColor, notes: notes || null});
        Object.assign(tableMap[parseInt(editId)], updated);
        refreshTable(parseInt(editId));
    } else {
        // pick a free spot on canvas — wrap the multipliers, not the sum (precedence bug)
        const outer = document.getElementById('canvas-outer');
        const count = Object.keys(tableMap).length;
        const x = outer.scrollLeft + 80 + ((count * 30) % 600);
        const y = outer.scrollTop  + 80 + ((count * 20) % 400);
        const created = await api('POST', '/api/wedding/seating/tables',
            {name, shape, capacity, color: selectedColor, notes: notes || null, x, y});
        tableMap[created.id] = created;
        assignMap[created.id] = {};
        renderTable(created);
    }
    updateStats();
}

async function deleteTable(tableId) {
    if (!confirm(`מחק את השולחן "${tableMap[tableId]?.name}"?\n כל ההושבות של שולחן זה יימחקו.`)) return;
    // remove assignments from local state
    for (const [guestId, info] of Object.entries(guestAssign)) {
        if (info.table_id === tableId) delete guestAssign[guestId];
    }
    delete assignMap[tableId];
    delete tableMap[tableId];
    document.getElementById('tbl-' + tableId)?.remove();
    renderPanel(document.getElementById('panel-search').value || null);
    updateStats();
    await api('DELETE', `/api/wedding/seating/tables/${tableId}`);
}

// ─── Utils ────────────────────────────────────────────────────────────────────
function abbrev(name) {
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 4);
    return parts[0].slice(0,3) + ' ' + parts[parts.length-1][0] + '.';
}

// slotIdx: 0 = primary guest, 1 = plus-one, 2+ = children
function seatContent(g, slotIdx) {
    if (!g) return '+';
    if (slotIdx <= 0) return abbrev(g.name);
    if (slotIdx === 1 && g.plus_one) {
        const n = g.plus_one_name ? abbrev(g.plus_one_name) : '+1';
        return `<span class="sub-name">${escHtml(n)}</span>`;
    }
    const childNum = g.plus_one ? slotIdx - 1 : slotIdx;
    return `<span class="sub-icon">👶${childNum > 1 ? childNum : ''}</span>`;
}

function seatGroupClasses(guestId, seatNum) {
    const ga = guestAssign[guestId];
    if (!ga || ga.seats.length <= 1) return '';
    const slotIdx = ga.seats.indexOf(seatNum);
    return ' group-member' + (slotIdx > 0 ? ' group-extra' : '');
}

function seatSlotIdx(guestId, seatNum) {
    const ga = guestAssign[guestId];
    if (!ga) return 0;
    const idx = ga.seats.indexOf(seatNum);
    return idx >= 0 ? idx : 0;
}

function seatTitle(g, slotIdx) {
    if (!g) return 'מושב ריק';
    if (slotIdx <= 0) return escHtml(g.name) + (g.plus_one ? ' +' + escHtml(g.plus_one_name||'1') : '');
    if (slotIdx === 1 && g.plus_one) return escHtml(g.plus_one_name || '+1') + ` (${escHtml(g.name)})`;
    const childNum = g.plus_one ? slotIdx - 1 : slotIdx;
    return `ילד ${childNum} (${escHtml(g.name)})`;
}
function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function api(method, url, body) {
    const opts = { method, headers: {'Content-Type':'application/json'} };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(url, opts);
    if (r.status === 204) return null;
    return r.json();
}
