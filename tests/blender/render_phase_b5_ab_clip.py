"""Render short, synchronized Phase B.5 preset clips from the comparison .blend."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

MODES = ("ORIGINAL", "HIGH", "MIDDLE", "LOW")


def save_render_result(path: Path, scene: bpy.types.Scene) -> None:
    image = bpy.data.images.get("Render Result")
    if image is None:
        raise AssertionError("Blender did not produce a Render Result")
    image.save_render(str(path), scene=scene)


def main() -> None:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) != 4:
        raise RuntimeError("Expected: -- OUTPUT_DIR START_SECONDS END_SECONDS SCALE_PERCENT")
    output_dir = Path(arguments[0]).resolve()
    start_seconds = float(arguments[1])
    end_seconds = float(arguments[2])
    scale_percent = int(arguments[3])
    if end_seconds <= start_seconds:
        raise ValueError("END_SECONDS must be greater than START_SECONDS")
    if not 1 <= scale_percent <= 100:
        raise ValueError("SCALE_PERCENT must be within 1..100")

    target = bpy.data.objects.get("PandaLip")
    if target is None or target.animation_data is None:
        raise AssertionError("Comparison file has no animated PandaLip Armature")
    actions = {
        str(action.get("phase_b5_mode")): action
        for action in bpy.data.actions
        if action.get("phase_b5_mode") in MODES
    }
    if set(actions) != set(MODES):
        raise AssertionError(f"Comparison file does not contain all Phase B.5 Actions: {actions}")

    scene = bpy.context.scene
    rate = scene.render.fps / scene.render.fps_base
    first_frame = math.floor(start_seconds * rate)
    last_frame = math.ceil(end_seconds * rate) - 1
    original_percentage = scene.render.resolution_percentage
    scene.render.resolution_percentage = scale_percent
    try:
        for mode in MODES:
            mode_dir = output_dir / mode.lower()
            mode_dir.mkdir(parents=True, exist_ok=True)
            target.animation_data.action = actions[mode]
            for output_index, frame in enumerate(range(first_frame, last_frame + 1)):
                scene.frame_set(frame)
                bpy.context.view_layer.update()
                bpy.ops.render.render()
                save_render_result(mode_dir / f"frame_{output_index:04d}.png", scene)
    finally:
        target.animation_data.action = actions["ORIGINAL"]
        scene.render.resolution_percentage = original_percentage
        scene.frame_set(first_frame)
    print(
        "PANDALIP_PHASE_B5_CLIP_FRAMES="
        f"{output_dir}; frames={last_frame - first_frame + 1}; fps={rate:g}"
    )


if __name__ == "__main__":
    main()
