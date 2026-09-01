"""Exercise Phase D generic Driver Mapping inside Blender."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from unittest import mock

import bpy

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

import panda_lip_blender as addon  # noqa: E402
from panda_lip_blender import driver_mapping, importer  # noqa: E402
from panda_lip_blender.constants import (  # noqa: E402
    BONE_NAMES,
    CHANNELS,
    CONTROLLER_VERSION,
    CONTROLLER_VERSION_KEY,
    MAPPING_PROPERTY_NAMES,
)
from panda_lip_blender.controller import create_controller  # noqa: E402
from panda_lip_blender.driver_mapping import (  # noqa: E402
    DriverMappingError,
    create_pandalip_drivers,
    is_pandalip_driver,
    mapping_status,
    remove_pandalip_drivers,
)
from panda_lip_blender.validation import load_pandalip  # noqa: E402

FIXTURE = REPOSITORY / "tests" / "fixtures" / "aiueo_ramp.pandalip"


class DriverMappingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        addon.register()

    @classmethod
    def tearDownClass(cls) -> None:
        addon.unregister()

    def setUp(self) -> None:
        self.scene = bpy.context.scene
        self._clear_settings()
        self._remove_test_data()
        self.assertEqual(bpy.ops.pandalip.create_controller(), {"FINISHED"})
        self.source = self.scene.panda_lip_settings.target_armature

    def tearDown(self) -> None:
        self.scene = bpy.context.scene
        self._clear_settings()
        self._remove_test_data()
        for action in list(bpy.data.actions):
            if action.name.startswith("PandaLip_"):
                bpy.data.actions.remove(action, do_unlink=True)

    def _clear_settings(self) -> None:
        settings = bpy.context.scene.panda_lip_settings
        settings.target_armature = None
        settings.driver_target_mesh = None
        settings.filepath = ""
        settings.quality = "ORIGINAL"
        for property_name in MAPPING_PROPERTY_NAMES.values():
            setattr(settings, property_name, "")

    @staticmethod
    def _remove_test_data() -> None:
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for obj in list(bpy.data.objects):
            if not (
                obj.get(CONTROLLER_VERSION_KEY) == CONTROLLER_VERSION
                or obj.name.startswith("PandaLipDriverTest")
            ):
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

    def _target(self, names: tuple[str, ...] = CHANNELS) -> bpy.types.Object:
        mesh = bpy.data.meshes.new("PandaLipDriverTestMesh")
        target = bpy.data.objects.new("PandaLipDriverTestTarget", mesh)
        self.scene.collection.objects.link(target)
        target.shape_key_add(name="Basis")
        for name in names:
            target.shape_key_add(name=name)
        self.scene.panda_lip_settings.driver_target_mesh = target
        return target

    def _set_mappings(self, mappings: dict[str, str]) -> None:
        settings = self.scene.panda_lip_settings
        for channel in CHANNELS:
            setattr(settings, MAPPING_PROPERTY_NAMES[channel], mappings.get(channel, ""))

    @staticmethod
    def _driver(target: bpy.types.Object, shape_key_name: str) -> bpy.types.FCurve | None:
        key_block = target.data.shape_keys.key_blocks[shape_key_name]
        return driver_mapping._value_driver(target.data.shape_keys, key_block)

    def _update(self) -> None:
        self.scene.frame_set(self.scene.frame_current, subframe=self.scene.frame_subframe)
        bpy.context.view_layer.update()

    def test_one_channel_mapping_skips_unset_channels_and_propagates_local_x(self) -> None:
        target = self._target(("MouthA", "Unused"))
        result = create_pandalip_drivers(self.source, target, {"A": "MouthA"})

        self.assertEqual(result.created, ("MouthA",))
        self.assertFalse(result.reused)
        fcurve = self._driver(target, "MouthA")
        self.assertIsNotNone(fcurve)
        self.assertIsNone(self._driver(target, "Unused"))
        self.assertTrue(is_pandalip_driver(fcurve, self.source, "A"))
        variable = fcurve.driver.variables[0]
        driver_target = variable.targets[0]
        self.assertEqual(variable.type, "TRANSFORMS")
        self.assertIs(driver_target.id, self.source)
        self.assertEqual(driver_target.bone_target, BONE_NAMES["A"])
        self.assertEqual(driver_target.transform_type, "LOC_X")
        self.assertEqual(driver_target.transform_space, "LOCAL_SPACE")
        self.assertEqual(fcurve.driver.expression, "pandalip_A")

        for value in (0.0, 0.25, 1.0):
            self.source.pose.bones[BONE_NAMES["A"]].location.x = value
            self._update()
            self.assertTrue(
                math.isclose(
                    target.data.shape_keys.key_blocks["MouthA"].value,
                    value,
                    abs_tol=1.0e-6,
                )
            )

    def test_five_channel_mapping_and_status(self) -> None:
        target = self._target()
        mappings = dict(zip(CHANNELS, CHANNELS, strict=True))
        self._set_mappings(mappings)

        for channel in CHANNELS:
            status = mapping_status(self.source, target, channel, channel)
            self.assertEqual(status.code, "READY")
        self.assertEqual(bpy.ops.pandalip.create_drivers(), {"FINISHED"})

        for index, channel in enumerate(CHANNELS, start=1):
            fcurve = self._driver(target, channel)
            self.assertIsNotNone(fcurve)
            self.assertTrue(is_pandalip_driver(fcurve, self.source, channel))
            self.source.pose.bones[BONE_NAMES[channel]].location.x = index / 5.0
        self._update()
        for index, channel in enumerate(CHANNELS, start=1):
            self.assertTrue(
                math.isclose(
                    target.data.shape_keys.key_blocks[channel].value,
                    index / 5.0,
                    abs_tol=1.0e-6,
                )
            )
            self.assertEqual(
                mapping_status(self.source, target, channel, channel).code,
                "CONNECTED",
            )

        for value in (0.0, 0.25, 1.0):
            for channel in CHANNELS:
                self.source.pose.bones[BONE_NAMES[channel]].location.x = value
            self._update()
            for channel in CHANNELS:
                self.assertTrue(
                    math.isclose(
                        target.data.shape_keys.key_blocks[channel].value,
                        value,
                        abs_tol=1.0e-6,
                    )
                )

    def test_validation_rejects_missing_invalid_and_basis_requests(self) -> None:
        target = self._target(("MouthA",))
        empty_mesh = bpy.data.meshes.new("PandaLipDriverTestNoKeysMesh")
        no_keys = bpy.data.objects.new("PandaLipDriverTestNoKeys", empty_mesh)
        self.scene.collection.objects.link(no_keys)
        non_mesh_data = bpy.data.curves.new("PandaLipDriverTestCurveData", "CURVE")
        non_mesh = bpy.data.objects.new("PandaLipDriverTestCurve", non_mesh_data)
        self.scene.collection.objects.link(non_mesh)

        with self.assertRaisesRegex(DriverMappingError, "Source Armature"):
            create_pandalip_drivers(None, target, {"A": "MouthA"})
        with self.assertRaisesRegex(DriverMappingError, "Target Mesh"):
            create_pandalip_drivers(self.source, None, {"A": "MouthA"})
        with self.assertRaisesRegex(DriverMappingError, "Mesh Object"):
            create_pandalip_drivers(self.source, non_mesh, {"A": "MouthA"})
        with self.assertRaisesRegex(DriverMappingError, "besides Basis"):
            create_pandalip_drivers(self.source, no_keys, {"A": "MouthA"})
        with self.assertRaisesRegex(DriverMappingError, "at least one"):
            create_pandalip_drivers(self.source, target, {})
        with self.assertRaisesRegex(DriverMappingError, "does not exist"):
            create_pandalip_drivers(self.source, target, {"A": "Wrong"})
        with self.assertRaisesRegex(DriverMappingError, "Basis cannot"):
            create_pandalip_drivers(self.source, target, {"A": "Basis"})
        with self.assertRaisesRegex(DriverMappingError, "only one"):
            create_pandalip_drivers(
                self.source,
                target,
                {"A": "MouthA", "I": "MouthA"},
            )

        original_name = self.source.data.bones[BONE_NAMES["O"]].name
        self.source.data.bones[BONE_NAMES["O"]].name = "Missing_CTRL_Lip_O"
        try:
            with self.assertRaisesRegex(DriverMappingError, "CTRL_Lip_O"):
                create_pandalip_drivers(self.source, target, {"A": "MouthA"})
        finally:
            self.source.data.bones["Missing_CTRL_Lip_O"].name = original_name

    def test_existing_driver_is_protected_and_prevents_partial_creation(self) -> None:
        target = self._target(("MouthA", "MouthI"))
        conflict = target.data.shape_keys.key_blocks["MouthI"].driver_add("value")
        conflict.driver.expression = "0.375"

        with self.assertRaisesRegex(DriverMappingError, "already has a driver"):
            create_pandalip_drivers(
                self.source,
                target,
                {"A": "MouthA", "I": "MouthI"},
            )

        self.assertIsNone(self._driver(target, "MouthA"))
        self.assertEqual(self._driver(target, "MouthI").as_pointer(), conflict.as_pointer())
        self.assertEqual(conflict.driver.expression, "0.375")
        self.assertEqual(
            mapping_status(self.source, target, "I", "MouthI").code,
            "CONFLICT",
        )

    def test_duplicate_driver_is_reused_without_modification(self) -> None:
        target = self._target(("MouthA",))
        first = create_pandalip_drivers(self.source, target, {"A": "MouthA"})
        fcurve = self._driver(target, "MouthA")

        second = create_pandalip_drivers(self.source, target, {"A": "MouthA"})

        self.assertEqual(first.created, ("MouthA",))
        self.assertEqual(second.created, ())
        self.assertEqual(second.reused, ("MouthA",))
        self.assertEqual(self._driver(target, "MouthA").as_pointer(), fcurve.as_pointer())

    def test_runtime_failure_rolls_back_only_new_drivers(self) -> None:
        target = self._target(("MouthA", "MouthI", "Unrelated"))
        unrelated = target.data.shape_keys.key_blocks["Unrelated"].driver_add("value")
        unrelated.driver.expression = "0.625"
        original = driver_mapping._configure_pandalip_driver
        calls = 0

        def fail_on_second(*args: object, **kwargs: object) -> None:
            nonlocal calls
            calls += 1
            original(*args, **kwargs)
            if calls == 2:
                raise RuntimeError("injected driver failure")

        with mock.patch.object(
            driver_mapping,
            "_configure_pandalip_driver",
            side_effect=fail_on_second,
        ):
            with self.assertRaisesRegex(DriverMappingError, "rolled back"):
                create_pandalip_drivers(
                    self.source,
                    target,
                    {"A": "MouthA", "I": "MouthI"},
                )

        self.assertIsNone(self._driver(target, "MouthA"))
        self.assertIsNone(self._driver(target, "MouthI"))
        self.assertEqual(
            self._driver(target, "Unrelated").as_pointer(),
            unrelated.as_pointer(),
        )
        self.assertEqual(unrelated.driver.expression, "0.625")

    def test_remove_deletes_only_exact_selected_source_signatures(self) -> None:
        target = self._target(("MouthA", "MouthI", "Unrelated"))
        create_pandalip_drivers(
            self.source,
            target,
            {"A": "MouthA", "I": "MouthI"},
        )
        unrelated = target.data.shape_keys.key_blocks["Unrelated"].driver_add("value")
        unrelated.driver.expression = "0.5"

        result = remove_pandalip_drivers(self.source, target)

        self.assertEqual(result.removed, ("MouthA", "MouthI"))
        self.assertIsNone(self._driver(target, "MouthA"))
        self.assertIsNone(self._driver(target, "MouthI"))
        self.assertEqual(
            self._driver(target, "Unrelated").as_pointer(),
            unrelated.as_pointer(),
        )

    def test_explicit_source_is_safe_with_multiple_controllers(self) -> None:
        first = self.source
        second = create_controller(bpy.context)
        target = self._target(("MouthA",))

        create_pandalip_drivers(second, target, {"A": "MouthA"})

        fcurve = self._driver(target, "MouthA")
        self.assertIs(fcurve.driver.variables[0].targets[0].id, second)
        first.pose.bones[BONE_NAMES["A"]].location.x = 1.0
        second.pose.bones[BONE_NAMES["A"]].location.x = 0.0
        self._update()
        self.assertTrue(
            math.isclose(target.data.shape_keys.key_blocks["MouthA"].value, 0.0)
        )
        second.pose.bones[BONE_NAMES["A"]].location.x = 0.8
        self._update()
        self.assertTrue(
            math.isclose(
                target.data.shape_keys.key_blocks["MouthA"].value,
                0.8,
                abs_tol=1.0e-6,
            )
        )

    def test_full_pipeline_all_quality_presets_drive_shape_keys(self) -> None:
        target = self._target()
        mappings = dict(zip(CHANNELS, CHANNELS, strict=True))
        create_pandalip_drivers(self.source, target, mappings)
        document = load_pandalip(FIXTURE)
        settings = self.scene.panda_lip_settings
        settings.filepath = str(FIXTURE)
        settings.start_frame = 100

        for quality in ("ORIGINAL", "HIGH", "MIDDLE", "LOW", "CUSTOM"):
            settings.quality = quality
            if quality == "CUSTOM":
                settings.custom_tolerance = 0.015
            self.assertEqual(bpy.ops.pandalip.import_animation(), {"FINISHED"})
            action = self.source.animation_data.action
            self.assertIsNotNone(action)
            for sample in document.samples:
                exact_frame = 100.0 + sample.time * 24.0
                integer_frame = math.floor(exact_frame)
                self.scene.frame_set(
                    integer_frame,
                    subframe=exact_frame - integer_frame,
                )
                bpy.context.view_layer.update()
                for channel_index, channel in enumerate(CHANNELS):
                    driven = target.data.shape_keys.key_blocks[channel].value
                    source_value = self.source.pose.bones[BONE_NAMES[channel]].location.x
                    self.assertTrue(
                        math.isclose(driven, source_value, abs_tol=1.0e-5),
                        f"{quality} {channel} frame {exact_frame}: {driven} != {source_value}",
                    )
                    self.assertTrue(
                        math.isclose(
                            source_value,
                            sample.weights[channel_index],
                            abs_tol=1.0e-5,
                        ),
                        f"{quality} {channel} frame {exact_frame}: "
                        f"{source_value} != {sample.weights[channel_index]}",
                    )
            self.source.animation_data.action = None
            bpy.data.actions.remove(action, do_unlink=True)

    def test_create_drivers_is_undoable_in_ui_mode(self) -> None:
        if bpy.app.background:
            self.skipTest("Blender disables ed.undo in background mode")
        bpy.ops.mesh.primitive_plane_add(size=1.0)
        target = bpy.context.object
        target.name = "PandaLipDriverTestTarget"
        bpy.ops.object.shape_key_add(from_mix=False)
        key = bpy.ops.object.shape_key_add(from_mix=False)
        self.assertEqual(key, {"FINISHED"})
        target.data.shape_keys.key_blocks[-1].name = "MouthA"
        self.scene.panda_lip_settings.driver_target_mesh = target
        self._set_mappings({"A": "MouthA"})
        source_name = self.source.name
        target_name = target.name
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
                bpy.ops.ed.undo_push(message="Initialize Panda Lip Driver undo test")
                self.assertEqual(bpy.ops.pandalip.create_drivers(), {"FINISHED"})
                self.assertIsNotNone(self._driver(target, "MouthA"))
                bpy.ops.ed.undo_push(message="Create Panda Lip Drivers")
                self.assertEqual(bpy.ops.ed.undo(), {"FINISHED"})

            restored_target = bpy.context.scene.objects[target_name]
            restored_source = bpy.context.scene.objects[source_name]
            self.assertIsNone(self._driver(restored_target, "MouthA"))
            self.assertIsNotNone(restored_source)
            self.assertEqual(
                bpy.context.scene.panda_lip_settings.driver_shape_key_a,
                "MouthA",
            )
            self.assertIn("UNDO", addon.operators.PANDALIP_OT_create_drivers.bl_options)
        finally:
            bpy.context.preferences.edit.use_global_undo = use_global_undo


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        DriverMappingIntegrationTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if "--quit-after-tests" in sys.argv:
        print(
            "PANDALIP_DRIVER_UI_TEST_PASS"
            if result.wasSuccessful()
            else "PANDALIP_DRIVER_UI_TEST_FAIL"
        )
        bpy.app.timers.register(
            lambda: (bpy.ops.wm.quit_blender(), None)[1],
            first_interval=0.1,
        )
    if not result.wasSuccessful():
        raise SystemExit(1)
