const PAGE_DATA = JSON.parse(document.getElementById('tasks-data').textContent);
function openModal(id) {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    document.getElementById(id).classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    var fab = document.getElementById('task-fab');
    if (fab) fab.style.display = 'none';
}
function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
    document.body.style.overflow = '';
    var fab = document.getElementById('task-fab');
    if (fab) fab.style.display = '';
    document.getElementById('task-id').value = '';
    document.getElementById('task-modal-title').textContent = 'הוספת משימה';
    ['t-title','t-due-date','t-notes'].forEach(f => document.getElementById(f).value = '');
    document.getElementById('t-category').value = 'general';
    document.getElementById('t-priority').value = 'medium';
    document.getElementById('t-owner').value = PAGE_DATA.me_name;
}

function editTask(t) {
    document.getElementById('task-modal-title').textContent = 'עריכת משימה';
    document.getElementById('task-id').value = t.id;
    document.getElementById('t-title').value = t.title || '';
    document.getElementById('t-category').value = t.category || 'general';
    document.getElementById('t-priority').value = t.priority || 'medium';
    document.getElementById('t-due-date').value = t.due_date || '';
    document.getElementById('t-notes').value = t.notes || '';
    document.getElementById('t-owner').value = t.owner || '';
    openModal('add-task-modal');
}

function saveTask() {
    const id = document.getElementById('task-id').value;
    const payload = {
        title: document.getElementById('t-title').value.trim(),
        category: document.getElementById('t-category').value,
        priority: document.getElementById('t-priority').value,
        due_date: document.getElementById('t-due-date').value || null,
        notes: document.getElementById('t-notes').value.trim() || null,
        owner: document.getElementById('t-owner').value || null,
    };
    if (!payload.title) { alert('יש להזין כותרת'); return; }

    const url = id ? `/api/wedding/tasks/${id}` : '/api/wedding/tasks';
    const method = id ? 'PUT' : 'POST';
    fetch(url, {method, headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)})
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(() => location.reload())
        .catch(() => alert('שגיאה'));
}

