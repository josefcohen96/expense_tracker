/* ─── Data ─────────────────────────────────────────────────────── */
const PAGE_DATA = JSON.parse(document.getElementById('vendors-data').textContent);
const ALL_VENDORS = PAGE_DATA.vendors;

ALL_VENDORS.forEach(v => {
    try { v._inc = JSON.parse(v.inclusions || '{}'); }
    catch { v._inc = {}; }
});

function vendorById(id) {
    return ALL_VENDORS.find(v => v.id === id) || null;
}

function escHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

const CATEGORY_LABELS_JS = {
    venue:'מקום', catering:'קייטרינג', chuppah:'ספק חופה', dj:"דיג'יי",
    sound:'ספק סאונד', tables_chairs:'שולחנות וכסאות', alcohol:'אלכוהול',
    photographer:'צלם', video:'וידאו', live_music:'מוזיקה חיה',
    flowers:'פרחים ועיצוב', transport:'הסעות', attire:'לבוש', other:'אחר',
};

/*
 * Per-category checklist items.
 * type 'restriction' inverts the semantics: true = יש מגבלה (warning),
 * false = אין מגבלה (good). Regular items: true = כלול, false = לא כלול.
 */
const CATEGORY_INCLUSIONS = {
    venue: [
        { key: 'noise_restriction', label: 'הגבלת רעש', type: 'restriction' },
        { key: 'infrastructure', label: 'תשתיות' },
        { key: 'tables_chairs',  label: 'שולחנות וכסאות' },
        { key: 'food',           label: 'אוכל' },
        { key: 'alcohol',        label: 'אלכוהול' },
        { key: 'dj',             label: "דיג'יי" },
        { key: 'sound',          label: 'סאונד' },
        { key: 'chuppah',        label: 'חופה' },
        { key: 'cake',           label: 'עוגה' },
        { key: 'parking',        label: 'חנייה' },
        { key: 'ac',             label: 'מיזוג' },
    ],
    catering: [
        { key: 'food',           label: 'אוכל' },
        { key: 'service',        label: 'שירות' },
        { key: 'dishes',         label: 'כלים' },
        { key: 'chef',           label: 'שף' },
        { key: 'cake',           label: 'עוגה' },
        { key: 'alcohol',        label: 'אלכוהול' },
        { key: 'setup',          label: 'הצבה' },
        { key: 'cleanup',        label: 'פינוי' },
    ],
    chuppah: [
        { key: 'structure',      label: 'מבנה החופה' },
        { key: 'flowers',        label: 'פרחים' },
        { key: 'installation',   label: 'התקנה' },
        { key: 'removal',        label: 'פירוק' },
        { key: 'lighting',       label: 'תאורה' },
        { key: 'fabric',         label: 'בד/וילון' },
    ],
    dj: [
        { key: 'sound_equipment',label: 'ציוד סאונד' },
        { key: 'lighting',       label: 'תאורה' },
        { key: 'mc',             label: 'MC' },
        { key: 'fog',            label: 'עשן' },
        { key: 'ceremony_music', label: 'מוזיקה לחופה' },
        { key: 'setup',          label: 'הצבה ופירוק' },
    ],
    sound: [
        { key: 'microphones',    label: 'מיקרופונים' },
        { key: 'speakers',       label: 'רמקולים' },
        { key: 'mixing',         label: 'ערבוב' },
        { key: 'setup',          label: 'התקנה' },
        { key: 'operator',       label: 'מפעיל' },
        { key: 'monitoring',     label: 'מוניטורים' },
    ],
    tables_chairs: [
        { key: 'round_tables',   label: 'שולחנות עגולים' },
        { key: 'chairs',         label: 'כיסאות' },
        { key: 'tablecloths',    label: 'מפות' },
        { key: 'napkins',        label: 'מפיות' },
        { key: 'delivery',       label: 'משלוח' },
        { key: 'setup',          label: 'הצבה' },
        { key: 'removal',        label: 'פינוי' },
    ],
    alcohol: [
        { key: 'wine',           label: 'יין' },
        { key: 'whiskey',        label: 'ויסקי' },
        { key: 'beer',           label: 'בירה' },
        { key: 'soft_drinks',    label: 'שתיות קלות' },
        { key: 'bartender',      label: 'ברמן' },
        { key: 'glasses',        label: 'כוסות' },
        { key: 'ice',            label: 'קרח' },
    ],
    photographer: [
        { key: 'raw_photos',     label: 'תמונות גלם' },
        { key: 'editing',        label: 'עריכה' },
        { key: 'album',          label: 'אלבום' },
        { key: 'prints',         label: 'הדפסות' },
        { key: 'second_shooter', label: 'צלם שני' },
        { key: 'ceremony',       label: 'חופה' },
        { key: 'delivery_weeks', label: 'מסירה תוך 6 שבועות' },
    ],
    video: [
        { key: 'full_video',     label: 'סרטון מלא' },
        { key: 'reel',           label: 'ריל' },
        { key: 'live_stream',    label: 'שידור חי' },
        { key: 'drone',          label: 'רחפן' },
        { key: 'ceremony',       label: 'חופה' },
        { key: 'second_camera',  label: 'מצלמה שנייה' },
    ],
    live_music: [
        { key: 'ceremony',       label: 'חופה' },
        { key: 'reception',      label: 'קבלת פנים' },
        { key: 'equipment',      label: 'ציוד' },
        { key: 'rehearsals',     label: 'חזרות' },
        { key: 'playlist',       label: 'רשימת שירים מותאמת' },
    ],
    flowers: [
        { key: 'bridal_bouquet', label: 'זר כלה' },
        { key: 'table_flowers',  label: 'פרחי שולחנות' },
        { key: 'chuppah_flowers',label: 'פרחי חופה' },
        { key: 'boutonniere',    label: 'תפרחת חתן' },
        { key: 'delivery',       label: 'משלוח' },
        { key: 'setup',          label: 'הצבה' },
    ],
    transport: [
        { key: 'pickup',         label: 'איסוף' },
        { key: 'dropoff',        label: 'הורדה' },
        { key: 'driver',         label: 'נהג' },
        { key: 'ac_bus',         label: 'אוטובוס ממוזג' },
        { key: 'return',         label: 'החזרה' },
    ],
    attire: [
        { key: 'dress',          label: 'שמלה' },
        { key: 'alterations',    label: 'תיקונים' },
        { key: 'accessories',    label: 'אקססוריז' },
        { key: 'veil',           label: 'רעלה' },
        { key: 'cleaning',       label: 'ניקוי אחרי' },
    ],
};

