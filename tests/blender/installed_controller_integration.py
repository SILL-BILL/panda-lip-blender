"""Verify the built and enabled Extension without importing repository sources."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import bpy

CHANNELS = ("A", "I", "U", "E", "O")
BONE_NAMES = {channel: f"CTRL_Lip_{channel}" for channel in CHANNELS}
ROOT_BONE_NAME = "PandaLip_Root"


def _argument_value(flag: str) -> Path:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    index = arguments.index(flag)
    return Path(arguments[index + 1]).resolve()


FIXTURE = _argument_value("--fixture")


class InstalledControllerIntegrationTests(unittest.TestCase):
    def test_enabled_zip_creates_controller_and_imports_original_and_middle(self) -> None:
        enabled = tuple(bpy.context.preferences.addons.keys())
        self.assertTrue(
            any(name.endswith(".panda_lip_blender") for name in enabled),
            f"installed extension is not enabled: {enabled}",
        )
        self.assertTrue(bpy.ops.pandalip.create_controller.poll())
        self.assertEqual(bpy.ops.pandalip.create_controller(), {"FINISHED"})

        scene = bpy.context.scene
        settings = scene.panda_lip_settings
        controller = settings.target_armature
        self.assertIsNotNone(controller)
        self.assertEqual(controller.type, "ARMATURE")
        root = controller.data.bones.get(ROOT_BONE_NAME)
        self.assertIsNotNone(root)
        self.assertIsNone(root.parent)
        for channel in CHANNELS:
            bone = controller.data.bones.get(BONE_NAMES[channel])
            self.assertIsNotNone(bone)
            self.assertIsNotNone(bone.parent)
            self.assertEqual(bone.parent.name, ROOT_BONE_NAME)
            limit = next(
                item
                for item in controller.pose.bones[bone.name].constraints
                if item.type == "LIMIT_LOCATION"
            )
            self.assertEqual(limit.owner_space, "LOCAL")
            self.assertEqual(
                (limit.min_x, limit.max_x, limit.min_y, limit.max_y, limit.min_z, limit.max_z),
                (0.0, 1.0, 0.0, 0.0, 0.0, 0.0),
            )

        mesh = bpy.data.meshes.new("PandaLipInstalledDriverMesh")
        driven_object = bpy.data.objects.new("PandaLipInstalledDriverTarget", mesh)
        scene.collection.objects.link(driven_object)
        driven_object.shape_key_add(name="Basis")
        shape_key_names = {
            channel: f"InstalledMouth_{channel}" for channel in CHANNELS
        }
        for shape_key_name in shape_key_names.values():
            driven_object.shape_key_add(name=shape_key_name)
        settings.driver_target_mesh = driven_object
        for channel in CHANNELS:
            setattr(
                settings,
                f"driver_shape_key_{channel.lower()}",
                shape_key_names[channel],
            )
        self.assertEqual(bpy.ops.pandalip.create_drivers(), {"FINISHED"})

        shape_keys = driven_object.data.shape_keys
        self.assertIsNotNone(shape_keys.animation_data)
        self.assertEqual(len(shape_keys.animation_data.drivers), len(CHANNELS))
        for channel in CHANNELS:
            key_block = shape_keys.key_blocks[shape_key_names[channel]]
            data_path = key_block.path_from_id("value")
            fcurve = next(
                curve
                for curve in shape_keys.animation_data.drivers
                if curve.data_path == data_path
            )
            driver = fcurve.driver
            self.assertEqual(driver.expression, f"pandalip_{channel}")
            self.assertEqual(len(driver.variables), 1)
            variable = driver.variables[0]
            self.assertEqual(variable.type, "TRANSFORMS")
            self.assertEqual(variable.targets[0].id, controller)
            self.assertEqual(variable.targets[0].bone_target, BONE_NAMES[channel])
            self.assertEqual(variable.targets[0].transform_type, "LOC_X")
            self.assertEqual(variable.targets[0].transform_space, "LOCAL_SPACE")

        settings.filepath = str(FIXTURE)
        settings.start_frame = 100
        key_counts: dict[str, int] = {}
        for quality in ("ORIGINAL", "MIDDLE"):
            settings.quality = quality
            self.assertEqual(bpy.ops.pandalip.import_animation(), {"FINISHED"})
            action = controller.animation_data.action
            self.assertIsNotNone(action)
            if bpy.app.version >= (4, 4, 0):
                curves = action.layers[0].strips[0].channelbags[0].fcurves
            else:
                curves = action.fcurves
            self.assertEqual(len(curves), len(CHANNELS))
            key_counts[quality] = sum(len(curve.keyframe_points) for curve in curves)
            for active_index, active_channel in enumerate(CHANNELS, start=1):
                exact_frame = 100.0 + active_index * 0.01 * 24.0
                integer_frame = math.floor(exact_frame)
                scene.frame_set(integer_frame, subframe=exact_frame - integer_frame)
                for channel in CHANNELS:
                    expected = 1.0 if channel == active_channel else 0.0
                    actual = shape_keys.key_blocks[shape_key_names[channel]].value
                    self.assertTrue(
                        math.isclose(actual, expected, abs_tol=1.0e-5),
                        f"{quality} {active_channel} drove {channel} to {actual}",
                    )
            controller.animation_data.action = None
            bpy.data.actions.remove(action, do_unlink=True)

        self.assertEqual(key_counts["ORIGINAL"], 35)
        self.assertLess(key_counts["MIDDLE"], key_counts["ORIGINAL"])
        self.assertEqual(bpy.ops.pandalip.remove_drivers(), {"FINISHED"})
        self.assertEqual(len(shape_keys.animation_data.drivers), 0)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        InstalledControllerIntegrationTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
