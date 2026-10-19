// ===== Status data for inline updates =====
function normalizeWhatsAppPhone(raw) {
    if (!raw) return '';
    // Strip everything except digits and a leading '+'
    var digits = String(raw).replace(/[^\d+]/g, '');
    if (digits.startsWith('+')) {
        digits = digits.slice(1);                 // already international
    } else if (digits.startsWith('00')) {
        digits = digits.slice(2);                 // 00-prefixed international
    } else if (digits.startsWith('972')) {
        // already Israeli country code, leave as is
    } else if (digits.startsWith('0')) {
        digits = '972' + digits.slice(1);         // Israeli local → +972 form
    } else {
        digits = '972' + digits;                  // fallback: assume Israeli
    }
    return digits;
}

function openWhatsAppRSVP(el) {
    var phone = normalizeWhatsAppPhone(el.dataset.phone);
    if (!phone) { alert('אין מספר טלפון תקין'); return; }
    var name = el.dataset.name || '';
    var msg = 'היי ' + name + '!\n' +
              'שלחנו לך הזמנה לחתונה שלנו 🎉\n' +
              'נשמח לדעת - האם תוכל/י להגיע?\n\n' +
              '✅ מגיע/ה\n' +
              '❌ לא מגיע/ה\n' +
              '🤔 עוד לא יודע/ת';
    window.open('https://wa.me/' + phone + '?text=' + encodeURIComponent(msg), '_blank');
}

var STATUS_MAP = {
    confirmed: {label:'מאושר', badge:'bg-green-100 text-green-700', dot:'bg-green-500'},
    maybe:     {label:'אולי',  badge:'bg-yellow-100 text-yellow-700', dot:'bg-yellow-500'},
    pending:   {label:'ממתין', badge:'bg-gray-100 text-gray-500', dot:'bg-gray-400'},
    declined:  {label:'לא מגיע', badge:'bg-red-100 text-red-600', dot:'bg-red-500'}
};

// ===== Toggle Guest List =====
function toggleGuestList() {
    var wrap = document.getElementById('guest-list-wrap');
    var chevron = document.getElementById('guest-list-chevron');
    var label = document.getElementById('toggle-label');
    var isCollapsed = wrap.classList.contains('collapsed');

    if (isCollapsed) {
        // Expand
        wrap.classList.remove('collapsed');
        wrap.style.maxHeight = wrap.scrollHeight + 'px';
        chevron.style.transform = '';
        label.textContent = 'הסתר';
        setTimeout(function() { wrap.style.maxHeight = ''; }, 350);
    } else {
        // Collapse
        wrap.style.maxHeight = wrap.scrollHeight + 'px';
        requestAnimationFrame(function() {
            wrap.classList.add('collapsed');
            chevron.style.transform = 'rotate(180deg)';
            label.textContent = 'הצג';
        });
    }
}

// ===== Status Picker =====
var _statusGuestId = null;

