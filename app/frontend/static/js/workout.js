// app/frontend/static/js/workout.js

// --- Global Workout State ---
let workoutStartTime = Date.now();
let workoutTimerInterval = null;
let activeExercises = [];

// --- Global Rest Timer State ---
let restTimerInterval = null;
let restTimeRemaining = 0;
let isTimerFinished = false;

// --- Gamification State ---
// Mirrors the server XP formula: every completed set is worth 10 XP + 1 XP per rep.
const XP_PER_SET = 10;
let comboCount = 0; // consecutive completed sets without unchecking

// --- Initialize Page ---
document.addEventListener('DOMContentLoaded', () => {
    // 1. Set default date to today in local timezone
    const dateInput = document.getElementById('workout-date');
    if (dateInput) {
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
});

// --- Start Workout Session (User triggered) ---
function startWorkoutSession() {
    workoutStartTime = Date.now();

    const startContainer = document.getElementById('start-session-container');
    const sessionContainer = document.getElementById('active-workout-session');

    if (startContainer) startContainer.classList.add('hidden');
    if (sessionContainer) sessionContainer.classList.remove('hidden');

    // Reset game HUD for the fresh session
    comboCount = 0;
    updateSessionScore();
    updateComboIndicator();

    startWorkoutTimer();
}


// --- Live Workout Timer Logic ---
function startWorkoutTimer() {
    workoutStartTime = Date.now();
    const timerLabel = document.getElementById('workout-timer');
    
    if (workoutTimerInterval) clearInterval(workoutTimerInterval);
    
    workoutTimerInterval = setInterval(() => {
        const elapsedMs = Date.now() - workoutStartTime;
        const totalSeconds = Math.floor(elapsedMs / 1000);
        
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
    }, 1000);
}

// --- Modal Controls ---
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

// --- Active Exercises DOM Rendering ---
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

function generateExerciseCardHTML(exercise) {
    let setsHTML = '';
    exercise.sets.forEach((set, idx) => {
        setsHTML += `
        <tr class="set-row border-b border-gray-100 ${set.done ? 'is-done' : ''}" data-set-id="${set.id}" data-exercise-id="${exercise.id}">
            <td class="py-2 text-center font-bold text-gray-500 text-xs w-8">${idx + 1}</td>
            <td class="py-1.5 text-center w-20">
                <input type="number" value="${set.reps}"
                       class="inline-edit-input w-14 text-center py-1.5 font-bold text-gray-800 rounded-lg"
                       onchange="updateSetData('${exercise.id}', '${set.id}', 'reps', this.value)"
                       inputmode="numeric" pattern="[0-9]*" min="0">
            </td>
            <td class="py-1.5 text-center w-20">
                <input type="number" value="${set.rest}"
                       class="inline-edit-input w-14 text-center py-1.5 text-gray-500 rounded-lg"
                       onchange="updateSetData('${exercise.id}', '${set.id}', 'rest', this.value)"
                       inputmode="numeric" pattern="[0-9]*" min="0">
            </td>
            <td class="py-1.5 text-center w-12">
                <div class="flex justify-center">
                    <input type="checkbox" ${set.done ? 'checked' : ''}
                           class="done-checkbox w-8 h-8 rounded-lg border-2 border-gray-300 text-green-600 focus:ring-green-500 cursor-pointer transition-all"
                           onchange="toggleSetDone('${exercise.id}', '${set.id}', this.checked)">
                </div>
            </td>
            <td class="py-1.5 text-center w-10">
                <button onclick="removeSet('${exercise.id}', '${set.id}')" class="text-gray-400 hover:text-red-500 active:scale-90 transition-colors p-1.5 rounded-lg">
                    <i class="fas fa-trash-alt text-xs"></i>
                </button>
            </td>
        </tr>
        `;
    });

    return `
    <div class="exercise-card bg-white border border-gray-200 shadow-md rounded-2xl p-4 mb-4 relative" data-exercise-id="${exercise.id}">
        <!-- Card Header -->
        <div class="flex justify-between items-center mb-3">
            <h3 class="text-base font-extrabold text-gray-900 leading-tight">${exercise.name}</h3>
            <button onclick="removeExercise('${exercise.id}')"
                    class="text-gray-400 hover:text-red-500 active:scale-90 transition-colors p-2 rounded-xl hover:bg-red-50 flex-shrink-0"
                    title="הסר תרגיל">
                <i class="fas fa-trash-alt"></i>
            </button>
        </div>

        <!-- Sets Table — columns sized to fit iPhone SE (375px) without horizontal scroll -->
        <div class="overflow-x-auto">
            <table class="w-full">
                <thead>
                    <tr class="border-b border-gray-200 text-xs text-gray-400 font-bold uppercase tracking-wider">
                        <th class="pb-2 text-center font-bold w-8">#</th>
                        <th class="pb-2 text-center font-bold">חזרות</th>
                        <th class="pb-2 text-center font-bold">מנוחה</th>
                        <th class="pb-2 text-center font-bold">✓</th>
                        <th class="pb-2 text-center font-bold w-10"></th>
                    </tr>
                </thead>
                <tbody id="sets-tbody-${exercise.id}">
                    ${setsHTML}
                </tbody>
            </table>
        </div>

        <!-- Card Footer -->
        <div class="mt-3 pt-2 flex justify-start">
            <button onclick="addSet('${exercise.id}')"
                    class="inline-flex items-center gap-1.5 px-3 py-2 border border-dashed border-purple-500 hover:border-purple-600 text-purple-700 font-bold text-xs rounded-xl hover:bg-purple-50/50 transition-all active:scale-95">
                <i class="fas fa-plus"></i>
                הוסף סט
            </button>
        </div>
    </div>
    `;
}

function renderActiveExercises() {
    const container = document.getElementById('active-exercises');
    if (!container) return;

    // Get current HTML nodes or completely rebuild
    const exerciseHTMLs = activeExercises.map(ex => generateExerciseCardHTML(ex));
    container.innerHTML = exerciseHTMLs.join('') || '';
    
    toggleEmptyState();
}

// --- Exercise/Set Management Operations ---
function addExercise(name) {
    const newEx = {
        id: 'ex-' + Date.now() + Math.random().toString(36).substr(2, 5),
        name: name,
        sets: [
            { id: 'set-1', reps: 8, rest: 90, done: false }
        ]
    };
    activeExercises.push(newEx);
    closeExerciseModal();
    renderActiveExercises();
}

function addCustomExercise() {
    const input = document.getElementById('custom-exercise-name');
    const name = input ? input.value.trim() : '';
    if (!name) return;

    addExercise(name);
    if (input) input.value = '';
}

function removeExercise(exerciseId) {
    activeExercises = activeExercises.filter(ex => ex.id !== exerciseId);
    renderActiveExercises();
}

function addSet(exerciseId) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return;

    // Copy reps/rest from the last set if available for streamlined experience (HEVY style)
    let lastReps = 8;
    let lastRest = 90;
    if (exercise.sets.length > 0) {
        const lastSet = exercise.sets[exercise.sets.length - 1];
        lastReps = lastSet.reps;
        lastRest = lastSet.rest;
    }

    exercise.sets.push({
        id: 'set-' + Date.now() + Math.random().toString(36).substr(2, 5),
        reps: lastReps,
        rest: lastRest,
        done: false
    });

    renderActiveExercises();
}