const STATUS_LABELS = {
    not_contacted:   'לא נוצר קשר',
    quote_received:  'הצעת מחיר התקבלה',
    contract_signed: 'חוזה נחתם',
    deal_closed:     'נסגרה עסקה',
    deposit_paid:    'מקדמה שולמה',
    fully_paid:      'שולם במלואו',
};

const STATUS_BADGE_CLASSES = {
    not_contacted:   'bg-gray-200 text-gray-700',
    quote_received:  'bg-blue-100 text-blue-700',
    contract_signed: 'bg-amber-100 text-amber-700',
    deal_closed:     'bg-rose-100 text-rose-700',
    deposit_paid:    'bg-orange-100 text-orange-700',
    fully_paid:      'bg-green-100 text-green-700',
};

/* ─── View toggle ──────────────────────────────────────────────── */
function setView(view) {
    const isCompare = view === 'compare';
    document.getElementById('view-cards').classList.toggle('hidden', isCompare);
    document.getElementById('view-compare').classList.toggle('hidden', !isCompare);
    document.getElementById('btn-cards').classList.toggle('active-view', !isCompare);
    document.getElementById('btn-compare').classList.toggle('active-view', isCompare);
    document.getElementById('btn-cards').classList.toggle('text-gray-500', isCompare);
    document.getElementById('btn-compare').classList.toggle('text-gray-500', !isCompare);
    if (isCompare) renderCompareView();
}

/* ─── Category filter ──────────────────────────────────────────── */
let activeFilter = 'all';

function filterCategory(cat) {
    activeFilter = cat;
    document.querySelectorAll('#filter-chips .filter-chip').forEach(chip => {
        chip.classList.toggle('filter-chip-active', chip.dataset.filter === cat);
    });
    document.querySelectorAll('#view-cards [data-cat-card]').forEach(el => {
        const cardCat = el.dataset.catCard;
        const show = cat === 'all' || (cardCat === cat && cardCat !== '__quickadd');
        el.classList.toggle('hidden', cardCat === '__quickadd' ? cat !== 'all' : !show);
    });
}

