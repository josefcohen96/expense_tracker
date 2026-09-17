#!/usr/bin/env python3
"""Build app/frontend/static/holo/exercises.glb — the workout arena's exercise hologram.

The figure is a stylised rig: capsule segments between joints, a ball on every joint. Poses
are authored as joint angles in the sagittal plane (0deg = up, 90deg = forward/+Z), run
through forward kinematics here, and baked into per-node translation/rotation keyframes, so
the model needs no skin and every clip drives the same nodes.

One animation clip per exercise, named by holo_key() in app/backend/app/routes/workouts.py.
A rep clip is authored as lowering -> pause -> pushing over its tempo in seconds; a hold clip
is the position itself with a slow breath. The arena time-scales whatever it finds.

Usage:
    python3 tools/build_exercises_glb.py [--out PATH] [--preview PATH]

Stdlib only — it runs without the app's requirements installed.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "frontend" / "static" / "holo" / "exercises.glb"

# ============================ figure ============================

L = {"spine": 0.30, "neck": 0.13, "head": 0.14, "sh_up": 0.04, "sh_w": 0.18,
     "uarm": 0.28, "farm": 0.26, "hand": 0.09, "hip_w": 0.10,
     "thigh": 0.42, "shin": 0.40, "foot": 0.17}

# (joint a, joint b, radius) — the segments drawn between joints
BONES = [("pelvis", "chest", 0.085), ("chest", "neck", 0.052), ("neck", "head", 0.045),
         ("shoulder_l", "shoulder_r", 0.05), ("hip_l", "hip_r", 0.055)]
for _s in ("l", "r"):
    BONES += [(f"shoulder_{_s}", f"elbow_{_s}", 0.05), (f"elbow_{_s}", f"wrist_{_s}", 0.042),
              (f"wrist_{_s}", f"hand_{_s}", 0.034), (f"hip_{_s}", f"knee_{_s}", 0.056),
              (f"knee_{_s}", f"ankle_{_s}", 0.048), (f"ankle_{_s}", f"toe_{_s}", 0.038)]

# (joint, radius) — the balls
BALLS = [("head", 0.115), ("pelvis", 0.07), ("chest", 0.06)]
for _s in ("l", "r"):
    BALLS += [(f"shoulder_{_s}", 0.058), (f"elbow_{_s}", 0.048), (f"wrist_{_s}", 0.04),
              (f"hip_{_s}", 0.058), (f"knee_{_s}", 0.05), (f"ankle_{_s}", 0.042)]


def vec(angle, length, spread=0.0, sx=1.0):
    """Sagittal direction: 0 = up (+Y), 90 = forward (+Z); spread splays sideways (+/-X)."""
    a, s = math.radians(angle), math.radians(spread)
    return (sx * length * math.sin(s),
            length * math.cos(a) * math.cos(s),
            length * math.sin(a) * math.cos(s))


def add(p, v):
    return (p[0] + v[0], p[1] + v[1], p[2] + v[2])


def body(**p):
    """Joint positions for one pose. Angles are absolute; `_l` / `_r` suffixes override a side."""
    def g(key, side, default=None):
        return p.get(f"{key}_{side}", p.get(key, default))

    torso = p.get("torso", 0.0)
    j = {"pelvis": (0.0, 0.0, 0.0)}
    j["chest"] = add(j["pelvis"], vec(torso, L["spine"]))
    neck_a = p.get("neck_a", torso)
    j["neck"] = add(j["chest"], vec(neck_a, L["neck"]))
    j["head"] = add(j["neck"], vec(p.get("head", neck_a), L["head"]))
    for side, sx in (("l", -1.0), ("r", 1.0)):
        shoulder = add(add(j["chest"], vec(torso, L["sh_up"])), (sx * L["sh_w"], 0.0, 0.0))
        j["shoulder_" + side] = shoulder
        arm, asp = g("arm", side, 180.0), g("arm_spread", side, 0.0)
        elbow = add(shoulder, vec(arm, L["uarm"], asp, sx))
        j["elbow_" + side] = elbow
        fore, fsp = g("elbow", side, arm), g("fore_spread", side, g("arm_spread", side, 0.0))
        wrist = add(elbow, vec(fore, L["farm"], fsp, sx))
        j["wrist_" + side] = wrist
        j["hand_" + side] = add(wrist, vec(g("hand", side, fore), L["hand"], fsp, sx))

        hip = add(j["pelvis"], (sx * L["hip_w"], 0.0, 0.0))
        j["hip_" + side] = hip
        thigh, lsp = g("hip", side, 180.0), g("leg_spread", side, 0.0)
        knee = add(hip, vec(thigh, L["thigh"], lsp, sx))
        j["knee_" + side] = knee
        shin = g("knee", side, thigh)
        ankle = add(knee, vec(shin, L["shin"], lsp, sx))
        j["ankle_" + side] = ankle
        j["toe_" + side] = add(ankle, vec(g("ankle", side, shin - 90.0), L["foot"], lsp, sx))
    return j


def posed(params, spec):
    """One pose placed in the world: anchored on its contact point, tilted, mapped to its plane."""
    j = body(**params)
    tilt = spec.get("tilt", 0.0)
    anchor, target = spec["anchor"]
    if tilt:
        a = math.radians(tilt)
        pivot = j[anchor]
        cos_a, sin_a = math.cos(a), math.sin(a)
        j = {k: (v[0],
                 pivot[1] + (v[1] - pivot[1]) * cos_a - (v[2] - pivot[2]) * sin_a,
                 pivot[2] + (v[1] - pivot[1]) * sin_a + (v[2] - pivot[2]) * cos_a)
             for k, v in j.items()}
    off = tuple(target[i] - j[anchor][i] for i in range(3))
    j = {k: add(v, off) for k, v in j.items()}
    if spec.get("plane") == "front":     # flags: the body runs across the front camera
        j = {k: (v[2], v[1], -v[0]) for k, v in j.items()}
    return j


# ============================ poses ============================

def d(base, **over):
    out = dict(base)
    out.update(over)
    return out


FLOOR = ("ankle_r", (0.0, 0.055, 0.0))
HANDS = ("wrist_r", (0.0, 0.0, 0.0))
BAR = ("wrist_r", (0.0, 2.15, 0.0))
LOW_BAR = ("wrist_r", (0.0, 1.05, 0.0))
DIP_BAR = ("wrist_r", (0.0, 1.15, 0.0))
PARALLETTE = ("wrist_r", (0.0, 0.32, 0.0))
POLE = ("wrist_r", (0.0, 1.55, 0.0))

STAND = dict(torso=3, arm=177, elbow=178, hip=180, knee=180, ankle=92, head=1)
SQUAT = dict(torso=42, arm=72, elbow=74, hip=105, knee=192, ankle=85, head=20)
PRONE = dict(torso=92, arm=184, elbow=178, hand=110, hip=272, knee=271, ankle=215, head=74)
PRONE_DOWN = d(PRONE, torso=90, arm=234, elbow=156, hip=270, knee=269)
HANG = dict(torso=354, arm=8, elbow=4, hip=182, knee=196, ankle=120, head=352)
PULL_TOP = dict(torso=348, arm=75, elbow=300, hip=184, knee=200, ankle=120, head=346)
DIP_TOP = dict(torso=8, arm=181, elbow=177, hand=150, hip=188, knee=205, ankle=120, head=4)
DIP_BOTTOM = d(DIP_TOP, torso=18, arm=225, elbow=285, hand=250, head=12)
HANDSTAND = dict(torso=180, neck_a=180, head=180, arm=180, elbow=180, hand=160,
                 hip=2, knee=1, ankle=15)
HSPU_DOWN = d(HANDSTAND, arm=120, elbow=230, hand=200, torso=176, hip=4)
PIKE = dict(torso=126, neck_a=140, head=150, arm=172, elbow=176, hand=140,
            hip=202, knee=190, ankle=215)
PIKE_DOWN = d(PIKE, arm=136, elbow=222, hand=190, torso=122)
PLANK = dict(torso=91, arm=183, elbow=95, hand=90, hip=271, knee=270, ankle=215, head=76)
LSIT = dict(torso=2, arm=180, elbow=180, hand=150, hip=92, knee=90, ankle=62, head=6)
FL = dict(torso=92, arm=2, elbow=358, hand=20, hip=272, knee=271, ankle=266, head=80)
PLANCHE = dict(torso=95, arm=205, elbow=185, hand=150, hip=272, knee=270, ankle=265, head=80)
FLAG = dict(torso=272, neck_a=280, head=290, arm_l=268, elbow_l=270, hand_l=270,
            arm_r=176, elbow_r=178, hand_r=178, hip=92, knee=91, ankle=86)

# clip key -> pose spec. `a` is where the rep starts (lowering from), `b` where it turns
# around; a hold uses `a` alone and breathes towards `b` if one is given.
SPECS = {
    # --- push ---
    "push_ups": dict(a=PRONE, b=PRONE_DOWN, anchor=HANDS),
    "diamond_push_ups": dict(a=d(PRONE, arm_spread=-15, fore_spread=-20),
                             b=d(PRONE_DOWN, arm=240, elbow=150, arm_spread=-4, fore_spread=-20),
                             anchor=HANDS),
    "pike_push_ups": dict(a=PIKE, b=PIKE_DOWN, anchor=HANDS),
    "elevated_pike_push_ups": dict(a=d(PIKE, torso=140, hip=210), b=d(PIKE_DOWN, torso=136, hip=210),
                                   anchor=HANDS),
    "handstand_push_ups": dict(a=HANDSTAND, b=HSPU_DOWN, anchor=HANDS),
    "full_freestanding_hspu": dict(a=d(HANDSTAND, hip=4, knee=2), b=HSPU_DOWN, anchor=HANDS),
    "straddle_freestanding_hspu": dict(a=d(HANDSTAND, leg_spread=34), b=d(HSPU_DOWN, leg_spread=34),
                                       anchor=HANDS),
    "wall_assisted_hspu": dict(a=d(HANDSTAND, torso=184, hip=356), b=d(HSPU_DOWN, torso=182),
                               anchor=HANDS),
    "negative_wall_hspu": dict(a=d(HANDSTAND, torso=184, hip=356), b=d(HSPU_DOWN, torso=182),
                               anchor=HANDS),
    "wall_assisted_handstand_hold": dict(a=d(HANDSTAND, torso=184, hip=356),
                                         b=d(HANDSTAND, torso=182, hip=0), anchor=HANDS),
    "wall_walks_holds": dict(a=d(HANDSTAND, torso=162, hip=20, knee=16, ankle=30),
                             b=d(HANDSTAND, torso=170, hip=12, knee=9, ankle=25), anchor=HANDS),
    "dips": dict(a=DIP_TOP, b=DIP_BOTTOM, anchor=DIP_BAR),
    "basic_dips": dict(a=DIP_TOP, b=d(DIP_BOTTOM, arm=215, elbow=300), anchor=DIP_BAR),
    "straight_bar_dips": dict(a=d(DIP_TOP, torso=14), b=d(DIP_BOTTOM, torso=26), anchor=DIP_BAR),

    # --- pull ---
    "pull_ups": dict(a=PULL_TOP, b=HANG, anchor=BAR),
    "basic_pull_ups": dict(a=PULL_TOP, b=HANG, anchor=BAR),
    "chin_ups": dict(a=d(PULL_TOP, arm_spread=-8, arm=85, elbow=295), b=d(HANG, arm_spread=-8),
                     anchor=BAR),
    "explosive_pull_ups": dict(a=d(PULL_TOP, arm=95, elbow=290, torso=344), b=HANG, anchor=BAR),
    "australian_pull_ups_rows": dict(a=dict(torso=90, arm=52, elbow=318, hip=270, knee=269,
                                            ankle=200, head=76),
                                     b=dict(torso=90, arm=6, elbow=2, hip=270, knee=269,
                                            ankle=200, head=76),
                                     anchor=LOW_BAR, tilt=-14),
    "active_scapula_hangs": dict(a=d(HANG, arm=14, elbow=8, head=346), b=d(HANG, arm=4, elbow=2),
                                 anchor=BAR),
    "scapula_shrugs": dict(a=d(HANG, arm=14, elbow=8, head=346), b=d(HANG, arm=4, elbow=2),
                           anchor=BAR),
    "one_arm_active_hang": dict(a=d(HANG, arm_r=10, elbow_r=5, arm_l=200, elbow_l=196, torso=8),
                                b=d(HANG, arm_r=6, elbow_r=3, arm_l=200, elbow_l=196, torso=6),
                                anchor=BAR),
    "muscle_ups": dict(a=d(DIP_TOP, torso=6, hip=184, knee=196), mid=d(PULL_TOP, arm=105, elbow=285),
                       b=HANG, anchor=BAR),
    "full_muscle_up": dict(a=d(DIP_TOP, torso=6, hip=184, knee=196), mid=d(PULL_TOP, arm=105, elbow=285),
                           b=HANG, anchor=BAR),
    "negative_muscle_up": dict(a=d(DIP_TOP, torso=6, hip=184, knee=196), mid=d(PULL_TOP, arm=105, elbow=285),
                               b=HANG, anchor=BAR),
    "assisted_muscle_up_band": dict(a=d(DIP_TOP, torso=6, hip=184, knee=150),
                                    mid=d(PULL_TOP, arm=105, elbow=285, knee=160),
                                    b=d(HANG, knee=150), anchor=BAR),

    # --- core ---
    "hanging_leg_raises": dict(a=d(HANG, hip=96, knee=92, ankle=60, torso=350),
                               b=d(HANG, hip=180, knee=180, ankle=100), anchor=BAR),
    "toes_to_bar": dict(a=d(HANG, hip=46, knee=40, ankle=20, torso=344),
                        b=d(HANG, hip=180, knee=180, ankle=100), anchor=BAR),
    "l_sit": dict(a=LSIT, b=d(LSIT, hip=88, torso=4), anchor=PARALLETTE),
    "tucked_l_sit": dict(a=d(LSIT, hip=96, knee=172, ankle=120),
                         b=d(LSIT, hip=92, knee=168, ankle=118, torso=4), anchor=PARALLETTE),
    "plank": dict(a=PLANK, b=d(PLANK, torso=92, hip=272), anchor=("elbow_r", (0.0, 0.05, 0.0))),
    "ab_wheel_rollouts": dict(a=dict(torso=58, arm=142, elbow=118, hand=110, hip=216, knee=268,
                                     ankle=250, head=44),
                              b=dict(torso=82, arm=98, elbow=94, hand=88, hip=246, knee=270,
                                     ankle=250, head=70),
                              anchor=("knee_r", (0.0, 0.055, 0.0))),

    # --- legs ---
    "bodyweight_squats": dict(a=STAND, b=SQUAT, anchor=FLOOR),
    "airborne_squats": dict(a=d(STAND, hip_l=198, knee_l=110, ankle_l=60, arm=95, elbow=92),
                            b=d(SQUAT, hip_r=112, knee_r=193, hip_l=214, knee_l=58, ankle_l=20,
                                arm=88, elbow=86),
                            anchor=FLOOR),
    "pistol_squats": dict(a=d(STAND, hip_l=152, knee_l=150, ankle_l=70, arm=95, elbow=92),
                          b=d(SQUAT, hip_r=100, knee_r=190, hip_l=62, knee_l=74, ankle_l=40,
                              arm=82, elbow=80, torso=46),
                          anchor=FLOOR),
    "shrimp_squats": dict(a=d(STAND, torso=8, hip_l=192, knee_l=96, ankle_l=50,
                              arm_l=152, elbow_l=212, arm_r=95, elbow_r=92),
                          b=d(SQUAT, torso=34, hip_r=116, knee_r=194, hip_l=224, knee_l=70,
                              ankle_l=30, arm_l=170, elbow_l=228, arm_r=88, elbow_r=86),
                          anchor=FLOOR),
    "bulgarian_split_squats": dict(a=d(STAND, torso=6, hip_l=248, knee_l=172, ankle_l=140,
                                       arm=172, elbow=174),
                                   b=d(STAND, torso=20, hip_r=112, knee_r=192, ankle_r=84,
                                       hip_l=262, knee_l=126, ankle_l=100, arm=168, elbow=170),
                                   anchor=FLOOR),
    "calf_raises": dict(a=d(STAND, ankle=126, torso=1), b=d(STAND, ankle=74, torso=4),
                        anchor=("toe_r", (0.0, 0.0, 0.0))),

    # --- planche family (hands on the floor, body above) ---
    "planche_lean": dict(a=d(PLANCHE, hip=272, knee=271, arm=200, elbow=178, torso=92),
                         b=d(PLANCHE, hip=273, knee=272, arm=203, elbow=178, torso=91),
                         anchor=HANDS),
    "frog_stand": dict(a=dict(torso=196, neck_a=150, head=138, arm=158, elbow=202, hand=120,
                              hip=138, knee=318, ankle=286),
                       b=dict(torso=194, neck_a=148, head=136, arm=160, elbow=204, hand=118,
                              hip=140, knee=316, ankle=286),
                       anchor=HANDS),
    "tuck_planche_hold": dict(a=d(PLANCHE, hip=250, knee=330, ankle=290),
                              b=d(PLANCHE, hip=252, knee=328, ankle=290, torso=94), anchor=HANDS),
    "advanced_tuck_planche": dict(a=d(PLANCHE, hip=268, knee=342, ankle=300),
                                  b=d(PLANCHE, hip=270, knee=340, ankle=300, torso=94), anchor=HANDS),
    "one_legged_advanced_tuck": dict(a=d(PLANCHE, hip_r=270, knee_r=268, ankle_r=264,
                                         hip_l=266, knee_l=342, ankle_l=300),
                                     b=d(PLANCHE, hip_r=271, knee_r=269, ankle_r=264,
                                         hip_l=268, knee_l=340, ankle_l=300, torso=94), anchor=HANDS),
    "straddle_planche_hold": dict(a=d(PLANCHE, hip=270, knee=268, leg_spread=32),
                                  b=d(PLANCHE, hip=271, knee=269, leg_spread=33, torso=94),
                                  anchor=HANDS),
    "full_planche_hold": dict(a=d(PLANCHE, hip=272, knee=270),
                              b=d(PLANCHE, hip=273, knee=271, torso=94), anchor=HANDS),

    # --- front lever family (hanging, body horizontal) ---
    "full_front_lever_hold": dict(a=FL, b=d(FL, torso=93, hip=273), anchor=BAR),
    "straddle_front_lever_hold": dict(a=d(FL, leg_spread=32), b=d(FL, leg_spread=33, torso=93),
                                      anchor=BAR),
    "one_legged_fl_hold": dict(a=d(FL, hip_l=300, knee_l=20, ankle_l=350),
                               b=d(FL, hip_l=302, knee_l=18, ankle_l=350, torso=93), anchor=BAR),
    "advanced_tuck_fl_hold": dict(a=d(FL, hip=284, knee=12, ankle=350),
                                  b=d(FL, hip=286, knee=10, ankle=350, torso=93), anchor=BAR),
    "tuck_front_lever_hold": dict(a=d(FL, torso=86, hip=32, knee=196, ankle=150),
                                  b=d(FL, torso=88, hip=34, knee=194, ankle=150), anchor=BAR),
    "tuck_fl_rows": dict(a=d(FL, torso=86, hip=32, knee=196, ankle=150, arm=52, elbow=318),
                         b=d(FL, torso=86, hip=32, knee=196, ankle=150), anchor=BAR),
    "reversed_deadlift_fl_pulls": dict(a=d(FL, hip=284, knee=12, ankle=350),
                                       b=d(HANG, hip=186, knee=196, arm=4, elbow=2), anchor=BAR),

    # --- human flag family (vertical pole, body across the front view) ---
    "full_human_flag_hold": dict(a=FLAG, b=d(FLAG, torso=273, hip=93), anchor=POLE, plane="front"),
    "straddle_human_flag_hold": dict(a=d(FLAG, leg_spread=30), b=d(FLAG, leg_spread=31),
                                     anchor=POLE, plane="front"),
    "tuck_human_flag_hold": dict(a=d(FLAG, hip=120, knee=210, ankle=170),
                                 b=d(FLAG, hip=122, knee=208, ankle=170), anchor=POLE, plane="front"),
    "angled_tucked_flag_hold": dict(a=d(FLAG, hip=120, knee=210, ankle=170), b=d(FLAG, hip=122, knee=208,
                                    ankle=170), anchor=POLE, plane="front", tilt=34),
    "low_flag_hold": dict(a=FLAG, b=d(FLAG, torso=273, hip=93), anchor=POLE, plane="front", tilt=-32),
    "high_flag_hold_wall_walk": dict(a=FLAG, b=d(FLAG, torso=273, hip=93), anchor=POLE,
                                     plane="front", tilt=52),
    "twisted_flag_hold": dict(a=d(FLAG, leg_spread=22, hip=100, knee=96),
                              b=d(FLAG, leg_spread=23, hip=102, knee=98), anchor=POLE, plane="front"),
    "one_arm_inverted_support": dict(a=d(FLAG, torso=272, hip=92, arm_r=176, elbow_r=178,
                                         arm_l=190, elbow_l=200),
                                     b=d(FLAG, torso=273, hip=93, arm_r=177, elbow_r=179,
                                         arm_l=190, elbow_l=200),
                                     anchor=POLE, plane="front", tilt=78),
}

# Tempo per clip, mirroring exercise_tempo() in routes/workouts.py (None = static hold).
HOLD_KEYS = {"advanced_tuck_fl_hold", "advanced_tuck_planche", "angled_tucked_flag_hold", "frog_stand",
             "full_front_lever_hold", "full_human_flag_hold", "full_planche_hold", "high_flag_hold_wall_walk",
             "l_sit", "low_flag_hold", "one_arm_active_hang", "one_arm_inverted_support",
             "one_legged_advanced_tuck", "one_legged_fl_hold", "planche_lean", "plank",
             "straddle_front_lever_hold", "straddle_human_flag_hold", "straddle_planche_hold",
             "tuck_front_lever_hold", "tuck_human_flag_hold", "tuck_planche_hold", "tucked_l_sit",
             "twisted_flag_hold", "wall_assisted_handstand_hold", "wall_walks_holds"}
TEMPOS = {"explosive_pull_ups": (2, 0, 1), "assisted_muscle_up_band": (2, 0, 1),
          "full_muscle_up": (2, 0, 1), "muscle_ups": (2, 0, 1),
          "negative_muscle_up": (5, 1, 1), "negative_wall_hspu": (5, 1, 1),
          "active_scapula_hangs": (2, 1, 1), "scapula_shrugs": (2, 1, 1),
          "toes_to_bar": (2, 1, 1), "calf_raises": (2, 1, 1)}


def tempo_for(key):
    return None if key in HOLD_KEYS else TEMPOS.get(key, (3, 1, 1))


# ============================ baking ============================

def ease(x):
    return x * x * (3.0 - 2.0 * x)


def blend(a, b, u):
    keys = set(a) | set(b)
    return {k: a.get(k, b.get(k)) * (1.0 - u) + b.get(k, a.get(k)) * u for k in keys}


def path_pose(spec, u):
    """u in [0, 1]: `a` -> (`mid`) -> `b`."""
    a, b, mid = spec["a"], spec.get("b", spec["a"]), spec.get("mid")
    if mid is None:
        return blend(a, b, u)
    return blend(a, mid, u * 2) if u <= 0.5 else blend(mid, b, (u - 0.5) * 2)


def frames_for(key, spec):
    """(times, poses) for one clip: a rep over its tempo, or a hold with a slow breath."""
    tempo = tempo_for(key)
    if tempo is None:
        span, steps = 4.0, 8
        pairs = [(span * i / steps, 0.5 - 0.5 * math.cos(2 * math.pi * i / steps))
                 for i in range(steps + 1)]
    else:
        down, pause, up = tempo
        pairs = [(down * i / 6.0, ease(i / 6.0)) for i in range(7)]
        if pause:
            pairs.append((down + pause, 1.0))
        start = down + pause
        pairs += [(start + up * i / 5.0, 1.0 - ease(i / 5.0)) for i in range(1, 6)]
    return [t for t, _ in pairs], [posed(path_pose(spec, u), spec) for _, u in pairs]


def normalise(poses):
    """One offset for the whole clip: centred on X/Z, standing on y = 0."""
    pts = [p for pose in poses for p in pose.values()]
    cx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2
    cz = (min(p[2] for p in pts) + max(p[2] for p in pts)) / 2
    low = min(p[1] for p in pts) - 0.05
    return [{k: (v[0] - cx, v[1] - low, v[2] - cz) for k, v in pose.items()} for pose in poses]


def quat_from_y(direction):
    """Rotation taking +Y to `direction` (glTF order: x, y, z, w)."""
    x, y, z = direction
    length = math.sqrt(x * x + y * y + z * z) or 1.0
    x, y, z = x / length, y / length, z / length
    if y > 0.999999:
        return (0.0, 0.0, 0.0, 1.0)
    if y < -0.999999:
        return (1.0, 0.0, 0.0, 0.0)
    ax, az = z, -x
    norm = math.sqrt(ax * ax + az * az) or 1.0
    half = math.acos(max(-1.0, min(1.0, y))) / 2
    s = math.sin(half) / norm
    return (ax * s, 0.0, az * s, math.cos(half))


def node_trs(pose, node):
    """(translation, rotation) for one bone or ball in this pose."""
    kind, a, b, _r = node
    if kind == "ball":
        return pose[a], (0.0, 0.0, 0.0, 1.0)
    pa, pb = pose[a], pose[b]
    return pa, quat_from_y((pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]))


def bone_length(pose, node):
    kind, a, b, _r = node
    if kind == "ball":
        return 1.0
    pa, pb = pose[a], pose[b]
    return math.dist(pa, pb) or 1e-4


# ============================ glTF ============================

class Blob:
    def __init__(self):
        self.data = bytearray()
        self.views = []
        self.accessors = []

    def _view(self, payload, target=None):
        while len(self.data) % 4:
            self.data.append(0)
        view = {"buffer": 0, "byteOffset": len(self.data), "byteLength": len(payload)}
        if target:
            view["target"] = target
        self.data.extend(payload)
        self.views.append(view)
        return len(self.views) - 1

    def floats(self, rows, kind, target=None, bounds=False):
        count = len(rows)
        width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[kind]
        flat = [v for row in rows for v in (row if width > 1 else (row,))]
        view = self._view(struct.pack(f"<{len(flat)}f", *flat), target)
        acc = {"bufferView": view, "componentType": 5126, "count": count, "type": kind}
        if bounds:  # required on POSITION, expected on an animation's input times
            cols = list(zip(*[row if width > 1 else (row,) for row in rows]))
            acc["min"] = [min(c) for c in cols]
            acc["max"] = [max(c) for c in cols]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def ushorts(self, values, target=None):
        view = self._view(struct.pack(f"<{len(values)}H", *values), target)
        self.accessors.append({"bufferView": view, "componentType": 5123, "count": len(values),
                               "type": "SCALAR", "min": [min(values)], "max": [max(values)]})
        return len(self.accessors) - 1


def cylinder(sides=12):
    """Unit segment along +Y (0..1), radius 1, with flat caps."""
    pos, nrm, idx = [], [], []
    for i in range(sides + 1):
        a = 2 * math.pi * i / sides
        cx, cz = math.cos(a), math.sin(a)
        pos += [(cx, 0.0, cz), (cx, 1.0, cz)]
        nrm += [(cx, 0.0, cz), (cx, 0.0, cz)]
    for i in range(sides):
        b = i * 2
        idx += [b, b + 1, b + 3, b, b + 3, b + 2]
    for y, normal in ((0.0, (0.0, -1.0, 0.0)), (1.0, (0.0, 1.0, 0.0))):
        centre = len(pos)
        pos.append((0.0, y, 0.0))
        nrm.append(normal)
        for i in range(sides + 1):
            a = 2 * math.pi * i / sides
            pos.append((math.cos(a), y, math.sin(a)))
            nrm.append(normal)
        for i in range(sides):
            ring = centre + 1 + i
            idx += [centre, ring, ring + 1] if y else [centre, ring + 1, ring]
    return pos, nrm, idx


def ball(lon=14, lat=9):
    pos, nrm, idx = [], [], []
    for i in range(lat + 1):
        phi = math.pi * i / lat
        for j in range(lon + 1):
            theta = 2 * math.pi * j / lon
            p = (math.sin(phi) * math.cos(theta), math.cos(phi), math.sin(phi) * math.sin(theta))
            pos.append(p)
            nrm.append(p)
    for i in range(lat):
        for j in range(lon):
            a = i * (lon + 1) + j
            b = a + lon + 1
            idx += [a, b, a + 1, a + 1, b, b + 1]
    return pos, nrm, idx


def ball_parent(joint):
    """(bone index, end) — the bone a joint's ball hangs off: 0 = its start, 1 = its far end."""
    for i, (a, _b, _r) in enumerate(BONES):
        if a == joint:
            return i, 0
    for i, (_a, b, _r) in enumerate(BONES):
        if b == joint:
            return i, 1
    raise KeyError(joint)