function openStatusPicker(guestId, currentStatus) {
    _statusGuestId = guestId;
    var overlay = document.getElementById('status-picker-overlay');
    var backdrop = overlay.querySelector('.modal-backdrop');
    var picker = overlay.querySelector('.status-picker');

    // Reset classes before showing
    backdrop.classList.remove('open');
    picker.classList.remove('open');

    overlay.classList.remove('hidden');
    void overlay.offsetHeight; // Force reflow so Safari renders initial state

    overlay.querySelectorAll('.status-opt').forEach(function(btn) {
        var isCurrent = btn.dataset.status === currentStatus;
        btn.classList.toggle('ring-2', isCurrent);
        btn.classList.toggle('ring-offset-1', isCurrent);
    });

    backdrop.classList.add('open');
    picker.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeStatusPicker() {
    var overlay = document.getElementById('status-picker-overlay');
    overlay.querySelector('.modal-backdrop').classList.remove('open');
    overlay.querySelector('.status-picker').classList.remove('open');
    setTimeout(function() {
        overlay.classList.add('hidden');
        document.body.style.overflow = '';
    }, 300);
    _statusGuestId = null;
}

function setGuestStatus(status) {
    if (!_statusGuestId) return;
    var id = _statusGuestId;
    var s = STATUS_MAP[status];
    if (!s) return;

    // All possible color classes across statuses, so we can swap cleanly without
    // clobbering each badge's own layout classes (mobile card vs desktop row differ).
    var allBadgeColors = [];
    var allDotColors = [];
    Object.keys(STATUS_MAP).forEach(function(k) {
        STATUS_MAP[k].badge.split(' ').forEach(function(c) {
            if (c && allBadgeColors.indexOf(c) < 0) allBadgeColors.push(c);
        });
        if (allDotColors.indexOf(STATUS_MAP[k].dot) < 0) allDotColors.push(STATUS_MAP[k].dot);
    });

    // Instant UI update - update *all* matching containers (mobile card AND desktop row)
    // Scope the query so we don't pick inline-editable spans that also carry data-guest-id.
    var containers = document.querySelectorAll('.guest-card[data-guest-id="' + id + '"], .guest-row[data-guest-id="' + id + '"]');
    containers.forEach(function(card) {
        var badge = card.querySelector('.status-badge');
        if (!badge) return;
        // Swap badge color classes
        allBadgeColors.forEach(function(c) { badge.classList.remove(c); });
        s.badge.split(' ').forEach(function(c) { if (c) badge.classList.add(c); });
        // Swap dot color
        var dot = badge.querySelector('.status-dot');
        if (dot) {
            allDotColors.forEach(function(c) { dot.classList.remove(c); });
            dot.classList.add(s.dot);
        }
        // Update label text (preserve surrounding chevron / layout)
        var label = badge.querySelector('.status-label');
        if (label) label.textContent = s.label;
        // Re-trigger flash animation
        badge.classList.remove('status-flash');
        void badge.offsetWidth;
        badge.classList.add('status-flash');
        // Update onclick so the picker reopens with the new current status preselected
        badge.setAttribute('onclick', "openStatusPicker(" + id + ", '" + status + "')");
        // Keep desktop table sort value in sync
        var td = badge.closest('td[data-sort-val]');
        if (td) td.setAttribute('data-sort-val', status);
    });

    closeStatusPicker();

    // API call in background
    fetch('/api/wedding/guests/' + id, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status: status})
    }).then(function(r) {
        if (!r.ok) throw new Error('http ' + r.status);
    }).catch(function() {
        alert('שגיאה בעדכון סטטוס');
        location.reload();
    });
}

// ===== Search / Filter =====
function filterGuests(query) {
    query = query.trim().toLowerCase();
    document.querySelectorAll('#guest-list-mobile .guest-card').forEach(function(card) {
        var name = (card.dataset.name || '').toLowerCase();
        card.style.display = (!query || name.indexOf(query) !== -1) ? '' : 'none';
    });
    document.querySelectorAll('.guest-row').forEach(function(row) {
        var name = (row.dataset.name || '').toLowerCase();
        var plusOne = (row.dataset.plusOne || '').toLowerCase();
        var match = !query || name.indexOf(query) !== -1 || plusOne.indexOf(query) !== -1;
        row.style.display = match ? '' : 'none';
    });
}

// ===== Scroll Preservation =====
function reloadWithScroll() {
    sessionStorage.setItem('guestScrollPos', window.scrollY);
    location.reload();
}

// ===== Guest-count engine (mobile) =====
// Sets the catering vendor's portions to the confirmed headcount.
function gcUpdatePortions(btn, vendorId, confirmed) {
    var err = document.getElementById('gc-catering-error');
    err.hidden = true;
    btn.disabled = true;
    fetch('/api/wedding/vendors/' + vendorId, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({portions_ordered: confirmed})
    }).then(function(r) {
        if (!r.ok) throw new Error();
        location.reload();
    }).catch(function() {
        btn.disabled = false;
        err.textContent = 'שגיאה בעדכון, נסו שוב';
        err.hidden = false;
    });
}

// ===== Guest Modal =====
function openGuestModal() {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;

    var modal = document.getElementById('add-guest-modal');
    var backdrop = modal.querySelector('.modal-backdrop');
    var sheet = modal.querySelector('.modal-sheet');

    backdrop.classList.remove('open');
    sheet.classList.remove('open');

    modal.classList.remove('hidden');
    void modal.offsetHeight;

    requestAnimationFrame(function() {
        backdrop.classList.add('open');
        sheet.classList.add('open');
    });
    document.body.style.overflow = 'hidden';

    var fab = document.getElementById('guest-fab');
    if (fab) fab.style.display = 'none';
}

