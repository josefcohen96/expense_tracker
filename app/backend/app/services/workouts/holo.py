"""The exercise hologram: reads the clips out of static/holo/exercises.glb."""
import json
import logging
import mimetypes
import re
import struct
from typing import Any

from ...templating import FRONTEND_DIR

logger = logging.getLogger(__name__)


# ====================== EXERCISE HOLOGRAM ======================
# One shared glTF-binary model with an animation clip per exercise, named by holo_key().
# An exercise without a clip keeps the plain arena — the hologram only appears when its
# clip exists. Each clip is one rep, authored as lowering → pause → pushing, so the
# arena can play it at the exercise's tempo.

HOLO_MODEL_PATH = FRONTEND_DIR / "static" / "holo" / "exercises.glb"
HOLO_MODEL_URL = "/static/holo/exercises.glb"
mimetypes.add_type("model/gltf-binary", ".glb")  # StaticFiles would serve it as text/plain


def holo_key(english_name: str) -> str:
    """Animation clip name for an exercise: 'Negative Muscle-Up' -> 'negative_muscle_up'."""
    return re.sub(r"[^a-z0-9]+", "_", english_name.lower()).strip("_")


_holo_clip_cache: dict[str, Any] = {"stamp": None, "clips": frozenset(), "front": frozenset(),
                                    "bounds": {}}


def holo_clips() -> frozenset:
    """Animation names inside the hologram model (read from the GLB's JSON chunk, cached by mtime)."""
    try:
        stat = HOLO_MODEL_PATH.stat()
    except OSError:
        return frozenset()
    stamp = (stat.st_mtime_ns, stat.st_size)
    if _holo_clip_cache["stamp"] != stamp:
        clips, front, bounds = frozenset(), frozenset(), {}
        try:
            with open(HOLO_MODEL_PATH, "rb") as f:
                magic, _version, _length = struct.unpack("<4sII", f.read(12))
                chunk_length, chunk_type = struct.unpack("<I4s", f.read(8))
                if magic == b"glTF" and chunk_type == b"JSON":
                    gltf = json.loads(f.read(chunk_length))
                    clips = frozenset(a["name"] for a in gltf.get("animations", []) if a.get("name"))
                    extras = gltf.get("extras", {})
                    front = frozenset(extras.get("front_view_clips", ()))
                    bounds = {k: v for k, v in extras.get("clip_bounds", {}).items()
                              if k in clips and isinstance(v, list) and len(v) == 6}
        except (OSError, ValueError, struct.error, AttributeError):
            logger.warning("Unreadable hologram model at %s", HOLO_MODEL_PATH)
        _holo_clip_cache.update(stamp=stamp, clips=clips, front=front, bounds=bounds)
    return _holo_clip_cache["clips"]


def holo_front_clips() -> frozenset:
    """Clips the model asks to open on the front camera — a flag is edge-on from the side."""
    holo_clips()
    return _holo_clip_cache["front"]


def holo_clip_bounds() -> dict[str, list]:
    """Per clip: [centre x, y, z, half-extent x, y, z] of everything the clip shows, so the
    arena can frame each exercise instead of the model's rest pose."""
    holo_clips()
    return _holo_clip_cache["bounds"]
