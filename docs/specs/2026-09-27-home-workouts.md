# בסלון — home-workouts

**Date:** 2026-09-27 · **Module:** workouts · **Who:** anyone who trains (Yosef first; Karina and Yonatan too)

## In one line
A no-bar, no-equipment mode in the arena: five home workouts (push, pull without a bar, gymnast core, legs, living-room skills), each run through the same warm-up → ready → set → rest → reward flow, for the days you are at home and not at the bar.

## The signature
**Nothing done at home is "instead of" training.** Every home exercise that is also a quest station (pike push-ups, planche lean, frog stand, wall handstand, sliding leg curl, nordic negatives …) is saved under the station's own name, so it counts toward conquering that station exactly as it would in a path workout, and its row in the plan wears the path's icon: "נספר למסלול 🤸". The other exercises climb a small ladder on their own (incline push-ups → push-ups → archer push-ups): once your best set reaches the target, the next home workout hands you the harder variant, with no settings and no button.

## Why these exercises (the research, kept short)
The choice follows the consensus of the serious bodyweight sources: the r/bodyweightfitness Recommended Routine, Steven Low's *Overcoming Gravity* and the gymnastics-strength school (GMB, Gymnastic Bodies).
1. **Movement patterns, not muscles.** Every workout pairs a push, a pull or hinge, a squat pattern and body tension. A home plan that is all push-ups builds imbalanced shoulders.
2. **Body tension is the skill multiplier.** The hollow body and the arch are the two positions every lever, handstand and muscle-up is built on. So they appear as a ladder, not as filler.
3. **Leverage replaces load.** Without weights, difficulty comes from changing the lever: incline → floor → archer, knees → pike, squat → split squat → shrimp. Hence ladders.
4. **Straight-arm strength and wrists need their own work.** The planche lean, frog stand, wall handstand and wrist warm-up are the entry to the push skills, and they need no equipment.
5. **Pulling without a bar is the honest weak spot.** Table rows are the only true horizontal pull at home. Everything else (Y-T-W, towel floor pulls, arch holds, reverse plank) is scapular and posterior-chain support. The pull workout says so instead of pretending.
6. **Hinge and hamstrings matter for everyone.** The Nordic path already exists; the legs workout feeds it with its own stations (a couch anchors the feet).

## Framings considered
- A (straight): a static list of home exercises with sets/reps to read — lost because it is a blog post, nothing is tracked and nothing counts.
- B (house style): home workouts run in the arena, save like any workout (XP, streak, records), credit path stations by name, and climb their own ladders from history — **chosen**.
- C (subtraction): add a "home" flag to the existing path plans and drop bar exercises from them — lost because most paths (muscle-up, front lever) are bar-only, so the result would be empty for exactly the paths people train most.

Calendar: "recommended today" follows the same recovery rule as the mission card. Board game: ladders with visible next rung. Bank statement: the history shows the home session like any other, with its type.

## Behaviour

### Entry points (the workouts page, mobile and desktop are the same page)
- **Home view (`#home`)**, directly under the mission card(s) and above "מסלולים אחרים": one row
  `🏠 בסלון · אימון בית בלי מוט` with sub-line `מומלץ היום: <workout name> · <n> סטים · בערך <m> דקות` and action `פתח`. Tapping opens `#house`.
- The first-run empty home view (`wk-empty`) gets the same row above its "או התחל אימון חופשי בלי מסלול" link.

### The `#house` view (new `data-view="house"` section; hash switching like the other views)
- Header: `בסלון` with sub-line `משקל גוף בלבד · בלי מוט ובלי ציוד`, and a back link to `#home` (`← חזרה`).
- One card per home workout (5 cards). The **recommended** one comes first with eyebrow `מומלץ היום`; the rest follow in catalog order. Each card shows:
  - icon + name (e.g. `💪 דחיפה בסלון`)
  - `מחזק: ` + the names of the paths it feeds (e.g. `מחזק: עמידת ידיים · פלאנץ' · עליית כוח`)
  - `<n> תרגילים · <s> סטים · בערך <m> דקות` and the XP pill `+<xp> XP` (same formula as path plans: `_session_xp(sets, reps, minutes)`)
  - the exercise list, one line each: Hebrew title + target (`3 × 12 חזרות` / `3 × 30 שניות`). A station exercise ends with the path chip `נספר למסלול <icon>`. A laddered exercise whose rung went up since last time shows `⬆ דרגה חדשה`.
  - button `להתחיל` (`data-start-house="<key>"`)
