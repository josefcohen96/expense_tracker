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

L = {"spine": 0.30, "neck": 0.12, "head": 0.14, "sh_up": 0.04, "sh_w": 0.18,
     "uarm": 0.28, "farm": 0.26, "hand": 0.13, "hip_w": 0.10,
     "thigh": 0.42, "shin": 0.40, "foot": 0.19}

# (joint a, joint b, radius, shape) — the segments drawn between joints. Shapes are lathes
# (see SHAPES) sized by the node's scale, so the figure has a silhouette instead of even
# sticks: a chest that widens into the shoulders over a narrow waist, muscled limbs, a
# paddle hand, a shoe. Every segment is oriented in full (its own X runs across the body),
# so the flat shapes stay flat the right way in any pose — see frame_quat().
BONES = [("pelvis", "chest", 0.115, "torso"), ("chest", "neck", 0.050, "neck"),
         ("neck", "head", 0.046, "neck"),
         ("shoulder_l", "shoulder_r", 0.058, "bar"), ("hip_l", "hip_r", 0.060, "bar")]
for _s in ("l", "r"):
    BONES += [(f"shoulder_{_s}", f"elbow_{_s}", 0.054, "uarm"),
              (f"elbow_{_s}", f"wrist_{_s}", 0.046, "farm"),
              (f"wrist_{_s}", f"hand_{_s}", 0.040, "hand"),
              (f"hip_{_s}", f"knee_{_s}", 0.066, "thigh"),
              (f"knee_{_s}", f"ankle_{_s}", 0.054, "shin"),
              (f"ankle_{_s}", f"toe_{_s}", 0.048, "foot")]

# Parts that ride on a bone: (joint, radius, shape, offset). The balls hide the seams at the
# joints; the offset (world units, in the bone's own frame: x across, y along, z forward)
# places the deltoid caps out on the shoulders, the nose on the face, the heel behind the
# ankle. `parent` names the bone to ride when a joint has more than one.
BALLS = [("head", 0.112, "head", None), ("pelvis", 0.080, "pelvis", None),
         ("chest", 0.064, "ball", None),
         ("head", 0.030, "nose", dict(offset=(0.0, -0.02, 0.10), parent=("neck", "head")))]
for _s in ("l", "r"):
    BALLS += [(f"shoulder_{_s}", 0.066, "deltoid", dict(parent=(f"shoulder_{_s}", f"elbow_{_s}"))),
              (f"elbow_{_s}", 0.046, "ball", None),
              (f"wrist_{_s}", 0.036, "ball", None), (f"hip_{_s}", 0.062, "ball", None),
              (f"knee_{_s}", 0.052, "ball", None), (f"ankle_{_s}", 0.040, "ball", None),
              (f"ankle_{_s}", 0.040, "heel", dict(offset=(0.0, -0.045, 0.012),
                                                  parent=(f"ankle_{_s}", f"toe_{_s}")))]

# Lathe profiles up the segment: (y, width, depth) as fractions of the part's radius —
# width across the body (local X), depth front to back (local Z) — revolved over `sides`.
# `stretch` lengthens a ball along its own Y; `depth` squashes a whole sphere.
SHAPES = {
    "torso": dict(profile=[(0.0, 0.96, 0.68), (0.22, 0.88, 0.60), (0.42, 0.86, 0.58),
                           (0.66, 1.12, 0.68), (0.86, 1.36, 0.70), (1.0, 1.30, 0.62)], sides=16),
    "uarm": dict(profile=[(0.0, 0.88, 0.88), (0.18, 1.0, 1.0), (0.52, 1.02, 0.98),
                          (0.86, 0.76, 0.76), (1.0, 0.66, 0.66)], sides=12),
    "farm": dict(profile=[(0.0, 0.80, 0.80), (0.22, 1.0, 1.0), (0.62, 0.84, 0.84),
                          (1.0, 0.60, 0.60)], sides=12),
    "thigh": dict(profile=[(0.0, 0.96, 0.96), (0.22, 1.04, 1.04), (0.62, 0.92, 0.92),
                           (1.0, 0.70, 0.70)], sides=12),
    "shin": dict(profile=[(0.0, 0.74, 0.74), (0.28, 1.0, 1.0), (0.66, 0.78, 0.78),
                          (1.0, 0.54, 0.54)], sides=12),
    "neck": dict(profile=[(0.0, 1.0, 1.0), (0.6, 0.95, 0.95), (1.0, 0.88, 0.88)], sides=10),
    "bar": dict(profile=[(0.0, 0.88, 0.88), (0.5, 1.0, 1.0), (1.0, 0.88, 0.88)], sides=8),
    # a flat paddle: wide across the palm, thin through it, rounding off at the fingertips
    "hand": dict(profile=[(0.0, 0.86, 0.60), (0.30, 1.20, 0.52), (0.62, 1.24, 0.44),
                          (0.88, 1.0, 0.36), (1.0, 0.56, 0.24)], sides=10),
    # a shoe: broad, low, squared off at the toe
    "foot": dict(profile=[(0.0, 0.82, 0.90), (0.30, 1.0, 0.84), (0.72, 1.06, 0.66),
                          (0.92, 0.96, 0.46), (1.0, 0.62, 0.30)], sides=10),
    "rod": dict(profile=[(0.0, 1.0, 1.0), (1.0, 1.0, 1.0)], sides=10),
    "ball": dict(sphere=(14, 9)),
    "pelvis": dict(sphere=(14, 9), depth=0.72),
    "deltoid": dict(sphere=(14, 9), stretch=1.2),
    "head": dict(sphere=(16, 11), depth=0.92, stretch=1.14),
    "nose": dict(sphere=(8, 6), depth=1.3, stretch=0.9),
    "heel": dict(sphere=(10, 7), stretch=0.9),
}


def shape_scale(shape, radius, length):
    """Node scale for one part: radius across, `length` along its own axis, `depth` front to back."""
    spec = SHAPES[shape]
    return [radius, length * spec.get("stretch", 1.0), radius * spec.get("depth", 1.0)]


SIDEWAYS = (1.0, 0.0, 0.0)     # the body's own left-right axis in the sagittal authoring frame


def vec(angle, length, spread=0.0, sx=1.0, lateral=SIDEWAYS):
    """Sagittal direction: 0 = up (+Y), 90 = forward (+Z); spread splays out along `lateral`."""
    a, s = math.radians(angle), math.radians(spread)
    side = sx * length * math.sin(s)
    return (side * lateral[0],
            length * math.cos(a) * math.cos(s) + side * lateral[1],
            length * math.sin(a) * math.cos(s) + side * lateral[2])


def add(p, v):
    return (p[0] + v[0], p[1] + v[1], p[2] + v[2])


def body(**p):
    """Joint positions for one pose. Angles are absolute; `_l` / `_r` suffixes override a side.
    `lateral` is where the shoulders and hips spread out from the spine — sideways unless the
    body is rolled, as in a human flag, where it is (0, 1, 0): one shoulder over the other."""
    def g(key, side, default=None):
        return p.get(f"{key}_{side}", p.get(key, default))

    torso = p.get("torso", 0.0)
    lat = p.get("lateral", SIDEWAYS)
    j = {"pelvis": (0.0, 0.0, 0.0)}
    j["chest"] = add(j["pelvis"], vec(torso, L["spine"]))
    neck_a = p.get("neck_a", torso)
    j["neck"] = add(j["chest"], vec(neck_a, L["neck"]))
    j["head"] = add(j["neck"], vec(p.get("head", neck_a), L["head"]))
    for side, sx in (("l", -1.0), ("r", 1.0)):
        shoulder = add(add(j["chest"], vec(torso, L["sh_up"])),
                       tuple(sx * L["sh_w"] * c for c in lat))
        j["shoulder_" + side] = shoulder
        arm, asp = g("arm", side, 180.0), g("arm_spread", side, 0.0)
        elbow = add(shoulder, vec(arm, L["uarm"], asp, sx, lat))
        j["elbow_" + side] = elbow
        fore, fsp = g("elbow", side, arm), g("fore_spread", side, g("arm_spread", side, 0.0))
        wrist = add(elbow, vec(fore, L["farm"], fsp, sx, lat))
        j["wrist_" + side] = wrist
        j["hand_" + side] = add(wrist, vec(g("hand", side, fore), L["hand"], fsp, sx, lat))

        hip = add(j["pelvis"], tuple(sx * L["hip_w"] * c for c in lat))
        j["hip_" + side] = hip
        thigh, lsp = g("hip", side, 180.0), g("leg_spread", side, 0.0)
        knee = add(hip, vec(thigh, L["thigh"], lsp, sx, lat))
        j["knee_" + side] = knee
        shin = g("knee", side, thigh)
        ankle = add(knee, vec(shin, L["shin"], lsp, sx, lat))
        j["ankle_" + side] = ankle
        j["toe_" + side] = add(ankle, vec(g("ankle", side, shin - 90.0), L["foot"], lsp, sx, lat))
    return j


