// app/frontend/static/js/workout.js
// Workouts page: quest select / map / profile / history views, and the arena —
// a full-screen workout that shows one set at a time (set → rest → reward).

// --- Global Workout State ---
let workoutStartTime = Date.now();
let workoutTimerInterval = null;
let activeExercises = [];
let sessionActive = false;

// --- Arena State ---
let arenaPhase = 'set';      // 'warmup' | 'ready' | 'set' | 'rest' | 'reward'
let warmupDone = [];         // indexes of warm-up items ticked off
let holdStartedAt = null;    // Date.now() when the current hold began (null = not holding)
let holdInterval = null;
let holdLastBeep = null;
let cursor = null;           // { exerciseId, setId } of the set on screen
let plannedSets = 0;         // sets the session set out to do (star ②)
let sessionPath = null;      // quest path key the session started from
let prShown = {};            // exercise name -> true once its record toast fired
let lastRestEnd = null;      // planned end of the last rest (combo grace)
let restTip = '';

// --- Global Rest Timer State ---
// Absolute-timestamp based so the countdown stays correct even when the
// mobile browser throttles timers in the background / with the screen off.
let restTimerInterval = null;
let restAutoAdvance = null;
let restEndsAt = null;
let restDuration = 0;
let isTimerFinished = false;
let restLastTick = null; // last second (3, 2, 1) already ticked aloud

// --- Gamification State ---
// Mirrors the server XP formula for the live counter only: every completed set is
// worth 10 XP + 1 XP per rep. The reward screen shows the server's number.
const XP_PER_SET = 10;
const COMBO_REST_GRACE_MS = 90 * 1000; // resting longer than this past the plan breaks the combo
const REST_AUTO_ADVANCE_MS = 6000;
const PR_TOAST_MS = 2500;
const DEFAULT_NEW_EXERCISE = { sets: 3, reps: 8, rest: 90 };
let comboCount = 0; // consecutive completed sets

// --- Persistence keys (namespaced; nothing else is touched) ---
const WORKOUT_SESSION_KEY = 'workout_active_session_v2';
const ACTIVE_PATH_KEY = 'workout_active_path_v1';
const SKILL_PROGRESS_KEY = 'workout_skill_progress_v1'; // legacy "כבשתי!" flags, imported once

// --- Screen Wake Lock (keep the phone awake mid-workout) ---
let wakeLock = null;

const reducedMotion = window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : { matches: false };

const CATEGORY_ICONS = { push: '💪', pull: '🧗', core: '🌀', legs: '🦵', general: '🏋️' };

// Calm, one-breath coach lines, rotated per rest.
const COACH_TIPS = {
    push: [
        'נשום דרך האף, כתפיים רחוק מהאוזניים. אם הסט האחרון הרגיש קל — תוסיף חזרה, לא מהירות.',
        'מרפקים בזווית של 45 מעלות מהגוף. ירידה איטית שווה יותר מעוד חזרה חפוזה.',
        'נעל בטן וישבן — הגוף זז כיחידה אחת, מהראש ועד העקבים.',
    ],
    pull: [
        'התחל כל חזרה מהשכמות: למטה ואחורה, ורק אז הידיים.',
        'תלייה מלאה בתחתית, חזה אל המוט למעלה. טווח מלא לפני עוד חזרות.',
        'שחרר את האחיזה בין הסטים ונער את הידיים — האמות צריכות את המנוחה הזו.',
    ],
    core: [
        'צלעות למטה, אגן מגולגל קלות. אם הגב התחתון מתקשת — קצר את הסט.',
        'נשימה קצרה ושקטה בזמן ההחזקה. איכות השניות חשובה יותר מהמספר.',
        'לחץ חזק את הרצפה או את המוט — המתח בידיים מייצב את כל הליבה.',
    ],
    legs: [
        'ברכיים בכיוון האצבעות, משקל על כל כף הרגל. ירידה בשליטה, עלייה בכוח.',
        'אם האיזון בורח — אחוז במשהו. עדיף טווח מלא עם עזרה מחצי טווח בלי.',
    ],
    general: [
        'כמה לגימות מים ונשימה עמוקה. הסט הבא מתחיל כשהנשימה חוזרת לקצב.',
        'תנועה נקייה לפני עוד חזרות. כשהטכניקה נשברת — זה הסוף הטבעי של הסט.',
    ],
};

// ====================== UTILITIES ======================

function uid(prefix) {
    return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function clampInt(value, min, max) {
    const parsed = parseInt(value, 10);
    if (isNaN(parsed)) return min;
    return Math.min(max, Math.max(min, parsed));
}

function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
}

// Numbers render mono + LTR inside the RTL layout.
function numHtml(value) {
    return `<span class="wk-num" dir="ltr">${escapeHtml(value)}</span>`;
}

// Hebrew count phrase: 'סט אחד' / '5 סטים'
function countHtml(n, one, many) {
    return n === 1 ? one : `${numHtml(formatNumber(n))} ${many}`;
}

function formatNumber(n) {
    return Number(n || 0).toLocaleString('en-US');
}

function $(selector, root) {
    return (root || document).querySelector(selector);
}

function $all(selector, root) {
    return Array.from((root || document).querySelectorAll(selector));
}

function vibrate(pattern) {
    if (reducedMotion.matches || !navigator.vibrate) return;
    navigator.vibrate(pattern);
}

// ====================== SOUND CUES ======================
// iOS Safari has no Vibration API, so every haptic moment has an audible twin: short
// oscillator notes from a Web Audio context that the first tap in the arena unlocks.
const SOUND_KEY = 'workout_sound_v1';
let soundOn = readSoundPref();
let audioCtx = null;

function readSoundPref() {
    try { return localStorage.getItem(SOUND_KEY) !== 'off'; } catch (e) { return true; }
}

function setSoundOn(on) {
    soundOn = !!on;
    try { localStorage.setItem(SOUND_KEY, soundOn ? 'on' : 'off'); } catch (e) { /* private mode */ }
    renderSoundToggle();
}

function toggleSound() {
    setSoundOn(!soundOn);
    if (soundOn) {
        unlockAudio();
        beep('set'); // hear what you just turned on
    }
}

function renderSoundToggle() {
    const btn = $('#arena-sound-btn');
    if (!btn) return;
    btn.setAttribute('aria-pressed', soundOn ? 'true' : 'false');
    btn.setAttribute('aria-label', soundOn ? 'צלילים פועלים — השתק' : 'צלילים מושתקים — הפעל');
    const icon = btn.querySelector('[data-sound-icon]');
    if (icon) icon.textContent = soundOn ? '🔔' : '🔕';
}

// Must be reached from a user gesture (tap / click) — browsers keep a context silent otherwise.
function unlockAudio() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    if (!audioCtx) {
        try { audioCtx = new Ctx(); } catch (e) { return null; }
    }
    if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
    return audioCtx;
}

// Per note: [frequency Hz, start offset s, length s]
const SOUND_PATTERNS = {
    tick: [[880, 0, .06]],                                                   // 3-2-1 countdown
    start: [[660, 0, .08]],                                                  // a hold began
    set: [[660, 0, .07], [880, .09, .1]],                                    // set logged
    end: [[660, 0, .1], [660, .16, .1], [990, .32, .22]],                    // rest over / hold over
    pr: [[523, 0, .09], [659, .1, .09], [784, .2, .09], [1047, .3, .26]],    // personal record
    levelup: [[523, 0, .12], [659, .14, .12], [784, .28, .12], [1047, .42, .12], [1319, .56, .4]],
};

function beep(kind) {
    if (!soundOn) return;
    const notes = SOUND_PATTERNS[kind];
    const ctx = audioCtx || unlockAudio();
    // A context that is not running yet would queue the notes and dump them all on unlock
    if (!notes || !ctx || ctx.state !== 'running') return;
    const t0 = ctx.currentTime + .01;
    notes.forEach(([freq, at, len]) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0, t0 + at);
        gain.gain.linearRampToValueAtTime(.25, t0 + at + .01);
        gain.gain.exponentialRampToValueAtTime(.001, t0 + at + len);
        osc.connect(gain).connect(ctx.destination);
        osc.start(t0 + at);
        osc.stop(t0 + at + len + .02);
    });
}

// One call per moment: the phone buzzes where it can and beeps everywhere.
function cue(kind, pattern) {
    vibrate(pattern);
    beep(kind);
}

// Any tap inside the arena counts as the unlocking gesture (a session resumed after a
// refresh never passes through the start button).
document.addEventListener('pointerdown', (e) => {
    if (e.target && e.target.closest && e.target.closest('#arena')) unlockAudio();
}, { capture: true, passive: true });

let workoutData = null;
function data() {
    if (!workoutData) {
        try {
            workoutData = JSON.parse($('#workout-data').textContent);
        } catch (e) {
            workoutData = {};
        }
        workoutData.paths = workoutData.paths || {};
        workoutData.stations = workoutData.stations || {};
        workoutData.records = workoutData.records || {};
        workoutData.catalog = workoutData.catalog || {};
        workoutData.form = workoutData.form || {};
    }
    return workoutData;
}

function findSet(exerciseId, setId) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return null;
    const set = exercise.sets.find(s => s.id === setId);
    if (!set) return null;
    return { exercise, set };
}

function isResolved(set) {
    return set.done || set.skipped;
}

function buildExercise(meta, setCount, reps, rest) {
    return {
        id: uid('ex'),
        name: meta.name,
        title: meta.title || meta.name,
        category: meta.category || 'general',
        skill_key: meta.skill_key || null,
        stage_index: Number.isInteger(meta.stage_index) ? meta.stage_index : null,
        sets: Array.from({ length: Math.max(1, setCount) }, () => ({
            id: uid('set'),
            reps: clampInt(reps, 0, 999),
            rest: clampInt(rest, 0, 999),
            done: false,
            skipped: false,
        })),
    };
}

// A hold is measured in seconds, a rep set in repetitions — the server says which,
// per exercise name, so a resumed session gets it right too.
function unitLabelFor(name) {
    const form = data().form[name];
    return (form && form.unit_label) || 'חזרות';
}

function unitLabel(exercise) {
    return unitLabelFor(exercise && exercise.name);
}

function exerciseIcon(exercise) {
    const path = exercise.skill_key && data().paths[exercise.skill_key];
    return path ? path.icon : (CATEGORY_ICONS[exercise.category] || CATEGORY_ICONS.general);
}

function sessionStats() {
    let doneSets = 0, doneReps = 0, skipped = 0, pending = 0, total = 0;
    activeExercises.forEach(ex => ex.sets.forEach(set => {
        total++;
        if (set.done) { doneSets++; doneReps += set.reps; }
        else if (set.skipped) skipped++;
        else pending++;
    }));
    return { doneSets, doneReps, skipped, pending, total };
}

// 'sec' for a timed hold (front lever, planche, L-sit…), 'reps' for everything else.
function exerciseUnit(exercise) {
    const form = exercise && data().form[exercise.name];
    return form && form.unit === 'sec' ? 'sec' : 'reps';
}

function isHolding() {
    return holdStartedAt !== null;
}

// ====================== PAGE SCROLL LOCK ======================
// Shared by the arena and the exercise picker (iOS-safe body lock).

