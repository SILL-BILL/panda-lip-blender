"""Exercise Phase C controller generation inside Blender."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import bpy

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

import panda_lip_blender as addon  # noqa: E402
from panda_lip_blender import importer  # noqa: E402
from panda_lip_blender.constants import (  # noqa: E402
    BONE_NAMES,
    CHANNELS,
    CONTROLLER_COLLECTION_NAME,
    CONTROLLER_OBJECT_NAME,
    CONTROLLER_VERSION,
    CONTROLLER_VERSION_KEY,
    MENU_WIDGET_NAME,
    ROOT_BONE_NAME,
    SWITCH_WIDGET_NAME,
)
from panda_lip_blender.controller import (  # noqa: E402
    controller_structure_error,
    find_existing_controller,
)

FIXTURE = REPOSITORY / "tests" / "fixtures" / "aiueo_ramp.pandalip"


class ControllerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        addon.register()

    @classmethod
    def tearDownClass(cls) -> None:
        addon.unregister()

    def setUp(self) -> None:
        self.scene = bpy.context.scene
        self.scene.panda_lip_settings.target_armature = None
        self.scene.panda_lip_settings.filepath = ""
        self.scene.panda_lip_settings.quality = "ORIGINAL"
        self.scene.cursor.location = (1.25, -2.0, 3.5)
        self._remove_generated_data()
        for action in list(bpy.data.actions):
            if action.name.startswith("PandaLip_"):
                bpy.data.actions.remove(action, do_unlink=True)

    def tearDown(self) -> None:
        scene = bpy.context.scene
        scene.panda_lip_settings.target_armature = None
        self._remove_generated_data()
        for action in list(bpy.data.actions):
            if action.name.startswith("PandaLip_"):
                bpy.data.actions.remove(action, do_unlink=True)

    @staticmethod
    def _remove_generated_data() -> None:
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for obj in list(bpy.data.objects):
            if obj.get(CONTROLLER_VERSION_KEY) != CONTROLLER_VERSION:
                continue
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                if isinstance(data, bpy.types.Armature):
                    bpy.data.armatures.remove(data)
                elif isinstance(data, bpy.types.Mesh):
                    bpy.data.meshes.remove(data)
        for collection in list(bpy.data.collections):
            if collection.get(CONTROLLER_VERSION_KEY) == CONTROLLER_VERSION:
                bpy.data.collections.remove(collection)

    def _create(self) -> bpy.types.Object:
        self.assertEqual(bpy.ops.pandalip.create_controller(), {"FINISHED"})
        controller = self.scene.panda_lip_settings.target_armature
        self.assertIsNotNone(controller)
        return controller

    def _assert_controller_contract(self, controller: bpy.types.Object) -> None:
        self.assertIsNone(controller_structure_error(controller))
        self.assertEqual(controller.type, "ARMATURE")
        self.assertEqual(controller.name, CONTROLLER_OBJECT_NAME)
        self.assertEqual(tuple(controller.location), tuple(self.scene.cursor.location))
        self.assertTrue(controller.show_in_front)
        self.assertEqual(controller.get(CONTROLLER_VERSION_KEY), CONTROLLER_VERSION)
        collection = bpy.data.collections.get(CONTROLLER_COLLECTION_NAME)
        self.assertIsNotNone(collection)
        self.assertIn(controller, collection.objects[:])

        root = controller.data.bones.get(ROOT_BONE_NAME)
        self.assertIsNotNone(root)
        self.assertIsNone(root.parent)
        self.assertFalse(root.use_deform)
        self.assertIsNotNone(controller.pose.bones[ROOT_BONE_NAME].custom_shape)

        shared_shape = None
        expected_rows = {"A": 0.50, "I": 0.25, "U": 0.0, "E": -0.25, "O": -0.50}
        for channel in CHANNELS:
            bone_name = BONE_NAMES[channel]
            bone = controller.data.bones.get(bone_name)
            self.assertIsNotNone(bone)
            self.assertIsNotNone(bone.parent)
            self.assertEqual(bone.parent.name, ROOT_BONE_NAME)
            self.assertFalse(bone.use_deform)
            self.assertTrue(math.isclose(bone.head_local.x, 0.25, abs_tol=1.0e-6))
            self.assertTrue(
                math.isclose(bone.head_local.z, expected_rows[channel], abs_tol=1.0e-6)
            )

            pose_bone = controller.pose.bones[bone_name]
            self.assertEqual(tuple(pose_bone.lock_location), (False, True, True))
            self.assertEqual(tuple(pose_bone.lock_rotation), (True, True, True))
            self.assertTrue(pose_bone.lock_rotation_w)
            self.assertEqual(tuple(pose_bone.lock_scale), (True, True, True))
            self.assertIsNotNone(pose_bone.custom_shape)
            if shared_shape is None:
                shared_shape = pose_bone.custom_shape
            self.assertIs(pose_bone.custom_shape, shared_shape)

            limits = [item for item in pose_bone.constraints if item.type == "LIMIT_LOCATION"]
            self.assertEqual(len(limits), 1)
            limit = limits[0]
            self.assertEqual(limit.owner_space, "LOCAL")
            self.assertTrue(limit.use_transform_limit)
            self.assertEqual(
                (
                    limit.use_min_x,
                    limit.use_max_x,
                    limit.use_min_y,
                    limit.use_max_y,
                    limit.use_min_z,
                    limit.use_max_z,
                ),
                (True, True, True, True, True, True),
            )
            self.assertEqual(
                (limit.min_x, limit.max_x, limit.min_y, limit.max_y, limit.min_z, limit.max_z),
                (0.0, 1.0, 0.0, 0.0, 0.0, 0.0),
            )
            for value in (0.0, 0.25, 1.0):
                pose_bone.location.x = value
                bpy.context.view_layer.update()
                self.assertTrue(math.isclose(pose_bone.location.x, value, abs_tol=1.0e-6))
            pose_bone.location.x = 0.0

        generated_widgets = [
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH"
            and obj.get(CONTROLLER_VERSION_KEY) == CONTROLLER_VERSION
        ]
        self.assertEqual(len(generated_widgets), 2)
        self.assertEqual(
            {widget.name for widget in generated_widgets},
            {MENU_WIDGET_NAME, SWITCH_WIDGET_NAME},
        )
        self.assertTrue(all(widget.hide_viewport for widget in generated_widgets))
        self.assertTrue(all(widget.hide_render for widget in generated_widgets))
        self.assertTrue(all(widget.hide_get() for widget in generated_widgets))

    def test_controller_creation_contract_and_target_assignment(self) -> None:
        controller = self._create()

        self._assert_controller_contract(controller)
        self.assertIs(find_existing_controller(self.scene), controller)
        self.assertIs(self.scene.panda_lip_settings.target_armature, controller)
        self.assertIs(bpy.context.view_layer.objects.active, controller)

    def test_duplicate_generation_is_prevented_by_structure(self) -> None:
        controller = self._create()
        object_count = len(bpy.data.objects)
        collection_count = len(bpy.data.collections)

        self.assertEqual(bpy.ops.pandalip.create_controller(), {"CANCELLED"})

        self.assertEqual(len(bpy.data.objects), object_count)
        self.assertEqual(len(bpy.data.collections), collection_count)
        self.assertIs(self.scene.panda_lip_settings.target_armature, controller)

    def test_bone_names_without_valid_structure_do_not_block_creation(self) -> None:
        invalid = self._create()
        invalid.name = "UserRigWithNamesOnly"
        pose_bone = invalid.pose.bones[BONE_NAMES["A"]]
        pose_bone.constraints.remove(pose_bone.constraints[0])
        self.scene.panda_lip_settings.target_armature = None

        generated = self._create()

        self.assertIsNot(generated, invalid)
        self.assertIsNotNone(controller_structure_error(invalid))
        self.assertIsNone(controller_structure_error(generated))

    def test_all_quality_presets_import_into_generated_controller(self) -> None:
        controller = self._create()
        settings = self.scene.panda_lip_settings
        settings.filepath = str(FIXTURE)
        settings.start_frame = 100
        generated_counts: dict[str, int] = {}

        for quality in ("ORIGINAL", "HIGH", "MIDDLE", "LOW", "CUSTOM"):
            settings.quality = quality
            if quality == "CUSTOM":
                settings.custom_tolerance = 0.015
            self.assertEqual(bpy.ops.pandalip.import_animation(), {"FINISHED"})
            action = controller.animation_data.action
            self.assertIsNotNone(action)
            curves = importer._action_fcurves(action)
            self.assertEqual(len(curves), len(CHANNELS))
            generated_counts[quality] = sum(
                len(curve.keyframe_points) for curve in curves
            )
            for channel in CHANNELS:
                expected_path = controller.pose.bones[BONE_NAMES[channel]].path_from_id(
                    "location"
                )
                curve = importer._find_fcurve(curves, expected_path, 0)
                self.assertEqual(curve.array_index, 0)
            controller.animation_data.action = None
            bpy.data.actions.remove(action, do_unlink=True)

        self.assertEqual(generated_counts["ORIGINAL"], 35)
        self.assertLess(generated_counts["MIDDLE"], generated_counts["ORIGINAL"])

    def test_file_browse_property_and_import_connection(self) -> None:
        settings = self.scene.panda_lip_settings
        filepath_property = settings.bl_rna.properties["filepath"]
        self.assertEqual(filepath_property.subtype, "FILE_PATH")

        controller = self._create()
        missing = FIXTURE.with_name("missing-file.pandalip")
        settings.filepath = str(missing)
        action_count = len(bpy.data.actions)

        with self.assertRaisesRegex(RuntimeError, "PandaLip file does not exist"):
            bpy.ops.pandalip.import_animation()
        self.assertEqual(len(bpy.data.actions), action_count)
        self.assertIsNone(controller.animation_data)

        settings.filepath = ""
        self.assertEqual(
            bpy.ops.pandalip.select_file(filepath=str(FIXTURE)),
            {"FINISHED"},
        )
        self.assertEqual(
            Path(bpy.path.abspath(settings.filepath)).resolve(),
            FIXTURE.resolve(),
        )
        self.assertEqual(bpy.ops.pandalip.import_animation(), {"FINISHED"})
        self.assertIsNotNone(controller.animation_data)
        self.assertIsNotNone(controller.animation_data.action)

    def test_controller_generation_is_undoable(self) -> None:
        if bpy.app.background:
            self.skipTest("Blender disables ed.undo in background mode")
        use_global_undo = bpy.context.preferences.edit.use_global_undo
        bpy.context.preferences.edit.use_global_undo = True
        try:
            window = bpy.context.window_manager.windows[0]
            area = next(item for item in window.screen.areas if item.type == "VIEW_3D")
            region = next(item for item in area.regions if item.type == "WINDOW")
            with bpy.context.temp_override(
                window=window,
                screen=window.screen,
                area=area,
                region=region,
            ):
                bpy.ops.ed.undo_push(message="Initialize Panda Lip controller undo test")
                controller = self._create()
                controller_name = controller.name
                collection_names = {
                    collection.name
                    for collection in bpy.data.collections
                    if collection.get(CONTROLLER_VERSION_KEY) == CONTROLLER_VERSION
                }
                widget_names = {
                    obj.name
                    for obj in bpy.data.objects
                    if obj.type == "MESH"
                    and obj.get(CONTROLLER_VERSION_KEY) == CONTROLLER_VERSION
                }

                self.assertEqual(bpy.ops.ed.undo(), {"FINISHED"})

            restored_scene = bpy.context.scene
            self.assertIsNone(bpy.data.objects.get(controller_name))
            self.assertTrue(all(bpy.data.objects.get(name) is None for name in widget_names))
            self.assertTrue(
                all(bpy.data.collections.get(name) is None for name in collection_names)
            )
            self.assertIsNone(find_existing_controller(restored_scene))
            self.assertIsNone(restored_scene.panda_lip_settings.target_armature)
        finally:
            bpy.context.preferences.edit.use_global_undo = use_global_undo


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ControllerIntegrationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if "--quit-after-tests" in sys.argv:
        print(
            "PANDALIP_CONTROLLER_UI_TEST_PASS"
            if result.wasSuccessful()
            else "PANDALIP_CONTROLLER_UI_TEST_FAIL"
        )
        bpy.app.timers.register(
            lambda: (bpy.ops.wm.quit_blender(), None)[1],
            first_interval=0.1,
        )
    if not result.wasSuccessful():
        raise SystemExit(1)