def chain_to(dy, dz, upper, lower, bend=1.0):
    """Absolute angles for a two-segment chain whose tip lands (dy, dz) from its root.
    `bend` picks which way the middle joint breaks: +1 forward (+Z), -1 backward."""
    reach = min(math.hypot(dy, dz), (upper + lower) * 0.999) or 1e-6
    base = math.degrees(math.atan2(dz, dy))
    cos_a = max(-1.0, min(1.0, (upper * upper + reach * reach - lower * lower) / (2 * upper * reach)))
    root = base + bend * math.degrees(math.acos(cos_a))
    mid_y, mid_z = upper * math.cos(math.radians(root)), upper * math.sin(math.radians(root))
    return root % 360, math.degrees(math.atan2(dz - mid_z, dy - mid_y)) % 360


def arm_to(dy, dz, bend=1.0):
    """Shoulder and elbow angles putting the wrist (dy, dz) from the shoulder."""
    arm, elbow = chain_to(dy, dz, L["uarm"], L["farm"], bend)
    return {"arm": arm, "elbow": elbow}


def leg_to(dy, dz, bend=1.0):
    """Hip and knee angles putting the ankle (dy, dz) from the hip."""
    hip, knee = chain_to(dy, dz, L["thigh"], L["shin"], bend)
    return {"hip": hip, "knee": knee}


def rotate_about(pose, pivot, angle):
    """The whole pose turned `angle` degrees about `pivot` in the sagittal (Y-Z) plane."""
    a = math.radians(angle)
    cos_a, sin_a = math.cos(a), math.sin(a)
    return {k: (v[0],
                pivot[1] + (v[1] - pivot[1]) * cos_a - (v[2] - pivot[2]) * sin_a,
                pivot[2] + (v[1] - pivot[1]) * sin_a + (v[2] - pivot[2]) * cos_a)
            for k, v in pose.items()}


LEG_JOINTS = ("hip", "knee", "ankle", "toe")


def contact_plan(pose, spec, base_tilt=0.0):
    """What holds the pose's second contact still, worked out on the clip's first frame:
    `pin` keeps a joint on the ray it started on from the anchor, `floor` keeps it at floor
    level (the level of the lowest non-leg joint unless the spec gives one), `plant` solves
    a leg so its ankle stays where it stood. None when the spec has no second contact."""
    _anchor, target = spec["anchor"]
    plan = {}
    if spec.get("pin"):
        joint = spec["pin"]
        plan["pin"] = (joint, (pose[joint][1] - target[1], pose[joint][2] - target[2]))
    if spec.get("floor"):
        joint, level = ((spec["floor"], None) if isinstance(spec["floor"], str)
                        else spec["floor"])
        if level is None:
            level = min(v[1] for k, v in pose.items() if k.split("_")[0] not in LEG_JOINTS)
        plan["floor"] = (joint, level - target[1], pose[joint][2] - target[2] < 0)
    if spec.get("plant"):
        joint = spec["plant"]
        plan["plant"] = (joint, pose[joint], pose["knee" + joint[-2:]])
    if spec.get("fixed"):
        # `pose` is the first frame already placed with its floor/pin: `base_tilt` is the
        # incline every later frame starts from and its contact is the spot to hold
        joint = spec["fixed"]
        plan["fixed"] = (joint, pose[joint], base_tilt)
    return plan or None


def _turn_to(j, target, joint, want):
    have = (j[joint][1] - target[1], j[joint][2] - target[2])
    turn = math.atan2(want[1], want[0]) - math.atan2(have[1], have[0])
    return rotate_about(j, target, math.degrees(turn)) if abs(turn) > 1e-9 else j


def _place(params, spec, extra_tilt=0.0):
    j = body(**params)
    tilt = spec.get("tilt", 0.0) + extra_tilt
    anchor, target = spec["anchor"]
    if tilt:
        j = rotate_about(j, j[anchor], tilt)
    off = tuple(target[i] - j[anchor][i] for i in range(3))
    return {k: add(v, off) for k, v in j.items()}


def _angle(v):
    """Direction of a sagittal vector (y, z) in the rotate_about() convention."""
    return math.degrees(math.atan2(v[1], v[0]))


def pose_tilt(placed, plain, spec):
    """How far `placed` was turned from `plain` (the same pose straight out of _place)."""
    _anchor, target = spec["anchor"]
    probe = "chest"
    return (_angle((placed[probe][1] - target[1], placed[probe][2] - target[2]))
            - _angle((plain[probe][1] - target[1], plain[probe][2] - target[2])))


def _fixed_solve(params, spec, plan):
    """Hands and the fixed joint both stay where they are; the body between the shoulders
    and that joint keeps its authored angles and pivots on the fixed joint; the arms are
    re-solved so the hands still land on the anchor. The authored pose only decides the
    depth — how high the shoulders sit above the hands — which is what a real push-up or
    row does: the toes or heels never skate, the body swings on them and the elbows give."""
    joint, spot, base_tilt = plan["fixed"]
    _anchor, target = spec["anchor"]
    j = _place(params, spec, base_tilt)
    shoulder, contact = j["shoulder_r"], j[joint]
    depth = shoulder[1] - target[1]                       # authored shoulder height
    reach = math.hypot(shoulder[1] - contact[1], shoulder[2] - contact[2])
    dy = max(-reach, min(reach, target[1] + depth - spot[1]))
    dz = math.sqrt(max(0.0, reach * reach - dy * dy)) * (1.0 if target[2] >= spot[2] else -1.0)
    turn = _angle((dy, dz)) - _angle((shoulder[1] - contact[1], shoulder[2] - contact[2]))
    tilt = base_tilt + turn
    want_shoulder = (spot[1] + dy, spot[2] + dz)
    # the arm chain, in the body's own (untilted) frame, from the shoulder to the anchor
    to_wrist = (target[1] - want_shoulder[0], target[2] - want_shoulder[1])
    a = math.radians(-tilt)
    local = (to_wrist[0] * math.cos(a) - to_wrist[1] * math.sin(a),
             to_wrist[0] * math.sin(a) + to_wrist[1] * math.cos(a))
    upper = L["uarm"] * math.cos(math.radians(params.get("arm_spread", 0.0)))
    lower = L["farm"] * math.cos(math.radians(params.get("fore_spread",
                                                         params.get("arm_spread", 0.0))))
    best = None
    for bend in (1.0, -1.0):          # the elbow breaks the way the authored pose has it
        arm, elbow = chain_to(local[0], local[1], upper, lower, bend)
        score = abs((arm - params.get("arm", 180.0) + 180.0) % 360.0 - 180.0)
        if best is None or score < best[0]:
            best = (score, arm, elbow)
    solved = dict(params, arm=best[1], elbow=best[2])
    for side in ("_l", "_r"):
        for k in ("arm", "elbow"):
            solved.pop(k + side, None)
    for k in ("hand", "hand_l", "hand_r"):    # the palms stay flat on the floor as the body turns
        if k in solved:
            solved[k] -= turn
    return _place(solved, spec, tilt)


def posed(params, spec, plan=None):
    """One pose placed in the world: anchored on its contact point, tilted, mapped to its plane.
    With a `plan` (see contact_plan()) the second contact holds too — the toes of a push-up
    stay on the floor as the body pivots about the hands, the heels of a row stay put, the
    rear foot of a split squat stays on its bench — instead of skating as the joints between
    the two contacts move."""
    _anchor, target = spec["anchor"]
    if plan and "fixed" in plan:
        j = _fixed_solve(params, spec, plan)
        if spec.get("plane") == "front":
            j = {k: (v[2], v[1], -v[0]) for k, v in j.items()}
        return j
    j = _place(params, spec)
    if plan:
        if "pin" in plan:
            joint, want = plan["pin"]
            j = _turn_to(j, target, joint, want)
        if "floor" in plan:
            joint, dy, behind = plan["floor"]
            reach = math.hypot(j[joint][1] - target[1], j[joint][2] - target[2])
            dy = max(-reach, min(reach, dy))
            dz = math.sqrt(max(0.0, reach * reach - dy * dy)) * (-1.0 if behind else 1.0)
            j = _turn_to(j, target, joint, (dy, dz))
        if "plant" in plan:
            # solve the planted leg for the ankle it started on; the knee breaks the way the
            # authored pose had it (pick the solution whose knee lands nearer it)
            joint, ankle, knee0 = plan["plant"]
            side = joint[-2:]
            hip = j["hip" + side]
            best = None
            for bend in (1.0, -1.0):
                angles = leg_to(ankle[1] - hip[1], ankle[2] - hip[2], bend)
                trial = _place(dict(params, **{"hip" + side: angles["hip"],
                                                "knee" + side: angles["knee"]}), spec)
                if "pin" in plan:
                    trial = _turn_to(trial, target, plan["pin"][0], plan["pin"][1])
                score = math.dist(trial["knee" + side], knee0)
                if best is None or score < best[0]:
                    best = (score, trial)
            j = best[1]
    if spec.get("plane") == "front":     # flags: the body runs across the front camera
        j = {k: (v[2], v[1], -v[0]) for k, v in j.items()}
    return j


