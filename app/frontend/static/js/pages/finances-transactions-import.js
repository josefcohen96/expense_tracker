(function () {
    'use strict';

    const PAGE_DATA = JSON.parse(document.getElementById('transactions-import-data').textContent);
    var CATEGORIES = PAGE_DATA.categories;

    var pick = document.getElementById('ci-pick');
    var drop = document.getElementById('ci-drop');
    var fileInput = document.getElementById('ci-file');
    var loading = document.getElementById('ci-loading');
    var errorLine = document.getElementById('ci-error');
    var preview = document.getElementById('ci-preview');
    var summary = document.getElementById('ci-summary');
    var payerSelect = document.getElementById('ci-payer');
    var accountSelect = document.getElementById('ci-account');
    var newTitle = document.getElementById('ci-new-title');
    var newList = document.getElementById('ci-new-list');
    var newEmpty = document.getElementById('ci-new-empty');
    var skipped = document.getElementById('ci-skipped');
    var skippedTitle = document.getElementById('ci-skipped-title');
    var skippedList = document.getElementById('ci-skipped-list');
    var submitBtn = document.getElementById('ci-submit');
    var submitError = document.getElementById('ci-submit-error');
    var done = document.getElementById('ci-done');
    var doneText = document.getElementById('ci-done-text');
    var doneLink = document.getElementById('ci-done-link');
    var undoBtn = document.getElementById('ci-undo');

    var NOT_MAX = 'הקובץ לא נראה כמו דוח של max';
    var READ_FAILED = 'שגיאה בקריאת הקובץ';
    var REASONS = { exists: 'קיימת', recurring: 'הוצאה קבועה' };

    var current = null;   // last preview response
    var created = [];     // ids from the last import

    function show(state) {
        pick.hidden = state !== 'pick';
        preview.hidden = state !== 'preview';
        done.hidden = state !== 'done';
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = text;
        return node;
    }

    function shortDate(iso) {
        var p = String(iso || '').split('-');
        return p.length === 3 ? p[2] + '.' + p[1] : iso;
    }

    function money(amount) {
        var n = Number(amount) || 0;
        var s = '₪' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return n < 0 ? '-' + s : s;
    }

    function amountNode(amount) {
        var span = el('span', 'font-semibold text-gray-900 whitespace-nowrap', money(amount));
        span.setAttribute('dir', 'ltr');
        return span;
    }

    function toastOnPhone(msg, actionLabel, onAction) {
        // The tab-bar toast only exists (and only makes sense) below lg.
        var desktop = window.matchMedia && window.matchMedia('(min-width: 1024px)').matches;
        if (window.AppToast && document.getElementById('qa-toast') && !desktop) {
            window.AppToast(msg, actionLabel, onAction, 6000);
            return true;
        }
        return false;
    }

    // ── State 1 ────────────────────────────────────────────────────────────
    function resetPick() {
        fileInput.value = '';
        loading.hidden = true;
        errorLine.hidden = true;
        current = null;
        created = [];
        show('pick');
    }

    function showError(text) {
        loading.hidden = true;
        errorLine.textContent = text;
        errorLine.hidden = false;
    }

    function upload(file) {
        if (!file) return;
        errorLine.hidden = true;
        loading.hidden = false;
        var form = new FormData();
        form.append('file', file);
        fetch('/api/transactions/import/preview', { method: 'POST', body: form, credentials: 'same-origin' })
            .then(function (res) {
                return res.json().catch(function () { return {}; }).then(function (data) {
                    if (!res.ok) {
                        showError(res.status === 400 && data.detail === NOT_MAX ? NOT_MAX : READ_FAILED);
                        return;
                    }
                    loading.hidden = true;
                    renderPreview(data);
                });
            })
            .catch(function () { showError(READ_FAILED); });
    }

    fileInput.addEventListener('change', function () { upload(fileInput.files[0]); });
    ['dragenter', 'dragover'].forEach(function (type) {
        drop.addEventListener(type, function (e) {
            e.preventDefault();
            drop.classList.add('bg-blue-50', 'border-blue-400');
        });
    });
    ['dragleave', 'drop'].forEach(function (type) {
        drop.addEventListener(type, function (e) {
            e.preventDefault();
            drop.classList.remove('bg-blue-50', 'border-blue-400');
        });
    });
    drop.addEventListener('drop', function (e) {
        var files = e.dataTransfer && e.dataTransfer.files;
        if (files && files.length) upload(files[0]);
    });

    // ── State 2 ────────────────────────────────────────────────────────────
    function categorySelect(selected) {
        var select = el('select', 'form-select text-sm');
        select.setAttribute('aria-label', 'קטגוריה');
        CATEGORIES.forEach(function (c) {
            var opt = el('option', null, c.name);
            opt.value = c.id;
            if (c.id === selected) opt.selected = true;
            select.appendChild(opt);
        });
        return select;
    }

    // One line per statement row: a checkbox (the user decides), the date, and the
    // merchant name, amount and category as editable fields. Rows the app already
    // has come unchecked with the reason; ticking one adds it anyway.
    function rowItem(row, checked) {
        var li = el('li', 'py-3 flex items-start gap-3');
        li.dataset.index = row.index;

        var box = el('input', 'mt-2 w-5 h-5 flex-shrink-0 accent-blue-600');
        box.type = 'checkbox';
        box.checked = checked;
        box.setAttribute('aria-label', row.merchant);
        box.addEventListener('change', updateSubmit);
        li.appendChild(box);

        var body = el('div', 'flex-1 min-w-0 flex flex-col lg:flex-row lg:items-start gap-2');

        var line = el('div', 'flex items-center gap-2 min-w-0 flex-1');
        line.appendChild(el('span', 'text-sm text-gray-500 whitespace-nowrap', shortDate(row.date)));
        var name = el('input', 'form-input text-sm flex-1 min-w-0');
        name.type = 'text';
        name.value = row.merchant;
        name.setAttribute('aria-label', 'שם בית העסק');
        name.dataset.field = 'merchant';
        name.addEventListener('input', function () { if (!box.checked) { box.checked = true; } updateSubmit(); });
        line.appendChild(name);
        var amount = el('input', 'form-input text-sm w-28 flex-shrink-0');
        amount.type = 'number';
        amount.step = '0.01';
        amount.value = String(row.amount);
        amount.setAttribute('dir', 'ltr');
        amount.setAttribute('aria-label', 'סכום');
        amount.dataset.field = 'amount';
        amount.addEventListener('input', function () { if (!box.checked) { box.checked = true; } updateSubmit(); });
        line.appendChild(amount);
        body.appendChild(line);

        var pickCat = el('div', 'lg:w-48 flex-shrink-0');
        pickCat.appendChild(categorySelect(row.category_id));
        if (row.status !== 'new') {
            pickCat.appendChild(el('p', 'text-xs text-gray-500 mt-1', REASONS[row.status] || ''));
        } else if (row.category_source === 'merchant') {
            pickCat.appendChild(el('p', 'text-xs text-gray-500 mt-1', 'כמו בפעם הקודמת'));
        } else if (row.category_source === 'fallback') {
            pickCat.appendChild(el('p', 'text-xs text-amber-600 font-medium mt-1', 'לא זוהתה קטגוריה'));
        }
        body.appendChild(pickCat);
        li.appendChild(body);
        return li;
    }

    // The ticked rows of both lists, as edited. A row whose amount is not a
    // number (or is zero) is flagged and left out until it is fixed.
    function checkedRows() {
        var rows = [];
        [newList, skippedList].forEach(function (list) {
            Array.prototype.forEach.call(list.children, function (li) {
                var box = li.querySelector('input[type="checkbox"]');
                var amountInput = li.querySelector('[data-field="amount"]');
                var amount = Number(amountInput.value);
                var bad = box.checked && (!isFinite(amount) || amount === 0 || amountInput.value.trim() === '');
                amountInput.classList.toggle('border-red-400', bad);
                if (!box.checked || bad) return;
                var row = current.rows[Number(li.dataset.index)];
                rows.push({
                    date: row.date,
                    amount: amount,
                    merchant: li.querySelector('[data-field="merchant"]').value.trim() || row.merchant,
                    category_id: Number(li.querySelector('select').value),
                });
            });
        });
        return rows;
    }

    function updateSubmit() {
        var n = checkedRows().length;
        submitBtn.textContent = 'הוסף ' + n + ' עסקאות';
        submitBtn.disabled = n === 0;
    }

    function renderPreview(data) {
        current = data;
        var parts = [];
        if (data.holder) parts.push(data.holder);
        if (data.card_last4) parts.push('כרטיס ' + data.card_last4);
        if (data.statement_month) parts.push(data.statement_month);
        summary.textContent = parts.join(' · ');
        summary.hidden = parts.length === 0;

        if (data.user_id !== null && data.user_id !== undefined) payerSelect.value = String(data.user_id);
        accountSelect.value = data.account_id ? String(data.account_id) : '';

        var fresh = data.rows.filter(function (r) { return r.status === 'new'; });
        // Rows that need a look first; the rest keep file order.
        fresh.sort(function (a, b) {
            var fa = a.category_source === 'fallback' ? 0 : 1;
            var fb = b.category_source === 'fallback' ? 0 : 1;
            return fa - fb || a.index - b.index;
        });
        var old = data.rows.filter(function (r) { return r.status !== 'new'; });

        newTitle.textContent = 'חדשות (' + fresh.length + ')';
        newList.textContent = '';
        fresh.forEach(function (r) { newList.appendChild(rowItem(r, true)); });
        newEmpty.hidden = fresh.length > 0;
        newList.hidden = fresh.length === 0;

        skippedTitle.textContent = 'כבר רשומות (' + old.length + ')';
        skippedList.textContent = '';
        old.forEach(function (r) { skippedList.appendChild(rowItem(r, false)); });
        skipped.hidden = old.length === 0;
        skipped.open = false;

        submitError.hidden = true;
        submitBtn.hidden = data.rows.length === 0;
        updateSubmit();
        show('preview');
    }

    submitBtn.addEventListener('click', function () {
        var rows = checkedRows();
        if (!rows.length || submitBtn.disabled) return;
        submitBtn.disabled = true;
        submitError.hidden = true;
        fetch('/api/transactions/import', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: Number(payerSelect.value),
                account_id: accountSelect.value ? Number(accountSelect.value) : null,
                rows: rows,
            }),
        })
            .then(function (res) {
                return res.json().catch(function () { return {}; }).then(function (data) {
                    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '');
                    renderDone(data);
                });
            })
            .catch(function (err) {
                submitError.textContent = (err && err.message) || 'שגיאה בשמירה';
                submitError.hidden = false;
                updateSubmit();
            });
    });

    // ── State 3 ────────────────────────────────────────────────────────────
    function renderDone(data) {
        created = data.created || [];
        var msg = 'נוספו ' + data.count + ' עסקאות';
        doneText.textContent = msg;
        var month = current && current.statement_month;
        doneLink.textContent = month ? 'לעסקאות של ' + month : 'לעסקאות';
        doneLink.href = '/finances/transactions?date_from=' + encodeURIComponent(data.date_from) +
            '&date_to=' + encodeURIComponent(data.date_to);
        undoBtn.disabled = false;
        // The inline button stays even where the toast shows, so undo outlives the pill.
        undoBtn.hidden = false;
        toastOnPhone(msg, 'ביטול', undo);
        show('done');
    }

    function undo() {
        if (!created.length) return;
        undoBtn.disabled = true;
        fetch('/api/transactions/import/undo', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: created }),
        })
            .then(function (res) {
                if (!res.ok) throw new Error('undo failed');
                if (!toastOnPhone('בוטל') && window.showToast) window.showToast('בוטל', 'success');
                resetPick();
            })
            .catch(function () {
                undoBtn.disabled = false;
                if (window.showToast) window.showToast('שגיאה', 'error');
            });
    }
    undoBtn.addEventListener('click', undo);
})();