/* ─── Inclusion chips (cards view) ────────────────────────────── */
function chipFor(item, val) {
    if (item.type === 'restriction') {
        if (val === true)  return `<span class="inclusion-chip chip-warn">⚠️ יש ${item.label}</span>`;
        if (val === false) return `<span class="inclusion-chip chip-yes">✓ אין ${item.label}</span>`;
        return '';
    }
    if (val === true)  return `<span class="inclusion-chip chip-yes">✓ ${item.label}</span>`;
    if (val === false) return `<span class="inclusion-chip chip-no">✗ ${item.label}</span>`;
    return '';
}

function renderInclusionChips(vendor) {
    const items = CATEGORY_INCLUSIONS[vendor.category];
    if (!items || !items.length) return '';

    const inc = vendor._inc || {};
    const withValue = items.filter(it => inc[it.key] !== undefined);
    if (!withValue.length) {
        return `<button onclick="openTourMode(${vendor.id})" class="inclusion-chip chip-unknown hover:bg-gray-200 min-h-[28px]">🚶 עוד לא סומן מה כלול — פתחו מצב סיור</button>`;
    }

    const MAX_CHIPS = 8;
    const shown = withValue.slice(0, MAX_CHIPS);
    let html = shown.map(it => chipFor(it, inc[it.key])).filter(Boolean).join(' ');
    if (withValue.length > MAX_CHIPS) {
        html += ` <span class="inclusion-chip chip-unknown">+${withValue.length - MAX_CHIPS}</span>`;
    }
    return html;
}

function refreshVendorChips(vendor) {
    const el = document.querySelector(`.inclusion-chips[data-vendor-id="${vendor.id}"]`);
    if (el) el.innerHTML = renderInclusionChips(vendor);
}

function refreshAllChips() {
    document.querySelectorAll('.inclusion-chips').forEach(el => {
        const v = vendorById(parseInt(el.dataset.vendorId));
        if (v) el.innerHTML = renderInclusionChips(v);
    });
}

/* ─── Compare View ─────────────────────────────────────────────── */
const COMPARE_CATEGORIES = [
    ['venue',         'מקום',             '🏛️'],
    ['catering',      'קייטרינג',          '🍽️'],
    ['chuppah',       'ספק חופה',          '⛪'],
    ['dj',            "דיג'יי",            '🎧'],
    ['sound',         'ספק סאונד',         '🔊'],
    ['tables_chairs', 'שולחנות וכסאות',    '🪑'],
    ['alcohol',       'אלכוהול',           '🥂'],
    ['photographer',  'צלם',               '📷'],
    ['video',         'וידאו',             '🎬'],
    ['live_music',    'מוזיקה חיה',        '🎻'],
    ['flowers',       'פרחים ועיצוב',      '💐'],
    ['transport',     'הסעות',             '🚌'],
    ['attire',        'לבוש',              '👗'],
];

function compareCell(item, val) {
    if (item.type === 'restriction') {
        if (val === true)  return '<span class="text-amber-600 text-sm font-bold whitespace-nowrap">⚠️ יש</span>';
        if (val === false) return '<span class="text-green-600 text-sm font-bold whitespace-nowrap">✓ אין</span>';
        return '<span class="text-gray-400 text-base">—</span>';
    }
    if (val === true)  return '<span class="text-green-500 text-lg">✓</span>';
    if (val === false) return '<span class="text-red-400 text-lg">✗</span>';
    return '<span class="text-gray-400 text-base">—</span>';
}