function closeGuestModal() {
    var modal = document.getElementById('add-guest-modal');
    modal.querySelector('.modal-backdrop').classList.remove('open');
    modal.querySelector('.modal-sheet').classList.remove('open');
    setTimeout(function() {
        modal.classList.add('hidden');
        document.body.style.overflow = '';
        var fab = document.getElementById('guest-fab');
        if (fab) fab.style.display = '';
    }, 350);
    document.getElementById('guest-id').value = '';
    document.getElementById('guest-modal-title').textContent = 'הוספת מוזמן';
    ['g-name','g-phone','g-group','g-table','g-children','g-plus-one-name','g-food-notes','g-notes'].forEach(function(f) {
        document.getElementById(f).value = '';
    });
    document.getElementById('g-status').value = 'pending';
    document.getElementById('g-meal-type').value = 'regular';
    document.getElementById('g-plus-one-meal-type').value = 'regular';
    document.getElementById('g-plus-one').checked = false;
    document.getElementById('g-transport').checked = false;
    document.getElementById('g-overnight').checked = false;
    document.getElementById('plus-one-name-wrap').classList.add('hidden');
}

document.getElementById('g-plus-one').addEventListener('change', function() {
    document.getElementById('plus-one-name-wrap').classList.toggle('hidden', !this.checked);
});

function editGuestFromBtn(btn) {
    var g = JSON.parse(btn.dataset.guest);
    document.getElementById('guest-modal-title').textContent = 'עריכת מוזמן';
    document.getElementById('guest-id').value = g.id;
    document.getElementById('g-name').value = g.name || '';
    document.getElementById('g-phone').value = g.phone || '';
    document.getElementById('g-group').value = g.group_name || '';
    document.getElementById('g-status').value = g.status || 'pending';
    document.getElementById('g-table').value = g.table_number || '';
    document.getElementById('g-children').value = g.children_count || 0;
    document.getElementById('g-plus-one').checked = !!g.plus_one;
    document.getElementById('g-transport').checked = !!g.needs_transport;
    document.getElementById('g-overnight').checked = !!g.staying_overnight;
    document.getElementById('g-plus-one-name').value = g.plus_one_name || '';
    document.getElementById('plus-one-name-wrap').classList.toggle('hidden', !g.plus_one);
    document.getElementById('g-meal-type').value = g.meal_type || 'regular';
    document.getElementById('g-plus-one-meal-type').value = g.plus_one_meal_type || 'regular';
    document.getElementById('g-food-notes').value = g.food_notes || '';
    document.getElementById('g-notes').value = g.notes || '';
    openGuestModal();
}

function saveGuest() {
    var id = document.getElementById('guest-id').value;
    var payload = {
        name: document.getElementById('g-name').value.trim(),
        phone: document.getElementById('g-phone').value.trim() || null,
        group_name: document.getElementById('g-group').value.trim() || null,
        status: document.getElementById('g-status').value,
        table_number: parseInt(document.getElementById('g-table').value) || null,
        children_count: parseInt(document.getElementById('g-children').value) || 0,
        plus_one: document.getElementById('g-plus-one').checked ? 1 : 0,
        plus_one_name: document.getElementById('g-plus-one-name').value.trim() || null,
        needs_transport: document.getElementById('g-transport').checked ? 1 : 0,
        staying_overnight: document.getElementById('g-overnight').checked ? 1 : 0,
        meal_type: document.getElementById('g-meal-type').value || 'regular',
        food_notes: document.getElementById('g-food-notes').value.trim() || null,
        plus_one_meal_type: document.getElementById('g-plus-one-meal-type').value || 'regular',
        notes: document.getElementById('g-notes').value.trim() || null,
    };
    if (!payload.name) { alert('יש להזין שם'); return; }

    var url = id ? '/api/wedding/guests/' + id : '/api/wedding/guests';
    var method = id ? 'PUT' : 'POST';
    fetch(url, {method: method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)})
        .then(function(r) { if (!r.ok) throw new Error(); return r.json(); })
        .then(function() { closeGuestModal(); reloadWithScroll(); })
        .catch(function() { alert('שגיאה בשמירה'); });
}

