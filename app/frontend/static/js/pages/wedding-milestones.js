(function () {
    const PAGE_DATA = JSON.parse(document.getElementById('milestones-data').textContent);
    var WEDDING = PAGE_DATA.wedding_date;
    var SAVE_FAILED = 'השמירה נכשלה, נסו שוב.';
    var JSON_HEADERS = { 'Content-Type': 'application/json' };

    /* ── helpers ─────────────────────────────────────────── */
    function isoAddDays(iso, days) {
        var p = iso.split('-').map(Number);
        return new Date(Date.UTC(p[0], p[1] - 1, p[2] + days)).toISOString().slice(0, 10);
    }
    function dotted(iso) {
        var p = iso.split('-').map(Number);
        return p[2] + '.' + p[1] + '.' + p[0];
    }
    function isVisible(el) {
        return !!(el && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
    }
    function showError(box, message) {
        if (!box) return;
        box.textContent = message || '';
        box.hidden = !message;
    }
    function errorDetail(res) {
        return res.json().then(function (body) {
            return typeof (body && body.detail) === 'string' ? body.detail : SAVE_FAILED;
        }, function () { return SAVE_FAILED; });
    }
    function saveWeddingDate(value, errorBox, button) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) {
            showError(errorBox, 'יש לבחור תאריך');
            return;
        }
        if (button) button.disabled = true;
        fetch('/api/wedding/settings', {
            method: 'POST', headers: JSON_HEADERS, credentials: 'same-origin',
            body: JSON.stringify({ key: 'wedding_date', value: value })
        }).then(function (res) {
            if (res.ok) { location.reload(); return; }
            return errorDetail(res).then(function (msg) { throw new Error(msg); });
        }).catch(function (err) {
            showError(errorBox, (err && err.message) || SAVE_FAILED);
            if (button) button.disabled = false;
        });
    }

    /* ── no wedding date: inline CTA ─────────────────────── */
    var ctaForm = document.getElementById('ms-cta-form');
    if (ctaForm) {
        ctaForm.addEventListener('submit', function (e) {
            e.preventDefault();
            saveWeddingDate(document.getElementById('ms-cta-date').value,
                ctaForm.querySelector('[data-ms-error]'), ctaForm.querySelector('[type=submit]'));
        });
    }
    if (!WEDDING) {
        window.msOpenEdit = window.msOpenDate = function () {};
        return;
    }

    /* ── sheets ──────────────────────────────────────────── */
    var openScrim = null, returnFocus = null, closeTimer = null, savedOverflow = '';
    var FOCUSABLE = 'button, input, select, textarea, a[href], [tabindex]:not([tabindex="-1"])';

    function openSheet(scrim, opener, focusEl) {
        if (openScrim) closeSheet(false);
        clearTimeout(closeTimer);
        returnFocus = isVisible(opener) ? opener : document.activeElement;
        scrim.hidden = false;
        void scrim.offsetWidth; // start the transition from the closed state
        scrim.classList.add('is-open');
        openScrim = scrim;
        savedOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        (focusEl || scrim.querySelector('[role=dialog]')).focus({ preventScroll: true });
    }
    function closeSheet(restoreFocus) {
        if (!openScrim) return;
        var scrim = openScrim;
        openScrim = null;
        scrim.classList.remove('is-open');
        scrim.classList.add('is-closing');
        document.body.style.overflow = savedOverflow;
        closeTimer = setTimeout(function () {
            scrim.hidden = true;
            // base.html only watches class/style changes to bring the tab bar back.
            scrim.classList.remove('is-closing');
        }, 240);
        if (restoreFocus !== false && returnFocus && returnFocus.focus) {
            returnFocus.focus({ preventScroll: true });
        }
    }
    document.querySelectorAll('.ms-scrim').forEach(function (scrim) {
        // .main-content is its own stacking context; lift the sheets above the navbar.
        document.body.appendChild(scrim);
        scrim.addEventListener('click', function (e) {
            if (e.target === scrim || e.target.closest('[data-ms-close]')) closeSheet();
        });
    });
    document.addEventListener('keydown', function (e) {
        if (!openScrim) return;
        if (e.key === 'Escape') { e.preventDefault(); closeSheet(); return; }
        if (e.key !== 'Tab') return;
        var dialog = openScrim.querySelector('[role=dialog]');
        var items = Array.prototype.filter.call(openScrim.querySelectorAll(FOCUSABLE), function (el) {
            return !el.disabled && isVisible(el);
        });
        if (!items.length) return;
        var first = items[0], last = items[items.length - 1], active = document.activeElement;
        var outside = !dialog.contains(active) || active === dialog;
        if (e.shiftKey && (active === first || outside)) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && (active === last || (outside && active !== dialog))) { e.preventDefault(); first.focus(); }
    });

    /* ── wedding date sheet ──────────────────────────────── */
    var dateScrim = document.getElementById('ms-date');
    var dateForm = document.getElementById('ms-date-form');
    var dateInput = document.getElementById('ms-d-date');
    window.msOpenDate = function (opener) {
        dateInput.value = WEDDING;
        showError(dateForm.querySelector('[data-ms-error]'), '');
        openSheet(dateScrim, opener, dateInput);
    };
    dateForm.addEventListener('submit', function (e) {
        e.preventDefault();
        saveWeddingDate(dateInput.value, dateForm.querySelector('[data-ms-error]'), dateForm.querySelector('[type=submit]'));
    });

    /* ── edit / add sheet ────────────────────────────────── */
    var editScrim = document.getElementById('ms-edit');
    var form = document.getElementById('ms-edit-form');
    var f = {
        heading: document.getElementById('ms-edit-title'),
        title: document.getElementById('ms-f-title'),
        count: document.getElementById('ms-f-count'),
        unit: document.getElementById('ms-f-unit'),
        after: document.getElementById('ms-f-after'),
        offsetLabel: document.getElementById('ms-f-offset-label'),
        computed: document.getElementById('ms-f-computed'),
        custom: document.getElementById('ms-f-custom'),
        reset: document.getElementById('ms-f-reset'),
        error: form.querySelector('[data-ms-error]'),
        actions: document.getElementById('ms-edit-actions'),
        submit: form.querySelector('[type=submit]'),
        del: document.getElementById('ms-f-delete'),
        confirm: document.getElementById('ms-del-confirm'),
        yes: document.getElementById('ms-del-yes'),
        no: document.getElementById('ms-del-no')
    };
    var editing = null; // {id, custom} or null for a new milestone

    function splitOffset(days) {
        var n = Math.abs(days);
        if (n >= 30 && n % 30 === 0) return [n / 30, 30];
        if (n > 0 && n % 7 === 0) return [n / 7, 7];
        return [n, 1];
    }
    function readOffset() {
        var raw = f.count.value.trim();
        if (!/^\d+$/.test(raw)) return null;
        var days = parseInt(raw, 10) * parseInt(f.unit.value, 10);
        return f.after.checked ? days : -days;
    }
    function syncOffsetUi() {
        f.offsetLabel.textContent = f.after.checked ? 'כמה זמן אחרי החתונה' : 'כמה זמן לפני החתונה';
        var offset = readOffset();
        f.computed.hidden = offset === null;
        if (offset !== null) f.computed.querySelector('span').textContent = dotted(isoAddDays(WEDDING, offset));
    }
    function setConfirming(on) {
        f.confirm.hidden = !on;
        f.actions.hidden = on;
        f.del.hidden = on || !editing;
        if (on) f.no.focus();
    }
    function setInvalid(el, bad) {
        if (bad) el.setAttribute('aria-invalid', 'true'); else el.removeAttribute('aria-invalid');
    }

    window.msOpenEdit = function (row, opener) {
        editing = row ? { id: row.dataset.id, custom: row.dataset.custom || '' } : null;
        f.heading.textContent = row ? 'עריכת אבן דרך' : 'אבן דרך חדשה';
        f.title.value = row ? row.dataset.title : '';
        var offset = row ? parseInt(row.dataset.offset, 10) : null;
        if (offset === null) {
            f.count.value = '';
            f.unit.value = '7';
            f.after.checked = false;
        } else {
            var parts = splitOffset(offset);
            f.count.value = parts[0];
            f.unit.value = String(parts[1]);
            f.after.checked = offset > 0;
        }
        f.custom.value = editing ? editing.custom : '';
        f.reset.hidden = !(editing && editing.custom);
        [f.title, f.count, f.custom].forEach(function (el) { setInvalid(el, false); });
        showError(f.error, '');
        f.submit.disabled = false;
        f.yes.disabled = false;
        setConfirming(false);
        syncOffsetUi();
        openSheet(editScrim, opener, row ? null : f.title);
    };

    [f.count, f.unit, f.after].forEach(function (el) {
        el.addEventListener('input', syncOffsetUi);
        el.addEventListener('change', syncOffsetUi);
    });
    f.reset.addEventListener('click', function () {
        f.custom.value = '';
        f.reset.hidden = true;
        f.custom.focus();
    });
    f.del.addEventListener('click', function () { setConfirming(true); });
    f.no.addEventListener('click', function () { setConfirming(false); f.del.focus(); });

    function request(method, url, body) {
        return fetch(url, {
            method: method, headers: JSON_HEADERS, credentials: 'same-origin',
            body: body === undefined ? undefined : JSON.stringify(body)
        }).then(function (res) {
            if (res.ok) return res.status === 204 ? null : res.json();
            return errorDetail(res).then(function (msg) { throw new Error(msg); });
        });
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        var title = f.title.value.trim();
        var offset = readOffset();
        var custom = f.custom.value;
        setInvalid(f.title, !title);
        setInvalid(f.count, offset === null);
        if (!title) { showError(f.error, 'יש להזין שם'); f.title.focus(); return; }
        if (offset === null) { showError(f.error, 'יש להזין מספר שלם'); f.count.focus(); return; }
        if (offset < -1000 || offset > 365) {
            setInvalid(f.count, true);
            showError(f.error, 'אפשר עד 1000 ימים לפני החתונה ועד 365 אחרי');
            f.count.focus();
            return;
        }
        showError(f.error, '');
        f.submit.disabled = true;
        var body = { title: title, offset_days: offset };
        var saving;
        if (editing) {
            if (custom !== editing.custom) body.custom_date = custom || null;
            saving = request('PUT', '/api/wedding/milestones/' + editing.id, body);
        } else {
            body.kind = 'general';
            saving = request('POST', '/api/wedding/milestones', body).then(function (created) {
                return custom ? request('PUT', '/api/wedding/milestones/' + created.id, { custom_date: custom }) : created;
            });
        }
        saving.then(function () { location.reload(); }, function (err) {
            showError(f.error, (err && err.message) || SAVE_FAILED);
            f.submit.disabled = false;
        });
    });

    f.yes.addEventListener('click', function () {
        if (!editing) return;
        f.yes.disabled = true;
        request('DELETE', '/api/wedding/milestones/' + editing.id).then(function () {
            location.reload();
        }, function (err) {
            f.yes.disabled = false;
            setConfirming(false);
            showError(f.error, (err && err.message) || 'המחיקה נכשלה, נסו שוב.');
        });
    });

    /* ── rail: toggle done (optimistic) and open the editor ─ */
    var rail = document.getElementById('ms-rail');
    var pending = {};
    var STATUSES = ['ms-done', 'ms-overdue', 'ms-next', 'ms-future'];

    function setRowState(row, status, completed) {
        STATUSES.forEach(function (c) { row.classList.remove(c); });
        row.classList.add('ms-' + status);
        row.dataset.status = status;
        row.dataset.completed = completed ? '1' : '0';
        row.querySelector('[data-ms-toggle]').setAttribute('aria-pressed', completed ? 'true' : 'false');
    }
    function pendingCount() { return Object.keys(pending).length; }

    // Re-render the live regions from the server so "next"/"overdue" move with the change.
    // Accept: text/html keeps sw.js from answering with a cached copy (it caches other GETs).
    function refreshRail() {
        fetch(location.pathname, {
            credentials: 'same-origin', cache: 'no-store', headers: { 'Accept': 'text/html' }
        }).then(function (res) {
            return res.ok ? res.text() : Promise.reject();
        }).then(function (html) {
            if (pendingCount()) return;
            var active = document.activeElement;
            var activeRow = active && active.closest && active.closest('.ms-row');
            var focusId = activeRow && activeRow.dataset.id;
            var focusSel = active && active.hasAttribute('data-ms-toggle') ? '[data-ms-toggle]' : '[data-ms-edit]';
            var doc = new DOMParser().parseFromString(html, 'text/html');
            document.querySelectorAll('[data-ms-live]').forEach(function (el) {
                var fresh = doc.getElementById(el.id);
                if (fresh) el.innerHTML = fresh.innerHTML;
            });
            if (focusId) {
                var row = rail.querySelector('.ms-row[data-id="' + focusId + '"]');
                var target = row && row.querySelector(focusSel);
                if (target) target.focus({ preventScroll: true });
            }
        }).catch(function () { /* the optimistic state stays until the next load */ });
    }

    function toggleRow(row) {
        var id = row.dataset.id;
        if (pending[id]) return;
        var wasDone = row.dataset.completed === '1';
        var prevStatus = row.dataset.status;
        var errorBox = row.querySelector('.ms-err');
        showError(errorBox, '');
        setRowState(row, wasDone ? row.dataset.open : 'done', !wasDone);
        pending[id] = true;
        request('PUT', '/api/wedding/milestones/' + id, { completed: wasDone ? 0 : 1 }).then(function () {
            delete pending[id];
            if (!pendingCount()) refreshRail();
        }, function () {
            delete pending[id];
            setRowState(row, prevStatus, wasDone);
            showError(errorBox, SAVE_FAILED);
            clearTimeout(row._msErrTimer);
            row._msErrTimer = setTimeout(function () { showError(errorBox, ''); }, 5000);
        });
    }

    rail.addEventListener('click', function (e) {
        var node = e.target.closest('[data-ms-toggle]');
        if (node) { toggleRow(node.closest('.ms-row')); return; }
        var card = e.target.closest('[data-ms-edit]');
        if (card) window.msOpenEdit(card.closest('.ms-row'), card);
    });
})();