function renderCompareView() {
    let html = '';
    COMPARE_CATEGORIES.forEach(([catKey, catLabel, catIcon]) => {
        const catVendors = ALL_VENDORS.filter(v => v.category === catKey);
        if (!catVendors.length) return;

        const incItems = CATEGORY_INCLUSIONS[catKey] || [];
        const hasAnyInclusions = catVendors.some(v => Object.keys(v._inc).length > 0);
        const prices = catVendors.map(v => v.price_quoted).filter(Boolean);
        const minPrice = prices.length ? Math.min(...prices) : null;

        html += `
        <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <!-- Section header -->
            <div class="bg-rose-50 px-5 py-3 border-b border-rose-100 flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <span class="text-xl">${catIcon}</span>
                    <h2 class="font-bold text-rose-900">${catLabel}</h2>
                    <span class="text-xs text-rose-400">(${catVendors.length} ספקים)</span>
                </div>
                <button onclick="openAddModal('${catKey}')" class="text-xs text-rose-500 hover:text-rose-700 font-medium min-h-[36px]">+ הוסף</button>
            </div>

            <!-- Comparison table -->
            <div class="overflow-x-auto">
                <table class="w-full text-sm" dir="rtl">
                    <thead>
                        <tr class="border-b border-gray-100">
                            <th class="text-right py-3 px-4 text-xs font-semibold text-gray-400 uppercase tracking-wide w-36 bg-gray-50/50">פרמטר</th>
                            ${catVendors.map(v => {
                                const isChosen = ['deal_closed','deposit_paid','fully_paid'].includes(v.status);
                                return `
                                <th class="py-3 px-4 text-center min-w-[140px] ${isChosen ? 'bg-rose-50/50' : ''}">
                                    <div class="flex flex-col items-center gap-1">
                                        <span class="font-bold text-gray-900 text-sm leading-tight">${escHtml(v.name)}</span>
                                        ${isChosen ? '<span class="text-xs bg-rose-600 text-white px-2 py-0.5 rounded-full font-medium">✓ נבחר</span>' : ''}
                                        ${v.price_quoted ? `<span class="font-bold text-sm ${minPrice && v.price_quoted === minPrice && catVendors.length > 1 ? 'text-green-600' : 'text-gray-700'}" dir="ltr">₪${v.price_quoted.toLocaleString()}</span>` : '<span class="text-gray-500 text-xs">ללא מחיר</span>'}
                                        <span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_BADGE_CLASSES[v.status] || 'bg-gray-200 text-gray-700'}">${STATUS_LABELS[v.status] || v.status}</span>
                                    </div>
                                </th>`;
                            }).join('')}
                        </tr>
                    </thead>
                    <tbody>`;

        if (incItems.length && hasAnyInclusions) {
            incItems.forEach((item, idx) => {
                const rowBg = idx % 2 === 0 ? '' : 'bg-gray-50/40';
                html += `
                <tr class="border-b border-gray-50 ${rowBg}">
                    <td class="py-2.5 px-4 text-xs font-medium text-gray-600 bg-gray-50/50">${item.label}</td>
                    ${catVendors.map(v => {
                        const isChosen = ['deal_closed','deposit_paid','fully_paid'].includes(v.status);
                        return `<td class="py-2.5 px-4 text-center ${isChosen ? 'bg-rose-50/30' : ''}">${compareCell(item, v._inc[item.key])}</td>`;
                    }).join('')}
                </tr>`;
            });
        } else if (incItems.length) {
            html += `
            <tr><td colspan="${catVendors.length + 1}" class="py-4 px-4 text-center text-xs text-gray-500 italic">
                לא הוזנו פרמטרים — פתחו מצב סיור כדי לסמן
            </td></tr>`;
        }

        // Notes row
        const anyNotes = catVendors.some(v => v.notes);
        if (anyNotes) {
            html += `
            <tr class="border-b border-gray-50 bg-blue-50/20">
                <td class="py-2.5 px-4 text-xs font-medium text-gray-500 bg-gray-50/50">הערות</td>
                ${catVendors.map(v => `<td class="py-2.5 px-4 text-xs text-gray-500 text-center">${escHtml(v.notes) || '—'}</td>`).join('')}
            </tr>`;
        }

        // Actions row
        html += `
                    <tr class="bg-gray-50/30">
                        <td class="py-3 px-4 bg-gray-50/50"></td>
                        ${catVendors.map(v => `
                        <td class="py-3 px-4 text-center">
                            <div class="flex gap-1.5 justify-center flex-wrap">
                                <button onclick="openTourMode(${v.id})"
                                        class="text-xs bg-rose-50 text-rose-600 hover:bg-rose-100 border border-rose-200 font-semibold px-2 py-1.5 rounded-lg min-h-[32px]">🚶 סיור</button>
                                <a href="/wedding/vendors/${v.id}" class="text-xs text-gray-600 hover:text-gray-800 font-medium px-2 py-1.5 rounded-lg hover:bg-gray-100 min-h-[32px] flex items-center">פרטים</a>
                                <button onclick="openEditModalById(${v.id})"
                                        class="text-xs text-gray-500 hover:text-gray-700 px-2 py-1.5 rounded-lg hover:bg-gray-100 min-h-[32px]">ערוך</button>
                                <button data-vendor-id="${v.id}" data-vendor-name="${escHtml(v.name)}"
                                        onclick="deleteVendor(parseInt(this.dataset.vendorId), this.dataset.vendorName)"
                                        class="text-xs text-red-400 hover:text-red-600 px-2 py-1.5 rounded-lg hover:bg-red-50 min-h-[32px]">מחק</button>
                            </div>
                        </td>`).join('')}
                    </tr>
                    </tbody>
                </table>
            </div>
        </div>`;
    });

    // Other vendors (not in predefined categories)
    const predefined = COMPARE_CATEGORIES.map(c => c[0]);
    const others = ALL_VENDORS.filter(v => !predefined.includes(v.category));
    if (others.length) {
        html += `<div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
            <div class="bg-gray-50 px-5 py-3 border-b border-gray-100">
                <h2 class="font-bold text-gray-700">ספקים נוספים</h2>
            </div>
            <div class="divide-y divide-gray-50">
            ${others.map(v => `
                <div class="px-5 py-3 flex items-center justify-between gap-2 flex-wrap">
                    <div>
                        <span class="font-semibold text-gray-800 text-sm">${escHtml(v.name)}</span>
                        <span class="text-xs text-gray-400 mr-2">${CATEGORY_LABELS_JS[v.category] || escHtml(v.category)}</span>
                    </div>
                    <div class="flex items-center gap-2 flex-wrap">
                        ${v.price_quoted ? `<span class="text-sm font-bold text-gray-700" dir="ltr">₪${v.price_quoted.toLocaleString()}</span>` : ''}
                        <span class="text-xs px-2 py-0.5 rounded-full ${STATUS_BADGE_CLASSES[v.status] || 'bg-gray-200 text-gray-700'}">${STATUS_LABELS[v.status] || ''}</span>
                        <a href="/wedding/vendors/${v.id}" class="text-xs text-rose-600 hover:text-rose-800 font-medium px-2 py-1 rounded-lg hover:bg-rose-50">פרטים</a>
                        <button onclick="openEditModalById(${v.id})"
                                class="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded-lg hover:bg-gray-100">ערוך</button>
                        <button data-vendor-id="${v.id}" data-vendor-name="${escHtml(v.name)}"
                                onclick="deleteVendor(parseInt(this.dataset.vendorId), this.dataset.vendorName)"
                                class="text-xs text-red-400 hover:text-red-600 px-2 py-1 rounded-lg hover:bg-red-50">מחק</button>
                    </div>
                </div>`).join('')}
            </div>
        </div>`;
    }

    if (!html) {
        html = '<div class="text-center py-12 text-gray-400">אין ספקים עדיין — לחצו + הוסף ספק</div>';
    }

    document.getElementById('compare-content').innerHTML = html;
}