def blend(a, b, u):
    """Pose parameters between `a` (u = 0) and `b` (u = 1); u past either end extrapolates.
    Angles take the short way round — a forearm going from 322deg to 4deg turns through 0,
    not down through 180."""
    out = {}
    for k in set(a) | set(b):
        va, vb = a.get(k, b.get(k)), b.get(k, a.get(k))
        if isinstance(va, tuple):                    # `lateral` is a vector
            out[k] = va
        else:
            out[k] = va + ((vb - va + 180.0) % 360.0 - 180.0) * u
    return out


# ============================ poses ============================

# What the hands are holding, derived from the pose's anchor (a spec's own `prop` wins).
# Without it a pull-up reads as a figure standing with bent arms.
def front_view(spec):
    """Whether the arena should open this clip on the front camera (flags and bar pulls)."""
    return spec.get("plane") == "front" or spec.get("view") == "front"


def anchor_prop(spec):
    return spec.get("prop", ANCHOR_PROP.get(spec["anchor"]))


def prop_rods(spec, pose):
    """(from, to, radius) per rod of this pose's prop. The grip never moves during a rep, so
    these come from the first frame and stay put; uprights make the rig read from every angle
    (a bare bar runs along X and is invisible end-on from the side camera)."""
    kind = anchor_prop(spec)
    if kind is None:
        return []
    _y, grip_y, grip_z = pose[spec["anchor"][0]]
    if kind == "bar":
        back = grip_z - 0.5                      # the frame stands behind the athlete
        rods = [((-0.62, grip_y, grip_z), (0.62, grip_y, grip_z), 0.026)]
        for x in (-0.62, 0.62):
            rods.append(((x, 0.0, back), (x, grip_y, back), 0.028))
            rods.append(((x, grip_y, back), (x, grip_y, grip_z), 0.026))
        return rods
    if kind == "rails":
        rods = []
        for wrist in (pose["wrist_l"], pose["wrist_r"]):
            rods.append(((wrist[0], grip_y, grip_z - 0.32), (wrist[0], grip_y, grip_z + 0.32), 0.026))
            rods.append(((wrist[0], 0.0, grip_z), (wrist[0], grip_y, grip_z), 0.026))
        return rods
    if kind == "pole":
        hands = [pose["hand_l"], pose["hand_r"], pose["wrist_l"], pose["wrist_r"]]
        x = sum(h[0] for h in hands) / len(hands)
        z = sum(h[2] for h in hands) / len(hands)
        return [((x, min(h[1] for h in hands) - 0.5, z), (x, max(h[1] for h in hands) + 0.5, z), 0.032)]
    return []


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

ANCHOR_PROP = {BAR: "bar", LOW_BAR: "bar", DIP_BAR: "rails", PARALLETTE: "rails", POLE: "pole"}

STAND = dict(torso=3, arm=177, elbow=178, hip=180, knee=180, ankle=92, head=1)
SQUAT = dict(torso=44, arm=72, elbow=74, ankle=86, head=22, **leg_to(-0.45, 0.2, bend=-1))
PRONE = dict(torso=92, arm=184, elbow=178, hand=110, hip=272, knee=271, ankle=215, head=74)
PRONE_DOWN = d(PRONE, torso=87, arm_spread=16, hip=267, knee=266, head=70,
               **arm_to(-0.23, -0.05))
GRIP_SPREAD = 10                 # hands a touch wider than the shoulders on the bar
HANG = dict(torso=354, arm=8, elbow=4, hip=182, knee=196, ankle=120, head=352,
            arm_spread=GRIP_SPREAD, fore_spread=GRIP_SPREAD)
# Elbows out to the sides at the top (pronated grip); the forearm angles back in so the
# hands stay where they were on the bar.
PULL_TOP = dict(torso=348, hip=184, knee=200, ankle=120, head=346, arm_spread=35, fore_spread=-12,
                **arm_to(0.2, 0.12))
# Halfway up a pull-up the legs drift forward of the line and swing back at the top — the
# small kip every real pull-up has; `mid` sits at the middle of the rep's timeline.
PULL_MID = d(blend(PULL_TOP, HANG, 0.5), hip=176, knee=206)
DIP_TOP = dict(torso=8, arm=181, elbow=177, hand=150, hip=188, knee=205, ankle=120, head=4)
DIP_BOTTOM = d(DIP_TOP, torso=20, hand=250, head=14, **arm_to(-0.37, 0.03))
HANDSTAND = dict(torso=186, neck_a=178, head=172, arm=178, elbow=182, hand=205,
                 hip=352, knee=356, ankle=20)
HSPU_DOWN = d(HANDSTAND, hand=205, torso=182, hip=350, **arm_to(-0.28, 0.14, bend=-1))
PIKE = dict(torso=126, neck_a=140, head=150, arm=172, elbow=176, hand=140,
            hip=202, knee=190, ankle=215)
PIKE_DOWN = d(PIKE, hand=190, torso=120, **arm_to(-0.3, 0.12))
PLANK = dict(torso=91, arm=183, elbow=95, hand=90, hip=271, knee=270, ankle=215, head=76)
LSIT = dict(torso=2, arm=180, elbow=180, hand=150, hip=92, knee=90, ankle=62, head=6)
FL = dict(torso=92, arm=2, elbow=358, hand=20, hip=272, knee=271, ankle=266, head=80)
PLANCHE = dict(torso=95, arm=205, elbow=185, hand=150, hip=272, knee=270, ankle=265, head=80)
# The flag is the one pose not in the sagittal plane: the body is rolled so the right shoulder
# sits above the left and the chest faces out (towards the front camera). The top arm reaches
# up the pole past the head, the bottom arm pushes down and in; both hands land on the pole.
FLAG = dict(torso=272, neck_a=280, head=290, lateral=(0.0, 1.0, 0.0),
            arm_l=226, elbow_l=226, hand_l=226, arm_r=282, elbow_r=282, hand_r=282,
            hip=92, knee=91, ankle=86)

