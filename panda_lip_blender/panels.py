"""Panda Lip sidebar panel."""

from __future__ import annotations

import bpy

from .operators import import_in_progress


class PANDALIP_PT_import(bpy.types.Panel):
    bl_label = "Panda Lip"
    bl_idname = "PANDALIP_PT_import"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Panda Lip"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        settings = context.scene.panda_lip_settings

        controller_box = layout.box()
        controller_box.label(text="Controller")
        controller_box.operator("pandalip.create_controller", icon="ARMATURE_DATA")

        import_box = layout.box()
        import_box.label(text="Import")
        row = import_box.row(align=True)
        row.prop(settings, "filepath", text="File")
        row.operator("pandalip.select_file", text="", icon="FILE_FOLDER")
        import_box.prop(settings, "target_armature")
        import_box.prop(settings, "start_frame")
        import_box.separator()
        import_box.label(text="Key Reduction")
        import_box.prop(settings, "quality", text="Quality")
        if settings.quality == "CUSTOM":
            import_box.prop(settings, "custom_tolerance")
        import_row = import_box.row()
        import_row.enabled = bool(settings.filepath) and settings.target_armature is not None
        import_row.enabled = import_row.enabled and not import_in_progress()
        import_row.operator("pandalip.import_animation", icon="ACTION")