/* ─── Body scroll lock (shared by modals) ─────────────────────── */
function lockScroll(lock) {
    document.body.style.overflow = lock ? 'hidden' : '';
}

/* ─── Add/Edit Modal — inclusions ─────────────────────────────── */
let modalInc = {};

function onCategoryChange() {
    const cat = document.getElementById('v-category').value;
    renderInclusionCheckboxes(cat, modalInc);
    togglePortionsField();
}

/* Portions ordered only applies to catering vendors. */
function togglePortionsField() {
    const isCatering = document.getElementById('v-category').value === 'catering';
    document.getElementById('v-portions-wrap').classList.toggle('hidden', !isCatering);
}

/* '' → null; a non-negative integer → that number; anything else → undefined (invalid). */
function parsePortions(raw) {
    const text = String(raw ?? '').trim();
    if (!text) return null;
    const n = Number(text);
    return Number.isInteger(n) && n >= 0 ? n : undefined;
}

function incBtnClasses(selected, kind) {
    // kind: 'good' (green), 'bad' (red), 'warn' (amber)
    if (!selected) return 'bg-white text-gray-400 border-gray-200';
    if (kind === 'good') return 'bg-green-500 text-white border-green-500';
    if (kind === 'warn') return 'bg-amber-500 text-white border-amber-500';
    return 'bg-red-400 text-white border-red-400';
}