# clip key -> pose spec. `a` is where the rep starts (lowering from), `b` where it turns
# around; a hold uses `a` alone and breathes towards `b` if one is given. `plane="front"`
# rotates the pose across the front camera (flags); `view="front"` only opens the clip on the
# front camera — for bar pulls, which are edge-on from the side (a body rising under a bar
# is a vertical line; the grip, the flaring elbows and the head clearing the bar all live in
# the frontal plane). The second contact is held by `pin` (a joint kept on its ray from the
# anchor), `floor` (a joint kept at floor level), `plant` (an ankle solved to stay put) or
# `fixed` (the joint stays put and the arms give, the body pivoting on it) — see
# contact_plan(); `family` picks the joint phasing of the rep (PHASING) when the anchor's own
# default is wrong.
SPECS = {
    # --- push ---
    "push_ups": dict(a=PRONE, b=PRONE_DOWN, anchor=HANDS, floor="toe_r", fixed="toe_r"),
    "diamond_push_ups": dict(a=d(PRONE, arm_spread=-15, fore_spread=-20),
                             b=d(PRONE_DOWN, arm_spread=-2, fore_spread=-18,
                                 **arm_to(-0.26, -0.02)),
                             anchor=HANDS, floor="toe_r", fixed="toe_r"),
    "pike_push_ups": dict(a=PIKE, b=PIKE_DOWN, anchor=HANDS, floor="toe_r", fixed="toe_r"),
    "elevated_pike_push_ups": dict(a=d(PIKE, torso=140, hip=210), b=d(PIKE_DOWN, torso=136, hip=210),
                                   anchor=HANDS, pin="toe_r", fixed="toe_r"),
    "handstand_push_ups": dict(a=HANDSTAND, b=HSPU_DOWN, anchor=HANDS),
    "full_freestanding_hspu": dict(a=d(HANDSTAND, hip=4, knee=2), b=HSPU_DOWN, anchor=HANDS),
    "straddle_freestanding_hspu": dict(a=d(HANDSTAND, leg_spread=34), b=d(HSPU_DOWN, leg_spread=34),
                                       anchor=HANDS),
    "wall_assisted_hspu": dict(a=d(HANDSTAND, torso=184, hip=356), b=d(HSPU_DOWN, torso=182),
                               anchor=HANDS, pin="ankle_r"),
    "partial_wall_hspu": dict(a=d(HANDSTAND, torso=184, hip=356),
                              b=d(HANDSTAND, torso=183, hip=355, **arm_to(-0.15, 0.08, bend=-1)),
                              anchor=HANDS, pin="ankle_r"),
    "freestanding_handstand_hold": dict(a=d(HANDSTAND, hip=2, knee=1, ankle=18),
                                        b=d(HANDSTAND, hip=358, knee=357, ankle=16), anchor=HANDS),
    # Hands by the hips and the shoulders kept out in front of them — the planche lean,
    # with the elbows folding back along the ribs instead of flaring out.
    "pseudo_planche_push_ups": dict(a=d(PRONE, hand=118, torso=93, **arm_to(-0.50, -0.16)),
                                    b=d(PRONE, hand=104, torso=88, hip=267, knee=266, head=70,
                                        **arm_to(-0.26, -0.20)),
                                    anchor=HANDS, floor="toe_r", fixed="toe_r"),
    "negative_wall_hspu": dict(a=d(HANDSTAND, torso=184, hip=356), b=d(HSPU_DOWN, torso=182),
                               anchor=HANDS, pin="ankle_r"),
    "wall_assisted_handstand_hold": dict(a=d(HANDSTAND, torso=184, hip=356),
                                         b=d(HANDSTAND, torso=182, hip=0), anchor=HANDS),
    "wall_walks_holds": dict(a=d(HANDSTAND, torso=162, hip=20, knee=16, ankle=30),
                             b=d(HANDSTAND, torso=170, hip=12, knee=9, ankle=25), anchor=HANDS,
                             pin="ankle_r"),
    "dips": dict(a=DIP_TOP, b=DIP_BOTTOM, anchor=DIP_BAR),
    "basic_dips": dict(a=DIP_TOP, b=d(DIP_BOTTOM, **arm_to(-0.43, 0.02)), anchor=DIP_BAR),
    "straight_bar_dips": dict(a=d(DIP_TOP, torso=14), b=d(DIP_BOTTOM, torso=26), anchor=DIP_BAR,
                              prop="bar"),

    # --- pull ---
    "pull_ups": dict(a=PULL_TOP, mid=PULL_MID, b=HANG, anchor=BAR, view="front"),
    "basic_pull_ups": dict(a=PULL_TOP, mid=PULL_MID, b=HANG, anchor=BAR, view="front"),
    "chin_ups": dict(a=d(PULL_TOP, arm_spread=-8, fore_spread=-8, **arm_to(0.24, 0.16)),
                     mid=d(PULL_MID, arm_spread=-8, fore_spread=-8, **arm_to(0.06, 0.12)),
                     b=d(HANG, arm_spread=-8, fore_spread=-8), anchor=BAR, view="front"),
    "explosive_pull_ups": dict(a=d(PULL_TOP, torso=344, **arm_to(0.3, 0.14)), b=HANG, anchor=BAR,
                               view="front"),
    "australian_pull_ups_rows": dict(a=dict(torso=90, arm=52, elbow=318, hip=270, knee=269,
                                            ankle=200, head=76),
                                     b=dict(torso=90, arm=6, elbow=2, hip=270, knee=269,
                                            ankle=200, head=76),
                                     anchor=LOW_BAR, floor=("ankle_r", 0.055), fixed="ankle_r"),
    "active_scapula_hangs": dict(a=d(HANG, arm=14, elbow=8, head=346), b=d(HANG, arm=4, elbow=2),
                                 anchor=BAR, view="front"),
    "scapula_shrugs": dict(a=d(HANG, arm=14, elbow=8, head=346), b=d(HANG, arm=4, elbow=2),
                           anchor=BAR, view="front"),
    "one_arm_active_hang": dict(a=d(HANG, arm_r=10, elbow_r=5, arm_l=200, elbow_l=196, torso=8),
                                b=d(HANG, arm_r=6, elbow_r=3, arm_l=200, elbow_l=196, torso=6),
                                anchor=BAR),
    "false_grip_hang": dict(a=d(HANG, hand=60), b=d(HANG, hand=64, arm=6, elbow=3),
                            anchor=BAR, view="front"),
    "false_grip_pull_ups": dict(a=d(PULL_TOP, hand=60, torso=346, **arm_to(0.16, 0.16)),
                                mid=d(PULL_MID, hand=60, **arm_to(0.04, 0.12)),
                                b=d(HANG, hand=60), anchor=BAR, view="front"),
    "low_bar_transitions": dict(a=d(DIP_TOP, torso=10, hip=150, knee=250, ankle=200),
                                mid=d(PULL_TOP, hip=150, knee=250, ankle=200, **arm_to(0.28, 0.2)),
                                b=d(HANG, hip=155, knee=250, ankle=200), anchor=LOW_BAR),
    "muscle_ups": dict(a=d(DIP_TOP, torso=6, hip=184, knee=196, arm_spread=GRIP_SPREAD),
                      mid=d(PULL_TOP, **arm_to(0.3, 0.2)), view="front",
                       b=HANG, anchor=BAR),
    "full_muscle_up": dict(a=d(DIP_TOP, torso=6, hip=184, knee=196, arm_spread=GRIP_SPREAD),
                          mid=d(PULL_TOP, **arm_to(0.3, 0.2)), view="front",
                           b=HANG, anchor=BAR),
    "negative_muscle_up": dict(a=d(DIP_TOP, torso=6, hip=184, knee=196, arm_spread=GRIP_SPREAD),
                              mid=d(PULL_TOP, **arm_to(0.3, 0.2)), view="front",
                               b=HANG, anchor=BAR),
    "assisted_muscle_up_band": dict(a=d(DIP_TOP, torso=6, hip=184, knee=150, arm_spread=GRIP_SPREAD),
                                    mid=d(PULL_TOP, knee=160, **arm_to(0.3, 0.2)),
                                    b=d(HANG, knee=150), anchor=BAR, view="front"),

    # --- core ---
    "hanging_leg_raises": dict(a=d(HANG, hip=96, knee=92, ankle=60, torso=350),
                               b=d(HANG, hip=180, knee=180, ankle=100), anchor=BAR, family="core"),
    "toes_to_bar": dict(a=d(HANG, hip=46, knee=40, ankle=20, torso=344),
                        b=d(HANG, hip=180, knee=180, ankle=100), anchor=BAR, family="core"),
    "l_sit": dict(a=LSIT, b=d(LSIT, hip=88, torso=4), anchor=PARALLETTE),
    "tucked_l_sit": dict(a=d(LSIT, hip=96, knee=172, ankle=120),
                         b=d(LSIT, hip=92, knee=168, ankle=118, torso=4), anchor=PARALLETTE),
    "plank": dict(a=PLANK, b=d(PLANK, torso=92, hip=272), anchor=("elbow_r", (0.0, 0.05, 0.0)),
                  floor="toe_r"),
    "ab_wheel_rollouts": dict(a=dict(torso=36, arm=150, elbow=126, hand=104, hip=208, knee=280,
                                     ankle=255, head=28),
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
                          b=d(SQUAT, hip_l=62, knee_l=74, ankle_l=40, arm=82, elbow=80, torso=48,
                              **{f"{k}_r": v for k, v in leg_to(-0.40, -0.10).items()}),
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
                                   anchor=FLOOR, plant="ankle_l"),
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
    "half_lay_planche_hold": dict(a=d(PLANCHE, hip=274, knee=356, ankle=318),
                                  b=d(PLANCHE, hip=275, knee=355, ankle=318, torso=94), anchor=HANDS),
    "full_planche_hold": dict(a=d(PLANCHE, hip=272, knee=270),
                              b=d(PLANCHE, hip=273, knee=271, torso=94), anchor=HANDS),

    # --- front lever family (hanging, body horizontal) ---
    "full_front_lever_hold": dict(a=FL, b=d(FL, torso=93, hip=273), anchor=BAR),
    "half_lay_front_lever_hold": dict(a=d(FL, hip=272, knee=0, ankle=336),
                                      b=d(FL, hip=273, knee=1, ankle=336, torso=93), anchor=BAR),
    "straddle_front_lever_hold": dict(a=d(FL, leg_spread=32), b=d(FL, leg_spread=33, torso=93),
                                      anchor=BAR),
    "one_legged_fl_hold": dict(a=d(FL, hip_l=300, knee_l=20, ankle_l=350),
                               b=d(FL, hip_l=302, knee_l=18, ankle_l=350, torso=93), anchor=BAR),
    "advanced_tuck_fl_hold": dict(a=d(FL, hip=284, knee=12, ankle=350),
                                  b=d(FL, hip=286, knee=10, ankle=350, torso=93), anchor=BAR),
    "tuck_front_lever_hold": dict(a=d(FL, torso=86, hip=26, knee=232, ankle=190),
                                  b=d(FL, torso=88, hip=28, knee=230, ankle=190), anchor=BAR),
    "tuck_fl_rows": dict(a=d(FL, torso=86, hip=26, knee=232, ankle=190, arm=52, elbow=318),
                         b=d(FL, torso=86, hip=26, knee=232, ankle=190), anchor=BAR),
    "reversed_deadlift_fl_pulls": dict(a=d(FL, hip=284, knee=12, ankle=350),
                                       b=d(HANG, hip=186, knee=196, arm=4, elbow=2), anchor=BAR),

    # --- human flag family (vertical pole, body across the front view) ---
    "full_human_flag_hold": dict(a=FLAG, b=d(FLAG, torso=273, hip=93), anchor=POLE, plane="front"),
    "straddle_human_flag_hold": dict(a=d(FLAG, leg_spread=30), b=d(FLAG, leg_spread=31),
                                     anchor=POLE, plane="front"),
    "tuck_human_flag_hold": dict(a=d(FLAG, hip=120, knee=210, ankle=170),
                                 b=d(FLAG, hip=122, knee=208, ankle=170), anchor=POLE, plane="front"),
    # A negative tilt lifts the feet above the horizontal, which is the easy end of the
    # flag: vertical first, then down through the angled tuck to a horizontal flag.
    "angled_tucked_flag_hold": dict(a=d(FLAG, hip=120, knee=210, ankle=170), b=d(FLAG, hip=122, knee=208,
                                    ankle=170), anchor=POLE, plane="front", tilt=-34),
    "vertical_flag_hold": dict(a=FLAG, b=d(FLAG, torso=273, hip=93), anchor=POLE,
                               plane="front", tilt=-62),
    "vertical_flag_negatives": dict(a=d(FLAG, hip=56, knee=55, ankle=50),
                                    b=d(FLAG, hip=92, knee=91, ankle=86),
                                    anchor=POLE, plane="front", tilt=-30),
    "one_legged_human_flag_hold": dict(a=d(FLAG, hip_l=120, knee_l=210, ankle_l=170),
                                       b=d(FLAG, hip_l=122, knee_l=208, ankle_l=170),
                                       anchor=POLE, plane="front"),
    "one_arm_inverted_support": dict(a=d(FLAG, torso=272, hip=92, arm_r=176, elbow_r=178,
                                         arm_l=190, elbow_l=200),
                                     b=d(FLAG, torso=273, hip=93, arm_r=177, elbow_r=179,
                                         arm_l=190, elbow_l=200),
                                     anchor=POLE, plane="front", tilt=-78),
}

