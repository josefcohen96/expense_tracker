const HOUR_H   = 80;
const START_H  = 8;
const TOTAL_H  = 19; // 08:00–03:00 next day

const PAGE_DATA = JSON.parse(document.getElementById('timeline-data').textContent);
let allEvents = PAGE_DATA.events;
let editingId = null;
let selDay = 'thursday';
let selCat = 'general';
let activeDay = 'thursday';

const PRESET_CATS = { ceremony:'💒', food:'🍽️', vendors:'📸', leisure:'🌿', logistics:'🚛', personal:'💕', general:'📌' };
const CAT_EMOJI  = PRESET_CATS; // alias kept for rendering
const CAT_BORDER = { ceremony:'#fb7185', food:'#fb923c', vendors:'#c084fc', leisure:'#2dd4bf', logistics:'#fbbf24', personal:'#f472b6', general:'#9ca3af', custom:'#818cf8' };
const DAY_ACTIVE = {
    thursday: 'border-amber-400 bg-amber-50 text-amber-700',
    friday:   'border-rose-400 bg-rose-50 text-rose-700',
    saturday: 'border-violet-400 bg-violet-50 text-violet-700'
};
const DAY_IDLE = 'border-gray-200 text-gray-500';

/* ── Time helpers ─────────────────────────────── */
function timeToTop(t) {
    if (!t) return 0;
    let [h, m] = t.split(':').map(Number);
    if (h < START_H) h += 24;
    return ((h - START_H) * 60 + m) / 60 * HOUR_H;
}
function durPx(start, end) {
    if (!end) return HOUR_H;
    let [sh, sm] = start.split(':').map(Number);
    let [eh, em] = end.split(':').map(Number);
    let sm2 = sh * 60 + sm, em2 = eh * 60 + em;
    if (em2 <= sm2) em2 += 24 * 60;
    return Math.max((em2 - sm2) / 60 * HOUR_H, 28);
}
function fmtTime(t) { return t ? t.slice(0,5) : ''; }

/* ── Build hour grid ──────────────────────────── */
function buildGrid(day) {
    const el = document.getElementById('grid-' + day);
    if (!el) return;
    for (let i = 0; i <= TOTAL_H; i++) {
        const top = i * HOUR_H;
        const hour = (START_H + i) % 24;
        // label
        const lbl = document.createElement('div');
        lbl.className = 'hour-label';
        lbl.style.top = top + 'px';
        lbl.textContent = String(hour).padStart(2,'0') + ':00';
        el.appendChild(lbl);
        if (i < TOTAL_H) {
            // solid hour line
            const line = document.createElement('div');
            line.className = 'hour-line';
            line.style.top = top + 'px';
            el.appendChild(line);
            // dashed half-hour line
            const half = document.createElement('div');
            half.className = 'half-line';
            half.style.top = (top + HOUR_H / 2) + 'px';
            el.appendChild(half);
        }
    }
    el.addEventListener('click', e => onGridClick(e, day));
}

/* ── Render events ────────────────────────────── */
function renderAll() {
    ['thursday','friday','saturday'].forEach(day => {
        const grid = document.getElementById('grid-' + day);
        if (!grid) return;
        grid.querySelectorAll('.event-card,.day-empty').forEach(el => el.remove());

        const dayEvs = allEvents.filter(e => e.day === day)
                                .sort((a,b) => a.start_time.localeCompare(b.start_time));

        if (!dayEvs.length) {
            const empty = document.createElement('div');
            empty.className = 'day-empty';
            empty.innerHTML = '<div style="font-size:2.5rem;margin-bottom:8px">🗓️</div><div style="font-size:13px;font-weight:500">לחץ + או על הציר להוסיף</div>';
            grid.appendChild(empty);
            return;
        }

        dayEvs.forEach(ev => grid.appendChild(makeCard(ev)));
    });
}