let scrollLocks = 0;

function lockPageScroll() {
    if (scrollLocks++ > 0) return;
    const scrollY = window.scrollY;
    document.body.dataset.scrollY = scrollY;
    document.body.style.top = `-${scrollY}px`;
    document.body.classList.add('modal-open');
}

function unlockPageScroll() {
    if (scrollLocks === 0) return;
    if (--scrollLocks > 0) return;
    const scrollY = parseInt(document.body.dataset.scrollY || '0', 10);
    document.body.classList.remove('modal-open');
    document.body.style.top = '';
    window.scrollTo(0, scrollY);
}

// ====================== SESSION PERSISTENCE ======================

function saveSession() {
    if (!sessionActive) return;
    try {
        const dateInput = $('#workout-date');
        const typeSelect = $('#workout-type');
        localStorage.setItem(WORKOUT_SESSION_KEY, JSON.stringify({
            startedAt: workoutStartTime,
            date: dateInput ? dateInput.value : '',
            type: typeSelect ? typeSelect.value : '',
            exercises: activeExercises,
            cursor,
            phase: ['rest', 'warmup', 'ready'].includes(arenaPhase) ? arenaPhase : 'set',
            warmupDone,
            restEndsAt,
            restDuration,
            plannedSets,
            path: sessionPath,
            prShown,
            comboCount,
            lastRestEnd,
        }));
    } catch (e) { /* private mode — session just won't survive a refresh */ }
}

function clearSavedSession() {
    try { localStorage.removeItem(WORKOUT_SESSION_KEY); } catch (e) { /* ignore */ }
}

function loadSavedSession() {
    try {
        const saved = JSON.parse(localStorage.getItem(WORKOUT_SESSION_KEY));
        if (!saved || typeof saved.startedAt !== 'number' || !Array.isArray(saved.exercises)) return null;
        return saved;
    } catch (e) {
        return null;
    }
}

// Rebuild exercises from storage defensively: bad entries are dropped,
// numbers are clamped, missing ids regenerated.
function sanitizeExercises(list) {
    const result = [];
    (list || []).forEach(ex => {
        if (!ex || typeof ex.name !== 'string' || !ex.name.trim() || !Array.isArray(ex.sets)) return;
        const sets = ex.sets.map(s => ({
            id: (s && typeof s.id === 'string') ? s.id : uid('set'),
            reps: clampInt(s && s.reps, 0, 999),
            rest: clampInt(s && s.rest, 0, 999),
            done: !!(s && s.done),
            skipped: !!(s && s.skipped && !s.done),
        }));
        if (sets.length === 0) return;
        const catalog = data().catalog[ex.name] || {};
        result.push({
            id: typeof ex.id === 'string' ? ex.id : uid('ex'),
            name: ex.name,
            title: typeof ex.title === 'string' && ex.title ? ex.title : (catalog.title || ex.name),
            category: typeof ex.category === 'string' ? ex.category : (catalog.category || 'general'),
            skill_key: typeof ex.skill_key === 'string' ? ex.skill_key : null,
            stage_index: Number.isInteger(ex.stage_index) ? ex.stage_index : null,
            sets,
        });
    });
    return result;
}

// ====================== WAKE LOCK ======================

async function requestWakeLock() {
    if (!('wakeLock' in navigator)) return;
    try {
        wakeLock = await navigator.wakeLock.request('screen');
    } catch (e) { /* denied / low battery — non-critical */ }
}

function releaseWakeLock() {
    if (wakeLock) {
        wakeLock.release().catch(() => {});
        wakeLock = null;
    }
}

document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && sessionActive) {
        requestWakeLock();
    }
    syncHologram();
});

// ====================== INITIALIZE PAGE ======================

document.addEventListener('DOMContentLoaded', () => {
    // 0. The page content is its own stacking context (under the navbar),
    //    so the full-screen layers are moved up to <body>.
    ['#arena', '#exercise-modal'].forEach(selector => {
        const layer = $(selector);
        if (layer) document.body.appendChild(layer);
    });

    // 1. Default the workout date to today (local timezone)
    const dateInput = $('#workout-date');
    if (dateInput && !dateInput.value) dateInput.value = todayIso();

    // 2. Views + the active quest path
    initActivePath();
    applyRoute();
    window.addEventListener('hashchange', () => {
        applyRoute();
        window.scrollTo(0, 0);
    });
    selectDefaultBadge();

    // 3. Desktop skill guide
    const select = $('#skill-select');
    if (select) displaySkillData(select.value);

    // 4. Persist date/type edits mid-session
    const typeSelect = $('#workout-type');
    if (dateInput) dateInput.addEventListener('change', saveSession);
    if (typeSelect) typeSelect.addEventListener('change', saveSession);

    wirePage();
    wireArenaSheet();
    wireHologram();

    // 5. Resume an in-progress workout after a refresh/navigation — straight into the arena
    const saved = loadSavedSession();
    if (saved) {
        if (dateInput && saved.date) dateInput.value = saved.date;
        if (typeSelect && saved.type) typeSelect.value = saved.type;
        resumeWorkoutSession(saved);
    }

    // 6. Stations used to be marked by hand in this browser; hand them to the server once
    migrateLegacySkillProgress();
});

function todayIso() {
    const today = new Date();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    return `${today.getFullYear()}-${mm}-${dd}`;
}

function wirePage() {
    document.addEventListener('click', (e) => {
        const startPath = e.target.closest('[data-start-path]');
        if (startPath) { startPathWorkout(startPath.dataset.startPath); return; }

        const choosePath = e.target.closest('[data-choose-path]');
        if (choosePath) {
            setActivePath(choosePath.dataset.choosePath);
            window.scrollTo({ top: 0, behavior: reducedMotion.matches ? 'auto' : 'smooth' });
            return;
        }

        const chip = e.target.closest('[data-map-chip]');
        if (chip && !chip.disabled) { setActivePath(chip.dataset.mapChip); return; }

        if (e.target.closest('[data-start-free]')) { startFreeWorkout(); return; }

        const badge = e.target.closest('[data-badge]');
        if (badge) { selectBadge(badge); return; }

        const addExercise = e.target.closest('[data-add-exercise]');
        if (addExercise) { addExerciseByName(addExercise.dataset.addExercise); return; }

        const addStation = e.target.closest('[data-add-station]');
        if (addStation) { addSkillProgression(addStation.dataset.addStation, parseInt(addStation.dataset.stage, 10)); }
    });

    const customInput = $('#custom-exercise-name');
    if (customInput) {
        customInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); addCustomExercise(); }
        });
    }

    const prLayer = $('#arena-pr-layer');
    if (prLayer) prLayer.addEventListener('click', hidePrToast);

    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        if ($('#exercise-modal').classList.contains('active')) closeExerciseModal();
    });
}

// ====================== VIEWS & ACTIVE PATH ======================

const VIEWS = ['home', 'map', 'profile', 'history'];
let activePath = null;

function applyRoute() {
    const [view, pathKey] = (location.hash || '#home').slice(1).split('/');
    if (pathKey) setActivePath(pathKey);
    showView(view);
}

function showView(name) {
    if (!VIEWS.includes(name) || !$(`[data-view="${name}"]`)) name = 'home';
    $all('[data-view]').forEach(el => { el.hidden = el.dataset.view !== name; });
    $all('#mobile-section-header .section-tab, [data-desk-tab]').forEach(tab => {
        const isActive = tab.getAttribute('href') === `#${name}`;
        tab.classList.toggle('is-active', isActive);
        if (isActive) tab.setAttribute('aria-current', 'page');
        else tab.removeAttribute('aria-current');
    });
    if (name === 'profile') scrollLadderToCurrent();
}

function initActivePath() {
    let stored = null;
    try { stored = localStorage.getItem(ACTIVE_PATH_KEY); } catch (e) { /* storage unavailable */ }
    const paths = data().paths;
    const key = stored && paths[stored] && paths[stored].unlocked ? stored : data().default_path;
    if (key) setActivePath(key, false);
}

