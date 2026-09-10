// app/frontend/static/js/workout.js

// --- Global Workout State ---
let workoutStartTime = Date.now();
let workoutTimerInterval = null;
let activeExercises = [];
let sessionActive = false;

// --- Global Rest Timer State ---
// Absolute-timestamp based so the countdown stays correct even when the
// mobile browser throttles timers in the background / with the screen off.
let restTimerInterval = null;
let restEndsAt = null;
let restDuration = 0;
let isTimerFinished = false;

// --- Gamification State ---
// Mirrors the server XP formula: every completed set is worth 10 XP + 1 XP per rep.
const XP_PER_SET = 10;
let comboCount = 0; // consecutive completed sets without unchecking

// --- Session persistence (survives refresh / accidental navigation) ---
const WORKOUT_SESSION_KEY = 'workout_active_session_v2';

// --- Screen Wake Lock (keep the phone awake mid-workout) ---
let wakeLock = null;

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

function findSet(exerciseId, setId) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return null;
    const set = exercise.sets.find(s => s.id === setId);
    if (!set) return null;
    return { exercise, set };
}

// ====================== SESSION PERSISTENCE ======================

function saveSession() {
    if (!sessionActive) return;
    try {
        const dateInput = document.getElementById('workout-date');
        const typeSelect = document.getElementById('workout-type');
        localStorage.setItem(WORKOUT_SESSION_KEY, JSON.stringify({
            startedAt: workoutStartTime,
            date: dateInput ? dateInput.value : '',
            type: typeSelect ? typeSelect.value : '',
            exercises: activeExercises
        }));
    } catch (e) { /* private mode — session just won't survive a refresh */ }
}

function clearSavedSession() {
    try { localStorage.removeItem(WORKOUT_SESSION_KEY); } catch (e) { /* ignore */ }
}

function loadSavedSession() {
    try {
        const data = JSON.parse(localStorage.getItem(WORKOUT_SESSION_KEY));
        if (!data || typeof data.startedAt !== 'number' || !Array.isArray(data.exercises)) return null;
        return data;
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
            done: !!(s && s.done)
        }));
        if (sets.length === 0) return;
        result.push({
            id: typeof ex.id === 'string' ? ex.id : uid('ex'),
            name: ex.name,
            sets
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
});

// ====================== INITIALIZE PAGE ======================

document.addEventListener('DOMContentLoaded', () => {
    // 1. Set default date to today in local timezone
    const dateInput = document.getElementById('workout-date');
    if (dateInput && !dateInput.value) {
        const today = new Date();
        const yyyy = today.getFullYear();
        const mm = String(today.getMonth() + 1).padStart(2, '0');
        const dd = String(today.getDate()).padStart(2, '0');
        dateInput.value = `${yyyy}-${mm}-${dd}`;
    }

    // 2. Initialize default skill details
    const select = document.getElementById('skill-select');
    if (select) {
        displaySkillData(select.value);
    }

    // 3. Paint quest stage maps (locked/current/conquered) from saved progress
    renderAllStageMaps();

    // 4. Persist date/type edits mid-session
    const typeSelect = document.getElementById('workout-type');
    if (dateInput) dateInput.addEventListener('change', saveSession);
    if (typeSelect) typeSelect.addEventListener('change', saveSession);

    // 5. Resume an in-progress workout after a refresh/navigation
    const saved = loadSavedSession();
    if (saved) {
        const exercises = sanitizeExercises(saved.exercises);
        activeExercises = exercises;
        workoutStartTime = saved.startedAt;
        if (dateInput && saved.date) dateInput.value = saved.date;
        if (typeSelect && saved.type) typeSelect.value = saved.type;
        resumeWorkoutSession();
    }
});

// ====================== WORKOUT SESSION LIFECYCLE ======================

function showSessionUI() {
    const startContainer = document.getElementById('start-session-container');
    const sessionContainer = document.getElementById('active-workout-session');
    if (startContainer) startContainer.classList.add('hidden');
    if (sessionContainer) sessionContainer.classList.remove('hidden');
}

// --- Start Workout Session (User triggered) ---
function startWorkoutSession() {
    workoutStartTime = Date.now();
    sessionActive = true;
    comboCount = 0;

    showSessionUI();
    updateSessionScore();
    updateComboIndicator();
    startWorkoutTimer();
    requestWakeLock();
    saveSession();
}