function deleteGuest(id) {
    if (!confirm('למחוק את המוזמן? פעולה זו תסיר גם את ההושבה והלינה.')) return;
    fetch('/api/wedding/guests/' + id, {method: 'DELETE'})
        .then(function(r) {
            if (!r.ok) throw new Error('http ' + r.status);
            reloadWithScroll();
        })
        .catch(function() { alert('שגיאה במחיקת המוזמן'); });
}

function toggleOvernight(id, current) {
    var newVal = current ? 0 : 1;
    fetch('/api/wedding/guests/' + id, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({staying_overnight: newVal})
    }).then(function(r) {
        if (!r.ok) throw new Error();
        reloadWithScroll();
    }).catch(function() { alert('שגיאה בעדכון'); });
}

// ===== Restore scroll position after reload =====
(function() {
    var savedPos = sessionStorage.getItem('guestScrollPos');
    if (savedPos) {
        sessionStorage.removeItem('guestScrollPos');
        window.scrollTo(0, parseInt(savedPos));
    }
})();

// ===== Inline Field Editing (double-click / double-tap) =====
var INLINE_INPUT_TYPES = {
    name: 'text', phone: 'tel', group_name: 'text',
    table_number: 'number', notes: 'textarea'
};
var INLINE_LTR_FIELDS = { phone: true, table_number: true };

function startInlineEdit(el) {
    if (el.querySelector('input, textarea')) return;

    var field = el.dataset.field;
    var guestId = el.dataset.guestId;
    var currentValue = el.dataset.value || '';
    var inputType = INLINE_INPUT_TYPES[field] || 'text';
    var originalHTML = el.innerHTML;

    var input;
    if (inputType === 'textarea') {
        input = document.createElement('textarea');
        input.rows = 2;
        input.className = 'inline-edit-input';
    } else {
        input = document.createElement('input');
        input.type = inputType;
        input.className = 'inline-edit-input';
    }
    input.value = currentValue;
    if (INLINE_LTR_FIELDS[field]) input.dir = 'ltr';
    if (inputType === 'number') { input.min = '0'; input.inputMode = 'numeric'; }

    el.innerHTML = '';
    el.appendChild(input);
    input.focus();
    input.select();

    var committed = false;

    function commit() {
        if (committed) return;
        committed = true;

        var rawVal = input.value.trim();

        if (rawVal === currentValue) {
            el.innerHTML = originalHTML;
            return;
        }

        var payload = {};
        if (field === 'table_number') {
            payload[field] = parseInt(rawVal) || null;
        } else if (field === 'children_count') {
            payload[field] = parseInt(rawVal) || 0;
        } else {
            payload[field] = rawVal || null;
        }

        el.innerHTML = originalHTML;

        fetch('/api/wedding/guests/' + guestId, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        }).then(function(r) {
            if (!r.ok) throw new Error();
            el.dataset.value = rawVal;
            el.classList.add('inline-save-flash');
            setTimeout(function() { el.classList.remove('inline-save-flash'); }, 800);
            reloadWithScroll();
        }).catch(function() {
            alert('שגיאה בשמירה');
        });
    }

    function abort() {
        if (committed) return;
        committed = true;
        el.innerHTML = originalHTML;
    }

    input.addEventListener('blur', commit);
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && inputType !== 'textarea') {
            e.preventDefault();
            input.removeEventListener('blur', commit);
            commit();
        }
        if (e.key === 'Escape') {
            input.removeEventListener('blur', commit);
            abort();
        }
    });
}

// ===== Table Sort =====
var _sortCol = null;
var _sortDir = 1;
var _STATUS_SORT_ORDER = { confirmed: 0, maybe: 1, pending: 2, declined: 3 };