function setActivePath(key, persist = true) {
    const path = data().paths[key];
    if (!path || !path.unlocked) return;
    activePath = key;
    $all('[data-mission]').forEach(el => { el.hidden = el.dataset.mission !== key; });
    $all('[data-path-row]').forEach(el => { el.hidden = el.dataset.pathRow === key; });
    $all('[data-map]').forEach(el => { el.hidden = el.dataset.map !== key; });
    $all('[data-map-chip]').forEach(chip => {
        const isActive = chip.dataset.mapChip === key;
        chip.classList.toggle('is-active', isActive);
        chip.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
    if (persist) {
        try { localStorage.setItem(ACTIVE_PATH_KEY, key); } catch (e) { /* storage unavailable */ }
    }
}

function scrollLadderToCurrent() {
    const ladder = $('[data-ladder]');
    const current = ladder && $('[data-current-rank]', ladder);
    if (!ladder || !current) return;
    ladder.scrollTop = current.offsetTop - (ladder.clientHeight - current.offsetHeight) / 2;
}

function selectBadge(badge) {
    const detail = $('[data-badge-detail]');
    if (!detail) return;
    $all('[data-badge]').forEach(b => b.classList.toggle('is-selected', b === badge));
    const unlocked = badge.dataset.unlocked === '1';
    const progress = unlocked
        ? 'הושג'
        : `${numHtml(formatNumber(badge.dataset.current))} / ${numHtml(formatNumber(badge.dataset.target))}`;
    detail.innerHTML = `<b>${escapeHtml(badge.dataset.title)}</b> — ${escapeHtml(badge.dataset.desc)} · ${progress}`;
}

// Open on the locked badge that is closest to unlocking (or the first one).
function selectDefaultBadge() {
    const badges = $all('[data-badge]');
    if (!badges.length) return;
    let best = null;
    let bestRatio = -1;
    badges.forEach(b => {
        if (b.dataset.unlocked === '1') return;
        const ratio = Number(b.dataset.current) / Math.max(1, Number(b.dataset.target));
        if (ratio > bestRatio) { best = b; bestRatio = ratio; }
    });
    selectBadge(best || badges[0]);
}

// ====================== WORKOUT SESSION LIFECYCLE ======================

function startPathWorkout(key) {
    const path = data().paths[key];
    if (!path || !path.unlocked) return;
    if (sessionActive) { openArena(); return; }
    setActivePath(key);
    const exercises = path.plan.exercises.map(ex => buildExercise(
        { ...ex, category: path.category }, ex.sets, ex.reps, ex.rest
    ));
    beginSession(exercises, key, path.workout_type, path.warmup && path.warmup.length > 0);
}

function startFreeWorkout() {
    if (sessionActive) { openArena(); return; }
    beginSession([], null, 'Calisthenics');
    openExerciseModal();
}

function beginSession(exercises, pathKey, workoutType, withWarmup = false) {
    activeExercises = exercises;
    warmupDone = [];
    holdStartedAt = null;
    workoutStartTime = Date.now();
    sessionActive = true;
    sessionPath = pathKey;
    comboCount = 0;
    prShown = {};
    lastRestEnd = null;
    holoSlow = false;
    plannedSets = exercises.reduce((n, ex) => n + ex.sets.length, 0);

    const dateInput = $('#workout-date');
    if (dateInput) dateInput.value = todayIso();
    const typeSelect = $('#workout-type');
    if (typeSelect && workoutType) typeSelect.value = workoutType;

    cursor = null;
    advanceCursor();
    arenaPhase = withWarmup ? 'warmup' : 'set';
    openArena();
    startWorkoutTimer();
    requestWakeLock();
    renderArena();
    saveSession();
}

// --- Resume a persisted session (after refresh) ---
function resumeWorkoutSession(saved) {
    activeExercises = sanitizeExercises(saved.exercises);
    workoutStartTime = saved.startedAt;
    sessionActive = true;
    sessionPath = typeof saved.path === 'string' ? saved.path : null;
    plannedSets = clampInt(saved.plannedSets, 0, 9999);
    prShown = (saved.prShown && typeof saved.prShown === 'object') ? saved.prShown : {};
    comboCount = clampInt(saved.comboCount, 0, 9999);
    lastRestEnd = typeof saved.lastRestEnd === 'number' ? saved.lastRestEnd : null;

    cursor = saved.cursor && typeof saved.cursor.setId === 'string' ? saved.cursor : null;
    if (!currentPosition()) advanceCursor();
    warmupDone = Array.isArray(saved.warmupDone) ? saved.warmupDone.filter(Number.isInteger) : [];
    holdStartedAt = null;

    const pathWarmup = sessionPath && data().paths[sessionPath] && data().paths[sessionPath].warmup;
    if (saved.phase === 'warmup' && pathWarmup && pathWarmup.length) arenaPhase = 'warmup';
    else if (saved.phase === 'ready' && sessionPath) arenaPhase = 'ready';
    else arenaPhase = 'set';
    openArena();
    startWorkoutTimer();
    requestWakeLock();

    const restEnd = typeof saved.restEndsAt === 'number' ? saved.restEndsAt : null;
    if (saved.phase === 'rest' && restEnd && Date.now() < restEnd + REST_AUTO_ADVANCE_MS) {
        resumeRest(restEnd, clampInt(saved.restDuration, 1, 999));
    } else {
        if (saved.phase === 'rest' && restEnd) lastRestEnd = restEnd;
        renderArena();
    }
    updateComboIndicator();
}

// --- Cancel the current session entirely ---
function cancelWorkout() {
    if (activeExercises.some(ex => ex.sets.some(s => s.done))
        && !confirm('לבטל את האימון הנוכחי? כל הסטים שסומנו יימחקו ולא יישמרו.')) return;

    sessionActive = false;
    clearSavedSession();
    activeExercises = [];
    cursor = null;
    comboCount = 0;

    if (workoutTimerInterval) clearInterval(workoutTimerInterval);
    stopRestTimer();
    stopHoldTimer();
    releaseWakeLock();
    closeArenaSheet(true);
    closeFormCheck();
    closeArena();
}

// --- Live Workout Timer Logic ---
// Renders elapsed time from workoutStartTime, so a resumed session keeps its original start.
function startWorkoutTimer() {
    const timerLabel = $('#workout-timer');
    if (workoutTimerInterval) clearInterval(workoutTimerInterval);

    const tick = () => {
        const totalSeconds = Math.max(0, Math.floor((Date.now() - workoutStartTime) / 1000));
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        const mmss = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        if (timerLabel) timerLabel.textContent = hours > 0 ? `${hours}:${mmss}` : mmss;
        const warmClock = $('#warmup-clock');
        if (warmClock && arenaPhase === 'warmup') warmClock.textContent = `${minutes}:${String(seconds).padStart(2, '0')}`;
    };

    tick();
    workoutTimerInterval = setInterval(tick, 1000);
}

// ====================== ARENA SHELL ======================

// Everything behind the arena is taken out of the tab order while it is open.
const ARENA_BACKGROUND = ['#wk-page', '#mobile-section-header', '#mobile-tab-bar', 'nav.nav-gradient', 'footer.footer'];

function openArena() {
    const arena = $('#arena');
    if (!arena || !arena.hidden) return;
    arena.hidden = false;
    document.body.classList.add('arena-open');
    lockPageScroll();
    unlockAudio();
    renderSoundToggle();
    ARENA_BACKGROUND.forEach(sel => $all(sel).forEach(el => el.setAttribute('inert', '')));
    arena.focus({ preventScroll: true });
}

function closeArena() {
    const arena = $('#arena');
    if (!arena || arena.hidden) return;
    arena.hidden = true;
    document.body.classList.remove('arena-open');
    ARENA_BACKGROUND.forEach(sel => $all(sel).forEach(el => el.removeAttribute('inert')));
    unlockPageScroll();
    syncHologram();
}

// ====================== CURSOR (the set on screen) ======================

function currentPosition() {
    if (!cursor) return null;
    const found = findSet(cursor.exerciseId, cursor.setId);
    return found && !isResolved(found.set) ? found : null;
}

// Move to the next unresolved set after the cursor, wrapping to the start.
function advanceCursor() {
    const flat = [];
    activeExercises.forEach(exercise => exercise.sets.forEach(set => flat.push({ exercise, set })));
    const start = cursor ? flat.findIndex(item => item.set.id === cursor.setId) : -1;
    for (let step = 1; step <= flat.length; step++) {
        const item = flat[(start + step + flat.length) % flat.length];
        if (!isResolved(item.set)) {
            cursor = { exerciseId: item.exercise.id, setId: item.set.id };
            return item;
        }
    }
    cursor = null;
    return null;
}

function pointCursorAt(exercise) {
    const set = exercise.sets.find(s => !s.done);
    if (!set) return false;
    set.skipped = false;
    cursor = { exerciseId: exercise.id, setId: set.id };
    return true;
}

// ====================== ARENA RENDERING ======================

function renderArena() {
    const arena = $('#arena');
    if (!arena) return;
    arena.dataset.phase = arenaPhase;
    if (arenaPhase === 'reward') {
        syncHologram();
        return;
    }

    if (arenaPhase === 'warmup') {
        renderWarmup();
        syncHologram();
        return;
    }
    if (arenaPhase === 'ready') {
        renderReady();
        syncHologram();
        return;
    }

    renderStatus();
    updateSessionScore(false);
    if (arenaPhase === 'set') renderSetPanel();
    else renderRestPanel();
    if (!$('#arena-sheet-layer').hidden) renderSheet();
    syncHologram();
}

function renderStatus() {
    const pos = currentPosition();
    const exIndex = pos ? activeExercises.indexOf(pos.exercise) : activeExercises.length - 1;
    const countEl = $('#arena-ex-count');
    if (countEl) {
        countEl.innerHTML = `תרגיל ${numHtml(Math.max(1, exIndex + 1))} מתוך ${numHtml(activeExercises.length)}`;
    }

    const rail = $('#arena-rail');
    if (rail) {
        rail.innerHTML = activeExercises.map(ex => {
            const state = ex.sets.every(isResolved) ? 'is-done' : (pos && pos.exercise === ex ? 'is-current' : '');
            return `<span class="${state}"></span>`;
        }).join('');
    }
}

function renderSetPanel() {
    const panel = $('[data-phase-panel="set"]');
    const pos = currentPosition();
    const ring = $('#arena-ring');
    const repsEl = $('#arena-reps');
    const compare = $('#arena-compare');

    const cues = $('#arena-cues');
    const tempoEl = $('#arena-tempo');
    stopHoldTimer();
    panel.dataset.hold = 'idle';

    if (activeExercises.length === 0) {
        panel.dataset.state = 'empty';
        panel.dataset.holo = 'off';
        panel.dataset.unit = 'reps';
        cues.hidden = tempoEl.hidden = true;
        return;
    }

    if (!pos) {
        const stats = sessionStats();
        panel.dataset.state = 'complete';
        panel.dataset.holo = 'off';
        ring.style.setProperty('--pct', '100%');
        repsEl.textContent = '✓';
        $('#arena-reps-label').textContent = 'הושלם';
        $('#arena-set-label').innerHTML = `כל ${numHtml(stats.total)} הסטים הושלמו`;
        $('#arena-ex-name').textContent = 'האימון מוכן לשמירה';
        compare.hidden = false;
        compare.innerHTML = `${countHtml(stats.doneSets, 'סט אחד', 'סטים')} · ${countHtml(stats.doneReps, 'חזרה אחת', 'חזרות')} · ${numHtml(`+${computeSessionScore()} XP`)} עד עכשיו`;
        panel.dataset.unit = 'reps';
        cues.hidden = tempoEl.hidden = true;
        return;
    }

    const { exercise, set } = pos;
    const doneInExercise = exercise.sets.filter(s => s.done).length;
    panel.dataset.state = 'active';
    const holo = holoFor(exercise);
    panel.dataset.holo = holoState(holo);
    if (holo) paintTempo(panel, holo.tempo);
    ring.style.setProperty('--pct', `${Math.round(doneInExercise * 100 / exercise.sets.length)}%`);
    const unit = exerciseUnit(exercise);
    panel.dataset.unit = unit;
    repsEl.textContent = set.reps;
    $('#arena-reps-label').textContent = unitLabel(exercise);
    $('#arena-done-label').textContent = 'סיימתי את הסט';
    $all('.arena-step-label').forEach(el => { el.textContent = unit === 'sec' ? 'כוונון שניות' : 'כוונון חזרות'; });
    $('#arena-set-xp').textContent = `+${XP_PER_SET + set.reps} XP`;
    $('#arena-set-label').innerHTML = `סט ${numHtml(exercise.sets.indexOf(set) + 1)} מתוך ${numHtml(exercise.sets.length)}`;
    $('#arena-ex-name').textContent = exercise.title;

    const line = compareLine(exercise, set.reps);
    compare.hidden = !line;
    compare.innerHTML = line;
    renderFormGuide(exercise, unit);
}

// Two form cues + the rep tempo under the exercise name — the plain arena's stand-in for the hologram.
function renderFormGuide(exercise, unit) {
    const cues = $('#arena-cues');
    const tempoEl = $('#arena-tempo');
    const form = data().form[exercise.name] || {};
    const list = Array.isArray(form.cues) ? form.cues.slice(0, 2) : [];
    cues.hidden = list.length === 0;
    cues.innerHTML = list.map(c => `
        <div class="arena-cue">
            <span class="arena-cue-pin">${escapeHtml(c.pin)}</span>
            <span class="arena-cue-text">${escapeHtml(c.text)}</span>
        </div>`).join('');

    if (unit === 'sec') {
        tempoEl.hidden = false;
        tempoEl.innerHTML = `<span class="arena-tempo-label">החזקה</span><span class="arena-tempo-text">נשימה שקטה לאורך כל ההחזקה — לא עוצרים אוויר. עוצרים כשהתנוחה נשברת.</span>`;
    } else if (Array.isArray(form.tempo) && form.tempo.length === 3) {
        const [down, pause, up] = form.tempo;
        const parts = [`ירידה ${down}`, pause ? `עצירה ${pause}` : '', `עלייה ${up}`].filter(Boolean);
        tempoEl.hidden = false;
        tempoEl.innerHTML = `<span class="arena-tempo-label">מקצב</span><span class="arena-tempo-text">${parts.map(numHtml).join(' · ')} שניות</span>`;
    } else {
        tempoEl.hidden = true;
    }
}

// ====================== HOLD TIMER ======================
// A hold station counts down its target seconds on the ring. Stopping early saves the
// seconds actually held, so the station's rep range is judged on the truth.

function startHold() {
    const pos = currentPosition();
    if (!pos || isHolding()) return;
    const target = pos.set.reps;
    if (target <= 0) return;
    holdStartedAt = Date.now();
    holdLastBeep = null;
    const panel = $('[data-phase-panel="set"]');
    panel.dataset.hold = 'running';
    $('#arena-done-label').textContent = 'עצור — סיימתי';
    $('#arena-set-xp').textContent = '';
    cue('start', 20);
    if (holdInterval) clearInterval(holdInterval);
    holdInterval = setInterval(tickHold, 100);
    tickHold();
}

function tickHold() {
    const pos = currentPosition();
    if (!pos || !isHolding()) { stopHoldTimer(); return; }
    const target = pos.set.reps;
    const elapsed = (Date.now() - holdStartedAt) / 1000;
    const remaining = Math.max(0, target - elapsed);
    const shown = Math.ceil(remaining);
    $('#arena-reps').textContent = shown;
    $('#arena-reps-label').textContent = 'שניות נשארו';
    $('#arena-ring').style.setProperty('--pct', `${Math.min(100, elapsed * 100 / target)}%`);
    if (shown <= 3 && shown > 0 && holdLastBeep !== shown) {
        holdLastBeep = shown;
        cue('tick', 15);
    }
    if (remaining <= 0) finishHold(target);
}

function stopHoldTimer() {
    if (holdInterval) clearInterval(holdInterval);
    holdInterval = null;
    holdStartedAt = null;
    holdLastBeep = null;
}

// The hold ended (timer ran out, or "עצור") — save the seconds really held and complete the set.
function finishHold(seconds) {
    const pos = currentPosition();
    stopHoldTimer();
    if (!pos) return;
    const held = clampInt(seconds, 0, 999);
    if (held <= 0) {
        // Nothing to save: back to the idle hold screen
        renderSetPanel();
        return;
    }
    pos.set.reps = Math.min(pos.set.reps, held);
    cue('end', [40, 60, 40]); // the one signal that has to reach someone upside down
    completeCurrentSet({ silent: true });
}

// "בפעם שעברה עשית 11 — עוד אחת והשיא נשבר" — only when there is history for the exercise.
function compareLine(exercise, reps) {
    const record = data().records[exercise.name];
    if (!record) return '';
    const best = Math.max(record.best, sessionBest(exercise.name));
    const need = best + 1 - reps;
    let tail;
    if (need <= 0) tail = 'זה שיא חדש';
    else if (need === 1) tail = 'עוד אחת והשיא נשבר';
    else if (need <= 3) tail = `עוד ${numHtml(need)} והשיא נשבר`;
    else tail = `השיא שלך ${numHtml(best)}`;
    const verb = exerciseUnit(exercise) === 'sec' ? 'החזקת' : 'עשית';
    const unit = exerciseUnit(exercise) === 'sec' ? ' שנ׳' : '';
    return `בפעם שעברה ${verb} ${numHtml(record.last)}${unit} — ${tail}`;
}

function sessionBest(name) {
    let best = 0;
    activeExercises.forEach(ex => {
        if (ex.name !== name) return;
        ex.sets.forEach(s => { if (s.done) best = Math.max(best, s.reps); });
    });
    return best;
}

function renderRestPanel() {
    const next = currentPosition();
    const tile = $('#rest-next-tile');
    const title = $('#rest-next-title');
    const sub = $('#rest-next-sub');
    const xp = $('#rest-next-xp');

    if (next) {
        const { exercise, set } = next;
        const index = exercise.sets.indexOf(set);
        const target = `יעד ${numHtml(set.reps)} ${escapeHtml(unitLabel(exercise))}`;
        tile.textContent = exerciseIcon(exercise);
        title.innerHTML = `${escapeHtml(exercise.title)} · סט ${numHtml(index + 1)}`;
        if (exercise.sets.length > 1 && index === exercise.sets.length - 1) sub.innerHTML = `הסט האחרון בתרגיל · ${target}`;
        else if (index === 0) sub.innerHTML = `תרגיל חדש · ${target}`;
        else sub.innerHTML = target;
        xp.textContent = `+${XP_PER_SET + set.reps}`;
    } else {
        tile.textContent = '🏁';
        title.textContent = 'זה היה הסט האחרון';
        sub.textContent = 'אחרי המנוחה — סיום ושמירה';
        xp.textContent = '';
    }

    $('#rest-coach-tip').textContent = restTip;
    const stats = sessionStats();
    $('#rest-strip-xp').textContent = `${formatNumber(computeSessionScore())} XP`;
    $('#rest-strip-sets').innerHTML = countHtml(stats.doneSets, 'סט אחד', 'סטים');
    $('#rest-combo-line').hidden = comboCount < 2;
}

function pickCoachTip(exercise) {
    const tips = COACH_TIPS[exercise && exercise.category] || COACH_TIPS.general;
    return tips[sessionStats().doneSets % tips.length];
}

// ====================== WARM-UP PHASE ======================

function renderWarmup() {
    const path = sessionPath && data().paths[sessionPath];
    const items = (path && path.warmup) || [];
    $('#warmup-path').textContent = path ? `מסלול ${path.name}` : 'אימון';
    $('#warmup-minutes').textContent = path && path.warmup_minutes ? path.warmup_minutes : 5;
    $('#warmup-list').innerHTML = items.map((item, i) => `
        <li>
            <button type="button" class="warmup-item${warmupDone.includes(i) ? ' is-done' : ''}" onclick="toggleWarmupItem(${i})" aria-pressed="${warmupDone.includes(i)}">
                <span class="warmup-check" aria-hidden="true">${warmupDone.includes(i) ? '✓' : i + 1}</span>
                <span class="warmup-text">
                    <span class="warmup-item-title">${escapeHtml(item.title)}</span>
                    <span class="warmup-item-detail">${escapeHtml(item.detail)}</span>
                </span>
            </button>
        </li>`).join('');
    const btn = $('#warmup-done-btn');
    const allDone = items.length > 0 && warmupDone.length >= items.length;
    btn.classList.toggle('is-ready', allDone);
}

function toggleWarmupItem(index) {
    if (warmupDone.includes(index)) warmupDone = warmupDone.filter(i => i !== index);
    else warmupDone = [...warmupDone, index];
    vibrate(8);
    renderWarmup();
    saveSession();
}

// The warm-up never drops straight into the first set: it leads to the "ready" screen,
// and the training starts only when the athlete presses start there.
function finishWarmup(skipped = false) {
    if (arenaPhase !== 'warmup') return;
    if (!skipped) vibrate(12);
    arenaPhase = 'ready';
    renderArena();
    saveSession();
}

// ====================== READY PHASE ======================
// Between the warm-up and the first set: what is about to happen, and one start button.

function renderReady() {
    const path = sessionPath && data().paths[sessionPath];
    $('#ready-path').textContent = path ? `מסלול ${path.name}` : 'אימון';

    const first = currentPosition();
    const tile = $('#ready-first-tile');
    const title = $('#ready-first-title');
    const sub = $('#ready-first-sub');
    if (first) {
        const { exercise, set } = first;
        tile.textContent = exerciseIcon(exercise);
        title.textContent = exercise.title;
        sub.innerHTML = `${countHtml(exercise.sets.length, 'סט אחד', 'סטים')} · יעד ${numHtml(set.reps)} ${escapeHtml(unitLabel(exercise))}`;
    } else {
        tile.textContent = '🏁';
        title.textContent = 'אין סטים לביצוע';
        sub.textContent = 'אפשר להוסיף תרגיל בזירה';
    }

    const stats = sessionStats();
    $('#ready-plan').innerHTML = `${countHtml(activeExercises.length, 'תרגיל אחד', 'תרגילים')} · ${countHtml(stats.total, 'סט אחד', 'סטים')}`;
    $('#ready-warmup-note').hidden = warmupDone.length === 0;
}

function startTraining() {
    if (arenaPhase !== 'ready') return;
    vibrate(12);
    arenaPhase = 'set';
    renderArena();
    saveSession();
}

function backToWarmup() {
    if (arenaPhase !== 'ready') return;
    const path = sessionPath && data().paths[sessionPath];
    if (!path || !path.warmup || !path.warmup.length) return;
    arenaPhase = 'warmup';
    renderArena();
    saveSession();
}

// ====================== HOLOGRAM (3a / 3b) ======================
// One shared glTF model with an animation clip per exercise (clip name = holo_key, see
// routes/workouts.py). Only exercises whose clip exists get the stage; the rest keep the
// plain set screen. Each clip is one rep, played so that a loop lasts the exercise's tempo.

const MODEL_VIEWER_URL = 'https://cdn.jsdelivr.net/npm/@google/model-viewer@4.3.1/dist/model-viewer.min.js';
const HOLO_ANGLE_KEY = 'workout_holo_angle_v1';
const HOLO_ANGLES = {
    side: '90deg 75deg 105%',
    front: '0deg 75deg 105%',
    top: '0deg 12deg 105%',
};
const HOLO_ANGLE_ORDER = ['side', 'front', 'top'];
const HOLO_FOV_DEG = 30;      // fixed, so a clip's framing can be computed from its bounds
const HOLO_FRAME_PAD = 1.12;  // breathing room round the clip's box
const HOLO_LOAD_TIMEOUT_MS = 20000;  // no model on screen by then → the plain arena for this session

let modelViewerLoading = null;
let holoFailed = false;   // the viewer or the model could not load: fall back to the plain arena
let holoSlow = false;     // .5× — resets every session
let stageViewer = null;
let formViewer = null;
let formOpener = null;
let formAngle = 'side';
let holoFrame = null;

function holoFor(exercise) {
    const holo = data().holo;
    if (!holo || holoFailed || !exercise) return null;
    const form = data().form[exercise.name];
    if (!form || !holo.clips.includes(form.holo_key)) return null;
    return form;
}

function currentHolo() {
    const pos = arenaPhase === 'set' ? currentPosition() : null;
    const form = pos && holoFor(pos.exercise);
    return form ? { exercise: pos.exercise, ...form } : null;
}

// The set screen's hologram state: 'on' only once the model is really on screen. Until then
// (and for good, if it never arrives) the plain cues and tempo stand in, so a slow or dead
// CDN never leaves an empty stage.
function holoState(holo) {
    if (!holo) return 'off';
    return stageViewer && stageViewer.loaded ? 'on' : 'loading';
}

function loadModelViewer() {
    if (!modelViewerLoading) {
        modelViewerLoading = import(MODEL_VIEWER_URL).catch((error) => {
            console.error('Hologram viewer failed to load', error);
            disableHologram();
        });
    }
    return modelViewerLoading;
}

function disableHologram() {
    if (holoFailed) return;
    holoFailed = true;
    closeFormCheck();
    if (!$('#arena').hidden) renderArena();
}

function createViewer(container, interactive) {
    loadModelViewer();
    const viewer = document.createElement('model-viewer');
    viewer.setAttribute('src', data().holo.model);
    viewer.setAttribute('alt', 'הדגמת התרגיל');
    viewer.setAttribute('interaction-prompt', 'none');
    viewer.setAttribute('disable-zoom', '');
    viewer.setAttribute('disable-pan', '');
    viewer.setAttribute('disable-tap', '');
    viewer.setAttribute('shadow-intensity', '0');
    viewer.setAttribute('environment-image', 'neutral');
    viewer.setAttribute('loading', 'eager');
    // The clips are framed by hand (setOrbit), so the viewer's own limits must not clamp them
    viewer.setAttribute('min-camera-orbit', 'auto auto 0.1m');
    viewer.setAttribute('max-camera-orbit', 'auto auto 60m');
    if (interactive) viewer.setAttribute('camera-controls', '');
    viewer.addEventListener('error', disableHologram);
    viewer.addEventListener('load', syncHologram);
    // A viewer that never fires load or error (blocked CDN, stalled download) would leave
    // the stage empty for the whole workout — give it a deadline instead.
    const deadline = setTimeout(() => {
        if (!viewer.loaded) {
            console.warn('Hologram did not load in time — using the plain arena');
            disableHologram();
        }
    }, HOLO_LOAD_TIMEOUT_MS);
    viewer.addEventListener('load', () => clearTimeout(deadline), { once: true });
    container.appendChild(viewer);
    return viewer;
}

function readAngles() {
    try { return JSON.parse(localStorage.getItem(HOLO_ANGLE_KEY)) || {}; } catch (e) { return {}; }
}

// The model names the clips that read from the front (the flags); everything else starts side-on.
function defaultAngle(key) {
    const holo = data().holo;
    return holo && (holo.front || []).includes(key) ? 'front' : HOLO_ANGLE_ORDER[0];
}

function angleFor(key) {
    const angle = readAngles()[key];
    return HOLO_ANGLES[angle] ? angle : defaultAngle(key);
}

function rememberAngle(key, angle) {
    const angles = readAngles();
    angles[key] = angle;
    try { localStorage.setItem(HOLO_ANGLE_KEY, JSON.stringify(angles)); } catch (e) { /* storage unavailable */ }
}

// The viewer frames the model's rest pose once, at load; a clip hanging from a bar is twice as
// tall. The model carries each clip's box (centre + half-extents), so the camera is aimed at
// the clip and pulled back until the box fits the slot — from this angle, at this aspect.
function clipFraming(viewer, key, angle) {
    const bounds = data().holo.bounds && data().holo.bounds[key];
    if (!bounds || bounds.length !== 6) return null;
    const [cx, cy, cz, hx, hy, hz] = bounds;
    const [theta, phi] = HOLO_ANGLES[angle].split(' ').map(parseFloat);
    const elevation = (90 - phi) * Math.PI / 180;
    const across = angle === 'side' ? hz : hx;          // what runs along the screen
    const depth = angle === 'side' ? hx : hz;           // what points at the camera
    const tall = hy * Math.cos(elevation) + depth * Math.sin(elevation);
    const aspect = viewer.clientHeight > 0 ? viewer.clientWidth / viewer.clientHeight : 1.8;
    const tan = Math.tan(HOLO_FOV_DEG / 2 * Math.PI / 180);
    const radius = HOLO_FRAME_PAD * Math.max(tall / tan, across / (tan * aspect), 0.5);
    return {
        target: `${cx}m ${cy}m ${cz}m`,
        orbit: `${theta}deg ${phi}deg ${radius.toFixed(3)}m`,
    };
}

// Re-applies the preset even when the user dragged away from the same value
function setOrbit(viewer, angle, key) {
    const framing = key ? clipFraming(viewer, key, angle) : null;
    viewer.cameraOrbit = '';
    if (framing) {
        viewer.fieldOfView = `${HOLO_FOV_DEG}deg`;
        viewer.cameraTarget = framing.target;
        viewer.cameraOrbit = framing.orbit;
    } else {
        viewer.cameraOrbit = HOLO_ANGLES[angle];
    }
}

function aimViewer(viewer, holo, angle) {
    if (viewer.getAttribute('animation-name') !== holo.holo_key) {
        viewer.setAttribute('animation-name', holo.holo_key);
    }
    if (viewer.dataset.angle !== angle || viewer.dataset.clip !== holo.holo_key) {
        viewer.dataset.angle = angle;
        viewer.dataset.clip = holo.holo_key;
        setOrbit(viewer, angle, holo.holo_key);
    }
}

function tempoTotal(tempo) {
    return tempo ? tempo.reduce((sum, part) => sum + part, 0) : 0;
}

function paintTempo(root, tempo) {
    $all('[data-tempo-bar] span', root).forEach((segment, i) => {
        segment.hidden = tempo ? tempo[i] === 0 : i > 0;
        segment.style.setProperty('--seg', tempo ? Math.max(tempo[i], 1) : 1);
        segment.classList.toggle('is-on', i === 0);
    });
    $('[data-tempo-value]', root).textContent = tempo ? tempo.join('-') : 'החזקה';
    const legend = $('[data-tempo-legend]', root);
    if (legend) legend.textContent = tempo ? 'ירידה · עצירה · דחיפה' : 'החזקה סטטית לאורך הסט';
}

// Keeps the loop at the exercise's tempo and lights the matching tempo segment.
function holoLoop() {
    holoFrame = null;
    const holo = currentHolo();
    const formOpen = !$('#arena-form-layer').hidden;
    const viewer = formOpen ? formViewer : stageViewer;
    if (!holo || !viewer) return;

    const duration = viewer.duration;
    if (viewer.loaded && duration > 0) {
        const total = tempoTotal(holo.tempo);
        const scale = (total ? duration / total : 1) * (holoSlow ? 0.5 : 1);
        if (Math.abs(viewer.timeScale - scale) > 0.001) viewer.timeScale = scale;
        if (viewer.paused) viewer.play();
        if (holo.tempo) {
            const t = ((viewer.currentTime % duration) / duration) * total;
            const active = t < holo.tempo[0] ? 0 : (t < holo.tempo[0] + holo.tempo[1] ? 1 : 2);
            const root = formOpen ? $('#arena-form-layer') : $('[data-phase-panel="set"]');
            $all('[data-tempo-bar] span', root).forEach((segment, i) => segment.classList.toggle('is-on', i === active));
        }
    }
    holoFrame = requestAnimationFrame(holoLoop);
}

// Plays exactly one viewer while the set screen (or the form check) is up and the tab is visible.
function syncHologram() {
    const arena = $('#arena');
    const holo = arena && !arena.hidden ? currentHolo() : null;
    const formOpen = !$('#arena-form-layer').hidden;

    if (holo) {
        if (!stageViewer) stageViewer = createViewer($('#holo-figure'), false);
        aimViewer(stageViewer, holo, angleFor(holo.holo_key));
        if (formOpen && formViewer) aimViewer(formViewer, holo, formAngle);
        // The viewer's load event lands here: swap the plain cues for the figure
        const panel = $('[data-phase-panel="set"]');
        if (panel) panel.dataset.holo = holoState(holo);
    } else if (formOpen) {
        closeFormCheck();
        return;
    }

    const active = holo && document.visibilityState === 'visible'
        ? (formOpen ? formViewer : stageViewer)
        : null;
    [stageViewer, formViewer].forEach(viewer => {
        if (viewer && viewer !== active && viewer.loaded && !viewer.paused) viewer.pause();
    });
    if (active && !holoFrame) {
        holoFrame = requestAnimationFrame(holoLoop);
    } else if (!active && holoFrame) {
        cancelAnimationFrame(holoFrame);
        holoFrame = null;
    }
    const slowBtn = $('#holo-slow-btn');
    if (slowBtn) slowBtn.setAttribute('aria-pressed', holoSlow ? 'true' : 'false');
}

function cycleHoloAngle() {
    const holo = currentHolo();
    if (!holo || !stageViewer) return;
    const current = angleFor(holo.holo_key);
    const next = HOLO_ANGLE_ORDER[(HOLO_ANGLE_ORDER.indexOf(current) + 1) % HOLO_ANGLE_ORDER.length];
    rememberAngle(holo.holo_key, next);
    syncHologram();
}

function toggleHoloSlow() {
    holoSlow = !holoSlow;
    syncHologram();
}

function paintFormAngles() {
    $all('[data-form-angle]').forEach(btn => {
        btn.setAttribute('aria-pressed', btn.dataset.formAngle === formAngle ? 'true' : 'false');
    });
}

function openFormCheck(trigger) {
    const holo = currentHolo();
    const layer = $('#arena-form-layer');
    if (!holo || !layer.hidden) return;
    formOpener = trigger || document.activeElement;
    formAngle = angleFor(holo.holo_key);

    $('#form-check-title').textContent = holo.exercise.title;
    const cues = (holo.cues || []).slice(0, 2);
    $all('[data-pin]', layer).forEach((pin, i) => {
        pin.hidden = !cues[i];
        if (cues[i]) $('.form-pin-label', pin).textContent = cues[i].pin;
    });
    const how = $('#form-how');
    how.textContent = holo.how || '';
    how.hidden = !holo.how;
    $('#form-cues').hidden = cues.length === 0;
    $('#form-cue-list').innerHTML = cues.map((cue, i) => `
        <li><span class="form-cue-num" dir="ltr">${i + 1}</span><span class="form-cue-text">${escapeHtml(cue.text)}</span></li>
    `).join('');
    paintTempo(layer, holo.tempo);
    paintFormAngles();

    layer.hidden = false;
    $all('.arena-phase').forEach(el => el.setAttribute('inert', ''));
    if (!formViewer) formViewer = createViewer($('#form-figure'), true);
    layer.scrollTop = 0;
    layer.focus({ preventScroll: true });
    syncHologram();
}

// Closing only hides the look — the set and any timer kept running underneath.
function closeFormCheck() {
    const layer = $('#arena-form-layer');
    if (!layer || layer.hidden) return;
    layer.hidden = true;
    $all('.arena-phase').forEach(el => el.removeAttribute('inert'));
    syncHologram();
    if (formOpener && formOpener.focus && formOpener.offsetParent) formOpener.focus({ preventScroll: true });
}

function wireHologram() {
    const angleBtn = $('#holo-angle-btn');
    if (angleBtn) angleBtn.addEventListener('click', cycleHoloAngle);
    const slowBtn = $('#holo-slow-btn');
    if (slowBtn) slowBtn.addEventListener('click', toggleHoloSlow);

    const layer = $('#arena-form-layer');
    if (!layer) return;
    layer.addEventListener('click', (e) => {
        if (e.target.closest('[data-form-close]')) { closeFormCheck(); return; }
        const angleChoice = e.target.closest('[data-form-angle]');
        if (angleChoice && formViewer) {
            const holo = currentHolo();
            formAngle = angleChoice.dataset.formAngle;
            if (holo) rememberAngle(holo.holo_key, formAngle);
            formViewer.dataset.angle = formAngle;
            setOrbit(formViewer, formAngle, holo && holo.holo_key);
            paintFormAngles();
        }
    });
    layer.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { e.preventDefault(); closeFormCheck(); return; }
        if (e.key !== 'Tab') return;
        const items = $all('button:not([disabled])', layer).filter(el => el.offsetParent !== null);
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === layer)) {
            e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault(); first.focus();
        }
    });
}