function renderInclusionCheckboxes(category, currentValues) {
    const items = CATEGORY_INCLUSIONS[category] || [];
    const container = document.getElementById('inclusions-checkboxes');
    document.getElementById('inclusions-section').style.display = items.length ? '' : 'none';

    // Keep only keys relevant to this category
    modalInc = {};
    items.forEach(it => {
        if (currentValues[it.key] !== undefined) modalInc[it.key] = currentValues[it.key];
    });

    if (!items.length) { container.innerHTML = ''; return; }

    container.innerHTML = items.map(item => {
        const val = modalInc[item.key];
        const isRestriction = item.type === 'restriction';
        const yesText = isRestriction ? 'יש' : '✓';
        const noText  = isRestriction ? 'אין' : '✗';
        const yesKind = isRestriction ? 'warn' : 'good';
        const noKind  = isRestriction ? 'good' : 'bad';
        return `
        <div class="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2 border border-gray-100 gap-2">
            <span class="text-sm text-gray-700 font-medium">${isRestriction ? '⚠️ ' : ''}${item.label}</span>
            <div class="flex gap-1.5 shrink-0" role="group">
                <button type="button" onclick="modalIncToggle('${item.key}', true)" data-inc-btn="${item.key}:yes"
                        class="min-h-[40px] min-w-[44px] px-2.5 rounded-lg border text-xs font-bold transition-all ${incBtnClasses(val === true, yesKind)}">${yesText}</button>
                <button type="button" onclick="modalIncToggle('${item.key}', false)" data-inc-btn="${item.key}:no"
                        class="min-h-[40px] min-w-[44px] px-2.5 rounded-lg border text-xs font-bold transition-all ${incBtnClasses(val === false, noKind)}">${noText}</button>
            </div>
        </div>`;
    }).join('');
}

function modalIncToggle(key, value) {
    if (modalInc[key] === value) delete modalInc[key];
    else modalInc[key] = value;
    // Re-render with current category to refresh button states
    renderInclusionCheckboxes(document.getElementById('v-category').value, modalInc);
}

function collectInclusions() {
    return { ...modalInc };
}

/* ─── Add/Edit Modal ───────────────────────────────────────────── */
function openAddModal(category) {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    document.getElementById('modal-title').textContent = 'הוספת ספק';
    document.getElementById('vendor-id').value = '';
    document.getElementById('open-tour-from-modal').classList.add('hidden');
    ['v-name','v-contact-name','v-phone','v-price-quoted','v-deposit-amount','v-deposit-date','v-notes','v-location','v-instagram','v-portions'].forEach(id => {
        document.getElementById(id).value = '';
    });
    document.getElementById('v-category').value = category || 'venue';
    document.getElementById('v-status').value = 'not_contacted';
    renderInclusionCheckboxes(category || 'venue', {});
    togglePortionsField();
    document.getElementById('vendor-modal').classList.remove('hidden');
    lockScroll(true);
    document.getElementById('v-name').focus();
}

function openEditModalById(id) {
    const v = vendorById(id);
    if (v) openEditModal(v);
}

function openEditModal(v) {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    document.getElementById('modal-title').textContent = 'עריכת ספק';
    document.getElementById('vendor-id').value = v.id;
    document.getElementById('v-name').value = v.name || '';
    document.getElementById('v-category').value = v.category || 'other';
    document.getElementById('v-contact-name').value = v.contact_name || '';
    document.getElementById('v-phone').value = v.phone || '';
    document.getElementById('v-price-quoted').value = v.price_quoted || '';
    document.getElementById('v-status').value = v.status || 'not_contacted';
    document.getElementById('v-deposit-amount').value = v.deposit_amount || '';
    document.getElementById('v-deposit-date').value = v.deposit_paid_date || '';
    document.getElementById('v-notes').value = v.notes || '';
    document.getElementById('v-location').value = v.location || '';
    document.getElementById('v-instagram').value = v.instagram_url || '';
    document.getElementById('v-portions').value = v.portions_ordered ?? '';
    let inc = {};
    try { inc = JSON.parse(v.inclusions || '{}'); } catch {}
    renderInclusionCheckboxes(v.category || 'other', inc);
    togglePortionsField();
    const tourBtn = document.getElementById('open-tour-from-modal');
    tourBtn.classList.toggle('hidden', !(CATEGORY_INCLUSIONS[v.category] || []).length);
    document.getElementById('vendor-modal').classList.remove('hidden');
    lockScroll(true);
    document.getElementById('vendor-modal-body').scrollTop = 0;
}