# Tempo per clip, mirroring exercise_tempo() in routes/workouts.py (None = static hold).
HOLD_KEYS = {"advanced_tuck_fl_hold", "advanced_tuck_planche", "angled_tucked_flag_hold", "frog_stand",
             "false_grip_hang", "freestanding_handstand_hold", "full_front_lever_hold",
             "full_human_flag_hold", "full_planche_hold", "half_lay_front_lever_hold",
             "half_lay_planche_hold",
             "l_sit", "one_arm_active_hang", "one_arm_inverted_support",
             "one_legged_advanced_tuck", "one_legged_fl_hold", "one_legged_human_flag_hold",
             "planche_lean", "plank",
             "straddle_front_lever_hold", "straddle_human_flag_hold", "straddle_planche_hold",
             "tuck_front_lever_hold", "tuck_human_flag_hold", "tuck_planche_hold", "tucked_l_sit",
             "vertical_flag_hold", "wall_assisted_handstand_hold",
             "wall_walks_holds"}
TEMPOS = {"explosive_pull_ups": (2, 0, 1), "assisted_muscle_up_band": (2, 0, 1),
          "full_muscle_up": (2, 0, 1), "muscle_ups": (2, 0, 1), "low_bar_transitions": (2, 0, 1),
          "negative_muscle_up": (5, 1, 1), "negative_wall_hspu": (5, 1, 1),
          "vertical_flag_negatives": (4, 1, 1),
          "active_scapula_hangs": (2, 1, 1), "scapula_shrugs": (2, 1, 1),
          "toes_to_bar": (2, 1, 1), "calf_raises": (2, 1, 1)}


def tempo_for(key):
    return None if key in HOLD_KEYS else TEMPOS.get(key, (3, 1, 1))


# ============================ baking ============================

def ease(x):
    return x * x * (3.0 - 2.0 * x)


def path_pose(spec, u):
    """u in [0, 1]: `a` -> (`mid`) -> `b`."""
    a, b, mid = spec["a"], spec.get("b", spec["a"]), spec.get("mid")
    if mid is None:
        return blend(a, b, u)
    # one key set along the whole path: a parameter one pose leaves out holds its neighbour's
    # value instead of dropping back to its default halfway through the rep
    keys = set(a) | set(mid) | set(b)
    a = {k: a.get(k, mid.get(k, b.get(k))) for k in keys}
    b = {k: b.get(k, mid.get(k, a.get(k))) for k in keys}
    mid = {k: mid.get(k, a[k] if isinstance(a[k], tuple) else (a[k] + b[k]) / 2) for k in keys}
    return blend(a, mid, u * 2) if u <= 0.5 else blend(mid, b, (u - 0.5) * 2)


def ease_down(x, snap=False):
    """The lowering: under control, with a longer brake into the bottom — a shorter one when
    the rep has no pause and swings straight through the turn."""
    return 1.0 - (1.0 - ease(x)) ** (1.1 if snap else 1.3)


def ease_up(x):
    """The drive: out of the hole with real speed, slowing into the lockout."""
    return 1.0 - (1.0 - x) ** 2.4


HOLD_SPAN = 4.0          # one breath per hold loop, seconds
SAMPLE_STEP = 0.04       # the motion is sampled this often, then thinned (see thin_keys)
KEY_TOLERANCE = 0.004    # metres a joint may stray from the sampled path between kept keys
GAZE_LAG = 0.08          # the head trails the body by this much (seconds), keeping its gaze
SETTLE = 0.03            # how far the body sinks past the turn during the pause
OVERSHOOT = 0.025        # how far the drive carries past the lockout before it settles
BREATH = 0.035           # chest expansion on a hold's inhale
TREMOR_DEG = 0.45        # the loaded arms shake this much on a hold
TREMOR_PERIOD = 1.0      # seconds; must divide HOLD_SPAN so the loop stays seamless
SAG_DEG = 1.8            # a hold's slow fight: the hips give this much and are pulled back

# Joint phasing: how far each joint group runs ahead of (-) or behind (+) the body's clock,
# in seconds. This is what separates a movement from a morph between two photographs —
# distal joints lead the lowering, the proximal ones set first for the drive, and the legs
# trail the pull like a pendulum. Real lags are a tenth of a second or so whatever the tempo.
PHASING = {
    "press": {"elbow": -0.06, "arm": -0.03, "torso": +0.05, "hip": +0.08, "knee": +0.08},
    "pull": {"arm": -0.10, "elbow": +0.02, "torso": +0.06, "hip": +0.12, "knee": +0.16},
    "squat": {"hip": -0.10, "torso": -0.08, "knee": 0.0, "ankle": +0.04, "arm": +0.12,
              "elbow": +0.12},
    "core": {"knee": -0.06, "hip": 0.0, "torso": +0.08, "arm": +0.06},
}
# pose parameter prefix -> the joint group whose clock it follows
PHASE_GROUP = {"arm": "arm", "fore": "arm", "elbow": "elbow", "hand": "elbow", "torso": "torso",
               "hip": "hip", "leg": "hip", "knee": "knee", "ankle": "ankle",
               "neck": "head", "head": "head"}


def family_for(spec):
    """Which phasing a rep uses, from what the body is anchored on unless the spec says."""
    if "family" in spec:
        return spec["family"]
    anchor = spec["anchor"]
    if anchor in (BAR, LOW_BAR):
        return "pull"
    if anchor == FLOOR:
        return "squat"
    if anchor in (HANDS, DIP_BAR, PARALLETTE):
        return "press"
    return None


def rep_u(t, tempo, offset=0.0):
    """Where along a -> b the body is at time t of a rep (loops over the tempo). `offset`
    shifts this joint's clock by that many seconds (positive trails the body).
    During the pause the body settles a touch past the turn, so the bottom reads as a
    bottom; the drive carries a touch past the lockout and settles back."""
    down, pause, up = tempo
    total = down + pause + up
    t = (t - offset) % total
    snap = pause == 0
    if t < down:
        return ease_down(t / down, snap)
    if t < down + pause:
        return 1.0 + SETTLE * math.sin(math.pi * (t - down) / pause)
    x = (t - down - pause) / up
    over = OVERSHOOT * (1.6 if snap else 1.0)
    settle = math.sin(math.pi * (x - 0.65) / 0.35) if x > 0.65 else 0.0
    return 1.0 - ease_up(x) - over * settle


def hold_u(t):
    return 0.5 - 0.5 * math.cos(2 * math.pi * (t % HOLD_SPAN) / HOLD_SPAN)


def sag_u(t):
    """The slow fight of a hold: the position gives through the middle of the loop and is
    pulled back by its end (0 at both ends, so the loop closes)."""
    return math.sin(math.pi * (t % HOLD_SPAN) / HOLD_SPAN) ** 3