// ====================== SET ACTIONS ======================

function completeCurrentSet(opts = {}) {
    const pos = currentPosition();
    if (!pos) return;
    if (isHolding()) {
        finishHold(Math.floor((Date.now() - holdStartedAt) / 1000));
        return;
    }
    const { exercise, set } = pos;

    // Resting far past the plan breaks the chain
    if (lastRestEnd && Date.now() - lastRestEnd > COMBO_REST_GRACE_MS) comboCount = 0;
    lastRestEnd = null;

    set.done = true;
    set.skipped = false;
    comboCount++;
    spawnXpFloat($('#arena-done-btn'), XP_PER_SET + set.reps);
    if (!opts.silent) cue('set', 12);

    const record = checkPersonalRecord(exercise, set);
    const next = advanceCursor();
    if (next && set.rest > 0) {
        restTip = pickCoachTip(exercise);
        startRestTimer(set.rest);
    } else {
        arenaPhase = 'set';
        renderArena();
    }
    updateSessionScore(true);
    updateComboIndicator();
    saveSession();
    if (record) showPrToast(record);
}

function skipCurrentSet() {
    const pos = currentPosition();
    if (!pos) return;
    stopHoldTimer();
    pos.set.skipped = true;
    comboCount = 0;
    lastRestEnd = null;
    advanceCursor();
    arenaPhase = 'set';
    renderArena();
    updateComboIndicator();
    saveSession();
}