function closeModal() {
    document.getElementById('vendor-modal').classList.add('hidden');
    lockScroll(false);
}

function tourFromModal() {
    const id = parseInt(document.getElementById('vendor-id').value);
    if (!id) return;
    closeModal();
    openTourMode(id);
}

function saveVendor() {
    const id = document.getElementById('vendor-id').value;
    const inclusions = collectInclusions();
    const payload = {
        name:              document.getElementById('v-name').value.trim(),
        category:          document.getElementById('v-category').value,
        contact_name:      document.getElementById('v-contact-name').value.trim() || null,
        phone:             document.getElementById('v-phone').value.trim() || null,
        price_quoted:      parseFloat(document.getElementById('v-price-quoted').value) || null,
        status:            document.getElementById('v-status').value,
        deposit_amount:    parseFloat(document.getElementById('v-deposit-amount').value) || null,
        deposit_paid_date: document.getElementById('v-deposit-date').value || null,
        notes:             document.getElementById('v-notes').value.trim() || null,
        location:          document.getElementById('v-location').value.trim() || null,
        instagram_url:     document.getElementById('v-instagram').value.trim() || null,
        inclusions:        JSON.stringify(inclusions),
        portions_ordered:  document.getElementById('v-category').value === 'catering'
                               ? parsePortions(document.getElementById('v-portions').value) : null,
    };
    if (!payload.name) { alert('יש להזין שם ספק'); return; }
    if (payload.portions_ordered === undefined) { alert('מספר מנות לא תקין'); return; }

    const url    = id ? `/api/wedding/vendors/${id}` : '/api/wedding/vendors';
    const method = id ? 'PUT' : 'POST';
    fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(() => location.reload())
        .catch(() => alert('שגיאה בשמירה'));
}

function deleteVendor(id, name) {
    if (!confirm(`למחוק את הספק "${name}"?`)) return;
    fetch(`/api/wedding/vendors/${id}`, { method: 'DELETE' })
        .then(r => { if (!r.ok) throw new Error(); location.reload(); })
        .catch(() => alert('שגיאה במחיקה'));
}

/* ─── Tour Mode ────────────────────────────────────────────────── */
let tourVendor = null;
let tourInc = {};
let tourSaveTimer = null;
let tourDirty = false;

function openTourMode(id) {
    const v = vendorById(id);
    if (!v) return;
    const items = CATEGORY_INCLUSIONS[v.category] || [];
    if (!items.length) { alert('לקטגוריה זו אין רשימת סימון'); return; }

    tourVendor = v;
    tourInc = { ...(v._inc || {}) };
    tourDirty = false;

    document.getElementById('tour-vendor-name').textContent = v.name;
    document.getElementById('tour-category').textContent = CATEGORY_LABELS_JS[v.category] || v.category;
    document.getElementById('tour-notes').value = v.notes || '';
    setTourStatus('');

    renderTourItems();
    document.getElementById('tour-modal').classList.remove('hidden');
    lockScroll(true);
    document.getElementById('tour-scroll').scrollTop = 0;
}