- If a session is already active, `להתחיל` opens the arena (same rule as `startPathWorkout`).

### Recommendation (derived, never stored)
`recommended = HOUSE_FOR_PATH[default_path]` where `default_path` is what `plan_today()` already returned (so yesterday's muscle group rests). Mapping: `muscle_up → pull`, `front_lever → pull`, `hspu → push`, `planche → push`, `human_flag → core`, `nordic_curl → legs`. If the mapped workout's `workout_type` equals a type trained yesterday, take the first workout in catalog order whose type was not trained yesterday.

### In the arena
- Start builds the exercises exactly like a path workout (`buildExercise` with sets/reps/rest per exercise), `workout_type` = the home workout's type, with its own warm-up list, then the "ready" screen, then sets.
- The arena labels (`#warmup-path`, `#ready-path`) read `בסלון · <workout name>` instead of `מסלול <name>`.
- The session resumes after a refresh like any other (`workout_active_session_v2`); the saved session remembers it is a house session.
- Station exercises are sent with their `skill_key`/`stage_index` so the reward screen shows station progress as usual.
- Rewards, XP, streak, records, achievements: unchanged code paths — a home session is an ordinary saved session.

### Ladders (derived from records)
Each laddered slot lists 2–3 rungs, easiest first. The rung offered = the first rung whose target is **not yet reached**, where "reached" means `records[name].best >= target` (best single set ever) — or, for a station rung, the station is conquered. If every rung is reached, the last rung is offered. `⬆ דרגה חדשה` shows when the offered rung is not the first and has no record yet.

### Empty / error states
- No history at all: recommended = `push`; every ladder starts at rung 1.
- The Yonatan-only login sees the same view (workouts is his module).

## The catalog (content is part of the spec — use these names, targets and texts)

Unit `sec` = hold. `[station: path/Name]` = reuse that station's exact saved name, target, rest, how and cues from `SKILL_PROGRESSIONS`. New exercises are saved under their plain English name (like the free-workout catalog) with the Hebrew title below. Sets are per slot.

### 1. `push` — 💪 דחיפה בסלון · type `Push` · feeds hspu, planche, muscle_up
Warm-up: סיבובי שורש כף היד (20 שניות לכל כיוון) · לחיצות כף יד על הרצפה (2 × 10) · שכיבות סמיכה בשכמות (2 × 10) · סיבובי כתפיים וזרועות (20 שניות לכל כיוון) · שכיבות סמיכה קלות בשיפוע (1 × 8)
| Slot | Sets | Rungs |
|---|---|---|
| Push-up ladder | 4 | Incline Push-ups `שכיבות סמיכה בשיפוע` 12 reps, rest 60 → Push-ups (existing catalog name) 12, rest 75 → Archer Push-ups `שכיבות סמיכה ארצ'ר` 6, rest 90 |
| Pike ladder | 3 | [station: hspu/Pike Push-ups] → [station: hspu/Elevated Pike Push-ups] → [station: hspu/Negative Wall HSPU] |
| Straight-arm | 3 | [station: planche/Planche Lean] → [station: planche/Pseudo Planche Push-ups] |
| Hindu Push-ups | 3 | Hindu Push-ups `שכיבות סמיכה הינדיות` 8, rest 75 |
| Hollow ladder | 3 | Tuck Hollow Hold `גוף חלול מקופל` 20 sec, rest 60 → Hollow Body Hold `החזקת גוף חלול` 30 sec, rest 60 → Hollow Body Rocks `נדנודי גוף חלול` 15 reps, rest 60 |

### 2. `pull` — 🪢 משיכה בלי מוט · type `Pull` · feeds muscle_up, front_lever
Card note under the name (shown on the card, one line): `בלי מוט אין תחליף מלא למתח — השולחן עושה את המשיכה, השאר מחזק את השכמות והגב.`
Warm-up: סיבובי כתפיים (20 שניות לכל כיוון) · חיבוק עצמי ופתיחה (2 × 10) · כיווצי שכמות בעמידה (2 × 10) · מלאכי שלג על הרצפה (2 × 8) · חתירה קלה מתחת לשולחן, ברכיים כפופות (1 × 6)
| Slot | Sets | Rungs |
|---|---|---|
| Table rows | 4 | Bent-Knee Table Rows `חתירה מתחת לשולחן (ברכיים כפופות)` 10, rest 75 → Table Rows `חתירה מתחת לשולחן` 10, rest 90 → Archer Table Rows `חתירת ארצ'ר מתחת לשולחן` 6, rest 90 |
| Y-T-W | 3 | Prone Y-T-W Raises `הרמות Y-T-W בשכיבה` 8, rest 60 |
| Floor pulls | 3 | Towel Floor Pulls `משיכות רצפה על מגבת` 8, rest 75 |
| Reverse plank | 3 | Reverse Plank Hold `פלאנק הפוך` 30 sec, rest 60 → Crab Reach `הושטת יד מעמידת סרטן` 8, rest 60 |
| Arch ladder | 3 | Arch Hold `החזקת קשת (סופרמן)` 30 sec, rest 60 → Arch Rocks `נדנודי קשת` 15, rest 60 |

### 3. `core` — 🔥 ליבה של מתעמל · type `Core` · feeds human_flag, front_lever, planche, muscle_up
Warm-up: חתול-פרה (2 × 8) · סיבובי אגן (20 שניות לכל כיוון) · דד באג איטי (1 × 6 לכל צד) · פלאנק קצר (1 × 20 שניות) · מתיחת פייק בישיבה (30 שניות)
| Slot | Sets | Rungs |
|---|---|---|
| Hollow ladder | 4 | same rungs as in `push` |
| Arch ladder | 3 | same rungs as in `pull` |
| Compression | 3 | Seated Knee Tucks `כיווצי ברכיים בישיבה` 12, rest 60 → Seated Pike Leg Lifts `הרמות רגליים בישיבת פייק` 10, rest 60 |
| Side plank | 3 | Side Plank `פלאנק צד` 30 sec, rest 45 → Copenhagen Side Plank `פלאנק צד קופנהגן` 20 sec, rest 60 |
| Dynamic core | 3 | Dead Bug `דד באג` 10, rest 45 → Tuck-ups `כיווצי בטן מקופלים` 12, rest 60 → V-ups `כפיפות V` 10, rest 60 |

### 4. `legs` — 🦵 רגליים בלי ציוד · type `Legs` · feeds nordic_curl
Warm-up: סיבובי אגן וברכיים (20 שניות לכל כיוון) · נדנודי רגל (2 × 10 לכל רגל) · סקוואט עמוק עם החזקה (2 × 20 שניות) · גשר ישבן קל (1 × 10) · מכרעים לאחור (1 × 6 לכל רגל)
| Slot | Sets | Rungs |
|---|---|---|
| Squat ladder | 4 | Bodyweight Squats (catalog) 20, rest 60 → Bulgarian Split Squats (catalog) 10, rest 75 → Shrimp Squats (catalog) 6, rest 90 |
| Single leg | 3 | Box Pistol Squats `פיסטול לספה` 6, rest 90 → Pistol Squats (catalog) 5, rest 120 |
| Cossack | 3 | Cossack Squats `סקוואט קוזאק` 8, rest 60 |
| Hamstrings | 3 | [station: nordic_curl/Single-Leg Glute Bridge] → [station: nordic_curl/Sliding Leg Curl] → [station: nordic_curl/Nordic Negatives] |
| Power | 3 | Tuck Jumps `קפיצות ברכיים לחזה` 8, rest 75 |

### 5. `skills` — 🤸 כישורים בסלון · type `Full Body` · feeds hspu, planche
Warm-up: the `hspu` path's warm-up list, as is.
| Slot | Sets | Rungs |
|---|---|---|
| Balance | 4 | [station: planche/Frog Stand] → [station: planche/Tuck Planche Hold] |
| Handstand | 4 | [station: hspu/Wall Walks (Holds)] → [station: hspu/Wall-Assisted Handstand Hold] → [station: hspu/Freestanding Handstand Hold] |
| Compression | 3 | same rungs as in `core` |
| Bear Crawl | 3 | Bear Crawl `זחילת דוב` 30 sec, rest 60 |
| Hollow rocks | 3 | Hollow Body Rocks (the third hollow rung, fixed) |

### How lines and cues for the new exercises
Each new exercise gets one `how` line and two cues `(pin, text)`, in the `_station` style:
- **Incline Push-ups**: "כפות ידיים על ספה או שולחן, גוף ישר מהעורף לעקבים, והחזה יורד עד הקצה." · (גוף קרש / ישבן ובטן נעולים — בלי לשקוע באגן) · (להנמיך בהדרגה / כשזה קל, עוברים למשטח נמוך יותר)
- **Archer Push-ups**: "ידיים רחבות; יורדים אל יד אחת כשהיד השנייה נשארת ישרה לצד, ומחליפים צד." · (יד ישרה נעולה / היד הצדדית רק מייצבת — לא דוחפת) · (חזרה = שני צדדים / סופרים כל צד כחצי חזרה)
- **Hindu Push-ups**: "מכלב מביט מטה צוללים עם החזה קרוב לרצפה קדימה ולמעלה לכלב מביט מעלה, וחוזרים לאחור." · (לצלול נמוך / החזה עובר קרוב לרצפה) · (לחזור בדחיפה / חוזרים לאחור בכוח הכתפיים, לא באגן)
- **Tuck Hollow Hold**: "שכיבה על הגב, גב תחתון צמוד לרצפה, ברכיים לחזה וכתפיים מורמות." · (גב תחתון לרצפה / אין רווח בין הגב לרצפה) · (צלעות למטה / מכווצים בטן כאילו מקבלים מכה)
- **Hollow Body Hold**: "מאותו מנח מיישרים רגליים וזרועות מעל הראש — צורת בננה נמוכה." · (גב תחתון לרצפה / אם הגב מתרומם, מרימים את הרגליים גבוה יותר) · (ידיים ליד האוזניים / זרועות ישרות מעל הראש)
- **Hollow Body Rocks**: "במנח גוף חלול מתנדנדים קדימה ואחורה כיחידה אחת, בלי לאבד את הצורה." · (גוף אחד / הצורה לא משתנה בנדנוד) · (תנועה קטנה / נדנוד קצר ונשלט)
- **Bent-Knee Table Rows**: "שוכבים מתחת לשולחן כבד ויציב, אוחזים בקצה ומושכים את החזה אליו, ברכיים כפופות." · (רק שולחן יציב / שולחן כבד שלא מתהפך — אם אין, חתירה עם מגבת סביב ידית דלת סגורה) · (חזה לשולחן / מושכים עם מרפקים צמודים לגוף)
- **Table Rows**: "אותה חתירה עם רגליים ישרות וגוף קרש מהכתפיים לעקבים." · (גוף קרש / האגן לא צונח) · (שכמות קודם / מתחילים בכיווץ שכמות)
- **Archer Table Rows**: "מושכים אל יד אחת כשהיד השנייה נשארת ישרה לצד, ומחליפים צד." · (יד אחת עובדת / היד הישרה עוזרת מעט) · (לאט למטה / ירידה של 2-3 שניות)
- **Prone Y-T-W Raises**: "שכיבה על הבטן, מרימים ידיים ישרות בצורת Y, אחר כך T ואחר כך W, עם עצירה קצרה למעלה." · (אגודלים למעלה / מסובבים את הידיים החוצה) · (שכמות אחורה ומטה / לא מושכים את הכתפיים לאוזניים)
- **Towel Floor Pulls**: "שכיבה על הבטן על רצפה חלקה עם מגבת מתחת לאגן; מושכים את הגוף קדימה בכפות הידיים ובאמות." · (מרפקים צמודים / מושכים מהגב, לא מהידיים) · (רגליים רפויות / הרגליים לא דוחפות)
- **Reverse Plank Hold**: "ישיבה עם ידיים מאחור, אצבעות לכיוון הרגליים; מרימים אגן לקו ישר מהכתפיים לעקבים." · (חזה פתוח / הכתפיים נמשכות אחורה ומטה) · (אגן גבוה / ישבן נעול, בלי לשקוע)
- **Crab Reach**: "מעמידת סרטן מרימים אגן ומושיטים יד אחת מעל הראש לאחור, וחוזרים; מחליפים צד." · (אגן למעלה / האגן עולה גבוה עם ההושטה) · (מבט אחרי היד / מסובבים את החזה אל התקרה)
- **Arch Hold**: "שכיבה על הבטן, מרימים יחד חזה, ידיים ישרות ורגליים ישרות, ומחזיקים." · (ישבן נעול / הכיווץ מתחיל בישבן) · (צוואר ארוך / מבט לרצפה, לא קדימה)
- **Arch Rocks**: "במנח קשת מתנדנדים קדימה ואחורה בלי לשבור את הצורה." · (גוף אחד / הצורה לא משתנה) · (תנועה קטנה / נדנוד קצר ונשלט)
- **Seated Knee Tucks**: "ישיבה עם ידיים לצד הירכיים, נשענים מעט אחורה ומכווצים ברכיים לחזה ובחזרה בלי לגעת ברצפה." · (לא לגעת / העקבים לא נוחתים בין החזרות) · (גב זקוף / לא קורסים אחורה)
- **Seated Pike Leg Lifts**: "ישיבת פייק עם רגליים ישרות, ידיים על הרצפה ליד הברכיים; מרימים את שתי הרגליים מהרצפה ומורידים." · (ברכיים נעולות / רגליים ישרות לגמרי) · (לדחוף עם הידיים / הידיים לוחצות ברצפה והגו נשען קדימה)
- **Side Plank**: "על אמה אחת, גוף ישר מהראש לעקבים, האגן מורם." · (אגן למעלה / האגן לא צונח לרצפה) · (כתף מעל מרפק / המרפק ישר מתחת לכתף)
- **Copenhagen Side Plank**: "פלאנק צד כשהרגל העליונה על ספה והתחתונה באוויר." · (ירך עליונה עובדת / הלחץ על הספה מגיע מהירך הפנימית) · (להתחיל מהברך / הברך על הספה היא הגרסה הקלה)
- **Dead Bug**: "שכיבה על הגב, ידיים למעלה וברכיים ב-90; מורידים יד ורגל נגדיות לאט ומחליפים." · (גב לרצפה / הגב התחתון לא מתרומם) · (לאט / 3 שניות לכל הורדה)
- **Tuck-ups**: "ממנח גוף חלול מקפלים ברכיים לחזה ועולים לישיבה על האגן, וחוזרים." · (איזון על האגן / היושבת נשארת קטנה) · (חזרה נשלטת / חוזרים לגוף חלול, לא נופלים)
- **V-ups**: "ממנח גוף חלול מרימים יחד רגליים ישרות וידיים ונוגעים באצבעות הרגליים." · (רגליים ישרות / הברכיים נעולות) · (לנחות רך / חוזרים לאט לגוף חלול)
- **Box Pistol Squats**: "על רגל אחת יורדים לאט עד ישיבה על ספה, ונעמדים בלי תנופה." · (ירידה איטית / 3 שניות עד הספה) · (ברך מעל האצבעות / הברך לא קורסת פנימה)
- **Cossack Squats**: "עמידה רחבה, יורדים על רגל אחת כשהשנייה ישרה ואצבעותיה למעלה, ומחליפים צד." · (עקב על הרצפה / העקב של הרגל הכפופה נשאר למטה) · (חזה פתוח / גו זקוף ככל האפשר)
- **Tuck Jumps**: "קפיצה גבוהה עם ברכיים לחזה ונחיתה רכה על כפות הרגליים." · (נחיתה שקטה / נוחתים רך עם ברכיים כפופות) · (איכות לפני כמות / עוצרים כשהקפיצה נהיית נמוכה)
- **Bear Crawl**: "על ידיים וכפות רגליים, ברכיים סנטימטר מעל הרצפה; הולכים קדימה ואחורה ביד ורגל נגדיות." · (ברכיים נמוכות / הברכיים לא עולות גבוה) · (גב שטוח / אפשר להניח כוס מים על הגב)

## Data
- **No schema change.** A home session is ordinary `workouts` rows. New exercises are saved by their English name with `skill_key`/`stage_index` null; station rungs are saved with the station's exact `station_exercise_name` and its `skill_key`/`stage_index`, so `_station_for` credits them.
- **Catalog** lives in a new module `app/backend/app/services/home_workouts.py`: `HOME_EXERCISES` (name → hebrew, unit, reps, rest, how, cues, category), `HOUSE_WORKOUTS` (ordered dict key → name, icon, workout_type, feeds, note, warmup, slots[{sets, rungs}]), where a rung is either a new exercise name or a `("station", skill_key, english_name)` reference. Pure data; no imports from `routes/`.
- **Derived in `routes/workouts.py`** (where `SKILL_PROGRESSIONS` lives): `compute_house(records, paths, default_path, history, today)` → list of workouts with the offered rung per slot, sets/minutes/xp, recommended key. Nothing is stored; nothing goes in `system_settings`.
- `EXERCISE_CATALOG`/title lookup: `_exercise_title` and `_exercise_unit` learn the home exercises (so history and records show the Hebrew name and the right unit). `exercise_form_data()` includes every home exercise (holo key, unit, tempo, how, cues). Holds (`unit == "sec"`) go to `HOLD_EXERCISES` semantics via the unit; tempos: Hollow/Arch Rocks `(1,0,1)`, Tuck Jumps `(1,0,1)`, Dead Bug `(3,1,1)`, others default.
- `admin_exercise_options()` gets a `🏠 בסלון` group with the new exercises, so the back office can edit a home session.

## API
No new endpoints. `GET /workouts` adds `house` to the template context and to `client_data` (`client_data.house = {key: {name, icon, workout_type, warmup, warmup_minutes, exercises:[{name, title, sets, reps, rest, unit, unit_label, skill_key, stage_index}]}}`). Saving uses the existing `POST /workouts`. Access is the workouts module's (unchanged).

## Hologram
Every new exercise needs a clip in `static/holo/exercises.glb` (the existing test `test_shipped_model_covers_every_exercise` enforces it). Add them to `tools/build_exercises_glb.py` by composing the existing pose constants (`d(POSE, …)`); floor exercises use no prop; table rows use the `bar` prop placed low. Regenerate with `python3 tools/build_exercises_glb.py`, add the rows to `static/holo/README.md`. An approximate pose is fine; a missing one is not.

## Files to touch
- `app/backend/app/services/home_workouts.py` — **new**: the catalog above.
- `app/backend/app/routes/workouts.py` — `compute_house`, `HOUSE_FOR_PATH`, context/client_data, `_exercise_title`/`_exercise_unit`, `exercise_form_data`, `TEMPO_BY_EXERCISE`, `admin_exercise_options`.
- `app/frontend/templates/pages/workout.html` — the home-view row (both home sections), the new `data-view="house"` section.
- `app/frontend/static/js/workout.js` — `house` in the view switcher; `startHouseWorkout(key)`; the session remembers its source (`path` stays for paths; add `house` key to the saved session) and warm-up / ready / resume read the warm-up and label from the house entry when the session is a house session.
- `app/frontend/static/css/workout.css` — styles for the row and cards, reusing `wk-mission`/`wk-path-row` tokens.
- `tools/build_exercises_glb.py`, `app/frontend/static/holo/exercises.glb`, `app/frontend/static/holo/README.md` — clips.
- `CLAUDE.md` — one bullet under the Workouts module.
- `tests/test_workouts_e2e.py` (+ `tests/test_workouts_arena_browser.py`) — tests below.

## Acceptance criteria
1. `GET /workouts` renders a `data-view="house"` section with 5 cards and the home-view row naming the recommended workout.
2. With no history the recommended workout is `push` and every slot offers rung 1.
3. After a history row of `Incline Push-ups` with best set 12, the push workout offers `Push-ups` in that slot and shows `⬆ דרגה חדשה`.
4. A station rung is saved under the station's name with its `skill_key`/`stage_index`, and saving 5 sessions of it in range conquers that station (same path code).
5. Recommendation follows `plan_today`: default path `nordic_curl` → `legs`; if yesterday was a `Legs` day it is not `legs`.
6. Every home exercise has a Hebrew title in history, the right unit (sec/reps) and a hologram clip.
7. In the browser: tapping `להתחיל` on a house card opens the arena on the warm-up with `בסלון · <name>`, then ready, then the first set of the offered rung; finishing saves rows with `workout_type` of that workout.
8. A refresh mid-session resumes the house session with its warm-up/label intact.
9. Path workouts, the mission card and the desktop layout of the other views are unchanged.

## Tests to add
- `test_house_catalog_is_well_formed` — every rung resolves (station refs exist in `SKILL_PROGRESSIONS`), every new exercise has how + two cues, units are `reps`/`sec`, names don't collide with station names.
- `test_house_ladder_climbs_from_records` — criterion 3, plus "all rungs reached → last rung".
- `test_house_station_rung_credits_path` — criterion 4.
- `test_house_recommendation_follows_plan_today` — criterion 5 and 2.
- `test_house_view_renders` — criterion 1 (and titles/units in history for a saved home row, criterion 6).
- Browser: `test_house_workout_runs_and_saves` — criterion 7 and 8.
- The existing `test_shipped_model_covers_every_exercise` must pass with the new clips.

## Out of scope
- Circuit / round-robin ordering and interval (EMOM/Tabata) timers.
- Letting the user pick a rung by hand in the card (the arena's existing edit sheet still allows changing reps).
- Any new achievement, XP rule or schema column.
- Custom user-built home workouts.

## Open questions
None: implement as written.