function arenaStepReps(delta) {
    const pos = currentPosition();
    if (!pos || isHolding()) return;
    pos.set.reps = clampInt(pos.set.reps + delta, 0, 999);
    renderSetPanel();
    saveSession();
}

// ====================== PERSONAL RECORDS ======================

function checkPersonalRecord(exercise, set) {
    const record = data().records[exercise.name];
    if (!record || prShown[exercise.name] || set.reps <= record.best) return null;
    prShown[exercise.name] = true;
    return { title: exercise.title, reps: set.reps, previous: record.best, unit: unitLabel(exercise) };
}

let prToastTimer = null;

function showPrToast(record) {
    const layer = $('#arena-pr-layer');
    if (!layer) return;
    cue('pr', [30, 40, 30]);
    const inTitle = /^[֐-׿]/.test(record.title) ? `ב${record.title}` : `· ${record.title}`;
    $('#arena-pr-detail').innerHTML =
        `${numHtml(record.reps)} ${escapeHtml(record.unit || 'חזרות')} ${escapeHtml(inTitle)} · הקודם ${numHtml(record.previous)}`;
    $('#arena-pr-delta').textContent = `+${record.reps - record.previous}`;
    layer.hidden = false;
    requestAnimationFrame(() => layer.classList.add('is-open'));
    clearTimeout(prToastTimer);
    prToastTimer = setTimeout(hidePrToast, PR_TOAST_MS);
}

