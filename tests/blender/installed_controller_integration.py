"""Verify the built and enabled Extension without importing repository sources."""

from __future__ import annotations

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
            controller.animation_data.action = None
            bpy.data.actions.remove(action, do_unlink=True)

        self.assertEqual(key_counts["ORIGINAL"], 35)
        self.assertLess(key_counts["MIDDLE"], key_counts["ORIGINAL"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        InstalledControllerIntegrationTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
