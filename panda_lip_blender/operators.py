"""Panda Lip file selection and import operators."""

from __future__ import annotations

import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper

from .constants import CHANNELS
from .controller import create_controller, find_existing_controller
from .importer import import_pandalip_file
from .validation import PandaLipValidationError

_IMPORT_IN_PROGRESS = False


def import_in_progress() -> bool:
    """Return whether the synchronous importer is currently running."""

    return _IMPORT_IN_PROGRESS


class PANDALIP_OT_select_file(bpy.types.Operator, ImportHelper):
    bl_idname = "pandalip.select_file"
    bl_label = "Select PandaLip File"
    bl_description = "Choose a .pandalip file"

    filename_ext = ".pandalip"
    filter_glob: StringProperty(default="*.pandalip", options={"HIDDEN"})

    def execute(self, context: bpy.types.Context) -> set[str]:
        context.scene.panda_lip_settings.filepath = self.filepath
        return {"FINISHED"}


class PANDALIP_OT_create_controller(bpy.types.Operator):
    bl_idname = "pandalip.create_controller"
    bl_label = "Create Panda Lip Controller"
    bl_description = "Create an independent standard AIUEO controller at the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT"

    def execute(self, context: bpy.types.Context) -> set[str]:
        existing = find_existing_controller(context.scene)
        if existing is not None:
            context.scene.panda_lip_settings.target_armature = existing
            self.report(
                {"WARNING"},
                f"A valid Panda Lip Controller already exists: {existing.name}",
            )
            return {"CANCELLED"}

        try:
            controller = create_controller(context)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not create Panda Lip Controller: {exc}")
            return {"CANCELLED"}

        context.scene.panda_lip_settings.target_armature = controller
        self.report({"INFO"}, f"Created Panda Lip Controller: {controller.name}")
        return {"FINISHED"}


class PANDALIP_OT_import(bpy.types.Operator):
    bl_idname = "pandalip.import_animation"
    bl_label = "Import PandaLip"
    bl_description = "Import PandaLip v1 weights as AIUEO pose-bone X Location keys"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        global _IMPORT_IN_PROGRESS

        settings = context.scene.panda_lip_settings
        if not settings.filepath:
            self.report({"ERROR"}, "Select a .pandalip file")
            return {"CANCELLED"}
        if settings.target_armature is None:
            self.report({"ERROR"}, "Select a Target Armature")
            return {"CANCELLED"}
        if _IMPORT_IN_PROGRESS:
            self.report({"WARNING"}, "A Panda Lip import is already in progress")
            return {"CANCELLED"}

        _IMPORT_IN_PROGRESS = True
        try:
            result = import_pandalip_file(
                settings.filepath,
                settings.target_armature,
                context.scene,
                settings.start_frame,
                settings.quality,
                settings.custom_tolerance,
            )
        except PandaLipValidationError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        except Exception as exc:
            self.report({"ERROR"}, f"PandaLip import failed; no Action was kept: {exc}")
            return {"CANCELLED"}
        finally:
            _IMPORT_IN_PROGRESS = False

        self.report(
            {"INFO"},
            f"Imported Panda Lip animation: {result.sample_count} samples / "
            f"{len(CHANNELS)} channels; Action: {result.action_name}; "
            f"Keys: {result.keyframe_count}/{result.source_keyframe_count}",
        )
        return {"FINISHED"}