def pose_params(spec, t, tempo, offsets):
    """Pose parameters at time t of a rep, each joint group on its own clock (see PHASING);
    the head trails a moment behind everything, keeping its gaze."""
    clocks = dict(offsets)
    clocks["head"] = clocks.get("head", 0.0) + GAZE_LAG
    base = path_pose(spec, rep_u(t, tempo))
    shifted = {}
    out = {}
    for k, v in base.items():
        off = clocks.get(PHASE_GROUP.get(k.split("_")[0]), 0.0)
        if isinstance(v, tuple) or off == 0.0:
            out[k] = v
            continue
        if off not in shifted:
            shifted[off] = path_pose(spec, rep_u(t, tempo, off))
        out[k] = shifted[off][k]
    return out


def hold_params(spec, t):
    """A hold at time t: breathing towards `b`, the loaded arms shivering in two tones that
    build on the exhale, the hips slowly giving and being pulled back, the gaze alive."""
    params = path_pose(spec, hold_u(t))
    shiver = (math.sin(2 * math.pi * t / TREMOR_PERIOD)
              + 0.6 * math.sin(4 * math.pi * t / TREMOR_PERIOD + 0.7))
    wobble = TREMOR_DEG * shiver * (0.5 + 0.5 * hold_u(t))
    sag = SAG_DEG * sag_u(t)
    nod = 0.6 * math.sin(2 * math.pi * t / HOLD_SPAN + 1.1)
    for k in list(params):
        if isinstance(params[k], tuple):
            continue
        group = PHASE_GROUP.get(k.split("_")[0])
        if group == "arm" and "spread" not in k:
            params[k] += wobble
        elif group == "elbow":
            params[k] += wobble * 0.5
        elif group in ("hip", "knee") and "spread" not in k:
            params[k] += sag
        elif group == "torso":
            params[k] += sag * 0.5
        elif group == "head":
            params[k] += nod
    return params


def frames_for(key, spec):
    """(times, poses, us, chest) for one clip: a rep over its tempo, or a hold that breathes.
    `chest` is the torso's width/depth factor per frame — the breath. Sampled densely; the
    keys that survive thin_keys() go into the file."""
    tempo = tempo_for(key)
    span = HOLD_SPAN if tempo is None else sum(tempo)
    steps = round(span / SAMPLE_STEP)
    times = [span * i / steps for i in range(steps + 1)]
    if tempo is None:
        us = [hold_u(t) for t in times]
        params = [hold_params(spec, t) for t in times]
        chest = [1.0 + BREATH * u for u in us]
    else:
        offsets = PHASING.get(family_for(spec), {})
        us = [rep_u(t, tempo) for t in times]
        params = [pose_params(spec, t, tempo, offsets) for t in times]
        chest = [1.0] * len(times)
    plain = posed(params[0], spec)
    first = contact_plan(plain, spec)          # the floor / pin set the first frame's incline
    if first and "fixed" in first:
        placed = posed(params[0], spec, first)
        plan = contact_plan(placed, spec, pose_tilt(placed, plain, spec))
    else:
        plan = first
    poses = [posed(p, spec, plan) for p in params]
    return thin_keys(times, poses, us, chest)


def thin_keys(times, poses, us, chest):
    """Drop the sampled frames the viewer's linear interpolation would reproduce anyway: a key
    is kept once any joint on the way to the next candidate strays past KEY_TOLERANCE from
    the straight line between the kept keys. Dense through the turn and the drive, sparse
    along a slow eccentric; the first and last frames always stay so the loop closes."""
    keep = [0]
    last = len(times) - 1
    while keep[-1] < last:
        i = keep[-1]
        j = i + 1
        while j < last:
            candidate = j + 1
            ok = True
            for k in range(i + 1, candidate):
                f = (times[k] - times[i]) / (times[candidate] - times[i])
                for joint, p in poses[k].items():
                    a, b = poses[i][joint], poses[candidate][joint]
                    err = math.dist(p, tuple(a[c] + (b[c] - a[c]) * f for c in range(3)))
                    if err > KEY_TOLERANCE:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
            j = candidate
        keep.append(j)
    return ([times[i] for i in keep], [poses[i] for i in keep], [us[i] for i in keep],
            [chest[i] for i in keep])


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


def _unit(v):
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / length, v[1] / length, v[2] / length)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def body_axes(pose):
    """(right, forward) of the whole figure: across the shoulders, and out of the chest."""
    sl, sr = pose["shoulder_l"], pose["shoulder_r"]
    right = _unit((sr[0] - sl[0], sr[1] - sl[1], sr[2] - sl[2]))
    p, c = pose["pelvis"], pose["chest"]
    forward = _unit(_cross(right, (c[0] - p[0], c[1] - p[1], c[2] - p[2])))
    return right, forward


def frame_quat(direction, right, forward):
    """Rotation whose Y runs along `direction` and whose X stays across the body, so a
    segment's width, depth and front are its own in every pose (quat_from_y() fixes only the
    axis and lets the roll fall where it may). A segment running across the body itself, like
    the shoulder line, keys its roll on `forward` instead."""
    y = _unit(direction)
    ref = right if abs(y[0] * right[0] + y[1] * right[1] + y[2] * right[2]) < 0.9 else forward
    dot = ref[0] * y[0] + ref[1] * y[1] + ref[2] * y[2]
    x = _unit((ref[0] - dot * y[0], ref[1] - dot * y[1], ref[2] - dot * y[2]))
    z = _cross(x, y)
    # rotation matrix with columns x, y, z -> quaternion (x, y, z, w)
    m00, m01, m02 = x[0], y[0], z[0]
    m10, m11, m12 = x[1], y[1], z[1]
    m20, m21, m22 = x[2], y[2], z[2]
    trace = m00 + m11 + m22
    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1.0)
        return ((m21 - m12) * s, (m02 - m20) * s, (m10 - m01) * s, 0.25 / s)
    if m00 > m11 and m00 > m22:
        s = 2.0 * math.sqrt(1.0 + m00 - m11 - m22)
        return (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    if m11 > m22:
        s = 2.0 * math.sqrt(1.0 + m11 - m00 - m22)
        return ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    s = 2.0 * math.sqrt(1.0 + m22 - m00 - m11)
    return ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)


def node_trs(pose, a, b, axes=None):
    """(translation, rotation) placing a segment from joint `a` to joint `b`."""
    pa, pb = pose[a], pose[b]
    right, forward = axes or body_axes(pose)
    return pa, frame_quat((pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]), right, forward)


def bone_length(pose, a, b):
    return math.dist(pose[a], pose[b]) or 1e-4


# ============================ geometry ============================

_GEO = {}


def lathe(profile, sides, offset=0.0):
    """Surface of revolution from a (y, width, depth) profile — elliptical rings, so a part
    can be wider than it is deep — with flat caps."""
    pos, nrm, idx, rings = [], [], [], []
    for i, (y, rw, rd) in enumerate(profile):
        y0, w0, d0 = profile[max(0, i - 1)]
        y1, w1, d1 = profile[min(len(profile) - 1, i + 1)]
        dy, dr = y1 - y0, ((w1 + d1) - (w0 + d0)) / 2
        norm = math.hypot(dy, dr) or 1.0
        ny, nr = -dr / norm, dy / norm
        ring = []
        for j in range(sides + 1):
            a = math.radians(offset) + 2 * math.pi * j / sides
            c, sn = math.cos(a), math.sin(a)
            ring.append(len(pos))
            pos.append((rw * c, y, rd * sn))
            # the in-plane normal of an ellipse is (cos/rw, sin/rd), not the radius direction
            ex, ez = c / (rw or 1e-6), sn / (rd or 1e-6)
            el = math.hypot(ex, ez) or 1.0
            nrm.append((nr * ex / el, ny, nr * ez / el))
        rings.append(ring)
    for lower, upper in zip(rings, rings[1:]):
        for j in range(sides):
            idx += [lower[j], upper[j], lower[j + 1], lower[j + 1], upper[j], upper[j + 1]]
    for (y, rw, rd), normal, flip in (((profile[0]), (0.0, -1.0, 0.0), True),
                                      ((profile[-1]), (0.0, 1.0, 0.0), False)):
        centre = len(pos)
        pos.append((0.0, y, 0.0))
        nrm.append(normal)
        first = len(pos)
        for j in range(sides + 1):
            a = math.radians(offset) + 2 * math.pi * j / sides
            pos.append((rw * math.cos(a), y, rd * math.sin(a)))
            nrm.append(normal)
        for j in range(sides):
            idx += [centre, first + j + 1, first + j] if flip else [centre, first + j, first + j + 1]
    return pos, nrm, idx


def sphere(lon=14, lat=9):
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


def geometry(shape):
    if shape not in _GEO:
        spec = SHAPES[shape]
        _GEO[shape] = (sphere(*spec["sphere"]) if "sphere" in spec
                       else lathe(spec["profile"], spec["sides"], spec.get("offset", 0.0)))
    return _GEO[shape]


