"""Run Phase A integration checks inside Blender with the reference .blend open."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from unittest import mock

import bpy

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from panda_lip_blender import importer  # noqa: E402
import panda_lip_blender as addon  # noqa: E402
from panda_lip_blender.constants import BONE_NAMES, CHANNELS  # noqa: E402
from panda_lip_blender.core import action_base_name  # noqa: E402
from panda_lip_blender import operators  # noqa: E402
from panda_lip_blender.validation import PandaLipValidationError, load_pandalip  # noqa: E402

FIXTURE = REPOSITORY / "tests" / "fixtures" / "aiueo_ramp.pandalip"


class ReferenceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = bpy.context.scene
        cls.target = bpy.data.objects.get("PandaLip")
        if cls.target is None:
            raise AssertionError("Reference file has no PandaLip object")
        cls.data = load_pandalip(FIXTURE)

    def setUp(self) -> None:
        self.old_fps = self.scene.render.fps
        self.old_fps_base = self.scene.render.fps_base
        self.old_frame = self.scene.frame_current
        self.old_subframe = self.scene.frame_subframe
        self.scene.render.fps = 24
        self.scene.render.fps_base = 1.0
        if self.target.animation_data is not None:
            self.target.animation_data.action = None
        self.actions_before = set(bpy.data.actions)

    def tearDown(self) -> None:
        if self.target.animation_data is not None:
            self.target.animation_data.action = None
        for action in set(bpy.data.actions).difference(self.actions_before):
            bpy.data.actions.remove(action, do_unlink=True)
        self.scene.render.fps = self.old_fps
        self.scene.render.fps_base = self.old_fps_base
        self.scene.frame_set(self.old_frame, subframe=self.old_subframe)

    def test_reference_controller_structure(self) -> None:
        self.assertEqual(self.target.type, "ARMATURE")
        self.assertEqual(
            [bone.name for bone in self.target.data.bones if bone.parent is None],
            ["PandaLip_Root"],
        )
        for bone_name in BONE_NAMES.values():
            pose_bone = self.target.pose.bones.get(bone_name)
            self.assertIsNotNone(pose_bone)
            self.assertEqual(pose_bone.parent.name, "PandaLip_Root")
            limits = [constraint for constraint in pose_bone.constraints if constraint.type == "LIMIT_LOCATION"]
            self.assertEqual(len(limits), 1)
            limit = limits[0]
            self.assertEqual(limit.owner_space, "LOCAL")
            self.assertTrue(limit.use_min_x and limit.use_max_x)
            self.assertEqual((limit.min_x, limit.max_x), (0.0, 1.0))
            self.assertTrue(limit.use_min_y and limit.use_max_y)
            self.assertEqual((limit.min_y, limit.max_y), (0.0, 0.0))
            self.assertTrue(limit.use_min_z and limit.use_max_z)
            self.assertEqual((limit.min_z, limit.max_z), (0.0, 0.0))

    def test_import_creates_x_only_linear_subframe_keys_and_unique_action(self) -> None:
        base_name = action_base_name(str(FIXTURE))
        previous = bpy.data.actions.new("PreviouslyAssignedAction")
        self.target.animation_data_create().action = previous
        collision = bpy.data.actions.new(base_name)
        original_non_x = {
            bone_name: (
                tuple(self.target.pose.bones[bone_name].location[1:]),
                tuple(self.target.pose.bones[bone_name].rotation_quaternion),
                tuple(self.target.pose.bones[bone_name].scale),
            )
            for bone_name in BONE_NAMES.values()
        }

        result = importer.import_pandalip_data(
            self.data, str(FIXTURE), self.target, self.scene, start_frame=100
        )
        action = self.target.animation_data.action
        self.assertIsNotNone(action)
        self.assertEqual(action.name, result.action_name)
        self.assertNotEqual(action.name, collision.name)
        self.assertTrue(action.name.startswith(base_name))
        self.assertIn(previous, bpy.data.actions[:])
        self.assertIn(collision, bpy.data.actions[:])
        self.assertEqual(result.keyframe_count, 35)
        self.assertEqual(result.source_keyframe_count, 35)
        self.assertEqual(result.reduction_mode, "ORIGINAL")
        self.assertIsNone(result.tolerance)
        self.assertEqual(result.effective_fps, 24.0)

        first_action = action
        second_result = importer.import_pandalip_data(
            self.data, str(FIXTURE), self.target, self.scene, start_frame=100
        )
        second_action = self.target.animation_data.action
        self.assertIsNotNone(second_action)
        self.assertIsNot(second_action, first_action)
        self.assertEqual(second_action.name, second_result.action_name)
        self.assertTrue(second_action.name.startswith(base_name))
        self.assertIn(first_action, bpy.data.actions[:])
        if bpy.app.version >= (4, 4, 0):
            self.assertGreaterEqual(len(second_action.layers), 1)
            self.assertGreaterEqual(len(second_action.slots), 1)

        curves = importer._action_fcurves(action)
        self.assertEqual(len(curves), 5)
        expected_frames = tuple(100.0 + sample.time * 24.0 for sample in self.data.samples)
        for channel_index, channel in enumerate(CHANNELS):
            bone_name = BONE_NAMES[channel]
            path = self.target.pose.bones[bone_name].path_from_id("location")
            curve = importer._find_fcurve(curves, path, 0)
            self.assertEqual(curve.array_index, 0)
            self.assertEqual(len(curve.keyframe_points), len(self.data.samples))
            for point, expected_frame, sample in zip(
                curve.keyframe_points, expected_frames, self.data.samples, strict=True
            ):
                self.assertTrue(math.isclose(point.co.x, expected_frame, abs_tol=1e-5))
                self.assertTrue(
                    math.isclose(point.co.y, sample.weights[channel_index], abs_tol=1e-6)
                )
                self.assertEqual(point.interpolation, "LINEAR")
        self.assertTrue(any(not math.isclose(frame, round(frame)) for frame in expected_frames))

        for bone_name, before in original_non_x.items():
            pose_bone = self.target.pose.bones[bone_name]
            self.assertEqual(tuple(pose_bone.location[1:]), before[0])
            self.assertEqual(tuple(pose_bone.rotation_quaternion), before[1])
            self.assertEqual(tuple(pose_bone.scale), before[2])

        # Evaluate each one-hot sample at its exact subframe. This confirms the
        # reference controller receives the expected 0 -> 1 local-X motion.
        for channel_index, channel in enumerate(CHANNELS, start=1):
            exact_frame = expected_frames[channel_index]
            integer_frame = math.floor(exact_frame)
            self.scene.frame_set(integer_frame, subframe=exact_frame - integer_frame)
            self.assertTrue(
                math.isclose(
                    self.target.pose.bones[BONE_NAMES[channel]].location.x, 1.0, abs_tol=1e-5
                )
            )

    def test_reduced_import_is_bounded_and_keeps_linear_endpoints(self) -> None:
        result = importer.import_pandalip_data(
            self.data,
            str(FIXTURE),
            self.target,
            self.scene,
            start_frame=100,
            reduction_mode="MIDDLE",
        )
        action = self.target.animation_data.action
        self.assertIsNotNone(action)
        self.assertEqual(result.reduction_mode, "MIDDLE")
        self.assertEqual(result.tolerance, 0.01)
        self.assertLess(result.keyframe_count, result.source_keyframe_count)

        curves = importer._action_fcurves(action)
        source_frames = tuple(100.0 + sample.time * 24.0 for sample in self.data.samples)
        for channel_index, channel in enumerate(CHANNELS):
            pose_bone = self.target.pose.bones[BONE_NAMES[channel]]
            curve = importer._find_fcurve(
                curves, pose_bone.path_from_id("location"), 0
            )
            self.assertTrue(
                math.isclose(curve.keyframe_points[0].co.x, source_frames[0], abs_tol=1e-5)
            )
            self.assertTrue(
                math.isclose(curve.keyframe_points[-1].co.x, source_frames[-1], abs_tol=1e-5)
            )
            for point in curve.keyframe_points:
                self.assertEqual(point.interpolation, "LINEAR")
            for frame, sample in zip(source_frames, self.data.samples, strict=True):
                error = abs(curve.evaluate(frame) - sample.weights[channel_index])
                self.assertLessEqual(error, result.tolerance + 1e-5)

    def test_missing_bone_is_rejected_before_action_creation(self) -> None:
        bone = self.target.data.bones[BONE_NAMES["O"]]
        original_name = bone.name
        bone.name = "TEMP_Missing_CTRL_Lip_O"
        action_count = len(bpy.data.actions)
        try:
            with self.assertRaisesRegex(PandaLipValidationError, "CTRL_Lip_O"):
                importer.import_pandalip_data(
                    self.data, str(FIXTURE), self.target, self.scene, start_frame=1
                )
        finally:
            bone.name = original_name
        self.assertEqual(len(bpy.data.actions), action_count)

    def test_missing_armature_is_rejected_before_action_creation(self) -> None:
        action_count = len(bpy.data.actions)
        with self.assertRaisesRegex(PandaLipValidationError, "Target Armature"):
            importer.import_pandalip_data(
                self.data, str(FIXTURE), None, self.scene, start_frame=1
            )
        self.assertEqual(len(bpy.data.actions), action_count)

    def test_operator_rejects_missing_inputs_and_reentrant_import(self) -> None:
        addon.register()
        action_count = len(bpy.data.actions)
        try:
            settings = self.scene.panda_lip_settings
            settings.quality = "ORIGINAL"
            self.assertEqual(settings.quality, "ORIGINAL")
            settings.filepath = ""
            settings.target_armature = None
            with self.assertRaisesRegex(RuntimeError, "Select a .pandalip file"):
                bpy.ops.pandalip.import_animation()

            settings.filepath = str(FIXTURE)
            with self.assertRaisesRegex(RuntimeError, "Select a Target Armature"):
                bpy.ops.pandalip.import_animation()

            settings.target_armature = self.target
            operators._IMPORT_IN_PROGRESS = True
            self.assertEqual(bpy.ops.pandalip.import_animation(), {"CANCELLED"})
            self.assertEqual(len(bpy.data.actions), action_count)
        finally:
            operators._IMPORT_IN_PROGRESS = False
            addon.unregister()

    def test_operator_applies_custom_quality(self) -> None:
        addon.register()
        try:
            settings = self.scene.panda_lip_settings
            settings.filepath = str(FIXTURE)
            settings.target_armature = self.target
            settings.start_frame = 100
            settings.quality = "CUSTOM"
            settings.custom_tolerance = 0.02
            self.assertEqual(bpy.ops.pandalip.import_animation(), {"FINISHED"})

            action = self.target.animation_data.action
            self.assertIsNotNone(action)
            generated_keys = sum(
                len(curve.keyframe_points) for curve in importer._action_fcurves(action)
            )
            self.assertLess(generated_keys, len(self.data.samples) * len(CHANNELS))
        finally:
            self.scene.panda_lip_settings.quality = "ORIGINAL"
            addon.unregister()

    def test_mid_import_failure_restores_previous_action_and_removes_partial_action(self) -> None:
        previous = bpy.data.actions.new("PreExistingAction")
        self.target.animation_data_create().action = previous
        actions_before_call = set(bpy.data.actions)

        original_set_curve_points = importer._set_curve_points
        completed_curves = 0

        def fail_after_a_partial_curve(*args: object, **kwargs: object) -> None:
            nonlocal completed_curves
            original_set_curve_points(*args, **kwargs)
            completed_curves += 1
            if completed_curves == 1:
                raise RuntimeError("injected after partial curve")

        with mock.patch.object(importer, "_set_curve_points", side_effect=fail_after_a_partial_curve):
            with self.assertRaisesRegex(RuntimeError, "injected after partial curve"):
                importer.import_pandalip_data(
                    self.data, str(FIXTURE), self.target, self.scene, start_frame=1
                )

        self.assertEqual(completed_curves, 1)
        self.assertIs(self.target.animation_data.action, previous)
        self.assertEqual(set(bpy.data.actions), actions_before_call)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceIntegrationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