// --- Resume a persisted session (after refresh) ---
function resumeWorkoutSession() {
    sessionActive = true;
    comboCount = 0;

    showSessionUI();
    renderActiveExercises();
    updateSessionScore();
    updateComboIndicator();
    startWorkoutTimer();
    requestWakeLock();
}

// --- Cancel the current session entirely ---
function cancelWorkout() {
    if (!confirm('לבטל את האימון הנוכחי? כל הסטים שסומנו יימחקו ולא יישמרו.')) return;

    sessionActive = false;
    clearSavedSession();
    activeExercises = [];
    comboCount = 0;

    if (workoutTimerInterval) clearInterval(workoutTimerInterval);
    skipRestTimer();
    releaseWakeLock();
    renderActiveExercises();

    const startContainer = document.getElementById('start-session-container');
    const sessionContainer = document.getElementById('active-workout-session');
    if (sessionContainer) sessionContainer.classList.add('hidden');
    if (startContainer) startContainer.classList.remove('hidden');
}

// --- Live Workout Timer Logic ---
// Renders elapsed time from workoutStartTime; the caller decides the start point,
// so a resumed session keeps counting from its original start.
function startWorkoutTimer() {
    const timerLabel = document.getElementById('workout-timer');

    if (workoutTimerInterval) clearInterval(workoutTimerInterval);

    const tick = () => {
        const elapsedMs = Date.now() - workoutStartTime;
        const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));

        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;

        let displayStr = '';
        if (hours > 0) {
            displayStr = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        } else {
            displayStr = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }

        if (timerLabel) {
            timerLabel.textContent = displayStr;
        }
    };

    tick();
    workoutTimerInterval = setInterval(tick, 1000);
}

// ====================== MODAL CONTROLS ======================

function openExerciseModal() {
    const modal = document.getElementById('exercise-modal');
    if (modal) {
        modal.classList.add('active');
        // iOS scroll lock: save current scroll position, then fix body in place
        const scrollY = window.scrollY;
        document.body.dataset.scrollY = scrollY;
        document.body.style.top = `-${scrollY}px`;
        document.body.classList.add('modal-open');
    }
}

function closeExerciseModal() {
    const modal = document.getElementById('exercise-modal');
    if (modal) {
        modal.classList.remove('active');
        // iOS scroll lock: restore scroll position after releasing body
        const scrollY = parseInt(document.body.dataset.scrollY || '0', 10);
        document.body.classList.remove('modal-open');
        document.body.style.top = '';
        window.scrollTo(0, scrollY);
    }
}

function closeExerciseModalOnBackdrop(event) {
    if (event.target === document.getElementById('exercise-modal')) {
        closeExerciseModal();
    }
}

// ====================== ACTIVE EXERCISES RENDERING ======================

function toggleEmptyState() {
    const emptyState = document.getElementById('empty-state');
    const workoutActions = document.getElementById('workout-actions');

    if (activeExercises.length === 0) {
        if (emptyState) emptyState.classList.remove('hidden');
        if (workoutActions) workoutActions.classList.add('hidden');
    } else {
        if (emptyState) emptyState.classList.add('hidden');
        if (workoutActions) workoutActions.classList.remove('hidden');
    }
}

function generateSetRowHTML(exercise, set, idx) {
    return `
    <div class="set-row ${set.done ? 'is-done' : ''}" data-set-id="${set.id}" data-exercise-id="${exercise.id}">
        <span class="set-index w-6 text-center text-xs font-black text-gray-400 flex-shrink-0">${idx + 1}</span>
        <div class="stepper-group" aria-label="חזרות">
            <button type="button" class="stepper-btn" onclick="stepSetValue('${exercise.id}', '${set.id}', 'reps', -1)" aria-label="הפחת חזרה">
                <i class="fas fa-minus"></i>
            </button>
            <input type="number" value="${set.reps}" min="0" max="999"
                   class="stepper-input" data-field="reps"
                   inputmode="numeric" pattern="[0-9]*"
                   onchange="updateSetData('${exercise.id}', '${set.id}', 'reps', this.value)">
            <button type="button" class="stepper-btn" onclick="stepSetValue('${exercise.id}', '${set.id}', 'reps', 1)" aria-label="הוסף חזרה">
                <i class="fas fa-plus"></i>
            </button>
        </div>
        <div class="stepper-group" aria-label="מנוחה בשניות">
            <button type="button" class="stepper-btn" onclick="stepSetValue('${exercise.id}', '${set.id}', 'rest', -10)" aria-label="הפחת 10 שניות מנוחה">
                <i class="fas fa-minus"></i>
            </button>
            <input type="number" value="${set.rest}" min="0" max="999"
                   class="stepper-input" data-field="rest"
                   inputmode="numeric" pattern="[0-9]*"
                   onchange="updateSetData('${exercise.id}', '${set.id}', 'rest', this.value)">
            <button type="button" class="stepper-btn" onclick="stepSetValue('${exercise.id}', '${set.id}', 'rest', 10)" aria-label="הוסף 10 שניות מנוחה">
                <i class="fas fa-plus"></i>
            </button>
        </div>
        <button type="button" class="set-done-btn" onclick="toggleSetDone('${exercise.id}', '${set.id}')"
                aria-label="סמן סט כבוצע" aria-pressed="${set.done ? 'true' : 'false'}">
            <i class="fas fa-check"></i>
        </button>
        <button type="button" class="set-del-btn" onclick="removeSet('${exercise.id}', '${set.id}')" aria-label="מחק סט">
            <i class="fas fa-trash-alt text-xs"></i>
        </button>
    </div>
    `;
}

