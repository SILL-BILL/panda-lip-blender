"""Prepare and reopen a .blend to verify persisted Phase D mapping state."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

import panda_lip_blender as addon  # noqa: E402
from panda_lip_blender import driver_mapping  # noqa: E402
from panda_lip_blender.constants import (  # noqa: E402
    BONE_NAMES,
    CHANNELS,
    MAPPING_PROPERTY_NAMES,
)

TARGET_NAME = "PandaLipPersistenceTarget"
SHAPE_KEY_NAMES = {channel: f"PersistedMouth_{channel}" for channel in CHANNELS}


def _arguments() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _argument_value(flag: str) -> Path:
    arguments = _arguments()
    index = arguments.index(flag)
    return Path(arguments[index + 1]).resolve()


def _register() -> None:
    if not hasattr(bpy.types.Scene, "panda_lip_settings"):
        addon.register()


def _prepare(output: Path) -> None:
    _register()
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    assert bpy.ops.pandalip.create_controller() == {"FINISHED"}

    scene = bpy.context.scene
    settings = scene.panda_lip_settings
    mesh = bpy.data.meshes.new(f"{TARGET_NAME}Mesh")
    target = bpy.data.objects.new(TARGET_NAME, mesh)
    scene.collection.objects.link(target)
    target.shape_key_add(name="Basis")
    for shape_key_name in SHAPE_KEY_NAMES.values():
        target.shape_key_add(name=shape_key_name)

    settings.driver_target_mesh = target
    for channel, property_name in MAPPING_PROPERTY_NAMES.items():
        setattr(settings, property_name, SHAPE_KEY_NAMES[channel])
    assert bpy.ops.pandalip.create_drivers() == {"FINISHED"}

    output.parent.mkdir(parents=True, exist_ok=True)
    assert bpy.ops.wm.save_as_mainfile(filepath=str(output)) == {"FINISHED"}
    print(f"PANDALIP_DRIVER_PERSISTENCE_PREPARED={output}")


def _verify(output: Path) -> None:
    _register()
    assert Path(bpy.data.filepath).resolve() == output

    scene = bpy.context.scene
    settings = scene.panda_lip_settings
    source = settings.target_armature
    target = settings.driver_target_mesh
    assert source is not None and source.name == "PandaLip"
    assert target is not None and target.name == TARGET_NAME

    for channel, property_name in MAPPING_PROPERTY_NAMES.items():
        shape_key_name = SHAPE_KEY_NAMES[channel]
        assert getattr(settings, property_name) == shape_key_name
        key_block = target.data.shape_keys.key_blocks[shape_key_name]
        fcurve = driver_mapping._value_driver(target.data.shape_keys, key_block)
        assert fcurve is not None
        assert driver_mapping.is_pandalip_driver(fcurve, source, channel)
        assert (
            driver_mapping.mapping_status(
                source,
                target,
                channel,
                shape_key_name,
            ).code
            == "CONNECTED"
        )

    for active_channel in CHANNELS:
        for channel in CHANNELS:
            source.pose.bones[BONE_NAMES[channel]].location.x = (
                0.625 if channel == active_channel else 0.0
            )
        bpy.context.view_layer.update()
        for channel in CHANNELS:
            actual = target.data.shape_keys.key_blocks[SHAPE_KEY_NAMES[channel]].value
            expected = 0.625 if channel == active_channel else 0.0
            assert math.isclose(actual, expected, abs_tol=1.0e-5), (
                active_channel,
                channel,
                actual,
            )

    print(f"PANDALIP_DRIVER_PERSISTENCE_REOPEN_PASS={output}")


if __name__ == "__main__":
    arguments = _arguments()
    output_path = _argument_value("--output")
    if "--prepare" in arguments:
        _prepare(output_path)
    elif "--verify" in arguments:
        _verify(output_path)
    else:
        raise SystemExit("Use --prepare or --verify")
