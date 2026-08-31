"""Create AIUEO pose-bone animation from validated PandaLip data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Iterable

import bpy

from .constants import ACTION_GROUP, BONE_NAMES, CHANNELS
from .core import action_base_name, effective_fps, times_to_frames
from .reduction import resolve_tolerance, simplify_indices
from .validation import PandaLipData, PandaLipValidationError, load_pandalip


@dataclass(frozen=True, slots=True)
class ImportResult:
    action_name: str
    sample_count: int
    keyframe_count: int
    source_keyframe_count: int
    effective_fps: float
    reduction_mode: str
    tolerance: float | None
    reduction_seconds: float
    key_generation_seconds: float


@dataclass(frozen=True, slots=True)
class ChannelCurve:
    frames: tuple[float, ...]
    values: tuple[float, ...]


def _validate_target(target: bpy.types.Object | None) -> None:
    if target is None:
        raise PandaLipValidationError("Select a Target Armature")
    if target.type != "ARMATURE":
        raise PandaLipValidationError(f"Target '{target.name}' is not an Armature object")
    missing = [bone_name for bone_name in BONE_NAMES.values() if target.pose.bones.get(bone_name) is None]
    if missing:
        raise PandaLipValidationError(
            f"Target Armature is missing required pose bone(s): {', '.join(missing)}"
        )


def _action_fcurves(action: bpy.types.Action) -> list[bpy.types.FCurve]:
    """Return F-Curves from legacy or Blender 4.4+ layered Actions."""

    legacy_fcurves = getattr(action, "fcurves", None)
    if legacy_fcurves is not None:
        return list(legacy_fcurves)

    curves: list[bpy.types.FCurve] = []
    for layer in getattr(action, "layers", ()):
        for strip in getattr(layer, "strips", ()):
            for channelbag in getattr(strip, "channelbags", ()):
                curves.extend(channelbag.fcurves)
    return curves


def _find_fcurve(
    curves: Iterable[bpy.types.FCurve], data_path: str, array_index: int
) -> bpy.types.FCurve:
    for curve in curves:
        if curve.data_path == data_path and curve.array_index == array_index:
            return curve
    raise RuntimeError(f"Blender did not create the expected X Location F-Curve: {data_path}")


def _set_curve_points(
    curve: bpy.types.FCurve, frames: tuple[float, ...], values: tuple[float, ...]
) -> None:
    points = curve.keyframe_points
    if len(points) != 1:
        raise RuntimeError("New Panda Lip F-Curve did not start with exactly one key")
    if len(frames) > 1:
        points.add(len(frames) - 1)
    coordinates = [coordinate for pair in zip(frames, values, strict=True) for coordinate in pair]
    points.foreach_set("co", coordinates)
    for point in points:
        point.interpolation = "LINEAR"
    curve.update()


def _restore_action_slot(animation_data: bpy.types.AnimData, slot: object | None) -> None:
    if slot is not None and hasattr(animation_data, "action_slot"):
        try:
            animation_data.action_slot = slot
        except (AttributeError, RuntimeError, TypeError):
            # Older/newer APIs may restore the sole matching slot automatically.
            pass


def _restore_scene_frame(scene: bpy.types.Scene, frame: int, subframe: float) -> None:
    try:
        scene.frame_set(frame, subframe=subframe)
    except (AttributeError, RuntimeError, TypeError):
        scene.frame_set(frame)


def _populate_action(
    action: bpy.types.Action,
    target: bpy.types.Object,
    channel_curves: dict[str, ChannelCurve],
) -> None:
    """Populate a new Action with five X-only, linear F-Curves."""

    data_paths: dict[str, str] = {}
    for channel in CHANNELS:
        channel_curve = channel_curves[channel]
        pose_bone = target.pose.bones[BONE_NAMES[channel]]
        pose_bone.location.x = channel_curve.values[0]
        inserted = pose_bone.keyframe_insert(
            data_path="location", index=0, frame=channel_curve.frames[0], group=ACTION_GROUP
        )
        if not inserted:
            raise RuntimeError(f"Blender rejected the first key for {BONE_NAMES[channel]}")
        data_paths[channel] = pose_bone.path_from_id("location")

    curves = _action_fcurves(action)
    for channel in CHANNELS:
        channel_curve = channel_curves[channel]
        curve = _find_fcurve(curves, data_paths[channel], 0)
        _set_curve_points(curve, channel_curve.frames, channel_curve.values)


def _prepare_channel_curves(
    data: PandaLipData,
    frames: tuple[float, ...],
    tolerance: float | None,
) -> dict[str, ChannelCurve]:
    times = tuple(sample.time for sample in data.samples)
    channel_curves: dict[str, ChannelCurve] = {}
    for channel_index, channel in enumerate(CHANNELS):
        values = tuple(sample.weights[channel_index] for sample in data.samples)
        if tolerance is None:
            channel_curves[channel] = ChannelCurve(frames=frames, values=values)
            continue
        indices = simplify_indices(times, values, tolerance)
        channel_curves[channel] = ChannelCurve(
            frames=tuple(frames[index] for index in indices),
            values=tuple(values[index] for index in indices),
        )
    return channel_curves


def import_pandalip_data(
    data: PandaLipData,
    filepath: str,
    target: bpy.types.Object | None,
    scene: bpy.types.Scene,
    start_frame: int,
    reduction_mode: str = "ORIGINAL",
    custom_tolerance: float = 0.01,
) -> ImportResult:
    """Create and assign a new Action, rolling back completely on failure."""

    _validate_target(target)
    assert target is not None
    rate = effective_fps(float(scene.render.fps), float(scene.render.fps_base))
    frames = times_to_frames(
        (sample.time for sample in data.samples),
        float(start_frame),
        float(scene.render.fps),
        float(scene.render.fps_base),
    )
    try:
        tolerance = resolve_tolerance(reduction_mode, custom_tolerance)
    except ValueError as exc:
        raise PandaLipValidationError(str(exc)) from exc
    reduction_started = time.perf_counter()
    channel_curves = _prepare_channel_curves(data, frames, tolerance)
    reduction_seconds = time.perf_counter() - reduction_started

    had_animation_data = target.animation_data is not None
    animation_data = target.animation_data_create()
    old_action = animation_data.action
    old_slot = getattr(animation_data, "action_slot", None)
    original_x = {
        bone_name: float(target.pose.bones[bone_name].location.x)
        for bone_name in BONE_NAMES.values()
    }
    old_frame = int(scene.frame_current)
    old_subframe = float(getattr(scene, "frame_subframe", 0.0))
    action: bpy.types.Action | None = None
    key_generation_started = time.perf_counter()

    try:
        action = bpy.data.actions.new(action_base_name(filepath))
        animation_data.action = action
        _populate_action(action, target, channel_curves)
    except BaseException:
        animation_data.action = old_action
        _restore_action_slot(animation_data, old_slot)
        if action is not None:
            bpy.data.actions.remove(action, do_unlink=True)
        if not had_animation_data and target.animation_data is not None:
            target.animation_data_clear()
        raise
    finally:
        for bone_name, value in original_x.items():
            target.pose.bones[bone_name].location.x = value
        _restore_scene_frame(scene, old_frame, old_subframe)

    key_generation_seconds = time.perf_counter() - key_generation_started
    keyframe_count = sum(len(curve.frames) for curve in channel_curves.values())
    return ImportResult(
        action_name=action.name,
        sample_count=len(data.samples),
        keyframe_count=keyframe_count,
        source_keyframe_count=len(data.samples) * len(CHANNELS),
        effective_fps=rate,
        reduction_mode=reduction_mode,
        tolerance=tolerance,
        reduction_seconds=reduction_seconds,
        key_generation_seconds=key_generation_seconds,
    )


def import_pandalip_file(
    filepath: str,
    target: bpy.types.Object | None,
    scene: bpy.types.Scene,
    start_frame: int,
    reduction_mode: str = "ORIGINAL",
    custom_tolerance: float = 0.01,
) -> ImportResult:
    """Load, fully validate, then import a PandaLip file."""

    resolved_path = Path(bpy.path.abspath(filepath)).resolve()
    data = load_pandalip(resolved_path)
    return import_pandalip_data(
        data,
        str(resolved_path),
        target,
        scene,
        start_frame,
        reduction_mode,
        custom_tolerance,
    )
