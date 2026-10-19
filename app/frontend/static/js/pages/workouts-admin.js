(function () {
    const DATA = JSON.parse(document.getElementById('workout-admin-data').textContent);
    const SESSIONS = {};
    DATA.sessions.forEach(s => { SESSIONS[s.id] = s; });
    // Every picker value the editor knows, so a saved name that isn't one falls back to "other"
    const KNOWN = new Set();
    DATA.exercise_options.forEach(g => g.options.forEach(o => KNOWN.add(o.value)));

    let editingId = null;

    // ---- search ----
    const search = document.getElementById('admin-search');
    const noResults = document.getElementById('admin-no-results');
    search.addEventListener('input', function () {
        const q = search.value.trim().toLowerCase();
        let shown = 0;
        document.querySelectorAll('[data-session]').forEach(card => {
            const hit = !q || card.dataset.search.indexOf(q) !== -1;
            card.classList.toggle('hidden', !hit);
            if (hit) shown++;
        });
        noResults.classList.toggle('hidden', shown > 0 || !q);
    });

    // ---- editor ----
    function exerciseSelect(selected) {
        const select = document.createElement('select');
        select.dataset.exSelect = '';
        select.className = 'flex-1 min-w-0 px-3 py-2 rounded-xl border border-gray-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300';
        DATA.exercise_options.forEach(group => {
            const optgroup = document.createElement('optgroup');
            optgroup.label = group.group;
            group.options.forEach(option => {
                const el = document.createElement('option');
                el.value = option.value;
                el.textContent = option.label;
                if (option.skill_key) {
                    el.dataset.skillKey = option.skill_key;
                    el.dataset.stageIndex = option.stage_index;
                }
                optgroup.appendChild(el);
            });
            select.appendChild(optgroup);
        });
        const other = document.createElement('option');
        other.value = '__other__';
        other.textContent = 'אחר (שם חופשי)';
        select.appendChild(other);
        select.value = selected && KNOWN.has(selected) ? selected : '__other__';
        return select;
    }

    function numberField(label, key, value, max) {
        const wrap = document.createElement('label');
        wrap.className = 'block';
        const caption = document.createElement('span');
        caption.className = 'block text-[11px] text-gray-500 mb-1';
        caption.textContent = label;
        const input = document.createElement('input');
        input.type = 'number';
        input.min = '0';
        input.max = String(max);
        input.inputMode = 'numeric';
        input.dir = 'ltr';
        input.dataset[key] = '';
        input.value = value === null || value === undefined ? '' : value;
        input.className = 'w-full px-2.5 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300';
        wrap.appendChild(caption);
        wrap.appendChild(input);
        return wrap;
    }

    window.addExerciseRow = function (exercise) {
        const ex = exercise || {};
        const row = document.createElement('div');
        row.className = 'rounded-xl border border-gray-200 p-3 space-y-2';
        row.dataset.row = '';
        if (ex.id) row.dataset.id = ex.id;

        const top = document.createElement('div');
        top.className = 'flex gap-2';
        const select = exerciseSelect(ex.exercise_name);
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'px-2.5 rounded-xl text-gray-400 hover:bg-red-50 hover:text-red-500 transition-colors';
        remove.setAttribute('aria-label', 'הסרת התרגיל');
        remove.textContent = '✕';
        remove.addEventListener('click', () => row.remove());
        top.appendChild(select);
        top.appendChild(remove);

        const custom = document.createElement('input');
        custom.type = 'text';
        custom.dataset.exCustom = '';
        custom.placeholder = 'שם התרגיל';
        custom.className = 'w-full px-3 py-2 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300';
        if (select.value === '__other__') {
            custom.value = ex.exercise_name || '';
        } else {
            custom.classList.add('hidden');
        }
        select.addEventListener('change', function () {
            custom.classList.toggle('hidden', select.value !== '__other__');
            if (select.value === '__other__') custom.focus();
        });

        const numbers = document.createElement('div');
        numbers.className = 'grid grid-cols-3 gap-2';
        numbers.appendChild(numberField('סטים', 'exSets', ex.total_sets, 100));
        numbers.appendChild(numberField('חזרות (סה״כ)', 'exReps', ex.total_reps, 5000));
        numbers.appendChild(numberField('שיא בסט', 'exMax', ex.max_reps, 5000));

        row.appendChild(top);
        row.appendChild(custom);
        row.appendChild(numbers);
        document.getElementById('session-exercises').appendChild(row);
        return row;
    };

    window.openSessionEditor = function (sessionId) {
        const session = sessionId ? SESSIONS[sessionId] : null;
        editingId = session ? session.id : null;
        document.getElementById('session-modal-title').textContent = session ? 'עריכת אימון' : 'אימון חדש';
        document.getElementById('session-date').value = session ? session.date : new Date().toISOString().slice(0, 10);
        document.getElementById('session-duration').value = session ? session.total_duration : 30;
        document.getElementById('session-user').value = String(session ? session.user_id : DATA.user_id);

        const type = document.getElementById('session-type');
        type.value = session ? session.workout_type : 'Calisthenics';
        if (!type.value) type.selectedIndex = 0;

        const list = document.getElementById('session-exercises');
        list.innerHTML = '';
        if (session) {
            session.exercises.forEach(ex => addExerciseRow(ex));
        } else {
            addExerciseRow();
        }
        showError('');
        const modal = document.getElementById('session-modal');
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    };

    window.closeSessionEditor = function () {
        const modal = document.getElementById('session-modal');
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    };

    function showError(message) {
        const box = document.getElementById('session-error');
        box.textContent = message;
        box.classList.toggle('hidden', !message);
    }

    function readRows() {
        const rows = [];
        document.querySelectorAll('#session-exercises [data-row]').forEach(row => {
            const select = row.querySelector('[data-ex-select]');
            const option = select.options[select.selectedIndex];
            const custom = row.querySelector('[data-ex-custom]').value.trim();
            const name = select.value === '__other__' ? custom : select.value;
            if (!name) return;
            const max = row.querySelector('[data-ex-max]').value;
            rows.push({
                id: row.dataset.id ? Number(row.dataset.id) : null,
                exercise_name: name,
                total_sets: Number(row.querySelector('[data-ex-sets]').value || 0),
                total_reps: Number(row.querySelector('[data-ex-reps]').value || 0),
                max_reps: max === '' ? null : Number(max),
                skill_key: option && option.dataset.skillKey ? option.dataset.skillKey : null,
                stage_index: option && option.dataset.skillKey ? Number(option.dataset.stageIndex) : null,
            });
        });
        return rows;
    }

    window.saveSession = function () {
        const date = document.getElementById('session-date').value;
        if (!date) { showError('צריך לבחור תאריך.'); return; }
        const exercises = readRows();
        if (!exercises.length) { showError('צריך לפחות תרגיל אחד עם שם.'); return; }

        const body = {
            user_id: Number(document.getElementById('session-user').value),
            date: date,
            workout_type: document.getElementById('session-type').value,
            total_duration: Number(document.getElementById('session-duration').value || 0),
            exercises: exercises,
        };
        const button = document.getElementById('session-save');
        button.disabled = true;
        fetch(editingId ? `/api/workouts/sessions/${editingId}` : '/api/workouts/sessions', {
            method: editingId ? 'PUT' : 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then(res => {
            if (!res.ok) return res.json().then(e => {
                // FastAPI sends a string for our own errors and a list for schema validation
                throw new Error(typeof e.detail === 'string' ? e.detail : 'נתונים לא תקינים');
            });
            location.href = `/workouts/admin?user=${body.user_id}`;
        }).catch(err => {
            button.disabled = false;
            showError('השמירה נכשלה: ' + err.message);
        });
    };

    window.deleteSession = function (sessionId, dateLabel) {
        if (!confirm(`למחוק את האימון מ-${dateLabel}? כל התרגילים שנשמרו בו יימחקו.`)) return;
        fetch(`/api/workouts/sessions/${sessionId}`, { method: 'DELETE', credentials: 'same-origin' })
            .then(res => { if (!res.ok) throw new Error(res.status); location.reload(); })
            .catch(() => alert('המחיקה נכשלה.'));
    };

    window.resetBefore = function () {
        const before = document.getElementById('reset-before').value;
        if (!before) { alert('צריך לבחור תאריך.'); return; }
        const doomed = DATA.sessions.filter(s => s.date < before).length;
        if (!doomed) { alert('אין אימונים לפני ' + before + '.'); return; }
        if (!confirm(`למחוק ${doomed} אימונים שלפני ${before}? האימונים מ-${before} והלאה נשארים.`)) return;
        const query = new URLSearchParams({ user_id: DATA.user_id, before: before });
        fetch(`/api/workouts/sessions?${query}`, { method: 'DELETE', credentials: 'same-origin' })
            .then(res => { if (!res.ok) throw new Error(res.status); location.reload(); })
            .catch(() => alert('המחיקה נכשלה.'));
    };

    // ---- imported "conquered by hand" stations ----
    function saveLegacy(chips) {
        const progress = {};
        chips.forEach(chip => {
            const key = chip.dataset.skill;
            (progress[key] = progress[key] || []).push(Number(chip.dataset.stage));
        });
        return fetch('/api/workouts/legacy-progress', {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: DATA.user_id, progress: progress }),
        }).then(res => {
            if (!res.ok) throw new Error(res.status);
            location.reload();
        }).catch(() => alert('העדכון נכשל.'));
    }

    window.dropLegacyStation = function (button) {
        const chip = button.closest('[data-legacy]');
        const rest = Array.from(document.querySelectorAll('[data-legacy]')).filter(c => c !== chip);
        saveLegacy(rest);
    };

    window.clearLegacyStations = function () {
        if (!confirm('לנקות את כל התחנות שיובאו ידנית?')) return;
        saveLegacy([]);
    };
})();