function makeCard(ev) {
    const cat     = ev.category || 'general';
    const isPreset = cat in PRESET_CATS;
    const top     = timeToTop(ev.start_time);
    const h       = durPx(ev.start_time, ev.end_time);

    // For custom categories: extract leading emoji if present, else show ✏️
    let emoji, label;
    if (isPreset) {
        emoji = PRESET_CATS[cat];
        label = null;
    } else {
        const firstChar = [...cat][0];
        const isEmoji   = /\p{Emoji}/u.test(firstChar);
        emoji = isEmoji ? firstChar : '✏️';
        label = isEmoji ? cat.slice([...cat][0].length).trim() : cat;
    }

    const card = document.createElement('div');
    card.className = `event-card ${isPreset ? 'cat-' + cat : 'cat-custom'}`;
    if (!isPreset) {
        card.style.cssText = `top:${top}px; height:${h}px;`;
    } else {
        card.style.cssText = `top:${top}px; height:${h}px;`;
    }

    const showEnd  = ev.end_time && h > 44;
    const showDesc = ev.description && h > 62;
    const showLabel = !isPreset && label && h > 44;

    card.innerHTML = `
        <div style="display:flex;align-items:flex-start;gap:5px;">
            <span style="font-size:13px;line-height:1;flex-shrink:0;margin-top:1px">${emoji}</span>
            <div style="min-width:0;flex:1;">
                <div style="font-size:11px;font-weight:700;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(ev.title)}</div>
                <div style="font-size:10px;opacity:0.65;margin-top:2px;">${fmtTime(ev.start_time)}${showEnd ? ' – ' + fmtTime(ev.end_time) : ''}${showLabel ? ' · ' + esc(label) : ''}</div>
                ${showDesc ? `<div style="font-size:10px;opacity:0.55;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(ev.description)}</div>` : ''}
            </div>
        </div>`;

    card.addEventListener('click', e => { e.stopPropagation(); openEdit(ev); });
    return card;
}

function esc(s) {
    if (!s) return '';
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

/* ── Grid click → add at that time ───────────── */
function onGridClick(e, day) {
    if (e.target.closest('.event-card')) return;
    const rect = document.getElementById('grid-' + day).getBoundingClientRect();
    const y = e.clientY - rect.top;
    const hoursF = y / HOUR_H;
    const absHour = START_H + Math.floor(hoursF);
    const mins = Math.round((hoursF % 1) * 60 / 15) * 15;
    const hour = absHour % 24;
    const startStr = String(hour).padStart(2,'0') + ':' + String(mins).padStart(2,'0');
    const endHour  = (hour + 1) % 24;
    const endStr   = String(endHour).padStart(2,'0') + ':' + String(mins).padStart(2,'0');
    openAdd(day, startStr, endStr);
}

/* ── Mobile tabs ──────────────────────────────── */
function switchDay(day) {
    activeDay = day;
    document.querySelectorAll('.timeline-day-col').forEach(col => {
        const isTarget = col.dataset.day === day;
        if (window.innerWidth < 1024) {
            col.classList.toggle('hidden', !isTarget);
            col.classList.toggle('lg:block', isTarget);
        }
    });
    ['thursday','friday','saturday'].forEach(d => {
        const btn = document.getElementById('tab-' + d);
        if (!btn) return;
        btn.className = `flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all ${d === day ? 'tab-active' : 'text-gray-500'}`;
    });
}

/* ── Modal ────────────────────────────────────── */
function openAdd(day, startTime, endTime) {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    editingId = null;
    selDay = day || activeDay;
    selCat = 'general';
    document.getElementById('modal-title').textContent = 'אירוע חדש';
    document.getElementById('event-title').value = '';
    document.getElementById('event-start-time').value = startTime || '';
    document.getElementById('event-end-time').value   = endTime   || '';
    document.getElementById('event-description').value = '';
    document.getElementById('custom-cat-input').value = '';
    document.getElementById('custom-cat-wrap').classList.add('hidden');
    document.getElementById('delete-btn').classList.add('hidden');
    setDay(selDay);
    setCategory('general');
    document.getElementById('event-modal').classList.remove('hidden');
    setTimeout(() => document.getElementById('event-title').focus(), 120);
}

function openAddModal(day) { openAdd(day, '', ''); }

function openEdit(ev) {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    editingId = ev.id;
    selDay = ev.day;
    const cat = ev.category || 'general';
    selCat = cat;
    document.getElementById('modal-title').textContent = 'עריכת אירוע';
    document.getElementById('event-title').value        = ev.title || '';
    document.getElementById('event-start-time').value  = ev.start_time || '';
    document.getElementById('event-end-time').value    = ev.end_time   || '';
    document.getElementById('event-description').value = ev.description || '';
    document.getElementById('delete-btn').classList.remove('hidden');
    // If custom category, pre-fill the text input
    const isPreset = cat in PRESET_CATS;
    document.getElementById('custom-cat-input').value = isPreset ? '' : cat;
    setDay(selDay);
    setCategory(isPreset ? cat : 'custom');
    document.getElementById('event-modal').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('event-modal').classList.add('hidden');
    editingId = null;
}

function setDay(day) {
    selDay = day;
    ['thursday','friday','saturday'].forEach(d => {
        const btn = document.getElementById('day-btn-' + d);
        if (!btn) return;
        btn.className = `day-btn py-3 rounded-xl text-sm font-semibold border-2 transition-all ${d === day ? DAY_ACTIVE[d] : DAY_IDLE + ' hover:border-gray-300'}`;
    });
}

function setCategory(cat) {
    selCat = cat;
    document.querySelectorAll('.cat-btn').forEach(btn => {
        btn.classList.remove('active');
        btn.style.borderColor = 'transparent';
        btn.style.transform   = '';
        btn.style.boxShadow   = '';
    });
    const isPreset = cat in PRESET_CATS || cat === 'custom';
    const btnId    = isPreset ? cat : 'custom';
    const active   = document.getElementById('cat-' + btnId);
    if (active) {
        active.classList.add('active');
        active.style.borderColor = CAT_BORDER[btnId] || '#818cf8';
    }
    // Show/hide custom text input
    const wrap = document.getElementById('custom-cat-wrap');
    if (cat === 'custom' || !(cat in PRESET_CATS)) {
        wrap.classList.remove('hidden');
        document.getElementById('custom-cat-input').focus();
    } else {
        wrap.classList.add('hidden');
    }
}

async function saveEvent() {
    const title = document.getElementById('event-title').value.trim();
    const start = document.getElementById('event-start-time').value;
    if (!title) {
        const inp = document.getElementById('event-title');
        inp.classList.add('border-red-400','ring-2','ring-red-200');
        inp.focus();
        setTimeout(() => inp.classList.remove('border-red-400','ring-2','ring-red-200'), 2000);
        return;
    }
    if (!start) { document.getElementById('event-start-time').focus(); return; }

    // Resolve final category: if "custom" selected, use the free-text value
    let finalCat = selCat;
    if (selCat === 'custom') {
        const customText = document.getElementById('custom-cat-input').value.trim();
        if (!customText) {
            document.getElementById('custom-cat-input').focus();
            document.getElementById('custom-cat-input').classList.add('border-red-400','ring-2','ring-red-200');
            setTimeout(() => document.getElementById('custom-cat-input').classList.remove('border-red-400','ring-2','ring-red-200'), 2000);
            return;
        }
        finalCat = customText;
    }

    const payload = {
        day:         selDay,
        title,
        start_time:  start,
        end_time:    document.getElementById('event-end-time').value || null,
        description: document.getElementById('event-description').value.trim() || null,
        category:    finalCat,
    };

    try {
        const url    = editingId ? `/api/wedding/timeline-events/${editingId}` : '/api/wedding/timeline-events';
        const method = editingId ? 'PUT' : 'POST';
        const res    = await fetch(url, { method, headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
        if (!res.ok) throw new Error();
        const saved  = await res.json();
        allEvents    = editingId
            ? allEvents.map(e => e.id === editingId ? saved : e)
            : [...allEvents, saved];
        closeModal();
        renderAll();
    } catch {
        alert('שגיאה בשמירה – נסה שוב');
    }
}

async function deleteCurrentEvent() {
    if (!editingId || !confirm('למחוק את האירוע?')) return;
    try {
        await fetch(`/api/wedding/timeline-events/${editingId}`, { method:'DELETE' });
        allEvents = allEvents.filter(e => e.id !== editingId);
        closeModal();
        renderAll();
    } catch {
        alert('שגיאה במחיקה');
    }
}

/* ── Backdrop click & Escape ──────────────────── */
document.getElementById('event-modal').addEventListener('click', function(e) {
    if (e.target === this) closeModal();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

/* ── Init ─────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
    ['thursday','friday','saturday'].forEach(buildGrid);
    // Mobile: show only Thursday by default
    if (window.innerWidth < 1024) {
        switchDay('thursday');
    }
    renderAll();
});