function generateExerciseCardHTML(exercise) {
    const doneCount = exercise.sets.filter(s => s.done).length;
    const allDone = doneCount === exercise.sets.length && exercise.sets.length > 0;
    const rowsHTML = exercise.sets.map((set, idx) => generateSetRowHTML(exercise, set, idx)).join('');

    return `
    <div class="exercise-card bg-white border ${allDone ? 'border-emerald-200' : 'border-gray-200'} shadow-md rounded-2xl p-3.5 sm:p-4 relative" data-exercise-id="${exercise.id}">
        <!-- Card Header -->
        <div class="flex justify-between items-center gap-2 mb-3">
            <div class="min-w-0">
                <h3 class="text-base font-extrabold text-gray-900 leading-tight truncate">${escapeHtml(exercise.name)}</h3>
                <span class="ex-progress text-[11px] font-bold ${allDone ? 'text-emerald-600' : 'text-gray-400'}">${doneCount}/${exercise.sets.length} סטים הושלמו</span>
            </div>
            <button onclick="removeExercise('${exercise.id}')"
                    class="text-gray-400 hover:text-red-500 active:scale-90 transition-colors p-2 rounded-xl hover:bg-red-50 flex-shrink-0"
                    title="הסר תרגיל" aria-label="הסר תרגיל">
                <i class="fas fa-trash-alt"></i>
            </button>
        </div>

        <!-- Column labels (match set-row flex proportions) -->
        <div class="flex items-center gap-1.5 px-2 mb-1.5 text-[10px] font-black text-gray-400 uppercase tracking-wide">
            <span class="w-6 text-center">#</span>
            <span class="flex-1 text-center">חזרות</span>
            <span class="flex-1 text-center">מנוחה (שנ')</span>
            <span class="w-11 text-center">בוצע</span>
            <span class="w-8"></span>
        </div>

        <!-- Set rows -->
        <div class="space-y-2 sets-list" id="sets-list-${exercise.id}">
            ${rowsHTML}
        </div>

        <!-- Card Footer -->
        <button onclick="addSet('${exercise.id}')"
                class="mt-3 w-full inline-flex items-center justify-center gap-1.5 px-3 py-2.5 border border-dashed border-purple-400 hover:border-purple-600 text-purple-700 font-bold text-xs rounded-xl hover:bg-purple-50/50 transition-all active:scale-[0.98]">
            <i class="fas fa-plus"></i>
            הוסף סט
        </button>
    </div>
    `;
}

function renderActiveExercises() {
    const container = document.getElementById('active-exercises');
    if (!container) return;

    container.innerHTML = activeExercises.map(ex => generateExerciseCardHTML(ex)).join('');
    toggleEmptyState();
}

// Re-render a single exercise card in place — cheaper and calmer than
// rebuilding the whole list on every set change.
function renderExerciseCard(exercise) {
    const card = document.querySelector(`.exercise-card[data-exercise-id="${exercise.id}"]`);
    if (!card) {
        renderActiveExercises();
        return;
    }
    const holder = document.createElement('div');
    holder.innerHTML = generateExerciseCardHTML(exercise).trim();
    card.replaceWith(holder.firstElementChild);
}