def ball_parent(joint, ride=None):
    """(bone index, end) — the bone a joint's ball hangs off: 0 = its start, 1 = its far end.
    `ride` (a bone's (a, b)) picks the bone when the joint belongs to more than one."""
    if ride:
        for i, (a, b, _r, _shape) in enumerate(BONES):
            if (a, b) == tuple(ride):
                return i, 0 if a == joint else 1
        raise KeyError(ride)
    for i, (a, _b, _r, _shape) in enumerate(BONES):
        if a == joint:
            return i, 0
    for i, (_a, b, _r, _shape) in enumerate(BONES):
        if b == joint:
            return i, 1
    raise KeyError(joint)


def ball_local(joint, radius, shape, extra, bone_scale):
    """(translation, scale) of a ball in its bone's local space: the bone's scale is undone
    and a local Y of 0 or 1 lands on the near or far joint; `offset` rides out from there."""
    extra = extra or {}
    _parent, end = ball_parent(joint, extra.get("parent"))
    ox, oy, oz = extra.get("offset", (0.0, 0.0, 0.0))
    want = shape_scale(shape, radius, radius)
    return ([ox / bone_scale[0], float(end) + oy / bone_scale[1], oz / bone_scale[2]],
            [want[i] / bone_scale[i] for i in range(3)])


PROP_SLOTS = 5


def prop_trs(spec, pose):
    """One transform per prop slot; an unused slot collapses to nothing inside the figure."""
    out = []
    for start, end, radius in prop_rods(spec, pose)[:PROP_SLOTS]:
        length = math.dist(start, end) or 1e-4
        out.append((start, quat_from_y(tuple(end[i] - start[i] for i in range(3))),
                    [radius, length, radius]))
    while len(out) < PROP_SLOTS:
        out.append((pose["pelvis"], (0.0, 0.0, 0.0, 1.0), [0.0, 0.0, 0.0]))
    return out


def parts(pose, spec=None, first=None, torso_scale=1.0):
    """Every drawable part of one pose as (shape, translation, rotation, scale) in world space."""
    out = ([("rod", t, q, s) for t, q, s in prop_trs(spec, first or pose) if s[1] > 0]
           if spec else [])
    bones = []
    axes = body_axes(pose)
    for a, b, radius, shape in BONES:
        translation, rotation = node_trs(pose, a, b, axes)
        scale = shape_scale(shape, radius, bone_length(pose, a, b))
        if shape == "torso":
            scale = [scale[0] * torso_scale, scale[1], scale[2] * torso_scale]
        bones.append((translation, rotation, scale))
        out.append((shape, translation, rotation, scale))
    for joint, radius, shape, extra in BALLS:
        parent, _end = ball_parent(joint, (extra or {}).get("parent"))
        t, q, s = bones[parent]
        local_t, local_s = ball_local(joint, radius, shape, extra, s)
        out.append((shape, apply_trs(t, q, s, local_t), q, [local_s[i] * s[i] for i in range(3)]))
    return out


def rotate(q, v):
    x, y, z = v
    qx, qy, qz, qw = q
    cx, cy, cz = qy * z - qz * y + qw * x, qz * x - qx * z + qw * y, qx * y - qy * x + qw * z
    return (x + 2 * (qy * cz - qz * cy), y + 2 * (qz * cx - qx * cz), z + 2 * (qx * cy - qy * cx))


def apply_trs(t, q, s, p):
    r = rotate(q, (p[0] * s[0], p[1] * s[1], p[2] * s[2]))
    return (r[0] + t[0], r[1] + t[1], r[2] + t[2])


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


def build(out_path):
    blob = Blob()
    used = list(dict.fromkeys([shape for *_x, shape in BONES]
                              + [shape for _j, _r, shape, _e in BALLS] + ["rod"]))
    meshes, mesh_index = [], {}
    for shape in used:
        pos, nrm, idx = geometry(shape)
        mesh_index[shape] = len(meshes)
        meshes.append({"name": shape, "primitives": [{
            "attributes": {"POSITION": blob.floats(pos, "VEC3", 34962, bounds=True),
                           "NORMAL": blob.floats(nrm, "VEC3", 34962)},
            "indices": blob.ushorts(idx, 34963), "material": 0}]})

    clips = sorted(SPECS)
    baked = {}
    for key in clips:
        times, poses, us, chest = frames_for(key, SPECS[key])
        baked[key] = (times, normalise(poses), us, chest)

    rest = baked["bodyweight_squats"][1][0]
    nodes, bone_scales = [], []
    for a, b, radius, shape in BONES:
        translation, rotation = node_trs(rest, a, b)
        scale = shape_scale(shape, radius, bone_length(rest, a, b))
        bone_scales.append(scale)
        nodes.append({"name": f"{a}__{b}", "mesh": mesh_index[shape], "translation": list(translation),
                      "rotation": list(rotation), "scale": scale})
    for slot, (translation, rotation, scale) in enumerate(prop_trs(SPECS["bodyweight_squats"], rest)):
        nodes.append({"name": f"prop_{slot}", "mesh": mesh_index["rod"], "translation": list(translation),
                      "rotation": list(rotation), "scale": scale})
    # The balls hang off their bone, so only the bones need animating (see ball_local()).
    for joint, radius, shape, extra in BALLS:
        parent, _end = ball_parent(joint, (extra or {}).get("parent"))
        translation, scale = ball_local(joint, radius, shape, extra, bone_scales[parent])
        nodes.append({"name": f"{shape}_{joint}", "mesh": mesh_index[shape],
                      "translation": translation, "scale": scale})
        nodes[parent].setdefault("children", []).append(len(nodes) - 1)
    torso = next(i for i, (_a, _b, _r, shape) in enumerate(BONES) if shape == "torso")

    # Where each clip lives: the box round every frame of the figure, so the arena can aim its
    # camera per clip. The viewer frames the rest pose otherwise, and a figure hanging from a
    # 2 m bar loses its head. The prop is left out on purpose — a bar's uprights run to the
    # floor and would shrink the athlete to a third of the slot; they simply run off-stage.
    bounds = {}
    for key in clips:
        _times, poses, _us, _chest = baked[key]
        pts = [p for pose in poses for p in pose.values()]
        lo = [min(p[i] for p in pts) - 0.13 for i in range(3)]
        hi = [max(p[i] for p in pts) + 0.13 for i in range(3)]
        bounds[key] = [round((lo[i] + hi[i]) / 2, 3) for i in range(3)] + \
                      [round((hi[i] - lo[i]) / 2, 3) for i in range(3)]

    animations = []
    for key in clips:
        times, poses, _us, chest = baked[key]
        time_acc = blob.floats(times, "SCALAR", bounds=True)
        still_acc = blob.floats([0.0], "SCALAR", bounds=True)  # props hold one constant keyframe
        samplers, channels = [], []
        tracks = []
        for a, b, _r, _shape in BONES:
            trs = [node_trs(pose, a, b) for pose in poses]
            tracks.append(([t for t, _ in trs], [r for _, r in trs], None))
        # The chest breathes on a hold; a rep pins it, so a hold's last breath never lingers.
        sx, sy, sz = bone_scales[torso]
        breath = [(sx * f, sy, sz * f) for f in chest]
        tracks[torso] = (tracks[torso][0], tracks[torso][1],
                         breath if any(abs(f - 1.0) > 1e-9 for f in chest) else [breath[0]])
        for translation, rotation, scale in prop_trs(SPECS[key], poses[0]):
            tracks.append(([translation], [rotation], [tuple(scale)]))
        for node_index, (translations, rotations, scales) in enumerate(tracks):
            paths = [("translation", translations, "VEC3"), ("rotation", rotations, "VEC4")]
            if scales is not None:
                paths.append(("scale", scales, "VEC3"))
            for path, values, kind in paths:
                samplers.append({"input": still_acc if len(values) == 1 else time_acc,
                                 "output": blob.floats(values, kind)})
                channels.append({"sampler": len(samplers) - 1,
                                 "target": {"node": node_index, "path": path}})
        animations.append({"name": key, "samplers": samplers, "channels": channels})

    gltf = {
        "asset": {"version": "2.0", "generator": "expense_tracker tools/build_exercises_glb.py"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(BONES) + PROP_SLOTS))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [{
            "name": "hologram",
            # Lit more than it glows: the neutral environment then shades the chest, the
            # limbs and the face, and the page's own drop-shadow supplies the halo. A stronger
            # emissive flattens the figure into one cyan silhouette.
            "pbrMetallicRoughness": {"baseColorFactor": [0.22, 0.64, 0.92, 1.0],
                                     "metallicFactor": 0.0, "roughnessFactor": 0.34},
            "emissiveFactor": [0.03, 0.17, 0.27],
            "doubleSided": True,
        }],
        "animations": animations,
        # Flags and bar pulls read from the front camera, not the side one; the arena reads this
        # back so those clips open on the angle that shows the pose (see holo_clips in workouts.py).
        "extras": {"front_view_clips": sorted(k for k, spec in SPECS.items() if front_view(spec)),
                   # per clip: centre x, y, z and half-extents x, y, z (metres)
                   "clip_bounds": bounds},
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