function hidePrToast() {
    const layer = $('#arena-pr-layer');
    if (!layer || layer.hidden) return;
    clearTimeout(prToastTimer);
    layer.classList.remove('is-open');
    setTimeout(() => { layer.hidden = true; }, reducedMotion.matches ? 0 : 200);
}

// ====================== SESSION SCORE HUD ======================

function computeSessionScore() {
    let score = 0;
    activeExercises.forEach(ex => {
        ex.sets.forEach(set => {
            if (set.done) score += XP_PER_SET + set.reps;
        });
    });
    return score;
}

function updateSessionScore(bump) {
    const scoreEl = $('#session-score');
    if (!scoreEl) return;
    scoreEl.textContent = computeSessionScore();
    if (!bump) return;
    scoreEl.classList.remove('is-bumped');
    void scoreEl.offsetWidth; // restart the CSS animation
    scoreEl.classList.add('is-bumped');
}

function updateComboIndicator() {
    const indicator = $('#combo-indicator');
    const countEl = $('#combo-count');
    if (!indicator || !countEl) return;

    const show = comboCount >= 2 && arenaPhase === 'set' && !!currentPosition();
    indicator.hidden = !show;
    if (!show) return;
    countEl.textContent = comboCount;
    indicator.classList.remove('is-popped');
    void indicator.offsetWidth;
    indicator.classList.add('is-popped');
}

// Floating "+XP" rising from the anchor. Pass a number for XP, or any string.
function spawnXpFloat(anchorEl, xp) {
    if (!anchorEl || reducedMotion.matches) return;
    const rect = anchorEl.getBoundingClientRect();
    const float = document.createElement('div');
    float.className = 'xp-float';
    float.setAttribute('dir', 'ltr');
    float.textContent = typeof xp === 'number' ? `+${xp} XP` : xp;
    float.style.left = `${rect.left + rect.width / 2 - 30}px`;
    float.style.top = `${rect.top - 8}px`;
    document.body.appendChild(float);
    setTimeout(() => float.remove(), 1300);
}

// ====================== REST SCREEN ======================

function formatRestTime(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function restRemainingSeconds() {
    if (!restEndsAt) return 0;
    return Math.max(0, Math.ceil((restEndsAt - Date.now()) / 1000));
}

function startRestTimer(seconds) {
    if (seconds <= 0) return;
    resumeRest(Date.now() + seconds * 1000, seconds);
}

function resumeRest(endsAt, duration) {
    clearTimeout(restAutoAdvance);
    isTimerFinished = false;
    restLastTick = null;
    restDuration = duration;
    restEndsAt = endsAt;
    if (!restTip) {
        const pos = currentPosition();
        restTip = pickCoachTip(pos && pos.exercise);
    }
    $('[data-phase-panel="rest"]').classList.remove('is-finished');
    $('#rest-ring-label').textContent = 'עד הסט הבא';

    arenaPhase = 'rest';
    renderArena();
    updateComboIndicator();

    if (restTimerInterval) clearInterval(restTimerInterval);
    restTimerInterval = setInterval(tickRestTimer, 250);
    tickRestTimer();
    saveSession();
}

function tickRestTimer() {
    const remaining = restRemainingSeconds();
    updateRestTimerDisplay(remaining);
    if (remaining <= 3 && remaining > 0 && restLastTick !== remaining) {
        restLastTick = remaining;
        cue('tick', 15);
    }
    if (remaining <= 0) {
        if (restTimerInterval) clearInterval(restTimerInterval);
        handleRestTimerCompletion();
    }
}

function updateRestTimerDisplay(remaining) {
    const clock = $('#timer-banner-clock');
    if (clock) clock.textContent = formatRestTime(remaining);
    const ring = $('#rest-ring');
    if (ring && restDuration > 0) {
        const pct = Math.min(100, Math.max(0, 100 * remaining / restDuration));
        ring.style.setProperty('--pct', `${pct}%`);
    }
}

function handleRestTimerCompletion() {
    if (isTimerFinished) return;
    isTimerFinished = true;
    $('[data-phase-panel="rest"]').classList.add('is-finished');
    $('#rest-ring-label').textContent = 'הזמן עבר';
    cue('end', [40, 60, 40]);

    // After a short alert, bring the next set on screen by itself
    const wait = Math.max(0, restEndsAt + REST_AUTO_ADVANCE_MS - Date.now());
    restAutoAdvance = setTimeout(() => {
        if (isTimerFinished && arenaPhase === 'rest') skipRestTimer();
    }, wait);
}

function adjustRestTimer(amount) {
    if (isTimerFinished) {
        // A finished timer restarts with the added time
        if (amount > 0) startRestTimer(amount);
        return;
    }
    if (!restEndsAt) return;
    restEndsAt += amount * 1000;
    restDuration = Math.max(1, restDuration + amount);
    tickRestTimer();
    saveSession();
}

function stopRestTimer() {
    if (restTimerInterval) clearInterval(restTimerInterval);
    clearTimeout(restAutoAdvance);
    isTimerFinished = false;
    restLastTick = null;
    restEndsAt = null;
    restTip = '';
}

// "אני מוכן" — end the rest and show the next set
function skipRestTimer() {
    if (restEndsAt) lastRestEnd = restEndsAt;
    stopRestTimer();
    if (arenaPhase === 'rest') {
        arenaPhase = 'set';
        renderArena();
        updateComboIndicator();
        saveSession();
    }
}

// ====================== EXERCISE SHEET (2d) ======================

let sheetOpener = null;
let expandedExerciseId = null;

function openArenaSheet(trigger) {
    const layer = $('#arena-sheet-layer');
    if (!layer || !layer.hidden) return;
    sheetOpener = trigger || document.activeElement;
    const pos = currentPosition();
    expandedExerciseId = null;
    renderSheet();
    layer.hidden = false;
    $all('.arena-phase').forEach(el => el.setAttribute('inert', ''));
    $('#arena-sheet').style.transform = '';
    requestAnimationFrame(() => layer.classList.add('is-open'));
    $('#arena-sheet').focus({ preventScroll: true });
    // Bring the current exercise into view
    if (pos) {
        const row = $(`.sheet-ex[data-ex="${pos.exercise.id}"]`);
        if (row) row.scrollIntoView({ block: 'nearest' });
    }
}

function closeArenaSheet(instant) {
    const layer = $('#arena-sheet-layer');
    if (!layer || layer.hidden) return;
    layer.classList.remove('is-open');
    $all('.arena-phase').forEach(el => el.removeAttribute('inert'));
    const done = () => {
        layer.hidden = true;
        $('#arena-sheet').style.transform = '';
        if (sheetOpener && sheetOpener.focus && document.contains(sheetOpener)) {
            sheetOpener.focus({ preventScroll: true });
        }
    };
    if (instant === true || reducedMotion.matches) done();
    else setTimeout(done, 240);
}

function renderSheet() {
    const list = $('#arena-sheet-list');
    if (!list) return;
    const pos = currentPosition();

    if (!activeExercises.length) {
        list.innerHTML = '<p class="rest-next-sub">עוד לא נוספו תרגילים.</p>';
    } else {
        list.innerHTML = activeExercises.map((ex, idx) => {
            const done = ex.sets.filter(s => s.done).length;
            const allResolved = ex.sets.every(isResolved);
            const isCurrent = pos && pos.exercise === ex;
            const state = isCurrent ? 'is-current' : (allResolved && done > 0 ? 'is-done' : '');
            const badge = isCurrent ? '🏋️' : (state === 'is-done' ? '✓' : numHtml(idx + 1));
            const open = ex.id === expandedExerciseId;
            return `
            <div class="sheet-ex ${state} ${open ? 'is-open' : ''}" data-ex="${ex.id}">
                <button type="button" class="sheet-ex-row" data-sheet-toggle="${ex.id}" aria-expanded="${open}">
                    <span class="sheet-ex-badge" aria-hidden="true">${badge}</span>
                    <span class="sheet-ex-name">${escapeHtml(ex.title)}</span>
                    <span class="sheet-ex-count" dir="ltr">${done}/${ex.sets.length}</span>
                    <span class="sheet-ex-chev" aria-hidden="true">⌄</span>
                </button>
                ${open ? sheetExerciseBody(ex, isCurrent) : ''}
            </div>`;
        }).join('');
    }

    const stats = sessionStats();
    const finishBtn = $('#arena-finish-early');
    if (finishBtn) {
        const early = stats.pending > 0;
        finishBtn.textContent = early ? 'סיום מוקדם' : 'סיום ושמירה';
        finishBtn.classList.toggle('is-danger', early);
        finishBtn.classList.toggle('is-finish', !early);
    }
}

function sheetExerciseBody(ex, isCurrent) {
    const unit = unitLabel(ex);
    const one = unit === 'שניות' ? 'שנייה' : 'חזרה';
    const rows = ex.sets.map((set, idx) => {
        const toggleClass = set.done ? 'is-done' : (set.skipped ? 'is-skipped' : '');
        const toggleLabel = set.done ? '✓' : (set.skipped ? 'דולג' : '✓');
        return `
        <div class="sheet-set">
            <span class="sheet-set-index" aria-hidden="true">${idx + 1}</span>
            <div class="sheet-stepper">
                <button type="button" onclick="stepSetValue('${ex.id}', '${set.id}', 'reps', -1)" aria-label="הפחת ${one} בסט ${idx + 1}">−</button>
                <input type="number" value="${set.reps}" min="0" max="999" inputmode="numeric" pattern="[0-9]*"
                       aria-label="${unit} בסט ${idx + 1}" data-set-input="${set.id}"
                       onchange="updateSetData('${ex.id}', '${set.id}', 'reps', this.value)">
                <span class="sheet-stepper-unit">${unit}</span>
                <button type="button" onclick="stepSetValue('${ex.id}', '${set.id}', 'reps', 1)" aria-label="הוסף ${one} בסט ${idx + 1}">+</button>
            </div>
            <button type="button" class="sheet-set-toggle ${toggleClass}" onclick="toggleSetDone('${ex.id}', '${set.id}')"
                    aria-pressed="${set.done}" aria-label="סט ${idx + 1} בוצע">${toggleLabel}</button>
            <button type="button" class="sheet-set-del" onclick="removeSet('${ex.id}', '${set.id}')" aria-label="מחק סט ${idx + 1}">
                <i class="fas fa-trash-alt" aria-hidden="true"></i>
            </button>
        </div>`;
    }).join('');

    const canJump = !isCurrent && ex.sets.some(s => !s.done);
    return `
    <div class="sheet-ex-body">
        ${rows}
        <div class="sheet-ex-actions">
            <button type="button" onclick="addSet('${ex.id}')">+ סט</button>
            ${canJump ? `<button type="button" onclick="jumpToExercise('${ex.id}')">לתרגיל הזה</button>` : ''}
            <button type="button" class="is-danger" onclick="removeExercise('${ex.id}')">הסר תרגיל</button>
        </div>
    </div>`;
}

function wireArenaSheet() {
    const layer = $('#arena-sheet-layer');
    const sheet = $('#arena-sheet');
    if (!layer || !sheet) return;

    layer.addEventListener('click', (e) => {
        if (e.target.closest('[data-sheet-close]')) { closeArenaSheet(); return; }
        const toggle = e.target.closest('[data-sheet-toggle]');
        if (toggle) {
            const id = toggle.dataset.sheetToggle;
            expandedExerciseId = expandedExerciseId === id ? null : id;
            renderSheet();
            const row = $(`.sheet-ex[data-ex="${id}"] .sheet-ex-row`);
            if (row) row.focus({ preventScroll: true });
        }
    });

    layer.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { e.preventDefault(); closeArenaSheet(); return; }
        if (e.key !== 'Tab') return;
        const items = $all('button:not([disabled]), input, select, summary, [href]', sheet)
            .filter(el => el.offsetParent !== null);
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === sheet)) {
            e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault(); first.focus();
        }
    });

    // Drag the grab handle down to dismiss
    const handle = $('[data-sheet-handle]', sheet);
    let dragStart = null;
    handle.addEventListener('pointerdown', (e) => {
        dragStart = e.clientY;
        handle.setPointerCapture(e.pointerId);
        sheet.classList.add('is-dragging');
    });
    handle.addEventListener('pointermove', (e) => {
        if (dragStart === null) return;
        sheet.style.transform = `translateY(${Math.max(0, e.clientY - dragStart)}px)`;
    });
    const endDrag = (e) => {
        if (dragStart === null) return;
        const dy = e.clientY - dragStart;
        dragStart = null;
        sheet.classList.remove('is-dragging');
        if (dy > 80) closeArenaSheet(); else sheet.style.transform = '';
    };
    handle.addEventListener('pointerup', endDrag);
    handle.addEventListener('pointercancel', endDrag);
}