function renderTourItems() {
    if (!tourVendor) return;
    const items = CATEGORY_INCLUSIONS[tourVendor.category] || [];
    const container = document.getElementById('tour-items');
    const scroller = document.getElementById('tour-scroll');
    const prevScroll = scroller.scrollTop;

    container.innerHTML = items.map(item => {
        const val = tourInc[item.key];
        const isRestriction = item.type === 'restriction';
        const yesText = isRestriction ? '⚠️ יש' : '✓ כלול';
        const noText  = isRestriction ? '✓ אין' : '✗ לא כלול';
        const yesKind = isRestriction ? 'warn' : 'good';
        const noKind  = isRestriction ? 'good' : 'bad';
        const marked = val !== undefined;
        return `
        <div class="bg-white rounded-2xl border ${marked ? 'border-gray-200' : 'border-gray-100'} shadow-sm p-3 flex items-center justify-between gap-2">
            <span class="text-base font-medium text-gray-800 min-w-0">${isRestriction ? '⚠️ ' : ''}${item.label}</span>
            <div class="flex gap-2 shrink-0">
                <button type="button" onclick="tourSet('${item.key}', true)"
                        class="min-h-[48px] min-w-[76px] px-3 rounded-xl border text-sm font-bold transition-all active:scale-95 ${incBtnClasses(val === true, yesKind)}">${yesText}</button>
                <button type="button" onclick="tourSet('${item.key}', false)"
                        class="min-h-[48px] min-w-[76px] px-3 rounded-xl border text-sm font-bold transition-all active:scale-95 ${incBtnClasses(val === false, noKind)}">${noText}</button>
            </div>
        </div>`;
    }).join('');

    scroller.scrollTop = prevScroll;

    // Progress
    const marked = items.filter(it => tourInc[it.key] !== undefined).length;
    document.getElementById('tour-progress-text').textContent = `${marked}/${items.length} סומנו`;
    document.getElementById('tour-progress-bar').style.width = items.length ? `${Math.round(marked / items.length * 100)}%` : '0%';
}

function tourSet(key, value) {
    if (tourInc[key] === value) delete tourInc[key];
    else tourInc[key] = value;
    tourDirty = true;
    renderTourItems();
    scheduleTourSave();
}

function setTourStatus(state) {
    const el = document.getElementById('tour-save-status');
    if (state === 'saving') {
        el.textContent = 'שומר…';
        el.className = 'text-xs font-medium text-gray-400 transition-opacity opacity-100';
    } else if (state === 'saved') {
        el.textContent = 'נשמר ✓';
        el.className = 'text-xs font-medium text-green-600 transition-opacity opacity-100';
        setTimeout(() => { el.classList.replace('opacity-100', 'opacity-0'); }, 1800);
    } else if (state === 'error') {
        el.textContent = 'שגיאה בשמירה';
        el.className = 'text-xs font-medium text-red-500 transition-opacity opacity-100';
    } else {
        el.className = 'text-xs font-medium text-gray-400 transition-opacity opacity-0';
    }
}

function scheduleTourSave() {
    clearTimeout(tourSaveTimer);
    tourSaveTimer = setTimeout(saveTourNow, 700);
}

function saveTourNow() {
    clearTimeout(tourSaveTimer);
    if (!tourVendor || !tourDirty) return;
    tourDirty = false;

    const notes = document.getElementById('tour-notes').value.trim() || null;
    const payload = { inclusions: JSON.stringify(tourInc), notes: notes };

    setTourStatus('saving');
    fetch(`/api/wedding/vendors/${tourVendor.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    })
    .then(r => { if (!r.ok) throw new Error(); return r.json(); })
    .then(updated => {
        // Sync the in-memory vendor so cards/compare/edit stay fresh without reload
        tourVendor.inclusions = updated.inclusions;
        tourVendor.notes = updated.notes;
        tourVendor._inc = { ...tourInc };
        refreshVendorChips(tourVendor);
        if (!document.getElementById('view-compare').classList.contains('hidden')) renderCompareView();
        setTourStatus('saved');
    })
    .catch(() => { tourDirty = true; setTourStatus('error'); });
}

function closeTourMode() {
    saveTourNow();  // flush pending changes
    document.getElementById('tour-modal').classList.add('hidden');
    lockScroll(false);
    tourVendor = null;
}

document.getElementById('tour-notes').addEventListener('input', () => {
    tourDirty = true;
    scheduleTourSave();
});

/* ─── Global listeners ─────────────────────────────────────────── */
// Close vendor modal on backdrop click
document.getElementById('vendor-modal').addEventListener('click', function(e) {
    if (e.target === this) closeModal();
});

// Close modals on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key !== 'Escape') return;
    if (!document.getElementById('tour-modal').classList.contains('hidden')) closeTourMode();
    else if (!document.getElementById('vendor-modal').classList.contains('hidden')) closeModal();
});

/* ─── Init ─────────────────────────────────────────────────────── */
// Portal the overlays to <body>: .main-content creates a stacking context
// (z-index:10) that would trap them below the fixed navbar (z-index:200).
['vendor-modal', 'tour-modal'].forEach(id => document.body.appendChild(document.getElementById(id)));
refreshAllChips();