# ============================ pictures ============================

def png(path, width, height, pixels):
    raw = b"".join(b"\0" + bytes(pixels[y * width * 3:(y + 1) * width * 3]) for y in range(height))
    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def preview(baked, path, cols=6, cell=200):
    """Fast stick sheet for angle work: start pose (cyan) over the turnaround (magenta)."""
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
        _times, poses, _us, _chest = baked[key]
        ox, oy = (n % cols) * cell, (n // cols) * cell
        side = not front_view(SPECS[key])
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
            for a, b, r, _shape in BONES:
                x0, y0 = screen(pose[a])
                x1, y1 = screen(pose[b])
                steps = max(2, int(math.dist((x0, y0), (x1, y1))))
                for step in range(steps + 1):
                    dot(x0 + (x1 - x0) * step / steps, y0 + (y1 - y0) * step / steps, r * scale, colour)
            for j, r, _shape, _extra in BALLS:
                x0, y0 = screen(pose[j])
                dot(x0, y0, r * scale, colour)
    png(path, width, height, buf)
    return keys


# The arena's three camera presets (HOLO_ANGLES in static/js/workout.js): theta, phi in degrees.
VIEWS = {"side": (90.0, 75.0), "front": (0.0, 75.0), "top": (0.0, 12.0)}


def camera(pose, view, pad=2.6):
    """Eye, basis and pixel scale for one of the arena's presets, framed on the pose."""
    pts = list(pose.values())
    centre = tuple((min(p[i] for p in pts) + max(p[i] for p in pts)) / 2 for i in range(3))
    radius = max(math.dist(p, centre) for p in pts) + 0.12
    theta, phi = (math.radians(a) for a in VIEWS[view])
    dist = radius * pad
    eye = (centre[0] + dist * math.sin(phi) * math.sin(theta),
           centre[1] + dist * math.cos(phi),
           centre[2] + dist * math.sin(phi) * math.cos(theta))
    fwd = [centre[i] - eye[i] for i in range(3)]
    norm = math.sqrt(sum(c * c for c in fwd))
    fwd = [c / norm for c in fwd]
    up_hint = (0.0, 0.0, 1.0) if abs(fwd[1]) > 0.94 else (0.0, 1.0, 0.0)
    right = [up_hint[1] * fwd[2] - up_hint[2] * fwd[1],
             up_hint[2] * fwd[0] - up_hint[0] * fwd[2],
             up_hint[0] * fwd[1] - up_hint[1] * fwd[0]]
    norm = math.sqrt(sum(c * c for c in right))
    right = [c / norm for c in right]
    up = [fwd[1] * right[2] - fwd[2] * right[1], fwd[2] * right[0] - fwd[0] * right[2],
          fwd[0] * right[1] - fwd[1] * right[0]]
    return eye, right, up, fwd, math.asin(min(1.0, radius / dist))


def shade_pose(buf, width, height, ox, oy, cell, pose, view, spec=None, first=None, chest=1.0,
               frame=None):
    """Z-buffered render of the real geometry: soft cyan body with a bright silhouette rim.
    `frame` (joint positions) fixes the camera on something other than the pose itself."""
    eye, right, up, fwd, half = camera(frame or pose, view)
    focal = (cell * 0.46) / math.tan(half)
    light = [0.55 * right[i] - 0.35 * fwd[i] + 0.75 * up[i] for i in range(3)]
    norm = math.sqrt(sum(c * c for c in light))
    light = [c / norm for c in light]
    depth = [1e9] * (cell * cell)

    def to_camera(p):
        d = (p[0] - eye[0], p[1] - eye[1], p[2] - eye[2])
        return (sum(d[i] * right[i] for i in range(3)), sum(d[i] * up[i] for i in range(3)),
                sum(d[i] * fwd[i] for i in range(3)))

    for shape, t, q, sc in parts(pose, spec, first, chest):
        vpos, vnrm, vidx = geometry(shape)
        world = [apply_trs(t, q, sc, p) for p in vpos]
        normals = []
        for n in vnrm:
            wn = rotate(q, (n[0] / sc[0], n[1] / sc[1], n[2] / sc[2]))
            length = math.sqrt(sum(c * c for c in wn)) or 1.0
            normals.append([c / length for c in wn])
        screen = []
        for p in world:
            cx, cy, cz = to_camera(p)
            screen.append((cell / 2 + focal * cx / cz, cell / 2 - focal * cy / cz, cz) if cz > 0.05
                          else None)
        for k in range(0, len(vidx), 3):
            tri = [screen[vidx[k + i]] for i in range(3)]
            if any(v is None for v in tri):
                continue
            (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = tri
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(area) < 1e-9:
                continue
            n0, n1, n2 = (normals[vidx[k + i]] for i in range(3))
            lo_x, hi_x = max(0, int(min(x0, x1, x2))), min(cell - 1, int(max(x0, x1, x2)) + 1)
            lo_y, hi_y = max(0, int(min(y0, y1, y2))), min(cell - 1, int(max(y0, y1, y2)) + 1)
            for py in range(lo_y, hi_y + 1):
                for px in range(lo_x, hi_x + 1):
                    sx, sy = px + 0.5, py + 0.5
                    w0 = ((x1 - sx) * (y2 - sy) - (x2 - sx) * (y1 - sy)) / area
                    w1 = ((x2 - sx) * (y0 - sy) - (x0 - sx) * (y2 - sy)) / area
                    w2 = 1.0 - w0 - w1
                    if w0 < 0 or w1 < 0 or w2 < 0:
                        continue
                    z = w0 * z0 + w1 * z1 + w2 * z2
                    slot = py * cell + px
                    if z >= depth[slot]:
                        continue
                    depth[slot] = z
                    nx = w0 * n0[0] + w1 * n1[0] + w2 * n2[0]
                    ny = w0 * n0[1] + w1 * n1[1] + w2 * n2[1]
                    nz = w0 * n0[2] + w1 * n1[2] + w2 * n2[2]
                    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                    nx, ny, nz = nx / length, ny / length, nz / length
                    lam = max(0.0, nx * light[0] + ny * light[1] + nz * light[2])
                    facing = abs(nx * fwd[0] + ny * fwd[1] + nz * fwd[2])
                    rim = (1.0 - facing) ** 3
                    tone = 0.2 + 0.8 * lam
                    i = ((oy + py) * width + ox + px) * 3
                    buf[i] = min(255, int(40 * tone + 190 * rim))
                    buf[i + 1] = min(255, int(170 * tone + 80 * rim))
                    buf[i + 2] = min(255, int(225 * tone + 30 * rim))


def render(baked, path, keys, view="side", frame=0.0, cols=4, cell=240):
    """Shaded contact sheet through the arena's own camera presets — the honest quality check."""
    rows = (len(keys) + cols - 1) // cols
    width, height = cols * cell, rows * cell
    buf = bytearray()
    for _ in range(width * height):
        buf += bytes((9, 12, 20))
    for n, key in enumerate(keys):
        _times, poses, us, chest = baked[key]
        if frame == "turn":                       # the bottom of the rep, where depth shows
            index = max(range(len(us)), key=lambda i: us[i])
        else:
            index = min(len(poses) - 1, max(0, round(float(frame) * (len(poses) - 1))))
        pose = poses[index]
        use = view if view != "auto" else ("front" if front_view(SPECS[key]) else "side")
        shade_pose(buf, width, height, (n % cols) * cell, (n // cols) * cell, cell, pose, use,
                   SPECS[key], poses[0], chest[index])
    png(path, width, height, buf)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--preview", type=Path, help="fast stick sheet of every pose")
    parser.add_argument("--render", type=Path, help="shaded render through the arena's cameras")
    parser.add_argument("--clips", help="comma-separated clip keys to render (default: all)")
    parser.add_argument("--view", default="auto", choices=["auto", *VIEWS], help="camera preset")
    parser.add_argument("--frame", default="turn",
                        help="'turn' (the rep's bottom, default) or a 0..1 point on the timeline")
    parser.add_argument("--cols", type=int, default=4)
    args = parser.parse_args()

    baked, size = build(args.out)
    print(f"{args.out}: {len(baked)} clips, {size / 1024:.0f} KB")
    if args.preview:
        keys = preview(baked, args.preview)
        print(f"{args.preview}: {len(keys)} cells")
        for i, key in enumerate(keys):
            print(f"{i:2d} {key}")
    if args.render:
        keys = args.clips.split(",") if args.clips else sorted(baked)
        unknown = [k for k in keys if k not in baked]
        if unknown:
            parser.error(f"unknown clips: {unknown}")
        render(baked, args.render, keys, args.view, args.frame, args.cols)
        print(f"{args.render}: {len(keys)} cells, view={args.view}, frame={args.frame}")


if __name__ == "__main__":
    main()