function refreshAfterEdit() {
    if (!currentPosition()) advanceCursor();
    renderArena();
    updateSessionScore(false);
    updateComboIndicator();
    saveSession();
}

function jumpToExercise(exerciseId) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise || !pointCursorAt(exercise)) return;
    if (arenaPhase === 'rest') stopRestTimer();
    arenaPhase = 'set';
    closeArenaSheet();
    refreshAfterEdit();
}

function finishEarly() {
    const { pending } = sessionStats();
    if (pending > 0) {
        const left = pending === 1 ? 'סט אחד עדיין לא בוצע' : `${pending} סטים עדיין לא בוצעו`;
        if (!confirm(`לסיים את האימון עכשיו? ${left}.`)) return;
    }
    finishWorkout();
}

// ====================== EXERCISE PICKER ======================

function openExerciseModal() {
    const modal = $('#exercise-modal');
    if (!modal || modal.classList.contains('active')) return;
    modal.classList.add('active');
    lockPageScroll();
}

function closeExerciseModal() {
    const modal = $('#exercise-modal');
    if (!modal || !modal.classList.contains('active')) return;
    modal.classList.remove('active');
    unlockPageScroll();
}

function closeExerciseModalOnBackdrop(event) {
    if (event.target === $('#exercise-modal')) closeExerciseModal();
}

// ====================== EXERCISE / SET OPERATIONS ======================

function addExerciseToSession(exercise, pathKey, workoutType) {
    closeExerciseModal();
    if (!sessionActive) {
        beginSession([exercise], pathKey || null, workoutType || 'Calisthenics');
        return;
    }
    activeExercises.push(exercise);
    plannedSets += exercise.sets.length;
    if (!currentPosition()) {
        pointCursorAt(exercise);
        if (arenaPhase === 'rest') stopRestTimer();
        arenaPhase = 'set';
    }
    expandedExerciseId = null;
    refreshAfterEdit();
}

function addExerciseByName(name) {
    const meta = data().catalog[name] || {};
    addExerciseToSession(buildExercise(
        { name, title: meta.title || name, category: meta.category || 'general' },
        DEFAULT_NEW_EXERCISE.sets, DEFAULT_NEW_EXERCISE.reps, DEFAULT_NEW_EXERCISE.rest
    ));
}

function addCustomExercise() {
    const input = $('#custom-exercise-name');
    const name = input ? input.value.trim() : '';
    if (!name) return;
    addExerciseByName(name);
    if (input) input.value = '';
}

// Desktop skill guide "+ אימון": one station of a path
function addSkillProgression(skillKey, stageIndex) {
    const station = (data().stations[skillKey] || [])[stageIndex];
    const path = data().paths[skillKey];
    if (!station || !path) return;
    const exercise = buildExercise(
        { name: station.name, title: station.title, category: path.category, skill_key: skillKey, stage_index: stageIndex },
        DEFAULT_NEW_EXERCISE.sets, station.reps, station.rest
    );
    addExerciseToSession(exercise, skillKey, path.workout_type);
}

function removeExercise(exerciseId) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return;
    if (exercise.sets.some(s => s.done)
        && !confirm(`להסיר את "${exercise.title}"? הסטים שכבר סומנו בו יימחקו.`)) return;

    activeExercises = activeExercises.filter(ex => ex.id !== exerciseId);
    if (cursor && cursor.exerciseId === exerciseId) cursor = null;
    if (arenaPhase === 'rest' && !activeExercises.some(ex => ex.sets.some(s => !isResolved(s)))) stopRestTimer();
    if (!restEndsAt) arenaPhase = 'set';
    refreshAfterEdit();
}

function addSet(exerciseId) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return;

    // Copy reps/rest from the last set
    const last = exercise.sets[exercise.sets.length - 1];
    const set = {
        id: uid('set'),
        reps: last ? last.reps : DEFAULT_NEW_EXERCISE.reps,
        rest: last ? last.rest : DEFAULT_NEW_EXERCISE.rest,
        done: false,
        skipped: false,
    };
    exercise.sets.push(set);
    plannedSets++;
    if (!currentPosition()) cursor = { exerciseId, setId: set.id };
    refreshAfterEdit();
}

function removeSet(exerciseId, setId) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return;

    const target = exercise.sets.find(s => s.id === setId);
    if (target && target.done && !confirm('הסט הזה כבר סומן כבוצע. למחוק אותו בכל זאת?')) return;

    exercise.sets = exercise.sets.filter(s => s.id !== setId);
    if (exercise.sets.length === 0) {
        activeExercises = activeExercises.filter(ex => ex.id !== exerciseId);
    }
    if (cursor && cursor.setId === setId) advanceCursor();
    refreshAfterEdit();
}

function updateSetData(exerciseId, setId, field, value) {
    const found = findSet(exerciseId, setId);
    if (!found || (field !== 'reps' && field !== 'rest')) return;

    const clamped = clampInt(value, 0, 999);
    found.set[field] = clamped;

    // Reflect the clamped value back so garbage input never lingers on screen
    const input = $(`[data-set-input="${setId}"]`);
    if (input && field === 'reps' && String(input.value) !== String(clamped)) input.value = clamped;

    if (arenaPhase === 'set') renderSetPanel();
    updateSessionScore(false);
    saveSession();
}

// +/- stepper buttons in the sheet
function stepSetValue(exerciseId, setId, field, delta) {
    const found = findSet(exerciseId, setId);
    if (!found) return;
    updateSetData(exerciseId, setId, field, (found.set[field] || 0) + delta);
}

// Sheet correction: mark / unmark a set without the rest flow
function toggleSetDone(exerciseId, setId) {
    const found = findSet(exerciseId, setId);
    if (!found) return;
    const set = found.set;

    if (set.done) {
        set.done = false;
        comboCount = 0; // breaking the chain resets the combo
        if (!currentPosition()) cursor = { exerciseId, setId };
    } else {
        set.done = true;
        set.skipped = false;
        comboCount++;
        const record = checkPersonalRecord(found.exercise, set);
        if (record) showPrToast(record);
    }
    refreshAfterEdit();
}

// ====================== FINISH WORKOUT & POST ======================

