# Exercise hologram model

The workout arena shows a looping hologram of the exercise pose (design turns `3a`/`3b`).
It is driven by **one file**: `exercises.glb` in this folder. Without that file the arena
shows its plain set screen, and nothing else changes.

The file that ships is generated — a stylised rig (segments between joints, a ball on every
joint) with one clip per exercise, built by `tools/build_exercises_glb.py`:

```bash
python3 tools/build_exercises_glb.py                      # writes exercises.glb
python3 tools/build_exercises_glb.py --preview poses.png   # + a contact sheet of every pose
```

The script needs nothing but the standard library. Poses live in its `SPECS` table as joint
angles in the sagittal plane (`0deg` = up, `90deg` = forward/+Z); where a rep's depth matters
they are authored through `arm_to()` / `leg_to()`, which solve the two-segment chain so the
contact point lands where you asked ("shoulders 23 cm above the hands, elbows towards the
feet") instead of by guessing angles.

Check the result with the two pictures it can draw:

```bash
python3 tools/build_exercises_glb.py --preview poses.png              # fast stick sheet, all clips
python3 tools/build_exercises_glb.py --render look.png --view side \
        --clips push_ups,dips --frame turn                            # shaded, through the arena's camera
```

`--render` rasterises the real geometry through the same three presets the arena uses
(`--view auto` picks the one each clip is authored for) and `--frame turn` shows the bottom of
the rep, which is where a bad pose shows up. Swapping in a better model by hand is fine too —
nothing in the app knows how the file was made, it only reads the clip names.

Two things beyond the poses make the difference in the arena:

- **Props.** A pull-up with nothing to hang from just looks like someone standing with bent
  arms, so each clip carries the rig its grip implies — a bar with uprights, a pair of
  parallettes, or a pole — taken from the pose's own contact point.
- **The clip's camera.** The arena opens on the side preset, which is edge-on for a human
  flag. The model lists the clips that read from the front in its glTF `extras`
  (`front_view_clips`), and `holo_clips()` passes that to the page.

## What the file must contain

- A glTF 2.0 binary (`.glb`) with a single figure. The app adds the cyan glow and the stage
  itself; a light, slightly emissive cyan material on the figure reads best.
- **One animation clip per exercise**, named exactly as the clip key below. An exercise whose
  clip is missing keeps the plain set screen, so clips can be added one at a time.
- Each clip is **one rep**: lowering → pause → pushing, in that order, returning to the start
  pose so it loops cleanly. Its length doesn't matter; the arena time-scales it so one loop
  lasts the tempo (e.g. `3-1-1` = 5 s). Holds are simply the held position, looping.
- The figure faces **+Z** (the "front" camera), standing on the origin. Camera presets:
  side `90deg 75deg`, front `0deg 75deg`, top `0deg 12deg`.

Clip keys come from `holo_key()` in `app/backend/app/routes/workouts.py`
(the English exercise name, lower-case, non-alphanumerics → `_`). Tempos come from
`exercise_tempo()` in the same file.

## Clip keys

| Clip key | Exercise | Tempo |
|---|---|---|
| `ab_wheel_rollouts` | Ab Wheel Rollouts | 3-1-1 |
| `active_scapula_hangs` | Active Scapula Hangs | 2-1-1 |
| `advanced_tuck_fl_hold` | Advanced Tuck FL Hold | hold |
| `advanced_tuck_planche` | Advanced Tuck Planche | hold |
| `airborne_squats` | Airborne Squats | 3-1-1 |
| `angled_tucked_flag_hold` | Angled Tucked Flag Hold | hold |
| `assisted_muscle_up_band` | Assisted Muscle-Up (Band) | 2-0-1 |
| `australian_pull_ups_rows` | Australian Pull-ups / Rows | 3-1-1 |
| `basic_dips` | Basic Dips | 3-1-1 |
| `basic_pull_ups` | Basic Pull-ups | 3-1-1 |
| `bodyweight_squats` | Bodyweight Squats | 3-1-1 |
| `bulgarian_split_squats` | Bulgarian Split Squats | 3-1-1 |
| `calf_raises` | Calf Raises | 2-1-1 |
| `chin_ups` | Chin-ups | 3-1-1 |
| `diamond_push_ups` | Diamond Push-ups | 3-1-1 |
| `dips` | Dips | 3-1-1 |
| `elevated_pike_push_ups` | Elevated Pike Push-ups | 3-1-1 |
| `explosive_pull_ups` | Explosive Pull-ups | 2-0-1 |
| `false_grip_hang` | False Grip Hang | hold |
| `false_grip_pull_ups` | False Grip Pull-ups | 3-1-1 |
| `freestanding_handstand_hold` | Freestanding Handstand Hold | hold |
| `frog_stand` | Frog Stand | hold |
| `full_freestanding_hspu` | Full Freestanding HSPU | 3-1-1 |
| `full_front_lever_hold` | Full Front Lever Hold | hold |
| `full_human_flag_hold` | Full Human Flag Hold | hold |
| `full_muscle_up` | Full Muscle-Up | 2-0-1 |
| `full_planche_hold` | Full Planche Hold | hold |
| `half_lay_front_lever_hold` | Half Lay Front Lever Hold | hold |
| `half_lay_planche_hold` | Half Lay Planche Hold | hold |
| `handstand_push_ups` | Handstand Push-ups | 3-1-1 |
| `hanging_leg_raises` | Hanging Leg Raises | 3-1-1 |
| `l_sit` | L-Sit | hold |
| `low_bar_transitions` | Low Bar Transitions | 2-0-1 |
| `muscle_ups` | Muscle-ups | 2-0-1 |
| `negative_muscle_up` | Negative Muscle-Up | 5-1-1 |
| `negative_wall_hspu` | Negative Wall HSPU | 5-1-1 |
| `one_arm_active_hang` | One Arm Active Hang | hold |
| `one_arm_inverted_support` | One Arm Inverted Support | hold |
| `one_legged_advanced_tuck` | One-Legged Advanced Tuck | hold |
| `one_legged_fl_hold` | One-Legged FL Hold | hold |
| `one_legged_human_flag_hold` | One-Legged Human Flag Hold | hold |
| `partial_wall_hspu` | Partial Wall HSPU | 3-1-1 |
| `pike_push_ups` | Pike Push-ups | 3-1-1 |
| `pistol_squats` | Pistol Squats | 3-1-1 |
| `planche_lean` | Planche Lean | hold |
| `plank` | Plank | hold |
| `pseudo_planche_push_ups` | Pseudo Planche Push-ups | 3-1-1 |
| `pull_ups` | Pull-ups | 3-1-1 |
| `push_ups` | Push-ups | 3-1-1 |
| `reversed_deadlift_fl_pulls` | Reversed Deadlift (FL Pulls) | 3-1-1 |
| `scapula_shrugs` | Scapula Shrugs | 2-1-1 |
| `shrimp_squats` | Shrimp Squats | 3-1-1 |
| `straddle_freestanding_hspu` | Straddle Freestanding HSPU | 3-1-1 |
| `straddle_front_lever_hold` | Straddle Front Lever Hold | hold |
| `straddle_human_flag_hold` | Straddle Human Flag Hold | hold |
| `straddle_planche_hold` | Straddle Planche Hold | hold |
| `straight_bar_dips` | Straight Bar Dips | 3-1-1 |
| `toes_to_bar` | Toes to Bar | 2-1-1 |
| `tuck_fl_rows` | Tuck FL Rows | 3-1-1 |
| `tuck_front_lever_hold` | Tuck Front Lever Hold | hold |
| `tuck_human_flag_hold` | Tuck Human Flag Hold | hold |
| `tuck_planche_hold` | Tuck Planche Hold | hold |
| `tucked_l_sit` | Tucked L-Sit | hold |
| `vertical_flag_hold` | Vertical Flag Hold | hold |
| `vertical_flag_negatives` | Vertical Flag Negatives | 4-1-1 |
| `wall_assisted_handstand_hold` | Wall-Assisted Handstand Hold | hold |
| `wall_assisted_hspu` | Wall-Assisted HSPU | 3-1-1 |
| `wall_walks_holds` | Wall Walks (Holds) | hold |

Replacing the file is enough — the page picks up the new clip list and cache-busts the model
by its modification time. `test_shipped_model_covers_every_exercise` in
`tests/test_workouts_e2e.py` fails if an exercise ends up without a clip.