function toggleTask(id, currentCompleted) {
    const newVal = currentCompleted ? 0 : 1;
    fetch(`/api/wedding/tasks/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({completed: newVal})
    })
    .then(r => { if (!r.ok) throw new Error(); location.reload(); })
    .catch(() => alert('שגיאה בעדכון המשימה'));
}

function deleteTask(id) {
    if (!confirm('למחוק משימה זו?')) return;
    fetch(`/api/wedding/tasks/${id}`, {method:'DELETE'})
        .then(r => { if (!r.ok) throw new Error(); location.reload(); })
        .catch(() => alert('שגיאה במחיקת המשימה'));
}
// Mobile task board: owner filter, optimistic completion with undo, swipe to complete, one-tap claim.
(function () {
    var board = document.getElementById('task-board');
    if (!board) return;
    var me = board.getAttribute('data-me');
    var people = JSON.parse(document.getElementById('task-people').textContent || '[]');
    var filter = me ? 'mine' : 'all';
    var DONE_PREVIEW = 5;
    var showAllDone = false;

    function rows() { return Array.prototype.slice.call(board.querySelectorAll('.tb-row')); }
    function groupEl(key) { return board.querySelector('.tb-group[data-group="' + key + '"]'); }
    function isOpen(row) { return !row.classList.contains('is-done'); }
    function owner(row) { return row.getAttribute('data-owner'); }

    function matches(row) {
        var o = owner(row);
        if (filter === 'all') return true;
        if (filter === 'none') return !o;
        if (filter === 'mine') return o === me || !o;
        return o === filter;
    }

    function refresh() {
        var all = rows();
        var anyOpenVisible = false;
        board.querySelectorAll('.tb-group').forEach(function (group) {
            var visible = 0;
            var isDone = group.getAttribute('data-group') === 'done';
            group.querySelectorAll('.tb-row').forEach(function (row) {
                var show = matches(row);
                if (show) visible++;
                row.hidden = !show || (isDone && !showAllDone && visible > DONE_PREVIEW);
            });
            group.hidden = visible === 0;
            group.querySelector('[data-group-count]').textContent = visible;
            if (!isDone && visible) anyOpenVisible = true;
            var more = group.querySelector('[data-show-more]');
            if (more) {
                more.hidden = showAllDone || visible <= DONE_PREVIEW;
                more.textContent = 'הצג עוד ' + (visible - DONE_PREVIEW);
            }
        });
        board.querySelector('[data-empty]').hidden = anyOpenVisible;

        // Chip and load-split counts count open tasks only.
        var open = all.filter(isOpen);
        var counts = { all: open.length, none: 0 };
        people.forEach(function (p) { counts[p.name] = 0; });
        open.forEach(function (row) {
            var o = owner(row);
            if (!o) counts.none++; else if (o in counts) counts[o]++;
        });
        counts.mine = me ? counts[me] : 0;
        board.querySelectorAll('.tb-filter').forEach(function (chip) {
            var key = chip.getAttribute('data-filter');
            chip.querySelector('[data-filter-count]').textContent = counts[key] || 0;
            if (key === 'none') chip.hidden = !counts.none && filter !== 'none';
        });
        var assigned = people.reduce(function (sum, p) { return sum + counts[p.name]; }, 0);
        board.querySelector('[data-split]').hidden = !assigned;
        people.forEach(function (p) {
            var bar = board.querySelector('[data-split-bar="' + p.name + '"]');
            if (bar) bar.style.width = (assigned ? counts[p.name] * 100 / assigned : 0) + '%';
            var label = board.querySelector('[data-split-count="' + p.name + '"]');
            if (label) label.textContent = counts[p.name];
        });
    }

    function placeRow(row) {
        var target = isOpen(row) ? row.getAttribute('data-open-group') : 'done';
        var list = groupEl(target).querySelector('[data-rows]');
        if (target === 'done') {
            list.insertBefore(row, list.firstChild);
            return;
        }
        var due = row.getAttribute('data-due');
        var next = Array.prototype.find.call(list.children, function (other) {
            return other !== row && other.getAttribute('data-due') > due;
        });
        list.insertBefore(row, next || null);
    }

    function setDoneState(row, done) {
        row.classList.toggle('is-done', done);
        row.classList.toggle('is-unassigned', !done && !owner(row));
        row.querySelector('.tb-check').setAttribute('aria-checked', done ? 'true' : 'false');
        var inner = row.querySelector('.tb-row-inner');
        inner.style.transition = 'none';
        inner.style.transform = '';
        row.classList.remove('is-swiping');
        placeRow(row);
        refresh();
    }

    function rowError(row, message) {
        var el = row.querySelector('.tb-row-error');
        el.textContent = message;
        el.hidden = !message;
    }

    function putTask(row, body) {
        return fetch('/api/wedding/tasks/' + row.getAttribute('data-task-id'), {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
    }

    function setCompleted(row, done, withUndo) {
        rowError(row, '');
        setDoneState(row, done);
        putTask(row, { completed: done ? 1 : 0 }).then(function () {
            if (withUndo && done && window.AppToast) {
                window.AppToast('המשימה סומנה כבוצעה', 'ביטול', function () { setCompleted(row, false, false); }, 4000);
            }
        }).catch(function () {
            setDoneState(row, !done);
            rowError(row, 'לא נשמר — נסו שוב');
        });
    }

    function claim(row, name) {
        var person = people.filter(function (p) { return p.name === name; })[0];
        if (!person) return;
        var cell = row.querySelector('[data-owner-cell]');
        var avatar = document.createElement('span');
        avatar.className = 'person-avatar';
        avatar.style.cssText = 'width:28px;height:28px;background:' + person.color;
        avatar.textContent = person.initial;
        avatar.setAttribute('aria-hidden', 'true');
        rowError(row, '');
        row.setAttribute('data-owner', name);
        row.classList.remove('is-unassigned');
        cell.insertBefore(avatar, cell.firstChild);
        refresh();
        putTask(row, { owner: name }).catch(function () {
            row.setAttribute('data-owner', '');
            row.classList.add('is-unassigned');
            avatar.remove();
            refresh();
            rowError(row, 'לא נשמר — נסו שוב');
        });
    }

    board.addEventListener('click', function (e) {
        var chip = e.target.closest('.tb-filter');
        if (chip) {
            filter = chip.getAttribute('data-filter');
            board.querySelectorAll('.tb-filter').forEach(function (c) {
                var on = c === chip;
                c.classList.toggle('is-active', on);
                c.setAttribute('aria-pressed', on ? 'true' : 'false');
            });
            refresh();
            return;
        }
        if (e.target.closest('[data-show-more]')) {
            showAllDone = true;
            refresh();
            return;
        }
        var row = e.target.closest('.tb-row');
        if (!row) return;
        if (row.getAttribute('data-swiped')) {
            row.removeAttribute('data-swiped');
            return;
        }
        if (e.target.closest('.tb-check')) {
            setCompleted(row, isOpen(row), true);
        } else if (e.target.closest('[data-claim]')) {
            claim(row, e.target.closest('[data-claim]').getAttribute('data-claim'));
        } else if (e.target.closest('[data-edit]')) {
            editTask(JSON.parse(row.getAttribute('data-task')));
        }
    });

    // Swipe start→end (right to left in RTL) completes an open task.
    board.querySelectorAll('.tb-row').forEach(function (row) {
        var inner = row.querySelector('.tb-row-inner');
        var startX = 0, startY = 0, dx = 0, axis = null, tracking = false;
        inner.addEventListener('touchstart', function (e) {
            if (!isOpen(row) || e.touches.length !== 1) return;
            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
            dx = 0;
            axis = null;
            tracking = true;
            inner.style.transition = 'none';
        }, { passive: true });
        inner.addEventListener('touchmove', function (e) {
            if (!tracking) return;
            var mx = e.touches[0].clientX - startX;
            var my = e.touches[0].clientY - startY;
            if (!axis) {
                if (Math.abs(mx) < 10 && Math.abs(my) < 10) return;
                axis = Math.abs(mx) > Math.abs(my) ? 'x' : 'y';
            }
            if (axis !== 'x') { tracking = false; return; }
            if (e.cancelable) e.preventDefault();
            dx = Math.min(0, mx);
            row.classList.toggle('is-swiping', dx < 0);
            inner.style.transform = 'translateX(' + dx + 'px)';
        }, { passive: false });
        function end() {
            if (!tracking) return;
            tracking = false;
            if (axis !== 'x') return;
            row.setAttribute('data-swiped', '1');
            setTimeout(function () { row.removeAttribute('data-swiped'); }, 350);
            inner.style.transition = 'transform 180ms cubic-bezier(.4,0,.2,1)';
            if (-dx > row.offsetWidth * 0.4) {
                inner.style.transform = 'translateX(-100%)';
                setTimeout(function () { setCompleted(row, true, true); }, 180);
            } else {
                inner.style.transform = '';
                setTimeout(function () { row.classList.remove('is-swiping'); }, 180);
            }
        }
        inner.addEventListener('touchend', end);
        inner.addEventListener('touchcancel', end);
    });

    refresh();
})();