function updateExerciseProgress(exercise) {
    const card = document.querySelector(`.exercise-card[data-exercise-id="${exercise.id}"]`);
    if (!card) return;
    const doneCount = exercise.sets.filter(s => s.done).length;
    const allDone = doneCount === exercise.sets.length && exercise.sets.length > 0;

    const chip = card.querySelector('.ex-progress');
    if (chip) {
        chip.textContent = `${doneCount}/${exercise.sets.length} סטים הושלמו`;
        chip.classList.toggle('text-emerald-600', allDone);
        chip.classList.toggle('text-gray-400', !allDone);
    }
    card.classList.toggle('border-emerald-200', allDone);
    card.classList.toggle('border-gray-200', !allDone);
}

// ====================== EXERCISE / SET OPERATIONS ======================

function addExercise(name) {
    const newEx = {
        id: uid('ex'),
        name: name,
        sets: [
            { id: uid('set'), reps: 8, rest: 90, done: false }
        ]
    };
    activeExercises.push(newEx);
    closeExerciseModal();
    renderActiveExercises();
    saveSession();
}

function addCustomExercise() {
    const input = document.getElementById('custom-exercise-name');
    const name = input ? input.value.trim() : '';
    if (!name) return;

    addExercise(name);
    if (input) input.value = '';
}

function removeExercise(exerciseId) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return;

    // Deleting completed work deserves a second thought
    if (exercise.sets.some(s => s.done)) {
        if (!confirm(`להסיר את "${exercise.name}"? הסטים שכבר סומנו בו יימחקו.`)) return;
    }

    activeExercises = activeExercises.filter(ex => ex.id !== exerciseId);
    renderActiveExercises();
    updateSessionScore();
    saveSession();
}

function addSet(exerciseId) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return;

    // Copy reps/rest from the last set for a streamlined experience (HEVY style)
    let lastReps = 8;
    let lastRest = 90;
    if (exercise.sets.length > 0) {
        const lastSet = exercise.sets[exercise.sets.length - 1];
        lastReps = lastSet.reps;
        lastRest = lastSet.rest;
    }

    exercise.sets.push({
        id: uid('set'),
        reps: lastReps,
        rest: lastRest,
        done: false
    });

    renderExerciseCard(exercise);
    saveSession();
}

function removeSet(exerciseId, setId) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return;

    const target = exercise.sets.find(s => s.id === setId);
    if (target && target.done && !confirm('הסט הזה כבר סומן כבוצע. למחוק אותו בכל זאת?')) return;

    exercise.sets = exercise.sets.filter(s => s.id !== setId);

    // If no sets are left, remove the exercise card completely
    if (exercise.sets.length === 0) {
        activeExercises = activeExercises.filter(ex => ex.id !== exerciseId);
        renderActiveExercises();
    } else {
        renderExerciseCard(exercise);
    }
    updateSessionScore();
    saveSession();
}

function updateSetData(exerciseId, setId, field, value) {
    const found = findSet(exerciseId, setId);
    if (!found || (field !== 'reps' && field !== 'rest')) return;

    const clamped = clampInt(value, 0, 999);
    found.set[field] = clamped;

    // Reflect the clamped value back so garbage input never lingers on screen
    const input = document.querySelector(`.set-row[data-set-id="${setId}"] .stepper-input[data-field="${field}"]`);
    if (input && String(input.value) !== String(clamped)) {
        input.value = clamped;
    }

    // Reps of an already-completed set affect the live score
    if (field === 'reps' && found.set.done) updateSessionScore();
    saveSession();
}

// +/- stepper buttons — instant, no keyboard needed
function stepSetValue(exerciseId, setId, field, delta) {
    const found = findSet(exerciseId, setId);
    if (!found) return;
    updateSetData(exerciseId, setId, field, (found.set[field] || 0) + delta);
}

