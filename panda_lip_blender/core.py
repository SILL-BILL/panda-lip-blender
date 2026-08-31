"""Blender-independent timing and naming helpers."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

from .constants import ACTION_PREFIX


def effective_fps(fps: float, fps_base: float) -> float:
    """Return Blender's effective frames per second.

    Blender represents rates such as 29.97 as ``fps / fps_base``.
    """

    if not math.isfinite(fps) or fps <= 0.0:
        raise ValueError("Scene FPS must be a finite value greater than zero")
    if not math.isfinite(fps_base) or fps_base <= 0.0:
        raise ValueError("Scene FPS Base must be a finite value greater than zero")
    return fps / fps_base


def times_to_frames(
    times: Iterable[float], start_frame: float, fps: float, fps_base: float
) -> tuple[float, ...]:
    """Map seconds to Blender frames without rounding away subframes."""

    rate = effective_fps(float(fps), float(fps_base))
    return tuple(float(start_frame) + float(time) * rate for time in times)


def action_base_name(filepath: str) -> str:
    """Build a readable Blender Action base name from the PandaLip filename."""

    stem = Path(filepath).stem.strip()
    # Blender accepts Unicode ID names. Only discard control characters, which
    # make Actions difficult to identify in UI lists.
    stem = "".join(character for character in stem if character.isprintable())
    return f"{ACTION_PREFIX}{stem or 'Import'}"
