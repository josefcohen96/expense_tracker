const PAGE_DATA = JSON.parse(document.getElementById('vendor-detail-data').textContent);
const VENDOR_ID = PAGE_DATA.vendor_id;
const VAT_RATE = 0.17;

const STATUS_LABELS = {
    not_contacted:   'לא נוצר קשר',
    quote_received:  'הצעת מחיר התקבלה',
    contract_signed: 'חוזה נחתם',
    deal_closed:     'נסגרה עסקה',
    deposit_paid:    'מקדמה שולמה',
    fully_paid:      'שולם במלואו'
};
const STATUS_COLORS = {
    not_contacted:   'bg-gray-200 text-gray-700',
    quote_received:  'bg-blue-100 text-blue-700',
    contract_signed: 'bg-amber-100 text-amber-700',
    deal_closed:     'bg-rose-100 text-rose-700',
    deposit_paid:    'bg-orange-100 text-orange-700',
    fully_paid:      'bg-green-100 text-green-700'
};

// ─── Quote Items ─────────────────────────────────────────────────────────────

// Seed from server-rendered data
let quoteItems = PAGE_DATA.quote_items;

function fmt(n) {
    return '₪' + n.toLocaleString('he-IL', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

// Pick whichever copy (mobile-stacked or desktop-grid) is currently visible.
// offsetParent is reliable across breakpoints; falls back to first input if neither
// appears visible (e.g. during initial hydration).
function _visibleInput(nodes) {
    for (const el of nodes) { if (el.offsetParent !== null) return el; }
    return nodes[0] || null;
}

function recalcTotals() {
    const rows = document.querySelectorAll('#items-list .item-row');
    let preVat = 0, vatAmount = 0;
    rows.forEach(row => {
        const qty = parseFloat((_visibleInput(row.querySelectorAll('.item-qty'))   || {}).value) || 0;
        const price = parseFloat((_visibleInput(row.querySelectorAll('.item-price')) || {}).value) || 0;
        const vatEl = _visibleInput(row.querySelectorAll('.item-vat'));
        const applyVat = vatEl ? vatEl.checked : false;
        const lineTotal = qty * price;
        preVat += lineTotal;
        if (applyVat) vatAmount += lineTotal * VAT_RATE;
    });
    const total = preVat + vatAmount;

    const hasTotals = rows.length > 0;
    document.getElementById('quote-totals').classList.toggle('hidden', !hasTotals);
    document.getElementById('tot-pre-vat').textContent  = fmt(preVat);
    document.getElementById('tot-vat').textContent      = fmt(vatAmount);
    document.getElementById('tot-total').textContent    = fmt(total);

    // Sync manual price field
    const priceInput = document.getElementById('price_quoted_input');
    const manualNote = document.getElementById('manual-price-note');
    if (hasTotals) {
        priceInput.value    = Math.round(total * 100) / 100;
        priceInput.readOnly = true;
        priceInput.classList.add('bg-gray-100', 'text-gray-500');
        manualNote.classList.remove('hidden');
    } else {
        priceInput.readOnly = false;
        priceInput.classList.remove('bg-gray-100', 'text-gray-500');
        manualNote.classList.add('hidden');
    }
}

function makeItemRow(item) {
    const div = document.createElement('div');
    div.className = 'item-row';

    const desc  = item.description || '';
    const qty   = item.quantity    ?? 1;
    const price = item.unit_price  ?? 0;
    const vat   = item.apply_vat   ?? 1;

    // Desktop: grid row, Mobile: stacked card
    div.innerHTML = `
        <div class="hidden sm:grid gap-1 items-center" style="grid-template-columns: 1fr 60px 90px 70px 28px">
            <input type="text"  value="${desc}"  placeholder="תיאור"
                   class="item-desc border rounded-lg px-2 py-1.5 text-sm w-full focus:outline-none focus:ring-1 focus:ring-rose-300 bg-white">
            <input type="number" value="${qty}"  min="0" step="any"
                   class="item-qty border rounded-lg px-2 py-1.5 text-sm w-full text-center focus:outline-none focus:ring-1 focus:ring-rose-300 bg-white" dir="ltr">
            <input type="number" value="${price}" min="0" step="any" placeholder="0"
                   class="item-price border rounded-lg px-2 py-1.5 text-sm w-full text-center focus:outline-none focus:ring-1 focus:ring-rose-300 bg-white" dir="ltr">
            <label class="flex items-center justify-center gap-1 cursor-pointer text-xs text-gray-600">
                <input type="checkbox" ${vat ? 'checked' : ''} class="item-vat accent-rose-500 w-4 h-4">
                כן
            </label>
            <button type="button" onclick="removeRow(this)"
                    class="text-gray-300 hover:text-red-400 transition-colors text-lg leading-none font-light">×</button>
        </div>
        <div class="sm:hidden border border-gray-200 rounded-xl p-3 bg-white space-y-2">
            <div class="flex items-center justify-between">
                <input type="text" value="${desc}" placeholder="תיאור"
                       class="item-desc border-0 border-b border-gray-200 px-0 py-1 text-base w-full focus:outline-none focus:ring-0 focus:border-rose-400 bg-transparent">
                <button type="button" onclick="removeRow(this)"
                        class="text-gray-300 hover:text-red-400 text-xl leading-none font-light p-2 -m-2 min-h-[44px] min-w-[44px] flex items-center justify-center">×</button>
            </div>
            <div class="grid grid-cols-3 gap-2">
                <div>
                    <span class="text-xs text-gray-600">כמות</span>
                    <input type="number" value="${qty}" min="0" step="any"
                           class="item-qty border border-gray-200 rounded-lg px-2 py-2 text-base w-full text-center focus:outline-none focus:ring-1 focus:ring-rose-300 bg-white" dir="ltr">
                </div>
                <div>
                    <span class="text-xs text-gray-600">מחיר (₪)</span>
                    <input type="number" value="${price}" min="0" step="any" placeholder="0"
                           class="item-price border border-gray-200 rounded-lg px-2 py-2 text-base w-full text-center focus:outline-none focus:ring-1 focus:ring-rose-300 bg-white" dir="ltr">
                </div>
                <div class="flex items-end">
                    <label class="flex items-center gap-2 cursor-pointer text-sm text-gray-600 py-2">
                        <input type="checkbox" ${vat ? 'checked' : ''} class="item-vat accent-rose-500 w-5 h-5">
                        + מע"מ
                    </label>
                </div>
            </div>
        </div>
    `;
    div.querySelectorAll('input').forEach(el => el.addEventListener('input', recalcTotals));
    return div;
}

function renderItems() {
    const list = document.getElementById('items-list');
    list.innerHTML = '';
    quoteItems.forEach(item => list.appendChild(makeItemRow(item)));
    recalcTotals();
}

function addItemRow() {
    const list = document.getElementById('items-list');
    list.appendChild(makeItemRow({ description: '', quantity: 1, unit_price: 0, apply_vat: 1 }));
    recalcTotals();
    list.lastElementChild.querySelector('.item-desc').focus();
}

function removeRow(btn) {
    btn.closest('.item-row').remove();
    recalcTotals();
}

function collectItems() {
    // Read from whichever copy (mobile vs desktop) is currently visible — checking
    // visibility, not viewport width, so a mid-edit resize doesn't pick the wrong inputs.
    return Array.from(document.querySelectorAll('#items-list .item-row')).map(row => {
        const desc  = _visibleInput(row.querySelectorAll('.item-desc'));
        const qty   = _visibleInput(row.querySelectorAll('.item-qty'));
        const price = _visibleInput(row.querySelectorAll('.item-price'));
        const vat   = _visibleInput(row.querySelectorAll('.item-vat'));
        return {
            description: (desc && desc.value || '').trim(),
            quantity:    parseFloat(qty && qty.value) || 1,
            unit_price:  parseFloat(price && price.value) || 0,
            apply_vat:   (vat && vat.checked) ? 1 : 0,
        };
    }).filter(item => item.description);
}

function saveQuoteItems() {
    const allRows = document.querySelectorAll('#items-list .item-row').length;
    const items = collectItems();
    if (allRows > items.length) {
        const dropped = allRows - items.length;
        if (!confirm(`${dropped} שורה ללא תיאור תיווסקנה ולא תישמרנה. להמשיך?`)) return;
    }
    fetch(`/api/wedding/vendors/${VENDOR_ID}/quote-items`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(items)
    })
    .then(r => { if (!r.ok) throw new Error(); return r.json(); })
    .then(data => {
        quoteItems = data.items;
        const msg = document.getElementById('items-save-msg');
        msg.classList.remove('hidden');
        setTimeout(() => msg.classList.add('hidden'), 3000);
    })
    .catch(() => alert('שגיאה בשמירת המרכיבים'));
}

// ─── Vendor Form ─────────────────────────────────────────────────────────────

function saveVendor(e) {
    e.preventDefault();
    const form = document.getElementById('vendor-form');
    const data = new FormData(form);
    const payload = {
        name:              data.get('name')?.trim() || null,
        category:          data.get('category'),
        contact_name:      data.get('contact_name')?.trim() || null,
        phone:             data.get('phone')?.trim() || null,
        price_quoted:      parseFloat(document.getElementById('price_quoted_input').value) || null,
        status:            data.get('status'),
        deposit_amount:    parseFloat(data.get('deposit_amount')) || null,
        deposit_paid_date: data.get('deposit_paid_date') || null,
        what_included:     data.get('what_included')?.trim() || null,
        notes:             data.get('notes')?.trim() || null,
        location:          data.get('location')?.trim() || null,
        instagram_url:     data.get('instagram_url')?.trim() || null,
        facebook_url:      data.get('facebook_url')?.trim() || null,
        portions_ordered:  data.get('category') === 'catering' ? parsePortions(data.get('portions_ordered')) : null,
    };
    if (payload.portions_ordered === undefined) { alert('מספר מנות לא תקין'); return; }

    fetch(`/api/wedding/vendors/${VENDOR_ID}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(r => { if (!r.ok) throw new Error(); return r.json(); })
    .then(v => {
        document.getElementById('display-name').textContent = v.name;
        const statusEl = document.getElementById('display-status');
        statusEl.textContent = STATUS_LABELS[v.status] || v.status;
        statusEl.className = `px-3 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[v.status] || 'bg-gray-100 text-gray-600'}`;
        const msg = document.getElementById('save-msg');
        msg.classList.remove('hidden');
        setTimeout(() => msg.classList.add('hidden'), 3000);
    })
    .catch(() => alert('שגיאה בשמירה'));
}

// Portions ordered only applies to catering vendors.
function togglePortionsField() {
    const category = document.querySelector('#vendor-form [name="category"]').value;
    document.getElementById('portions-wrap').classList.toggle('hidden', category !== 'catering');
}

// '' → null; a non-negative integer → that number; anything else → undefined (invalid).
function parsePortions(raw) {
    const text = String(raw ?? '').trim();
    if (!text) return null;
    const n = Number(text);
    return Number.isInteger(n) && n >= 0 ? n : undefined;
}

function deleteVendor() {
    if (!confirm('למחוק את הספק?')) return;
    fetch(`/api/wedding/vendors/${VENDOR_ID}`, { method: 'DELETE' })
        .then(r => { if (!r.ok) throw new Error(); return r; })
        .then(() => { window.location.href = '/wedding/vendors'; })
        .catch(() => alert('שגיאה במחיקת הספק'));
}

// ─── File Attachments ────────────────────────────────────────────────────────

function uploadFile(input) {
    const file = input.files[0];
    if (!file) return;
    input.value = '';  // reset so same file can be re-selected

    const status = document.getElementById('upload-status');
    status.classList.remove('hidden');

    const formData = new FormData();
    formData.append('file', file);

    fetch(`/api/wedding/vendors/${VENDOR_ID}/files`, {
        method: 'POST',
        body: formData,
    })
    .then(r => {
        if (!r.ok) return r.json().then(d => { throw new Error(d.detail || 'שגיאה בהעלאה'); });
        return r.json();
    })
    .then(f => {
        status.classList.add('hidden');
        const empty = document.getElementById('files-empty');
        if (empty) empty.remove();
        document.getElementById('files-list').prepend(makeFileRow(f));
    })
    .catch(err => {
        status.classList.add('hidden');
        alert(err.message || 'שגיאה בהעלאת הקובץ');
    });
}

function makeFileRow(f) {
    const div = document.createElement('div');
    div.id = `file-row-${f.id}`;
    div.className = 'flex items-center gap-3 bg-white border border-gray-100 rounded-xl px-3 py-2.5';

    const isPdf = f.mime_type === 'application/pdf';
    const sizeMB = (f.file_size / 1024 / 1024).toFixed(1);

    div.innerHTML = `
        ${isPdf
            ? `<svg class="w-8 h-8 shrink-0 text-red-500" fill="currentColor" viewBox="0 0 24 24">
                 <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm-1 1.5L18.5 9H13V3.5z"/>
               </svg>`
            : `<svg class="w-8 h-8 shrink-0 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                 <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                       d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
               </svg>`
        }
        <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-gray-800 truncate">${escHtml(f.original_name)}</div>
            <div class="text-xs text-gray-500">${sizeMB} MB</div>
        </div>
        <a href="/api/wedding/files/${f.id}" target="_blank" rel="noopener"
           class="shrink-0 text-xs text-rose-600 hover:text-rose-800 font-medium px-2 py-1.5 rounded-lg hover:bg-rose-50 min-h-[36px] flex items-center">
            פתח
        </a>
        <button type="button" onclick="deleteFile(${f.id})"
                class="shrink-0 text-gray-300 hover:text-red-400 transition-colors p-1.5 rounded-lg hover:bg-red-50 min-h-[36px] min-w-[36px] flex items-center justify-center">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
            </svg>
        </button>
    `;
    return div;
}

function deleteFile(id) {
    if (!confirm('למחוק קובץ זה?')) return;
    fetch(`/api/wedding/files/${id}`, { method: 'DELETE' })
    .then(r => {
        if (!r.ok) throw new Error();
        const row = document.getElementById(`file-row-${id}`);
        if (row) row.remove();
        if (!document.querySelector('#files-list [id^="file-row-"]')) {
            const empty = document.createElement('div');
            empty.id = 'files-empty';
            empty.className = 'text-xs text-gray-400 text-center py-3';
            empty.textContent = 'אין קבצים מצורפים עדיין. העלה PDF של הצעת מחיר.';
            document.getElementById('files-list').appendChild(empty);
        }
    })
    .catch(() => alert('שגיאה במחיקת הקובץ'));
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ─── Init ─────────────────────────────────────────────────────────────────────

renderItems();
