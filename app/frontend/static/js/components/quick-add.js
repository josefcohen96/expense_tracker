// Quick-add bottom sheet (mobile). Markup: templates/layout/_quick_add.html.
// Opened from the tab bar "+"; kind is 'expense' on כספים and 'task' elsewhere.
(function () {
    'use strict';

    var root = document.getElementById('quick-add');
    var fab = document.getElementById('mobile-fab');
    if (!root || !fab) return;

    var sheet = root.querySelector('.qa-sheet');
    var context = root.getAttribute('data-context') || 'today';
    var reloadOn = (root.getAttribute('data-reload-on') || '').split(/\s+/);
    var toast = document.getElementById('qa-toast');

    var MAX_INT_DIGITS = 7;

    var options = null;
    var optionsPromise = null;
    var state = null;
    var opener = null;
    var saving = false;

    function $(sel, scope) { return (scope || root).querySelector(sel); }
    function $all(sel, scope) { return Array.prototype.slice.call((scope || root).querySelectorAll(sel)); }
    function panel(kind) { return $('[data-qa-panel="' + kind + '"]'); }

    function isoDate(d) {
        var m = d.getMonth() + 1, day = d.getDate();
        return d.getFullYear() + '-' + (m < 10 ? '0' : '') + m + '-' + (day < 10 ? '0' : '') + day;
    }
    function addDays(days) {
        var d = new Date();
        d.setDate(d.getDate() + days);
        return isoDate(d);
    }
    function dayLabel(iso) {
        if (iso === addDays(0)) return 'היום';
        if (iso === addDays(-1)) return 'אתמול';
        if (iso === addDays(1)) return 'מחר';
        var parts = iso.split('-');
        return Number(parts[2]) + '.' + Number(parts[1]);
    }

    function loadOptions() {
        if (!optionsPromise) {
            optionsPromise = fetch('/api/quick-add/options', { credentials: 'same-origin' })
                .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
                .then(function (data) { options = data; return data; })
                .catch(function (err) { optionsPromise = null; throw err; });
        }
        return optionsPromise;
    }

    // ── Chips ────────────────────────────────────────────────────────────────
    function selectChip(group, value) {
        $all('.qa-chip[data-value]', group).forEach(function (chip) {
            var on = chip.getAttribute('data-value') === String(value);
            chip.classList.toggle('is-selected', on);
            chip.setAttribute('aria-checked', on ? 'true' : 'false');
        });
    }
    function chip(label, value, extraClass) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'qa-chip' + (extraClass ? ' ' + extraClass : '');
        b.setAttribute('role', 'radio');
        b.setAttribute('data-value', value);
        b.textContent = label;
        return b;
    }

    // ── Expense ──────────────────────────────────────────────────────────────
    function formatAmount(raw) {
        var parts = (raw || '0').split('.');
        var intPart = String(Number(parts[0] || '0')).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        return '₪' + intPart + (parts.length > 1 ? '.' + parts[1] : '');
    }
    function renderAmount() {
        $('[data-qa-amount]').textContent = formatAmount(state.amount);
    }
    function pressKey(key) {
        var a = state.amount;
        if (key === 'back') {
            a = a.slice(0, -1);
        } else if (key === '.') {
            if (a.indexOf('.') === -1) a = (a || '0') + '.';
        } else {
            var dot = a.indexOf('.');
            if (dot !== -1 && a.length - dot > 2) return;
            if (dot === -1 && a.replace(/^0+/, '').length >= MAX_INT_DIGITS) return;
            a = (a === '0' ? '' : a) + key;
        }
        state.amount = a;
        setError('');
        renderAmount();
    }
    function renderTokens() {
        var payer = options.people.filter(function (p) { return p.id === state.payer; })[0];
        var account = options.accounts.filter(function (a) { return a.id === state.account; })[0];
        $('[data-qa-token="date"]').textContent = dayLabel(state.date);
        $('[data-qa-token="payer"]').textContent = payer ? payer.display : '—';
        $('[data-qa-token="account"]').textContent = account ? account.name : 'ללא חשבון';
    }
    function cycle(list, current) {
        var ids = list.map(function (x) { return x.id; });
        return ids[(ids.indexOf(current) + 1) % ids.length];
    }
    function renderCategories(expanded) {
        var box = $('[data-qa-categories]');
        box.innerHTML = '';
        var cats = options.categories;
        var shown = expanded ? cats : cats.slice(0, 5);
        shown.forEach(function (c) {
            box.appendChild(chip((c.emoji ? c.emoji + ' ' : '') + c.name, c.id));
        });
        if (!expanded && cats.length > shown.length) {
            var more = chip('עוד ▾', 'more', 'qa-chip-more');
            more.removeAttribute('role');
            box.appendChild(more);
        }
        selectChip(box, state.category);
    }
    function setupExpense() {
        state = {
            kind: 'expense',
            amount: '',
            date: addDays(0),
            payer: options.me ? options.me.id : (options.people[0] || {}).id,
            account: options.default_account_id,
            category: options.categories.length ? options.categories[0].id : null,
        };
        $('[data-qa-note]').value = '';
        renderAmount();
        renderTokens();
        renderCategories(false);
    }

    // ── Task ─────────────────────────────────────────────────────────────────
    function renderOwners() {
        var box = $('[data-qa-owners]');
        box.innerHTML = '';
        options.people.forEach(function (p) {
            var b = chip('', p.name);
            var av = document.createElement('span');
            av.className = 'person-avatar';
            av.style.cssText = 'width:20px;height:20px;font-size:9px;background:' + p.color;
            av.textContent = p.initial;
            b.appendChild(av);
            b.appendChild(document.createTextNode(' ' + p.display));
            box.appendChild(b);
        });
        box.appendChild(chip('אף אחד', ''));
        selectChip(box, state.owner);
    }
    function renderTaskModule() {
        var wedding = state.module === 'wedding';
        $('[data-qa-owner-row]').hidden = !wedding;
        $('[data-qa-category-row]').hidden = !wedding;
        selectChip($('[data-qa-modules]'), state.module);
        root.setAttribute('data-accent', state.module === 'renovation' ? 'renovation' : 'wedding');
    }
    function renderDue() {
        var group = $('[data-qa-due]');
        var label = $('[data-qa-due-label]');
        var preset = { '': 'none' };
        preset[addDays(0)] = '0';
        preset[addDays(1)] = '1';
        preset[addDays(7)] = '7';
        var value = state.due in preset ? preset[state.due] : 'pick';
        label.textContent = value === 'pick' ? dayLabel(state.due) : 'תאריך';
        selectChip(group, value);
    }
    function setupTask() {
        var canRenovate = !!options.renovation;
        state = {
            kind: 'task',
            module: context === 'renovation' && canRenovate ? 'renovation' : 'wedding',
            owner: options.me ? options.me.name : '',
            due: '',
            category: 'general',
        };
        $('[data-qa-task-title]').value = '';
        $('[data-qa-module-row]').hidden = !canRenovate;
        renderOwners();
        var cats = $('[data-qa-task-categories]');
        cats.innerHTML = '';
        options.wedding_categories.forEach(function (c) { cats.appendChild(chip(c.label, c.key)); });
        selectChip(cats, state.category);
        renderTaskModule();
        renderDue();
    }

    // ── Sheet ────────────────────────────────────────────────────────────────
    function setError(msg) {
        $all('[data-qa-error]').forEach(function (el) { el.textContent = msg; });
    }
    function showKind(kind) {
        var other = kind === 'expense' ? 'task' : 'expense';
        panel(kind).hidden = false;
        panel(other).hidden = true;
        root.querySelector('#qa-title').textContent = kind === 'expense' ? 'הוצאה חדשה' : 'משימה חדשה';
        $('[data-qa-switch]').textContent = kind === 'expense' ? '⇄ משימה' : '⇄ הוצאה';
        root.setAttribute('data-kind', kind);
        root.setAttribute('data-accent', kind === 'expense' ? 'finances' : 'wedding');
        setError('');
        if (!options) return;
        if (kind === 'expense') setupExpense(); else setupTask();
    }

    function focusables() {
        return $all('button:not([disabled]), input:not([tabindex="-1"]), [href]', sheet)
            .filter(function (el) { return !el.closest('[hidden]') && el.offsetParent !== null; });
    }

    function open(kind) {
        if (!root.hidden) return;
        opener = document.activeElement;
        root.hidden = false;
        document.body.style.overflow = 'hidden';
        sheet.style.transform = '';
        // Next frame so the transition runs from the closed state.
        requestAnimationFrame(function () { root.classList.add('is-open'); });
        showKind(kind);
        sheet.focus({ preventScroll: true });
        if (!options) {
            root.classList.add('is-loading');
            loadOptions().then(function () {
                root.classList.remove('is-loading');
                showKind(root.getAttribute('data-kind'));
                if (kind === 'task') $('[data-qa-task-title]').focus();
            }).catch(function () {
                root.classList.remove('is-loading');
                setError('לא הצלחנו לטעון את האפשרויות. נסו שוב.');
            });
        } else if (kind === 'task') {
            $('[data-qa-task-title]').focus();
        }
    }

    function close() {
        if (root.hidden) return;
        root.classList.remove('is-open');
        document.body.style.overflow = '';
        var done = function () {
            root.hidden = true;
            sheet.style.transform = '';
            if (opener && opener.focus) opener.focus({ preventScroll: true });
        };
        var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduce) done(); else setTimeout(done, 240);
    }

    // A dark pill above the tab bar, optionally with one action (e.g. "ביטול").
    function hideToast() {
        clearTimeout(showToast.timer);
        toast.classList.remove('is-visible');
        setTimeout(function () { if (!toast.classList.contains('is-visible')) toast.hidden = true; }, 200);
    }
    function showToast(msg, actionLabel, onAction, duration) {
        if (!toast) return;
        toast.textContent = '';
        var text = document.createElement('span');
        text.textContent = msg;
        toast.appendChild(text);
        if (actionLabel && onAction) {
            var action = document.createElement('button');
            action.type = 'button';
            action.textContent = actionLabel;
            action.addEventListener('click', function () { hideToast(); onAction(); });
            toast.appendChild(action);
        }
        toast.hidden = false;
        requestAnimationFrame(function () { toast.classList.add('is-visible'); });
        clearTimeout(showToast.timer);
        showToast.timer = setTimeout(hideToast, duration || 2600);
    }
    window.AppToast = showToast;

    function postJSON(url, body) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then(function (r) {
            if (!r.ok) return r.json().catch(function () { return {}; }).then(function (e) {
                throw new Error(typeof e.detail === 'string' ? e.detail : '');
            });
            return r.json();
        });
    }

    function save() {
        if (saving || !options) return;
        var kind = state.kind;
        var request;
        if (kind === 'expense') {
            var amount = parseFloat(state.amount);
            if (!(amount > 0)) { setError('הקלידו סכום'); return; }
            if (!state.category) { setError('בחרו קטגוריה'); return; }
            request = postJSON('/api/transactions', {
                date: state.date,
                amount: amount,
                category_id: state.category,
                user_id: state.payer,
                account_id: state.account || null,
                notes: $('[data-qa-note]').value.trim() || null,
            });
        } else {
            var title = $('[data-qa-task-title]').value.trim();
            if (!title) { setError('מה צריך לעשות?'); $('[data-qa-task-title]').focus(); return; }
            request = state.module === 'renovation'
                ? postJSON('/api/renovation/tasks', { title: title, due_date: state.due || null })
                : postJSON('/api/wedding/tasks', {
                    title: title,
                    due_date: state.due || null,
                    owner: state.owner || null,
                    category: state.category,
                    priority: 'medium',
                });
        }
        saving = true;
        root.classList.add('is-saving');
        request.then(function () {
            saving = false;
            root.classList.remove('is-saving');
            close();
            if (reloadOn.indexOf(kind) !== -1) {
                location.reload();
            } else {
                showToast(kind === 'expense' ? 'ההוצאה נשמרה' : 'המשימה נשמרה');
            }
        }).catch(function (err) {
            saving = false;
            root.classList.remove('is-saving');
            setError(err && err.message ? err.message : 'השמירה נכשלה. נסו שוב.');
        });
    }

    // ── Events ───────────────────────────────────────────────────────────────
    fab.addEventListener('pointerdown', function () { loadOptions().catch(function () {}); }, { passive: true });
    fab.addEventListener('click', function (e) {
        e.preventDefault();
        open(context === 'finances' ? 'expense' : 'task');
    });

    $all('[data-qa-close]').forEach(function (el) { el.addEventListener('click', close); });
    $('[data-qa-switch]').addEventListener('click', function () {
        showKind(root.getAttribute('data-kind') === 'expense' ? 'task' : 'expense');
    });
    $all('[data-qa-save]').forEach(function (el) { el.addEventListener('click', save); });

    $('[data-qa-keypad]').addEventListener('click', function (e) {
        var key = e.target.closest('[data-key]');
        if (key && state) pressKey(key.getAttribute('data-key'));
    });
    $('[data-qa-categories]').addEventListener('click', function (e) {
        var c = e.target.closest('.qa-chip[data-value]');
        if (!c || !state) return;
        var v = c.getAttribute('data-value');
        if (v === 'more') { renderCategories(true); return; }
        state.category = Number(v);
        selectChip(this, v);
        setError('');
    });

    var dateInput = $('[data-qa-date]');
    $('[data-qa-token="date"]').addEventListener('click', function () {
        dateInput.value = state.date;
        if (dateInput.showPicker) { try { dateInput.showPicker(); return; } catch (err) { /* fall through */ } }
        dateInput.focus();
        dateInput.click();
    });
    dateInput.addEventListener('change', function () {
        if (dateInput.value) { state.date = dateInput.value; renderTokens(); }
    });
    $('[data-qa-token="payer"]').addEventListener('click', function () {
        if (options.people.length) { state.payer = cycle(options.people, state.payer); renderTokens(); }
    });
    $('[data-qa-token="account"]').addEventListener('click', function () {
        if (options.accounts.length) { state.account = cycle(options.accounts, state.account); renderTokens(); }
    });

    $('[data-qa-modules]').addEventListener('click', function (e) {
        var c = e.target.closest('.qa-chip[data-value]');
        if (c) { state.module = c.getAttribute('data-value'); renderTaskModule(); }
    });
    $('[data-qa-owners]').addEventListener('click', function (e) {
        var c = e.target.closest('.qa-chip[data-value]');
        if (c) { state.owner = c.getAttribute('data-value'); selectChip(this, state.owner); }
    });
    $('[data-qa-task-categories]').addEventListener('click', function (e) {
        var c = e.target.closest('.qa-chip[data-value]');
        if (c) { state.category = c.getAttribute('data-value'); selectChip(this, state.category); }
    });
    var dueInput = $('[data-qa-due-input]');
    $('[data-qa-due]').addEventListener('click', function (e) {
        var c = e.target.closest('.qa-chip[data-value]');
        if (!c) return;
        var v = c.getAttribute('data-value');
        if (v === 'pick') {
            dueInput.value = state.due || addDays(0);
            if (dueInput.showPicker) { try { dueInput.showPicker(); return; } catch (err) { /* fall through */ } }
            dueInput.focus();
            dueInput.click();
            return;
        }
        state.due = v === 'none' ? '' : addDays(Number(v));
        renderDue();
    });
    dueInput.addEventListener('change', function () {
        if (dueInput.value) { state.due = dueInput.value; renderDue(); }
    });
    $('[data-qa-task-title]').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); save(); }
    });

    root.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { e.preventDefault(); close(); return; }
        if (e.key === 'Tab') {
            var items = focusables();
            if (!items.length) return;
            var first = items[0], last = items[items.length - 1];
            if (e.shiftKey && (document.activeElement === first || document.activeElement === sheet)) {
                e.preventDefault(); last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault(); first.focus();
            }
            return;
        }
        // Hardware keyboard on the amount pad.
        if (state && state.kind === 'expense' && e.target.tagName !== 'INPUT') {
            if (/^[0-9.]$/.test(e.key)) { e.preventDefault(); pressKey(e.key); }
            else if (e.key === 'Backspace') { e.preventDefault(); pressKey('back'); }
            else if (e.key === 'Enter') { e.preventDefault(); save(); }
        }
    });

    // Drag the grab handle down to dismiss.
    var handle = $('[data-qa-handle]');
    var dragStart = null;
    handle.addEventListener('pointerdown', function (e) {
        dragStart = e.clientY;
        handle.setPointerCapture(e.pointerId);
        sheet.classList.add('is-dragging');
    });
    handle.addEventListener('pointermove', function (e) {
        if (dragStart === null) return;
        var dy = Math.max(0, e.clientY - dragStart);
        sheet.style.transform = 'translateY(' + dy + 'px)';
    });
    function endDrag(e) {
        if (dragStart === null) return;
        var dy = e.clientY - dragStart;
        dragStart = null;
        sheet.classList.remove('is-dragging');
        if (dy > 80) close(); else sheet.style.transform = '';
    }
    handle.addEventListener('pointerup', endDrag);
    handle.addEventListener('pointercancel', endDrag);

    // Pages can open the sheet directly, e.g. <button data-open-quick-add="task">.
    document.addEventListener('click', function (e) {
        var trigger = e.target.closest('[data-open-quick-add]');
        if (!trigger) return;
        e.preventDefault();
        open(trigger.getAttribute('data-open-quick-add') || 'task');
    });

    window.QuickAdd = { open: open, close: close };
})();