function sortTable(colIdx) {
    if (_sortCol === colIdx) {
        _sortDir = -_sortDir;
    } else {
        _sortCol = colIdx;
        _sortDir = 1;
    }
    document.querySelectorAll('#guest-desktop-table th[data-col]').forEach(function(th) {
        var arrow = th.querySelector('.sort-arrow');
        if (!arrow) return;
        var idx = parseInt(th.dataset.col);
        if (idx === colIdx) {
            arrow.textContent = _sortDir === 1 ? ' ↑' : ' ↓';
            arrow.classList.remove('text-gray-300');
            arrow.classList.add('text-rose-500');
        } else {
            arrow.textContent = ' ↕';
            arrow.classList.remove('text-rose-500');
            arrow.classList.add('text-gray-300');
        }
    });
    var tbody = document.querySelector('#guest-desktop-table tbody');
    var rows = Array.from(tbody.querySelectorAll('tr.guest-row'));
    rows.sort(function(a, b) {
        var aCells = a.querySelectorAll('td');
        var bCells = b.querySelectorAll('td');
        var aVal = aCells[colIdx] ? (aCells[colIdx].dataset.sortVal || '') : '';
        var bVal = bCells[colIdx] ? (bCells[colIdx].dataset.sortVal || '') : '';
        if (colIdx === 3) {
            var aO = _STATUS_SORT_ORDER[aVal] !== undefined ? _STATUS_SORT_ORDER[aVal] : 99;
            var bO = _STATUS_SORT_ORDER[bVal] !== undefined ? _STATUS_SORT_ORDER[bVal] : 99;
            return (aO - bO) * _sortDir;
        }
        if (colIdx === 5 || colIdx === 9) {
            return ((parseFloat(aVal) || 0) - (parseFloat(bVal) || 0)) * _sortDir;
        }
        if (colIdx === 4 || colIdx === 6 || colIdx === 7) {
            return ((bVal === '1' ? 1 : 0) - (aVal === '1' ? 1 : 0)) * _sortDir;
        }
        return aVal.localeCompare(bVal, 'he') * _sortDir;
    });
    rows.forEach(function(r) { tbody.appendChild(r); });
}

// ─── Invite Link Modal ────────────────────────────────────────────────────────

let _inviteGuestId = null;
let _inviteGuestName = '';

function openInviteModal(guestId, guestName) {
    _inviteGuestId = guestId;
    _inviteGuestName = guestName;
    const modal = document.getElementById('invite-modal');
    const linkArea = document.getElementById('invite-link-area');
    const linkInput = document.getElementById('invite-link-input');
    document.getElementById('invite-guest-name').textContent = guestName;
    linkArea.classList.add('hidden');
    linkInput.value = '';
    modal.classList.remove('hidden');
    requestAnimationFrame(() => {
        modal.querySelector('.modal-backdrop').classList.add('open');
        modal.querySelector('.modal-sheet').classList.add('open');
    });
    // Auto-fetch existing link
    fetch(`/api/wedding/guests/${guestId}/invite-link`)
        .then(r => r.json())
        .then(data => {
            if (data.link) showInviteLink(data.link);
        });
}

function closeInviteModal() {
    const modal = document.getElementById('invite-modal');
    modal.querySelector('.modal-backdrop').classList.remove('open');
    modal.querySelector('.modal-sheet').classList.remove('open');
    setTimeout(() => modal.classList.add('hidden'), 350);
}

function generateInviteLink() {
    const btn = document.getElementById('generate-invite-btn');
    btn.disabled = true;
    btn.textContent = 'יוצר...';
    fetch(`/api/wedding/guests/${_inviteGuestId}/generate-invite`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            showInviteLink(data.link);
            btn.textContent = 'צור לינק חדש';
            btn.disabled = false;
        })
        .catch(() => {
            btn.textContent = 'שגיאה, נסה שוב';
            btn.disabled = false;
        });
}

function showInviteLink(link) {
    const linkArea = document.getElementById('invite-link-area');
    const linkInput = document.getElementById('invite-link-input');
    linkInput.value = link;
    linkArea.classList.remove('hidden');
    document.getElementById('invite-wa-btn').href =
        `https://wa.me/?text=${encodeURIComponent('היי! יוסף וקארינה מזמינים אותך לחתונתם 💍\n' + link)}`;
}

function copyInviteLink() {
    const input = document.getElementById('invite-link-input');
    navigator.clipboard.writeText(input.value).then(() => {
        const btn = document.getElementById('copy-invite-btn');
        btn.textContent = '✓ הועתק!';
        setTimeout(() => { btn.textContent = 'העתק'; }, 2000);
    });
}