function removeSet(exerciseId, setId) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return;

    exercise.sets = exercise.sets.filter(s => s.id !== setId);
    
    // If no sets are left, remove the exercise card completely
    if (exercise.sets.length === 0) {
        removeExercise(exerciseId);
    } else {
        renderActiveExercises();
    }
}

function updateSetData(exerciseId, setId, field, value) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return;

    const set = exercise.sets.find(s => s.id === setId);
    if (!set) return;

    const parsedNum = parseInt(value, 10);
    set[field] = isNaN(parsedNum) ? 0 : parsedNum;
}

function toggleSetDone(exerciseId, setId, isChecked) {
    const exercise = activeExercises.find(ex => ex.id === exerciseId);
    if (!exercise) return;

    const set = exercise.sets.find(s => s.id === setId);
    if (!set) return;

    set.done = isChecked;

    // Direct DOM manipulation for instant premium visual response (no full re-render)
    const rowEl = document.querySelector(`.set-row[data-set-id="${setId}"]`);
    if (rowEl) {
        if (isChecked) {
            rowEl.classList.add('is-done');
        } else {
            rowEl.classList.remove('is-done');
        }
    }

    // --- Game feedback: XP + combo ---
    if (isChecked) {
        comboCount++;
        spawnXpFloat(rowEl, XP_PER_SET + set.reps);
        if (navigator.vibrate) navigator.vibrate(40);
    } else {
        comboCount = 0; // breaking the chain resets the combo
    }
    updateSessionScore();
    updateComboIndicator();

    // Trigger Sticky Rest Timer countdown if checked "Done"
    if (isChecked) {
        startRestTimer(set.rest);
    }
}

// --- Session Score HUD ---
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