def build(out_path):
    nodes_spec = [("bone", a, b, r) for a, b, r in BONES]
    blob = Blob()

    meshes = []
    for geo in (cylinder(), ball()):
        pos, nrm, idx = geo
        meshes.append({"primitives": [{
            "attributes": {"POSITION": blob.floats(pos, "VEC3", 34962, bounds=True),
                           "NORMAL": blob.floats(nrm, "VEC3", 34962)},
            "indices": blob.ushorts(idx, 34963), "material": 0}]})

    clips = sorted(SPECS)
    baked = {}
    for key in clips:
        times, poses = frames_for(key, SPECS[key])
        baked[key] = (times, normalise(poses))

    rest = baked["bodyweight_squats"][1][0]
    nodes, lengths = [], []
    for node in nodes_spec:
        _kind, a, b, radius = node
        translation, rotation = node_trs(rest, node)
        length = bone_length(rest, node)
        lengths.append(length)
        nodes.append({"name": f"{a}__{b}", "mesh": 0, "translation": list(translation),
                      "rotation": list(rotation), "scale": [radius, length, radius]})
    for joint, radius in BALLS:
        parent, end = ball_parent(joint)
        bone_radius, length = BONES[parent][2], lengths[parent]
        nodes.append({"name": f"ball_{joint}", "mesh": 1, "translation": [0.0, float(end), 0.0],
                      "scale": [radius / bone_radius, radius / length, radius / bone_radius]})
        nodes[parent].setdefault("children", []).append(len(nodes) - 1)

    animations = []
    for key in clips:
        times, poses = baked[key]
        time_acc = blob.floats(times, "SCALAR", bounds=True)
        samplers, channels = [], []
        for node_index, node in enumerate(nodes_spec):
            trs = [node_trs(pose, node) for pose in poses]
            for path, values in (("translation", [t for t, _ in trs]), ("rotation", [r for _, r in trs])):
                kind = "VEC3" if path == "translation" else "VEC4"
                samplers.append({"input": time_acc, "output": blob.floats(values, kind)})
                channels.append({"sampler": len(samplers) - 1,
                                 "target": {"node": node_index, "path": path}})
        animations.append({"name": key, "samplers": samplers, "channels": channels})

    gltf = {
        "asset": {"version": "2.0", "generator": "expense_tracker tools/build_exercises_glb.py"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes_spec)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [{
            "name": "hologram",
            "pbrMetallicRoughness": {"baseColorFactor": [0.42, 0.85, 1.0, 1.0],
                                     "metallicFactor": 0.0, "roughnessFactor": 0.55},
            "emissiveFactor": [0.16, 0.55, 0.72],
            "doubleSided": True,
        }],
        "animations": animations,
        "buffers": [{"byteLength": len(blob.data)}],
        "bufferViews": blob.views,
        "accessors": blob.accessors,
    }

    json_chunk = json.dumps(gltf, separators=(",", ":")).encode()
    json_chunk += b" " * ((-len(json_chunk)) % 4)
    bin_chunk = bytes(blob.data) + b"\0" * ((-len(blob.data)) % 4)
    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    glb = (struct.pack("<4sII", b"glTF", 2, total)
           + struct.pack("<I4s", len(json_chunk), b"JSON") + json_chunk
           + struct.pack("<I4s", len(bin_chunk), b"BIN\0") + bin_chunk)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(glb)
    return baked, len(glb)


