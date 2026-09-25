/* Spanish between sets — spaced-repetition cards during the rest, and the #spanish study view.
 *
 * The server owns the spacing (services/spanish.py replays the review rows); this file only
 * shows cards, speaks them, listens for an answer and posts the grade. The first cards come
 * with the page (client_data.spanish.queue) so a rest never waits on the network.
 *
 * A rest of 45 s or more opens the cards; after each grade the next card follows at once,
 * whatever the clock says, and the athlete decides when to leave ("אני מוכן"). Once a card
 * has been touched the rest no longer walks to the next set by itself (holdsRest), the timer
 * just keeps counting in the background. Every graded card stays on a trail, so "‹ הקודם"
 * brings a word back to look at (already saved, nothing is recorded twice).
 *
 * The mic on a recall card is a toggle — one tap listens, the next hands the answer over — and
 * listening is bounded by LISTEN (maxMs / settleMs), so the athlete is never stuck in it.
 *
 * Exposes window.Spanish = { onRestStart(seconds), onRestEnd(), holdsRest(), mountStudy(el),
 * toggle(), ... } plus the pure decision helpers (restHasCards, readEnabled, normalise,
 * tokenJaccard, gradeFromSpeech, highlight) so they can be checked without a rest on screen.
 */
(function () {
    'use strict';

    const ENABLED_KEY = 'workout_spanish_v1';
    const PENDING_KEY = 'workout_spanish_pending_v1';
    const API = '/api/workouts/spanish';
    const MIN_REST = 45;            // shorter rests stay quiet
    const STUDY_SIZE = 15;
    const TOP_UP_BELOW = 3;
    const MATCH_GOOD = 0.6;
    const GRADES = [
        { grade: 0, label: 'שוב' },
        { grade: 1, label: 'קשה' },
        { grade: 2, label: 'טוב' },
        { grade: 3, label: 'קל' },
    ];

    // ------------------------------------------------------------ pure helpers

    function restHasCards(seconds, enabled) {
        if (enabled === false) return false;
        return (Number(seconds) || 0) >= MIN_REST;
    }

    function readEnabled(stored) {
        return stored !== 'off';
    }

    function normalise(text) {
        return String(text || '')
            .toLowerCase()
            .normalize('NFD').replace(/[̀-ͯ]/g, '')
            .replace(/[^a-z0-9\s]/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function tokenJaccard(a, b) {
        const x = new Set(normalise(a).split(' ').filter(Boolean));
        const y = new Set(normalise(b).split(' ').filter(Boolean));
        if (!x.size && !y.size) return 0;
        let both = 0;
        x.forEach(t => { if (y.has(t)) both += 1; });
        return both / (x.size + y.size - both);
    }

    function gradeFromSpeech(heard, expected) {
        return tokenJaccard(heard, expected) >= MATCH_GOOD ? 2 : 1;
    }

    function escapeHtml(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function highlight(es, target) {
        const at = target ? es.indexOf(target) : -1;
        if (at < 0) return escapeHtml(es);
        return escapeHtml(es.slice(0, at)) + '<mark>' + escapeHtml(target) + '</mark>' +
            escapeHtml(es.slice(at + target.length));
    }

    // ------------------------------------------------------------ state

    function pageData() {
        const el = document.getElementById('workout-data');
        if (!el) return {};
        try { return (JSON.parse(el.textContent) || {}).spanish || {}; } catch (e) { return {}; }
    }

    const initial = pageData();
    let queue = (initial.queue || []).slice();
    let stats = initial.stats || null;
    const studyNewCap = initial.study_new_cap || 15;
    const done = new Set();         // graded (and not re-queued) during this page load
    let fetching = null;

    function isEnabled() {
        try { return readEnabled(localStorage.getItem(ENABLED_KEY)); } catch (e) { return true; }
    }

    function setEnabled(on) {
        try { localStorage.setItem(ENABLED_KEY, on ? 'on' : 'off'); } catch (e) { /* private mode */ }
        renderToggle();
        if (!on) hideRestSlot();
    }

    function toggle() {
        setEnabled(!isEnabled());
    }

    function renderToggle() {
        const on = isEnabled();
        document.querySelectorAll('[data-spanish-toggle]').forEach(btn => {
            btn.setAttribute('aria-pressed', on ? 'true' : 'false');
            const label = btn.querySelector('[data-spanish-toggle-label]') || btn;
            label.textContent = on ? 'ספרדית: פועל' : 'ספרדית: כבוי';
        });
    }

    function renderStats() {
        if (!stats) return;
        document.querySelectorAll('[data-spanish-stat]').forEach(el => {
            const key = el.dataset.spanishStat;
            if (stats[key] != null) el.textContent = stats[key];
        });
        const themes = stats.per_theme || {};
        document.querySelectorAll('[data-spanish-theme]').forEach(row => {
            const t = themes[row.dataset.spanishTheme];
            if (!t) return;
            const count = row.querySelector('[data-spanish-theme-count]');
            if (count) count.textContent = `${t.in_pocket} / ${t.total}`;
            const bar = row.querySelector('[data-spanish-theme-bar]');
            if (bar) bar.style.width = `${t.total ? Math.round(100 * t.in_pocket / t.total) : 0}%`;
        });
    }

    function requeue(card, mode, after) {
        const copy = Object.assign({}, card, { mode });
        queue.splice(Math.min(after, queue.length), 0, copy);
    }

    function afterGrade(card, grade, mode) {
        const i = queue.indexOf(card);
        if (i >= 0) queue.splice(i, 1);
        if (mode === 'intro') requeue(card, 'recall', 2);        // met now, recalled later this session
        else if (grade === 0) requeue(card, 'recall', 3);        // lapsed: due again now
        else done.add(card.id);
        topUp();
    }

    function merge(items) {
        const have = new Set(queue.map(c => c.id));
        (items || []).forEach(c => {
            if (!have.has(c.id) && !done.has(c.id)) { queue.push(c); have.add(c.id); }
        });
    }

    function fetchQueue(newCap) {
        const params = new URLSearchParams({ limit: String(STUDY_SIZE) });
        if (newCap) params.set('new_cap', String(newCap));
        return fetch(`${API}/queue?${params}`, { credentials: 'same-origin' })
            .then(r => (r.ok ? r.json() : null))
            .then(body => {
                if (!body) return;
                merge(body.items);
                if (body.stats) { stats = body.stats; renderStats(); }
            })
            .catch(() => { /* offline: keep what we have */ });
    }

    function topUp() {
        if (queue.length >= TOP_UP_BELOW || fetching) return fetching || Promise.resolve();
        fetching = fetchQueue().finally(() => { fetching = null; });
        return fetching;
    }

    // ------------------------------------------------------------ posting (keepalive + pending)

    function readPending() {
        try { return JSON.parse(localStorage.getItem(PENDING_KEY)) || []; } catch (e) { return []; }
    }

    function writePending(list) {
        try {
            if (list.length) localStorage.setItem(PENDING_KEY, JSON.stringify(list));
            else localStorage.removeItem(PENDING_KEY);
        } catch (e) { /* storage unavailable */ }
    }

    function send(body) {
        return fetch(`${API}/reviews`, {
            method: 'POST',
            credentials: 'same-origin',
            keepalive: true,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then(r => {
            if (r.status === 201) return r.json();
            if (r.status >= 400 && r.status < 500) return null;   // rejected for good: drop it
            throw new Error(`HTTP ${r.status}`);
        });
    }

    function record(body) {
        return send(body)
            .then(res => {
                if (res && res.stats) { stats = res.stats; renderStats(); }
                return res;
            })
            .catch(() => {
                const pending = readPending();
                pending.push(body);
                writePending(pending);
                return null;
            });
    }

    function flushPending() {
        const pending = readPending();
        if (!pending.length) return;
        writePending([]);
        pending.reduce((chain, body) => chain.then(() => send(body)
            .then(res => { if (res && res.stats) { stats = res.stats; renderStats(); } })
            .catch(() => { const left = readPending(); left.push(body); writePending(left); })),
        Promise.resolve());
    }

    // ------------------------------------------------------------ speech

    let voice = null;

    function pickVoice() {
        if (!('speechSynthesis' in window)) return null;
        const voices = window.speechSynthesis.getVoices() || [];
        const es = voices.filter(v => (v.lang || '').toLowerCase().replace('_', '-').startsWith('es'));
        const byLang = lang => es.find(v => v.lang.replace('_', '-').toLowerCase() === lang);
        return byLang('es-es') || byLang('es-mx') || es[0] || null;
    }

    function refreshVoice() {
        voice = pickVoice();
        document.documentElement.classList.toggle('sp-has-voice', !!voice);
    }

    function speak(text, slow) {
        if (!voice || !text) return;
        try {
            window.speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance(text);
            u.voice = voice;
            u.lang = voice.lang;
            u.rate = slow ? 0.7 : 1;
            window.speechSynthesis.speak(u);
        } catch (e) { /* speech unavailable */ }
    }

    function stopSpeaking() {
        try { if ('speechSynthesis' in window) window.speechSynthesis.cancel(); } catch (e) { /* ignore */ }
    }

    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition || null;

    /* One answer is a few words, so listening is bounded: after `maxMs` the recogniser is
       told to stop, and if it has not ended `settleMs` later whatever was heard is used.
       iOS Safari does not end a recognition by itself when the speaker goes quiet, delivers
       its words only once stopped, and sometimes never fires `onend` — without the clock the
       mic would pulse forever and the answer would never be graded. */
    const LISTEN = { maxMs: 8000, settleMs: 1500 };
    let listening = null;   // { rec, transcript, done, stopping, timers, finish }

    /* Listens for one answer; calls onDone(transcript, error) exactly once — '' when nothing was
       heard or the listening was cancelled, `error` the recogniser's error name if it gave one.
       Returns false when it could not start. */
    function listen(onDone) {
        if (!Recognition) return false;
        stopListening();
        const session = { rec: null, transcript: '', error: '', done: false, stopping: false, timers: [] };
        function finish(deliver) {
            if (session.done) return;
            session.done = true;
            session.timers.forEach(clearTimeout);
            if (listening === session) listening = null;
            try { session.rec.abort(); } catch (e) { /* already ended */ }
            onDone(deliver ? session.transcript : '', session.error);
        }
        session.finish = finish;
        let rec;
        try {
            rec = new Recognition();
            rec.lang = 'es-ES';
            rec.continuous = false;
            rec.interimResults = true;     // iOS may hand over only interim results before it is stopped
            rec.maxAlternatives = 1;
        } catch (e) { onDone(''); return false; }
        session.rec = rec;
        rec.onresult = (event) => {
            const results = event.results || [];
            let text = '';
            let final = false;
            for (let i = 0; i < results.length; i++) {
                const alt = results[i] && results[i][0];
                if (alt && alt.transcript) text += (text ? ' ' : '') + alt.transcript;
                if (results[i] && results[i].isFinal) final = true;
            }
            if (text.trim()) session.transcript = text.trim();
            if (final) finish(true);       // the answer is in: no need to wait for an onend that may never come
        };
        rec.onerror = (event) => {         // no permission / nothing heard: '' leaves the grades alone
            session.error = (event && event.error) || 'error';
            finish(true);
        };
        rec.onend = () => finish(true);
        session.timers.push(setTimeout(() => stopListening(true), LISTEN.maxMs));
        listening = session;
        try { rec.start(); } catch (e) { finish(false); return false; }
        return true;
    }

    /* deliver=true: the athlete is done talking — stop() lets the last words through, and the
       answer is handed over when the recogniser ends (or after settleMs, whichever comes first).
       Otherwise the listening is dropped and nothing is delivered. */
    function stopListening(deliver) {
        const session = listening;
        if (!session) return;
        if (!deliver) { session.finish(false); return; }
        if (session.stopping) return;
        session.stopping = true;
        try { session.rec.stop(); } catch (e) { session.finish(true); return; }
        session.timers.push(setTimeout(() => session.finish(true), LISTEN.settleMs));
    }

    function isListening() {
        return !!(listening && !listening.stopping);
    }

    // ------------------------------------------------------------ the card component

    function audioButtons() {
        return '<button type="button" class="sp-audio" data-sp-say aria-label="השמע">🔊</button>' +
            '<button type="button" class="sp-audio is-slow" data-sp-slow aria-label="השמע לאט">לאט</button>';
    }

    function metaLine(card) {
        const note = card.note ? `<span class="sp-note">${escapeHtml(card.note)}</span>` : '';
        return `<div class="sp-meta"><span class="sp-theme">${escapeHtml(card.theme_title)}</span>${note}</div>`;
    }

    function spanishLine(card) {
        return `<p class="sp-es" dir="ltr" lang="es">${highlight(card.es, card.target_es)}</p>`;
    }

    /* "‹ הקודם" / "הבא ›" under a card: back along the trail of graded cards, forward to the live one. */
    function navRow(nav) {
        if (!nav || (!nav.back && !nav.forward)) return '';
        const back = nav.back
            ? '<button type="button" class="sp-nav-btn" data-sp-back>‹ הקודם</button>' : '<span></span>';
        const forward = nav.forward
            ? '<button type="button" class="sp-nav-btn" data-sp-forward>הבא ›</button>' : '<span></span>';
        return `<div class="sp-nav">${back}${forward}</div>`;
    }

    function wireNav(el, nav) {
        const back = el.querySelector('[data-sp-back]');
        const forward = el.querySelector('[data-sp-forward]');
        if (back && nav && nav.back) back.addEventListener('click', () => { stopListening(); nav.back(); });
        if (forward && nav && nav.forward) forward.addEventListener('click', () => { stopListening(); nav.forward(); });
    }

    function newCardEl(host, card, mode) {
        host.innerHTML = '';
        const el = document.createElement('div');
        el.className = 'sp-card';
        el.dataset.mode = mode;
        el.dataset.itemId = card.id;
        host.appendChild(el);
        return el;
    }

    /* A card that was already graded, brought back to look at: everything shown, nothing recorded. */
    function mountPastCard(host, card, nav) {
        stopListening();
        const el = newCardEl(host, card, 'past');
        el.dataset.stage = 'revealed';
        el.innerHTML = `<p class="sp-he">${escapeHtml(card.he)}</p>` + spanishLine(card) + metaLine(card) +
            `<div class="sp-actions is-past">${audioButtons()}<span class="sp-saved">✓ נשמר</span></div>` +
            navRow(nav);
        const say = el.querySelector('[data-sp-say]');
        const slow = el.querySelector('[data-sp-slow]');
        if (say) say.addEventListener('click', () => speak(card.es, false));
        if (slow) slow.addEventListener('click', () => speak(card.es, true));
        wireNav(el, nav);
        speak(card.es, false);
        return el;
    }

    /* Renders `card` into `host`; calls onGraded(grade, mode) once the learner answers.
       `nav.back` (optional) opens the previously graded card. */
    function mountCard(host, card, context, onGraded, nav) {
        stopListening();
        const mode = card.mode === 'recall' ? 'recall' : 'intro';
        const el = newCardEl(host, card, mode);

        let answered = false;
        function grade(value) {
            if (answered) return;
            answered = true;
            stopListening();
            record({ item_id: card.id, grade: value, mode, context });
            afterGrade(card, value, mode);
            onGraded(value, mode);
        }

        function wireAudio() {
            const say = el.querySelector('[data-sp-say]');
            const slow = el.querySelector('[data-sp-slow]');
            if (say) say.addEventListener('click', () => speak(card.es, false));
            if (slow) slow.addEventListener('click', () => speak(card.es, true));
        }

        if (mode === 'intro') {
            el.dataset.stage = 'revealed';
            el.innerHTML = spanishLine(card) +
                `<p class="sp-he">${escapeHtml(card.he)}</p>` + metaLine(card) +
                `<div class="sp-actions">${audioButtons()}` +
                '<button type="button" class="sp-primary" data-sp-got>הבנתי</button></div>' + navRow(nav);
            wireAudio();
            wireNav(el, nav);
            el.querySelector('[data-sp-got]').addEventListener('click', () => grade(2));
            speak(card.es, false);
            return el;
        }

        el.dataset.stage = 'prompt';
        const mic = Recognition
            ? '<button type="button" class="sp-mic" data-sp-mic aria-label="דבר — המיקרופון מקשיב">🎤</button>' : '';
        el.innerHTML = `<p class="sp-he is-prompt">${escapeHtml(card.he)}</p>` +
            '<p class="sp-hint">תגיד את זה בספרדית</p>' +
            `<div class="sp-actions">${mic}<button type="button" class="sp-primary" data-sp-reveal>הצג</button></div>` +
            navRow(nav);
        wireNav(el, nav);

        let suggested = null;
        let heard = '';

        function reveal() {
            if (el.dataset.stage === 'revealed') return;
            stopListening();
            el.dataset.stage = 'revealed';
            const heardLine = heard ? `<p class="sp-heard" dir="ltr" lang="es">${escapeHtml(heard)}</p>` : '';
            el.innerHTML = `<p class="sp-he">${escapeHtml(card.he)}</p>` + spanishLine(card) + metaLine(card) +
                heardLine +
                `<div class="sp-actions is-audio">${audioButtons()}</div>` +
                '<div class="sp-grades" role="group" aria-label="כמה זה היה קל?">' +
                GRADES.map(g => `<button type="button" class="sp-grade${g.grade === suggested ? ' is-suggested' : ''}"` +
                    ` data-sp-grade="${g.grade}">${g.label}</button>`).join('') +
                '</div>' + navRow(nav);
            wireAudio();
            wireNav(el, nav);
            el.querySelectorAll('[data-sp-grade]').forEach(btn => {
                btn.addEventListener('click', () => grade(Number(btn.dataset.spGrade)));
            });
            speak(card.es, false);
        }

        el.querySelector('[data-sp-reveal]').addEventListener('click', reveal);
        const micBtn = el.querySelector('[data-sp-mic]');
        const hint = el.querySelector('.sp-hint');
        if (micBtn) {
            const setHint = text => { if (hint) hint.textContent = text; };
            function micIdle() {
                micBtn.classList.remove('is-listening');
                micBtn.textContent = '🎤';
                micBtn.setAttribute('aria-label', 'דבר — המיקרופון מקשיב');
            }
            // One tap listens, the next tap ends it: the mic is never a state the athlete
            // cannot leave (and it ends by itself after a few seconds either way).
            micBtn.addEventListener('click', () => {
                if (isListening()) { stopListening(true); return; }
                if (listening) return;                       // still handing over the last answer
                micBtn.classList.add('is-listening');
                micBtn.textContent = '⏹ סיימתי';
                micBtn.setAttribute('aria-label', 'מקשיב — הקש לסיום');
                setHint('מקשיב… הקש שוב כשסיימת');
                const started = listen((text, error) => {
                    micIdle();
                    if (el.dataset.stage === 'revealed') return;
                    if (!text) {
                        const denied = error === 'not-allowed' || error === 'service-not-allowed';
                        setHint(denied ? 'אין הרשאה למיקרופון — הצג' : 'לא שמעתי — נסה שוב, או הצג');
                        return;
                    }
                    heard = text;
                    suggested = gradeFromSpeech(text, card.es);
                    reveal();
                });
                if (!started) { micIdle(); setHint('המיקרופון לא זמין — הצג'); }
            });
        }
        return el;
    }

    // ------------------------------------------------------------ the trail (back / forward)

    /* A run of cards in one host (a rest, or a study session): the graded ones stay on the
       trail so the athlete can step back to a word; forward returns to the live card. */
    function makeTrail(host, live, onGraded) {
        const trail = { host, past: [], live, onGraded };
        trail.showLive = function () {
            const card = queue[0];
            const back = trail.past.length ? () => trail.showPast(trail.past.length - 1) : null;
            if (!card) { trail.live(null, back); return; }
            trail.live(card, back);
        };
        trail.showPast = function (i) {
            const nav = {
                back: i > 0 ? () => trail.showPast(i - 1) : null,
                forward: () => (i + 1 < trail.past.length ? trail.showPast(i + 1) : trail.showLive()),
            };
            mountPastCard(host, trail.past[i], nav);
        };
        trail.mount = function (card, back, context) {
            mountCard(host, card, context, (grade, mode) => {
                trail.past.push(card);
                trail.onGraded(grade, mode);
            }, { back });
        };
        return trail;
    }

    // ------------------------------------------------------------ in the arena (rest panel)

    let rest = null;   // { endsAt, engaged, trail }

    function restSlot() {
        return document.getElementById('rest-spanish');
    }

    function hideRestSlot() {
        const slot = restSlot();
        if (!slot) return;
        slot.hidden = true;
        const host = slot.querySelector('[data-spanish-card]');
        if (host) host.innerHTML = '';
        const panel = slot.closest('.arena-rest');
        if (panel) panel.classList.remove('has-spanish');
    }

    function openRestSlot() {
        const slot = restSlot();
        const host = slot && slot.querySelector('[data-spanish-card]');
        if (!host) return null;
        slot.hidden = false;
        const panel = slot.closest('.arena-rest');
        if (panel) panel.classList.add('has-spanish');
        if (!host.dataset.spanishWired) {
            host.dataset.spanishWired = '1';
            // Any tap on a card means the athlete is studying: the rest is theirs to end.
            host.addEventListener('click', () => { if (rest) rest.engaged = true; });
        }
        return host;
    }

    function showRestLive(card, back) {
        const host = openRestSlot();
        if (!host || !rest) return;
        if (!card) {
            host.innerHTML = '<p class="sp-done">✓ הכל נשמר · אין עוד כרטיסים כרגע</p>' +
                navRow({ back });
            wireNav(host, { back });
            topUp().then(() => { if (rest && queue.length && host.querySelector('.sp-done')) rest.trail.showLive(); });
            return;
        }
        rest.trail.mount(card, back, 'rest');
    }

    function onRestStart(seconds) {
        const endsAt = Date.now() + (Number(seconds) || 0) * 1000;
        if (rest) {            // the same rest restarted (+10s after the end): keep the card on screen
            rest.endsAt = endsAt;
            return;
        }
        if (!restHasCards(seconds, isEnabled())) { hideRestSlot(); return; }
        rest = { endsAt, engaged: false, trail: null };
        const host = openRestSlot();
        if (!host) { rest = null; return; }
        // After every grade the next card follows at once — the clock does not decide.
        rest.trail = makeTrail(host, showRestLive, () => { if (rest) rest.trail.showLive(); });
        rest.trail.showLive();
    }

    /* True while the athlete is studying in this rest: the arena then waits for "אני מוכן"
       instead of walking to the next set by itself when the timer ends. */
    function holdsRest() {
        return !!(rest && rest.engaged);
    }

    function onRestEnd() {
        // An ungraded card records nothing: it stays at the head of the queue for the next rest.
        rest = null;
        stopListening();
        stopSpeaking();
        hideRestSlot();
    }

    // ------------------------------------------------------------ the #spanish view

    let study = null;

    function renderDots(root) {
        const dots = root.querySelector('[data-spanish-dots]');
        if (!dots || !study) return;
        dots.innerHTML = Array.from({ length: study.size }, (_, i) =>
            `<span class="${i < study.graded ? 'is-done' : (i === study.graded ? 'is-current' : '')}"></span>`).join('');
        dots.hidden = !study.size;
    }

    function showSummary(root, back) {
        const host = root.querySelector('[data-spanish-card]');
        if (host) {
            host.innerHTML = navRow({ back });
            wireNav(host, { back });
        }
        const summary = root.querySelector('[data-spanish-summary]');
        const empty = root.querySelector('[data-spanish-empty]');
        const didSomething = study && study.graded > 0;
        if (summary) {
            summary.hidden = !didSomething;
            if (didSomething) {
                summary.innerHTML = `<span class="wk-num" dir="ltr">${study.recalls}</span> חזרות · ` +
                    `<span class="wk-num" dir="ltr">${study.intros}</span> מילים חדשות`;
            }
        }
        if (empty) empty.hidden = didSomething;
        const dots = root.querySelector('[data-spanish-dots]');
        if (dots && !didSomething) dots.hidden = true;
    }

    function nextStudyCard(root) {
        if (!study) return;
        study.trail.showLive();
    }

    function showStudyLive(root, card, back) {
        const host = root.querySelector('[data-spanish-card]');
        if (!host || !study) return;
        if (!card || study.graded >= study.size) { showSummary(root, back); return; }
        renderDots(root);
        study.trail.mount(card, back, 'study');
    }

    function startStudy(root) {
        const summary = root.querySelector('[data-spanish-summary]');
        const empty = root.querySelector('[data-spanish-empty]');
        if (summary) summary.hidden = true;
        if (empty) empty.hidden = true;
        const host = root.querySelector('[data-spanish-card]');
        if (!host) return;
        study = { size: Math.min(STUDY_SIZE, queue.length), graded: 0, intros: 0, recalls: 0, trail: null };
        study.trail = makeTrail(host, (card, back) => showStudyLive(root, card, back), (grade, mode) => {
            if (mode === 'intro') {
                study.intros += 1;
                // its recall comes back later in this same session
                if (study.size < STUDY_SIZE) study.size += 1;
            } else {
                study.recalls += 1;
            }
            study.graded += 1;
            renderDots(root);
            nextStudyCard(root);
        });
        if (!study.size) { showSummary(root); return; }
        nextStudyCard(root);
    }

    function mountStudy(root) {
        if (!root) return;
        renderStats();
        if (!root.dataset.spanishWired) {
            root.dataset.spanishWired = '1';
            const more = root.querySelector('[data-spanish-more]');
            if (more) {
                more.addEventListener('click', () => {
                    more.disabled = true;
                    fetchQueue(studyNewCap).then(() => { more.disabled = false; startStudy(root); });
                });
            }
        }
        // Mid-session (coming back to the view): keep the card that is on screen.
        if (study && study.graded < study.size && root.querySelector('.sp-card')) return;
        startStudy(root);
        // Refresh from the server (rests on this page may have moved things); a longer queue
        // lengthens the session up to STUDY_SIZE, an empty one turns into the empty state.
        fetchQueue().then(() => {
            if (!study) return;
            if (!study.size && queue.length) { startStudy(root); return; }
            study.size = Math.max(study.size, Math.min(STUDY_SIZE, study.graded + queue.length));
            renderDots(root);
        });
    }

    // ------------------------------------------------------------ boot

    if ('speechSynthesis' in window) {
        refreshVoice();
        try { window.speechSynthesis.addEventListener('voiceschanged', refreshVoice); } catch (e) {
            window.speechSynthesis.onvoiceschanged = refreshVoice;
        }
    }

    function boot() {
        renderToggle();
        renderStats();
        flushPending();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();

    window.Spanish = {
        onRestStart,
        onRestEnd,
        holdsRest,
        mountStudy,
        toggle,
        isEnabled,
        setEnabled,
        queue: () => queue.slice(),
        stats: () => stats,
        // pure decision helpers
        restHasCards,
        readEnabled,
        normalise,
        tokenJaccard,
        gradeFromSpeech,
        highlight,
        MIN_REST,
        LISTEN,
        isListening,
    };
})();
