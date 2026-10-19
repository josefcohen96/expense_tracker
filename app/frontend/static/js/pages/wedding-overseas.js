// הזמנות מחו״ל: one-tap stage moves with undo, accordion rows with a comment thread, add/edit sheet.
(function () {
    var board = document.getElementById('ov-board');
    if (!board) return;
    var me = board.getAttribute('data-me');
    var people = JSON.parse(document.getElementById('ov-people').textContent || '[]');
    var mePerson = people.filter(function (p) { return p.name === me; })[0] || null;
    var LABELS = {};
    board.querySelectorAll('.ov-lane').forEach(function (lane) {
        LABELS[lane.getAttribute('data-lane')] = lane.getAttribute('data-label');
    });
    var KNOWN_STORES = Array.prototype.map.call(
        document.querySelectorAll('#ov-stores [data-store]:not([data-store="__other"])'),
        function (b) { return b.getAttribute('data-store'); });

    function toast(msg, label, fn) {
        if (window.AppToast) window.AppToast(msg, label, fn, 4000);
    }

    function money(v) { return '₪' + Math.round(v).toLocaleString('en-US'); }

    function refresh() {
        board.querySelectorAll('.ov-lane').forEach(function (lane) {
            var key = lane.getAttribute('data-lane');
            var visible = Array.prototype.filter.call(lane.querySelectorAll('.ov-row'), function (r) { return !r.hidden; });
            lane.querySelector('[data-lane-count]').textContent = visible.length;
            if (key === 'to_order') {
                lane.querySelector('[data-lane-empty]').hidden = visible.length > 0;
            } else {
                lane.hidden = visible.length === 0;
            }
            var total = lane.querySelector('[data-lane-total]');
            if (total) {
                var sum = 0, any = false;
                visible.forEach(function (r) {
                    var est = parseFloat(r.getAttribute('data-estimate'));
                    if (!isNaN(est)) { sum += est; any = true; }
                });
                total.hidden = !any;
                total.querySelector('[data-total-value]').textContent = any ? money(sum) : '';
            }
        });
    }

    function laneRows(stage) {
        var lane = board.querySelector('.ov-lane[data-lane="' + stage + '"]');
        return lane ? lane.querySelector('[data-rows]') : null;
    }

    function place(row, stage, ordered, arrived) {
        row.setAttribute('data-stage', stage);
        row.querySelector('[data-ordered-ago]').textContent = ordered || 'היום';
        row.querySelector('[data-arrived-ago]').textContent = arrived || 'היום';
        var list = laneRows(stage);
        if (list) list.appendChild(row);
        refresh();
    }

    function putItem(id, body) {
        return fetch('/api/wedding/overseas/' + id, {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
    }

    function moveTo(row, stage, withUndo) {
        var prev = row.getAttribute('data-stage');
        var prevOrdered = row.querySelector('[data-ordered-ago]').textContent;
        var prevArrived = row.querySelector('[data-arrived-ago]').textContent;
        place(row, stage, stage === 'to_order' ? null : prevOrdered, stage === 'arrived' ? prevArrived : null);
        putItem(row.getAttribute('data-item-id'), { stage: stage }).then(function (item) {
            row.querySelector('[data-ordered-ago]').textContent = item.ordered_ago || 'היום';
            row.querySelector('[data-arrived-ago]').textContent = item.arrived_ago || 'היום';
            if (withUndo) {
                toast('הפריט עבר ל' + LABELS[stage], 'ביטול', function () { moveTo(row, prev, false); });
            }
        }).catch(function () {
            place(row, prev, prevOrdered, prevArrived);
            toast('שגיאה בשמירה');
        });
    }

    function toggle(row) {
        var detail = row.querySelector('[data-detail]');
        var open = detail.hidden;
        board.querySelectorAll('.ov-row').forEach(function (other) {
            other.querySelector('[data-detail]').hidden = true;
            other.classList.remove('is-open');
            other.querySelector('[data-toggle]').setAttribute('aria-expanded', 'false');
        });
        detail.hidden = !open;
        row.classList.toggle('is-open', open);
        row.querySelector('[data-toggle]').setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    function commentEl(body, person) {
        var wrap = document.createElement('div');
        wrap.className = 'ov-comment';
        var av = document.createElement('span');
        av.className = 'person-avatar' + (person ? '' : ' ov-anon');
        av.style.cssText = 'width:24px;height:24px' + (person ? ';background:' + person.color : '');
        av.setAttribute('aria-hidden', 'true');
        av.textContent = person ? person.initial : '?';
        var inner = document.createElement('div');
        inner.className = 'ov-comment-body';
        var p = document.createElement('p');
        p.className = 'ov-comment-text';
        p.textContent = body;
        var when = document.createElement('span');
        when.className = 'ov-comment-when';
        when.textContent = 'היום';
        inner.appendChild(p);
        inner.appendChild(when);
        wrap.appendChild(av);
        wrap.appendChild(inner);
        return wrap;
    }

    function setCount(row, delta) {
        var cc = row.querySelector('[data-cc]');
        var n = (parseInt(cc.textContent, 10) || 0) + delta;
        cc.textContent = n;
        row.querySelector('[data-cc-wrap]').hidden = n <= 0;
    }

    function postComment(row, form) {
        var input = form.querySelector('input');
        var body = input.value.trim();
        if (!body) return;
        input.value = '';
        var el = commentEl(body, mePerson);
        row.querySelector('[data-thread]').appendChild(el);
        setCount(row, 1);
        var payload = { body: body };
        if (me) payload.author = me;
        fetch('/api/wedding/overseas/' + row.getAttribute('data-item-id') + '/comments', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(function (r) { if (!r.ok) throw new Error(r.status); }).catch(function () {
            el.remove();
            setCount(row, -1);
            input.value = body;
            toast('שגיאה בשמירה');
        });
    }

    board.addEventListener('click', function (e) {
        var row = e.target.closest('.ov-row');
        if (!row) return;
        var act = e.target.closest('[data-to]');
        if (act) { moveTo(row, act.getAttribute('data-to'), true); return; }
        if (e.target.closest('[data-edit]')) { openSheet(JSON.parse(row.getAttribute('data-item'))); return; }
        if (e.target.closest('[data-toggle]')) toggle(row);
    });
    board.addEventListener('submit', function (e) {
        var form = e.target.closest('[data-compose]');
        if (!form) return;
        e.preventDefault();
        postComment(form.closest('.ov-row'), form);
    });

    // Lead time (weeks before the wedding) for the big order.
    var leadEdit = board.querySelector('[data-lead-edit]');
    var leadForm = board.querySelector('[data-lead-form]');
    if (leadEdit && leadForm) {
        leadEdit.addEventListener('click', function () {
            leadForm.hidden = !leadForm.hidden;
            if (!leadForm.hidden) leadForm.querySelector('input').focus();
        });
        leadForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var weeks = parseInt(leadForm.querySelector('input').value, 10);
            if (!(weeks >= 1 && weeks <= 20)) { toast('זמן אספקה חייב להיות בין שבוע ל-20 שבועות'); return; }
            fetch('/api/wedding/settings', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: 'overseas_lead_days', value: String(weeks * 7) }),
            }).then(function (r) { if (!r.ok) throw new Error(r.status); location.reload(); })
              .catch(function () { toast('שגיאה בשמירה'); });
        });
    }

    // ── Sheet ──
    var sheet = document.getElementById('ov-sheet');
    var form = document.getElementById('ov-form');
    var fTitle = document.getElementById('ov-title');
    var fUrl = document.getElementById('ov-url');
    var fOther = document.getElementById('ov-store-other');
    var fPrice = document.getElementById('ov-price');
    var fQty = document.getElementById('ov-qty');
    var fError = document.getElementById('ov-form-error');
    var delBtn = document.getElementById('ov-delete');
    var editingId = null;
    var store = '';

    function selectStore(key) {
        store = key;
        document.querySelectorAll('#ov-stores [data-store]').forEach(function (b) {
            b.classList.toggle('is-active', b.getAttribute('data-store') === key);
        });
        fOther.hidden = key !== '__other';
    }

    function openSheet(item) {
        editingId = item ? item.id : null;
        document.getElementById('ov-sheet-title').textContent = item ? 'עריכת פריט' : 'פריט חדש';
        fTitle.value = item ? item.title : '';
        fUrl.value = item && item.url ? item.url : '';
        fPrice.value = item && item.sample_price != null ? item.sample_price : '';
        fQty.value = item && item.quantity_needed != null ? item.quantity_needed : '';
        var s = item && item.store ? item.store : '';
        if (!s) { selectStore(''); fOther.value = ''; }
        else if (KNOWN_STORES.indexOf(s) >= 0) { selectStore(s); fOther.value = ''; }
        else { selectStore('__other'); fOther.value = s; }
        fError.hidden = true;
        delBtn.hidden = !item;
        sheet.classList.remove('hidden');
        sheet.classList.add('flex');
        if (!item) setTimeout(function () { fTitle.focus(); }, 50);
    }

    function closeSheet() {
        sheet.classList.add('hidden');
        sheet.classList.remove('flex');
    }

    document.querySelectorAll('[data-ov-add]').forEach(function (b) {
        b.addEventListener('click', function () { openSheet(null); });
    });
    sheet.querySelectorAll('[data-sheet-close]').forEach(function (b) { b.addEventListener('click', closeSheet); });
    document.getElementById('ov-stores').addEventListener('click', function (e) {
        var chip = e.target.closest('[data-store]');
        if (!chip) return;
        var key = chip.getAttribute('data-store');
        selectStore(store === key ? '' : key);
        if (store === '__other') fOther.focus();
    });

    function numberOrNull(input, parse) {
        var v = input.value.trim();
        if (v === '') return null;
        var n = parse(v);
        return isNaN(n) ? null : n;
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        var title = fTitle.value.trim();
        if (!title) { fTitle.focus(); return; }
        // A pasted "www.aliexpress.com/..." is what a phone keyboard produces; the server wants http(s).
        var url = fUrl.value.trim();
        if (url && !/^https?:\/\//i.test(url)) url = 'https://' + url;
        var body = {
            title: title,
            url: url || null,
            store: store === '__other' ? (fOther.value.trim() || null) : (store || null),
            sample_price: numberOrNull(fPrice, parseFloat),
            quantity_needed: numberOrNull(fQty, function (v) { return parseInt(v, 10); }),
        };
        if (!editingId && me) body.created_by = me;
        fetch(editingId ? '/api/wedding/overseas/' + editingId : '/api/wedding/overseas', {
            method: editingId ? 'PUT' : 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then(function (r) {
            if (r.ok) { closeSheet(); location.reload(); return; }
            // The server answers 422 with a Hebrew reason; show it instead of a generic error.
            return r.json().then(function (data) {
                var detail = data && typeof data.detail === 'string' ? data.detail : '';
                throw new Error(detail);
            }, function () { throw new Error(''); });
        }).catch(function (err) {
            fError.textContent = (err && err.message) || 'שגיאה בשמירה';
            fError.hidden = false;
        });
    });

    // Delete waits for the undo window; a page leave sends it right away.
    var pendingDeletes = {};
    function sendDelete(id, keepalive) {
        delete pendingDeletes[id];
        return fetch('/api/wedding/overseas/' + id, { method: 'DELETE', credentials: 'same-origin', keepalive: !!keepalive });
    }
    delBtn.addEventListener('click', function () {
        var id = editingId;
        if (!id) return;
        closeSheet();
        var row = board.querySelector('.ov-row[data-item-id="' + id + '"]');
        if (row) row.hidden = true;
        refresh();
        pendingDeletes[id] = setTimeout(function () {
            sendDelete(id, false).then(function (r) { if (!r.ok) throw new Error(r.status); }).catch(function () {
                if (row) row.hidden = false;
                refresh();
                toast('שגיאה בשמירה');
            });
        }, 4000);
        toast('הפריט נמחק', 'ביטול', function () {
            clearTimeout(pendingDeletes[id]);
            delete pendingDeletes[id];
            if (row) row.hidden = false;
            refresh();
        });
    });
    window.addEventListener('pagehide', function () {
        Object.keys(pendingDeletes).forEach(function (id) {
            clearTimeout(pendingDeletes[id]);
            sendDelete(id, true);
        });
    });

    refresh();
})();