// --- Sticky Rest Timer countdown Logic ---
function formatRestTime(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function startRestTimer(seconds) {
    if (seconds <= 0) return;

    // Reset banner appearance to standard active dark style
    const banner = document.getElementById('rest-timer-banner');
    const bannerIcon = document.getElementById('timer-banner-icon');
    
    if (!banner) return;
    
    // Reset status
    isTimerFinished = false;
    banner.className = "fixed bottom-0 left-0 right-0 z-[400] bg-gray-900/95 text-white border-t border-gray-800 shadow-2xl py-4 px-6 transition-transform duration-300 ease-out";
    if (bannerIcon) {
        bannerIcon.className = "w-10 h-10 bg-purple-600/30 text-purple-400 rounded-full flex items-center justify-center text-lg flex-shrink-0";
        bannerIcon.innerHTML = `<i class="fas fa-hourglass-half animate-spin-slow"></i>`;
    }

    // Display banner
    banner.classList.remove('translate-y-full');

    restTimeRemaining = seconds;
    updateRestTimerDisplay();

    if (restTimerInterval) clearInterval(restTimerInterval);

    restTimerInterval = setInterval(() => {
        restTimeRemaining--;
        updateRestTimerDisplay();

        if (restTimeRemaining <= 0) {
            clearInterval(restTimerInterval);
            handleRestTimerCompletion();
        }
    }, 1000);
}

function updateRestTimerDisplay() {
    const clock = document.getElementById('timer-banner-clock');
    if (clock) {
        clock.textContent = formatRestTime(restTimeRemaining);
    }
}

function handleRestTimerCompletion() {
    isTimerFinished = true;
    const banner = document.getElementById('rest-timer-banner');
    const bannerIcon = document.getElementById('timer-banner-icon');
    
    if (banner) {
        // Change color to warm orange-red warning style
        banner.className = "fixed bottom-0 left-0 right-0 z-[400] bg-red-600/95 border-t border-red-500 shadow-2xl py-4 px-6 text-white transition-transform duration-300 ease-out animate-pulse";
    }
    
    if (bannerIcon) {
        bannerIcon.className = "w-10 h-10 bg-white/20 text-white rounded-full flex items-center justify-center text-lg flex-shrink-0";
        bannerIcon.innerHTML = `<i class="fas fa-bell"></i>`;
    }

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
        // If timer was finished, restart it with adjusted value
        startRestTimer(Math.max(10, amount));
        return;
    }
    
    restTimeRemaining = Math.max(0, restTimeRemaining + amount);
    updateRestTimerDisplay();
    
    if (restTimeRemaining === 0) {
        clearInterval(restTimerInterval);
        handleRestTimerCompletion();
    }
}

function skipRestTimer() {
    if (restTimerInterval) clearInterval(restTimerInterval);
    
    const banner = document.getElementById('rest-timer-banner');
    if (banner) {
        banner.classList.add('translate-y-full');
    }
}

// --- Finish Workout & POST payload ---
async function finishWorkout() {
    // 1. Verify there is at least one exercise and at least one completed set
    let totalCompletedSets = 0;
    activeExercises.forEach(ex => {
        ex.sets.forEach(set => {
            if (set.done) totalCompletedSets++;
        });
    });

    if (activeExercises.length === 0 || totalCompletedSets === 0) {
        alert("נא לסמן לפחות סט אחד כבוצע (V) לפני שמירת האימון!");
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

    // 4. Send POST request
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
            // Success animation/feedback
            if (navigator.vibrate) {
                navigator.vibrate([100, 50, 100, 50, 300]);
            }
            // Game-style victory screen with rewards from the server
            showVictoryModal(data.rewards, totalCompletedSets);
        } else {
            alert(`שגיאה בשמירת האימון: ${data.message || 'שגיאה כללית בשרת'}`);
        }
    } catch (error) {
        console.error("Save workout request failed", error);
        alert("נכשלה ההתקשרות עם השרת. אנא בדוק את החיבור לרשת ונסה שנית.");
    }
}

// --- Interactive Skill Progressions Guide Logic ---
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
    const cleanEnglishName = name;
    const displayName = `${cleanHebrewName} (${cleanEnglishName})`;
    
    // Ensure unique ID for exercise
    const exId = 'ex-' + Date.now() + Math.random().toString(36).substr(2, 5);
    
    const newEx = {
        id: exId,
        name: displayName,
        sets: [
            { id: 'set-' + Date.now() + '-1', reps: reps, rest: rest, done: false }
        ]
    };
    
    activeExercises.push(newEx);
    renderActiveExercises();
    
    // 3. Smooth scroll to exercises container
    const exercisesContainer = document.getElementById('active-exercises');
    if (exercisesContainer) {
        exercisesContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}