function toggleSetDone(exerciseId, setId) {
    const found = findSet(exerciseId, setId);
    if (!found) return;
    const set = found.set;

    set.done = !set.done;

    // Direct DOM manipulation for instant visual response (no full re-render)
    const rowEl = document.querySelector(`.set-row[data-set-id="${setId}"]`);
    if (rowEl) {
        rowEl.classList.toggle('is-done', set.done);
        const doneBtn = rowEl.querySelector('.set-done-btn');
        if (doneBtn) doneBtn.setAttribute('aria-pressed', set.done ? 'true' : 'false');
    }
    updateExerciseProgress(found.exercise);

    // --- Game feedback: XP + combo + rest timer ---
    if (set.done) {
        comboCount++;
        spawnXpFloat(rowEl, XP_PER_SET + set.reps);
        if (navigator.vibrate) navigator.vibrate(40);
        if (set.rest > 0) startRestTimer(set.rest);
    } else {
        comboCount = 0; // breaking the chain resets the combo
    }
    updateSessionScore();
    updateComboIndicator();
    saveSession();
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

function updateSessionScore() {
    const scoreEl = document.getElementById('session-score');
    if (!scoreEl) return;
    scoreEl.textContent = computeSessionScore();
    scoreEl.classList.remove('score-bump');
    void scoreEl.offsetWidth; // restart the CSS animation
    scoreEl.classList.add('score-bump');
}

function updateComboIndicator() {
    const indicator = document.getElementById('combo-indicator');
    const countEl = document.getElementById('combo-count');
    if (!indicator || !countEl) return;

    if (comboCount >= 2) {
        countEl.textContent = comboCount;
        indicator.classList.remove('hidden');
        indicator.classList.remove('combo-pop');
        void indicator.offsetWidth;
        indicator.classList.add('combo-pop');
    } else {
        indicator.classList.add('hidden');
    }
}

// Floating "+XP" particle rising from the completed set row.
// Pass a number for XP, or any string for a custom celebration text.
function spawnXpFloat(anchorEl, xp) {
    if (!anchorEl) return;
    const rect = anchorEl.getBoundingClientRect();
    const float = document.createElement('div');
    float.className = 'xp-float text-lg';
    float.textContent = typeof xp === 'number' ? `+${xp} XP` : xp;
    float.style.left = `${rect.left + rect.width / 2 - 30}px`;
    float.style.top = `${rect.top}px`;
    document.body.appendChild(float);
    setTimeout(() => float.remove(), 1300);
}

// ====================== STICKY REST TIMER ======================

function formatRestTime(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function restRemainingSeconds() {
    if (!restEndsAt) return 0;
    return Math.max(0, Math.ceil((restEndsAt - Date.now()) / 1000));
}

function setBannerFinishedLook(finished) {
    const banner = document.getElementById('rest-timer-banner');
    const bannerIcon = document.getElementById('timer-banner-icon');
    if (banner) banner.classList.toggle('timer-finished', finished);
    if (bannerIcon) {
        if (finished) {
            bannerIcon.className = 'w-10 h-10 bg-white/20 text-white rounded-full flex items-center justify-center text-lg flex-shrink-0';
            bannerIcon.innerHTML = '<i class="fas fa-bell"></i>';
        } else {
            bannerIcon.className = 'w-10 h-10 bg-purple-600/30 text-purple-400 rounded-full flex items-center justify-center text-lg flex-shrink-0';
            bannerIcon.innerHTML = '<i class="fas fa-hourglass-half animate-spin-slow"></i>';
        }
    }
}

function startRestTimer(seconds) {
    if (seconds <= 0) return;

    const banner = document.getElementById('rest-timer-banner');
    if (!banner) return;

    isTimerFinished = false;
    restDuration = seconds;
    restEndsAt = Date.now() + seconds * 1000;

    setBannerFinishedLook(false);
    banner.classList.remove('translate-y-full');

    if (restTimerInterval) clearInterval(restTimerInterval);
    restTimerInterval = setInterval(tickRestTimer, 250);
    tickRestTimer();
}

function tickRestTimer() {
    const remaining = restRemainingSeconds();
    updateRestTimerDisplay(remaining);

    if (remaining <= 0) {
        if (restTimerInterval) clearInterval(restTimerInterval);
        handleRestTimerCompletion();
    }
}

function updateRestTimerDisplay(remaining) {
    const clock = document.getElementById('timer-banner-clock');
    if (clock) {
        clock.textContent = formatRestTime(remaining);
    }
    const progress = document.getElementById('timer-banner-progress');
    if (progress && restDuration > 0) {
        const pct = Math.min(100, Math.max(0, 100 * (1 - remaining / restDuration)));
        progress.style.width = `${pct}%`;
    }
}

function handleRestTimerCompletion() {
    if (isTimerFinished) return;
    isTimerFinished = true;

    setBannerFinishedLook(true);

    // Trigger haptic vibration if supported (mobile browsers)
    if (navigator.vibrate) {
        navigator.vibrate([200, 100, 200, 100, 300]);
    }

    // Auto-close banner after 6 seconds of completion alert
    setTimeout(() => {
        if (isTimerFinished) {
            skipRestTimer();
        }
    }, 6000);
}

function adjustRestTimer(amount) {
    if (isTimerFinished) {
        // If timer was finished, restart it with the adjusted value
        if (amount > 0) startRestTimer(amount);
        return;
    }
    if (!restEndsAt) return;

    restEndsAt += amount * 1000;
    restDuration = Math.max(1, restDuration + amount);
    tickRestTimer();
}

function skipRestTimer() {
    if (restTimerInterval) clearInterval(restTimerInterval);
    isTimerFinished = false;
    restEndsAt = null;

    const banner = document.getElementById('rest-timer-banner');
    if (banner) {
        banner.classList.add('translate-y-full');
        banner.classList.remove('timer-finished');
    }
}

// ====================== FINISH WORKOUT & POST ======================

async function finishWorkout() {
    // 1. Verify there is at least one exercise and at least one completed set
    let totalCompletedSets = 0;
    activeExercises.forEach(ex => {
        ex.sets.forEach(set => {
            if (set.done) totalCompletedSets++;
        });
    });

    if (activeExercises.length === 0 || totalCompletedSets === 0) {
        alert("נא לסמן לפחות סט אחד כבוצע (✓) לפני שמירת האימון!");
        return;
    }

    // 2. Compute duration in minutes
    const elapsedMs = Date.now() - workoutStartTime;
    const durationMinutes = Math.round(elapsedMs / 60000) || 1; // minimum 1 minute

    // 3. Aggregate completed data
    const exercisesData = [];
    activeExercises.forEach(ex => {
        let completedSets = 0;
        let completedReps = 0;

        ex.sets.forEach(set => {
            if (set.done) {
                completedSets++;
                completedReps += set.reps;
            }
        });

        if (completedSets > 0) {
            exercisesData.push({
                exercise_name: ex.name,
                total_sets: completedSets,
                total_reps: completedReps
            });
        }
    });

    const workoutDate = document.getElementById('workout-date').value;
    const workoutType = document.getElementById('workout-type').value;

    const payload = {
        date: workoutDate,
        workout_type: workoutType,
        total_duration: durationMinutes,
        exercises: exercisesData
    };

    // 4. Send POST request — button locked so a double-tap can't save twice
    const finishBtn = document.getElementById('finish-workout-btn');
    const originalBtnHTML = finishBtn ? finishBtn.innerHTML : '';
    if (finishBtn) {
        finishBtn.disabled = true;
        finishBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> שומר אימון...';
    }

    const restoreBtn = () => {
        if (finishBtn) {
            finishBtn.disabled = false;
            finishBtn.innerHTML = originalBtnHTML;
        }
    };

    try {
        const response = await fetch('/workouts', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (response.ok && data.status === 'success') {
            // The workout is safely on the server — stop the session
            sessionActive = false;
            clearSavedSession();
            if (workoutTimerInterval) clearInterval(workoutTimerInterval);
            skipRestTimer();
            releaseWakeLock();

            if (navigator.vibrate) {
                navigator.vibrate([100, 50, 100, 50, 300]);
            }
            // Game-style victory screen with rewards from the server
            showVictoryModal(data.rewards, totalCompletedSets);
        } else {
            restoreBtn();
            alert(`שגיאה בשמירת האימון: ${data.message || 'שגיאה כללית בשרת'}`);
        }
    } catch (error) {
        console.error("Save workout request failed", error);
        restoreBtn();
        alert("נכשלה ההתקשרות עם השרת. האימון שלך לא אבד — אפשר לנסות לשמור שוב.");
    }
}

// ====================== SIDEBAR TABS & SKILL GUIDE ======================

const SIDEBAR_TABS = ['history', 'skills', 'achievements'];

function switchSidebarTab(tabName) {
    SIDEBAR_TABS.forEach(name => {
        const tabBtn = document.getElementById(`tab-${name}`);
        const content = document.getElementById(`sidebar-${name}-content`);
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
        // Auto display selected skill details
        const select = document.getElementById('skill-select');
        if (select) {
            displaySkillData(select.value);
        }
    }
}

function displaySkillData(skillKey) {
    // Hide all skill detail blocks
    const detailBlocks = document.querySelectorAll('.skill-detail-block');
    detailBlocks.forEach(block => block.classList.add('hidden'));

    // Show the selected one
    const selectedBlock = document.getElementById(`skill-details-${skillKey}`);
    if (selectedBlock) {
        selectedBlock.classList.remove('hidden');
    }
}

function toggleCuesAccordion(skillKey) {
    const content = document.getElementById(`accordion-content-${skillKey}`);
    const icon = document.getElementById(`accordion-icon-${skillKey}`);

    if (content) {
        content.classList.toggle('hidden');
    }
    if (icon) {
        icon.classList.toggle('rotate-180');
    }
}

// ====================== VICTORY SCREEN & CONFETTI ======================

function animateCountUp(el, target, durationMs) {
    if (!el) return;
    const start = performance.now();
    const step = (now) => {
        const progress = Math.min((now - start) / durationMs, 1);
        // ease-out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(target * eased);
        if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
}

function launchConfetti(pieceCount) {
    const colors = ['#facc15', '#a855f7', '#22c55e', '#3b82f6', '#f97316', '#ec4899'];
    for (let i = 0; i < pieceCount; i++) {
        const piece = document.createElement('div');
        piece.className = 'confetti-piece';
        const size = 6 + Math.random() * 8;
        piece.style.left = `${Math.random() * 100}vw`;
        piece.style.width = `${size}px`;
        piece.style.height = `${size * (0.4 + Math.random() * 0.8)}px`;
        piece.style.background = colors[Math.floor(Math.random() * colors.length)];
        piece.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
        piece.style.animationDuration = `${2.2 + Math.random() * 2.5}s`;
        piece.style.animationDelay = `${Math.random() * 0.8}s`;
        document.body.appendChild(piece);
        setTimeout(() => piece.remove(), 6000);
    }
}

function showVictoryModal(rewards, completedSets) {
    const modal = document.getElementById('victory-modal');
    if (!modal || !rewards) {
        // Fallback if the server didn't send rewards (e.g. older cached response)
        alert("האימון נשמר בהצלחה!");
        window.location.reload();
        return;
    }

    modal.classList.add('active');
    launchConfetti(90);

    // Stars: 1 for finishing, 2 for a solid session, 3 for a big one
    const starCount = completedSets >= 16 ? 3 : (completedSets >= 8 ? 2 : 1);
    const stars = modal.querySelectorAll('.victory-star');
    stars.forEach((star, idx) => {
        star.classList.toggle('earned', idx < starCount);
    });

    // XP earned count-up
    animateCountUp(document.getElementById('victory-xp'), rewards.xp_gained, 1400);

    // Level + progress bar toward the next level
    const levelEl = document.getElementById('victory-level');
    if (levelEl) levelEl.textContent = rewards.new_level;
    const xpLabel = document.getElementById('victory-xp-label');
    if (xpLabel) xpLabel.textContent = `${rewards.xp_in_level} / ${rewards.xp_for_next} XP`;
    const bar = document.getElementById('victory-xp-bar');
    if (bar) {
        // Animate from 0 to the real progress after the card pops in
        setTimeout(() => { bar.style.width = `${rewards.progress_pct}%`; }, 400);
    }

    // Level-up banner
    if (rewards.leveled_up) {
        const banner = document.getElementById('victory-levelup');
        const newLevelEl = document.getElementById('victory-new-level');
        if (newLevelEl) newLevelEl.textContent = rewards.new_level;
        if (banner) banner.classList.remove('hidden');
        // Extra celebration for a level-up
        setTimeout(() => launchConfetti(60), 900);
    }

    // Newly unlocked achievements
    if (rewards.new_achievements && rewards.new_achievements.length > 0) {
        const container = document.getElementById('victory-achievements');
        if (container) {
            container.innerHTML = rewards.new_achievements.map(ach => `
                <div class="flex items-center gap-3 bg-yellow-400/10 border border-yellow-400/30 rounded-xl px-3 py-2.5">
                    <div class="w-10 h-10 rounded-full bg-gradient-to-br from-yellow-400 to-amber-500 text-white flex items-center justify-center flex-shrink-0">
                        <i class="fas ${ach.icon}"></i>
                    </div>
                    <div>
                        <p class="text-xs font-black text-yellow-300">הישג חדש: ${ach.title}</p>
                        <p class="text-[10px] text-purple-300">${ach.desc}</p>
                    </div>
                </div>
            `).join('');
            container.classList.remove('hidden');
        }
    }
}

function closeVictoryModal() {
    // Reload refreshes the player card, history and achievements with server state
    window.location.reload();
}

// ====================== QUEST STAGE MAP (Skill progressions as game levels) ======================
// Stage completion is personal training progress, persisted locally per browser.

const SKILL_PROGRESS_KEY = 'workout_skill_progress_v1';

function getSkillProgress() {
    try {
        return JSON.parse(localStorage.getItem(SKILL_PROGRESS_KEY)) || {};
    } catch (e) {
        return {};
    }
}

function saveSkillProgress(progress) {
    try {
        localStorage.setItem(SKILL_PROGRESS_KEY, JSON.stringify(progress));
    } catch (e) { /* private mode — progress just won't persist */ }
}

function toggleStageComplete(skillKey, stageIdx) {
    const progress = getSkillProgress();
    const completed = new Set(progress[skillKey] || []);

    if (completed.has(stageIdx)) {
        completed.delete(stageIdx);
    } else {
        completed.add(stageIdx);
        // Small celebration for conquering a stage
        const node = document.getElementById(`stage-${skillKey}-${stageIdx}`);
        spawnXpFloat(node, '⭐');
        if (navigator.vibrate) navigator.vibrate([60, 40, 60]);
        launchConfetti(25);
    }

    progress[skillKey] = Array.from(completed).sort((a, b) => a - b);
    saveSkillProgress(progress);
    renderStageMap(skillKey);
}

function renderStageMap(skillKey) {
    const nodes = document.querySelectorAll(`.stage-node[data-skill="${skillKey}"]`);
    if (!nodes.length) return;

    const completed = new Set(getSkillProgress()[skillKey] || []);
    // The "current" stage is the first uncompleted one
    let currentIdx = 0;
    while (completed.has(currentIdx)) currentIdx++;

    nodes.forEach(node => {
        const idx = parseInt(node.dataset.stage, 10);
        const isDone = completed.has(idx);
        const isCurrent = idx === currentIdx;

        node.classList.toggle('stage-completed', isDone);
        node.classList.toggle('stage-current', isCurrent);
        node.classList.toggle('stage-locked', !isDone && !isCurrent);

        const dotLabel = node.querySelector('.stage-dot-label');
        if (dotLabel) {
            dotLabel.innerHTML = isDone ? '<i class="fas fa-check"></i>'
                : (!isCurrent ? '<i class="fas fa-lock text-[8px]"></i>' : `${idx + 1}`);
        }
        const statusIcon = node.querySelector('.stage-status-icon');
        if (statusIcon) {
            statusIcon.innerHTML = isDone ? '<i class="fas fa-star text-yellow-500 text-[10px]"></i>'
                : (isCurrent ? '<i class="fas fa-location-arrow text-purple-500 text-[10px]"></i>' : '');
        }
        const conquerLabel = node.querySelector('.stage-conquer-label');
        if (conquerLabel) conquerLabel.textContent = isDone ? 'בטל' : 'כבשתי!';
    });

    // Quest progress bar + counter
    const total = nodes.length;
    const doneCount = Math.min(completed.size, total);
    const bar = document.getElementById(`quest-bar-${skillKey}`);
    if (bar) bar.style.width = `${Math.round(doneCount * 100 / total)}%`;
    const counter = document.getElementById(`quest-progress-${skillKey}`);
    if (counter) counter.textContent = `${doneCount}/${total} שלבים`;
}

function renderAllStageMaps() {
    const skillKeys = new Set();
    document.querySelectorAll('.stage-node[data-skill]').forEach(node => skillKeys.add(node.dataset.skill));
    skillKeys.forEach(key => renderStageMap(key));
}

function addSkillProgression(name, hebrew, reps, rest) {
    // 1. If workout session not started, start it
    const sessionContainer = document.getElementById('active-workout-session');
    if (sessionContainer && sessionContainer.classList.contains('hidden')) {
        startWorkoutSession();
    }

    // 2. Build new exercise and add to list
    const cleanHebrewName = hebrew || name;
    const displayName = `${cleanHebrewName} (${name})`;

    activeExercises.push({
        id: uid('ex'),
        name: displayName,
        sets: [
            { id: uid('set'), reps: clampInt(reps, 0, 999), rest: clampInt(rest, 0, 999), done: false }
        ]
    });

    renderActiveExercises();
    saveSession();

    // 3. Smooth scroll to exercises container
    const exercisesContainer = document.getElementById('active-exercises');
    if (exercisesContainer) {
        exercisesContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}