# ============================ preview ============================

def png(path, width, height, pixels):
    raw = b"".join(b"\0" + bytes(pixels[y * width * 3:(y + 1) * width * 3]) for y in range(height))
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def preview(baked, path, cols=6, cell=200):
    """Contact sheet: first (cyan) and mid (magenta) pose of every clip, in clip order."""
    keys = sorted(baked)
    rows = (len(keys) + cols - 1) // cols
    width, height = cols * cell, rows * cell
    buf = bytearray(width * height * 3)

    def dot(cx, cy, radius, colour):
        for y in range(max(0, int(cy - radius)), min(height, int(cy + radius) + 1)):
            for x in range(max(0, int(cx - radius)), min(width, int(cx + radius) + 1)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                    i = (y * width + x) * 3
                    buf[i:i + 3] = bytes(colour)

    for n, key in enumerate(keys):
        times, poses = baked[key]
        ox, oy = (n % cols) * cell, (n // cols) * cell
        side = SPECS[key].get("plane") != "front"
        picks = [(poses[0], (70, 220, 255)), (poses[len(poses) // 2], (255, 90, 190))]
        pts = [p for pose, _ in picks for p in pose.values()]
        flat = [(p[2] if side else p[0], p[1]) for p in pts]
        span = max(max(a for a, _ in flat) - min(a for a, _ in flat),
                   max(b for _, b in flat) - min(b for _, b in flat), 0.4)
        scale = (cell - 24) / span
        mx = (min(a for a, _ in flat) + max(a for a, _ in flat)) / 2
        my = (min(b for _, b in flat) + max(b for _, b in flat)) / 2
        for y in range(oy, min(height, oy + cell)):
            for x in range(ox, min(width, ox + cell)):
                i = (y * width + x) * 3
                buf[i:i + 3] = bytes((10, 14, 22) if (n // cols + n) % 2 else (14, 18, 28))
        for pose, colour in picks:
            def screen(p):
                return (ox + cell / 2 + ((p[2] if side else p[0]) - mx) * scale,
                        oy + cell / 2 - (p[1] - my) * scale)
            for a, b, r in BONES:
                x0, y0 = screen(pose[a])
                x1, y1 = screen(pose[b])
                steps = max(2, int(math.dist((x0, y0), (x1, y1))))
                for s in range(steps + 1):
                    dot(x0 + (x1 - x0) * s / steps, y0 + (y1 - y0) * s / steps, r * scale, colour)
            for j, r in BALLS:
                x0, y0 = screen(pose[j])
                dot(x0, y0, r * scale, colour)
    png(path, width, height, buf)
    return keys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--preview", type=Path, help="write a PNG contact sheet of the poses")
    args = parser.parse_args()
    baked, size = build(args.out)
    print(f"{args.out}: {len(baked)} clips, {size / 1024:.0f} KB")
    if args.preview:
        keys = preview(baked, args.preview)
        print(f"{args.preview}: {len(keys)} cells")
        for i, key in enumerate(keys):
            print(f"{i:2d} {key}")


if __name__ == "__main__":
    main()