async function finishWorkout() {
    const stats = sessionStats();
    if (activeExercises.length === 0 || stats.doneSets === 0) {
        alert('נא לסמן לפחות סט אחד כבוצע לפני שמירת האימון!');
        return;
    }

    const durationMinutes = Math.round((Date.now() - workoutStartTime) / 60000) || 1; // minimum 1 minute

    const exercisesData = [];
    activeExercises.forEach(ex => {
        const doneSets = ex.sets.filter(s => s.done);
        if (!doneSets.length) return;
        exercisesData.push({
            exercise_name: ex.name,
            total_sets: doneSets.length,
            total_reps: doneSets.reduce((sum, s) => sum + s.reps, 0),
            max_reps: Math.max(...doneSets.map(s => s.reps)),
            skill_key: ex.skill_key,
            stage_index: ex.stage_index,
        });
    });

    const payload = {
        date: $('#workout-date').value || todayIso(),
        workout_type: $('#workout-type').value,
        total_duration: durationMinutes,
        exercises: exercisesData,
    };

    // Buttons locked so a double-tap can't save twice
    const buttons = [$('#finish-workout-btn'), $('#arena-finish-early')].filter(Boolean);
    buttons.forEach(btn => { btn.disabled = true; });
    const unlock = () => buttons.forEach(btn => { btn.disabled = false; });

    try {
        const response = await fetch('/workouts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const result = await response.json();

        if (response.ok && result.status === 'success') {
            // The workout is safely on the server — stop the session
            sessionActive = false;
            clearSavedSession();
            if (workoutTimerInterval) clearInterval(workoutTimerInterval);
            stopRestTimer();
            releaseWakeLock();
            unlock();
            showReward(result.rewards, {
                minutes: durationMinutes,
                doneSets: stats.doneSets,
                doneReps: stats.doneReps,
                planned: plannedSets || stats.total,
                skipped: stats.skipped,
                pending: stats.pending,
            });
        } else {
            unlock();
            alert(`שגיאה בשמירת האימון: ${result.message || 'שגיאה כללית בשרת'}`);
        }
    } catch (error) {
        console.error('Save workout request failed', error);
        unlock();
        alert('נכשלה ההתקשרות עם השרת. האימון שלך לא אבד — אפשר לנסות לשמור שוב.');
    }
}

// ====================== REWARD SCREEN ======================

function animateCountUp(el, target, durationMs, format) {
    if (!el) return;
    if (reducedMotion.matches) { el.textContent = format(target); return; }
    const start = performance.now();
    const step = (now) => {
        const progress = Math.min((now - start) / durationMs, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        el.textContent = format(Math.round(target * eased));
        if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
}

function rewardRow(kind, tileHtml, title, sub) {
    return `
    <div class="reward-row is-${kind}">
        <span class="reward-row-tile" aria-hidden="true">${tileHtml}</span>
        <div class="reward-row-text">
            <div class="reward-row-title">${title}</div>
            <div class="reward-row-sub">${sub}</div>
        </div>
    </div>`;
}

// 7.5 stays 7.5, 12 stays 12 — the reward screen quotes the average set as saved
function formatAverage(value) {
    return Number.isInteger(value) ? formatNumber(value) : String(value);
}

function fillRows(containerId, rows) {
    const container = $(containerId);
    if (!container) return;
    container.innerHTML = rows.join('');
    container.hidden = rows.length === 0;
}

function showReward(rewards, stats) {
    if (!rewards) {
        // Fallback if the server didn't send rewards (e.g. an older cached response)
        alert('האימון נשמר בהצלחה!');
        window.location.reload();
        return;
    }

    closeArenaSheet(true);
    closeFormCheck();
    hidePrToast();
    arenaPhase = 'reward';
    renderArena();
    const panel = $('[data-phase-panel="reward"]');
    panel.scrollTop = 0;

    $('#reward-summary').innerHTML = [
        countHtml(stats.minutes, 'דקה אחת', 'דקות'),
        countHtml(stats.doneSets, 'סט אחד', 'סטים'),
        countHtml(stats.doneReps, 'חזרה אחת', 'חזרות'),
    ].join(' · ');

    // Stars: ① finished ② hit the planned sets ③ nothing skipped or left behind
    const earned = [true, stats.doneSets >= stats.planned, stats.skipped === 0 && stats.pending === 0];
    $all('.reward-star', panel).forEach((star, idx) => star.classList.toggle('is-earned', earned[idx]));
    const hints = [];
    if (!earned[1]) hints.push(`הכוכב השני: להשלים את כל ${stats.planned} הסטים המתוכננים`);
    if (!earned[2]) hints.push('הכוכב השלישי: לסיים בלי לדלג על סט');
    $('#reward-star-hints').innerHTML = hints.map(escapeHtml).join('<br>');
    $('#victory-stars').setAttribute('aria-label', `${earned.filter(Boolean).length} מתוך 3 כוכבים`);

    animateCountUp($('#victory-xp'), rewards.xp_gained, 900, n => `+${formatNumber(n)} XP`);
    $('#reward-total').innerHTML = `סה״כ ${numHtml(`${formatNumber(rewards.total_xp)} XP`)}`;

    $('#victory-level').textContent = `שלב ${rewards.new_level} ← ${rewards.new_level + 1}`;
    $('#victory-xp-label').textContent = `${formatNumber(rewards.xp_in_level)} / ${formatNumber(rewards.xp_for_next)}`;
    const bar = $('#victory-xp-bar');
    bar.style.width = '0%';
    setTimeout(() => { bar.style.width = `${rewards.progress_pct}%`; }, reducedMotion.matches ? 0 : 400);

    const nextRank = rewards.next_rank;
    $('#reward-next-rank').innerHTML = nextRank && nextRank.title
        ? `עוד ${numHtml(`${formatNumber(nextRank.xp_needed)} XP`)} לדרגת <b>${escapeHtml(nextRank.title)}</b>`
        : `הגעת לדרגה הגבוהה ביותר — <b>${escapeHtml(rewards.rank.title)}</b>`;

    const levelUp = $('#victory-levelup');
    levelUp.hidden = !rewards.leveled_up;
    if (rewards.leveled_up) {
        levelUp.innerHTML = `עלית שלב! ברוך הבא לשלב ${numHtml(rewards.new_level)} · ${escapeHtml(rewards.rank.title)}`;
        cue('levelup', [30, 50, 30, 50, 80]);
    }

    fillRows('#victory-achievements', (rewards.new_achievements || []).map(a => rewardRow(
        'achievement', `<i class="fas ${escapeHtml(a.icon)}"></i>`,
        `הישג חדש · ${escapeHtml(a.title)}`, escapeHtml(a.desc)
    )));
    fillRows('#reward-stations', (rewards.new_stations || []).map(s => rewardRow(
        'station', escapeHtml(s.icon),
        `תחנה נכבשה · ${escapeHtml(s.station)}`,
        s.next ? `מסלול ${escapeHtml(s.path)} · התחנה הבאה: ${escapeHtml(s.next)}` : `מסלול ${escapeHtml(s.path)} הושלם`
    )));
    // Whether each station trained today counted towards conquering it. A conquered
    // station has nothing left to count, and one just conquered has its own row above.
    fillRows('#reward-progress', (rewards.station_progress || [])
        .filter(s => !s.conquered)
        .map(s => s.counted
            ? rewardRow('progress', escapeHtml(s.icon),
                `נספר לכיבוש · ${escapeHtml(s.station)}`,
                `מסלול ${escapeHtml(s.path)} · ${numHtml(s.in_range)} מתוך ${numHtml(s.to_conquer)} אימונים בטווח`)
            : rewardRow('miss', '🎯',
                `לא נספר לכיבוש · ${escapeHtml(s.station)}`,
                `ממוצע ${numHtml(formatAverage(s.average))} ${escapeHtml(s.unit_label)} לסט · `
                + `הטווח לכיבוש הוא ${numHtml(`${s.floor}–${s.target}`)} · עדיין ${numHtml(s.in_range)} מתוך ${numHtml(s.to_conquer)}`)
        ));
    fillRows('#reward-records', (rewards.new_records || []).map(r => rewardRow(
        'record', '📈',
        `שיא אישי · ${numHtml(r.reps)} ${escapeHtml(unitLabelFor(r.exercise_name))}`,
        `${escapeHtml(r.title)} · השיא הקודם היה ${numHtml(r.previous)}${r.previous_ago ? ` · ${escapeHtml(r.previous_ago)}` : ''}`
    )));

    $('#reward-home-btn').focus({ preventScroll: true });
}

// Kept name: the reward's "חזרה למפת המסע" reloads onto the map with server state
function closeVictoryModal() {
    if (location.hash !== '#map') {
        history.replaceState(null, '', `${location.pathname}${location.search}#map`);
    }
    window.location.reload();
}

// ====================== DESKTOP SIDEBAR & SKILL GUIDE ======================

const SIDEBAR_TABS = ['history', 'skills'];

function switchSidebarTab(tabName) {
    SIDEBAR_TABS.forEach(name => {
        const tabBtn = $(`#tab-${name}`);
        const content = $(`#sidebar-${name}-content`);
        const isActive = name === tabName;

        if (tabBtn) {
            tabBtn.classList.toggle('border-indigo-600', isActive);
            tabBtn.classList.toggle('text-indigo-600', isActive);
            tabBtn.classList.toggle('border-transparent', !isActive);
            tabBtn.classList.toggle('text-gray-500', !isActive);
        }
        if (content) content.classList.toggle('hidden', !isActive);
    });

    if (tabName === 'skills') {
        const select = $('#skill-select');
        if (select) displaySkillData(select.value);
    }
}

function displaySkillData(skillKey) {
    $all('.skill-detail-block').forEach(block => block.classList.add('hidden'));
    const selectedBlock = $(`#skill-details-${skillKey}`);
    if (selectedBlock) selectedBlock.classList.remove('hidden');
}

function toggleCuesAccordion(skillKey) {
    const content = $(`#accordion-content-${skillKey}`);
    const icon = $(`#accordion-icon-${skillKey}`);
    if (content) content.classList.toggle('hidden');
    if (icon) icon.classList.toggle('rotate-180');
}

// ====================== LEGACY STATION FLAGS ======================
// Stations used to be conquered with a "כבשתי!" button saved in this browser only.
// They're now counted on the server; send any old flags once, then forget them.

async function migrateLegacySkillProgress() {
    let stored;
    try { stored = localStorage.getItem(SKILL_PROGRESS_KEY); } catch (e) { return; }
    if (stored === null) return;

    let progress = {};
    try {
        const parsed = JSON.parse(stored);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            Object.entries(parsed).forEach(([key, indexes]) => {
                if (!Array.isArray(indexes)) return;
                const valid = indexes.filter(Number.isInteger);
                if (valid.length) progress[key] = valid;
            });
        }
    } catch (e) { /* unreadable — nothing worth keeping */ }

    const forget = () => { try { localStorage.removeItem(SKILL_PROGRESS_KEY); } catch (e) { /* ignore */ } };
    if (!Object.keys(progress).length) { forget(); return; }

    try {
        const response = await fetch('/workouts/legacy-progress', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ progress }),
        });
        if (!response.ok) return; // keep the flags and try again next visit
        forget();
        // The map was rendered before the import; show it with the imported stations
        if (!sessionActive) window.location.reload();
    } catch (e) { /* offline — try again next visit */ }
}
