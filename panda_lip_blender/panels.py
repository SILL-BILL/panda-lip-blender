"""Panda Lip sidebar panel."""

from __future__ import annotations

import bpy

from .operators import import_in_progress


class PANDALIP_PT_import(bpy.types.Panel):
    bl_label = "Panda Lip Import"
    bl_idname = "PANDALIP_PT_import"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Panda Lip"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        settings = context.scene.panda_lip_settings

        row = layout.row(align=True)
        row.prop(settings, "filepath", text="File")
        row.operator("pandalip.select_file", text="", icon="FILE_FOLDER")
        layout.prop(settings, "target_armature")
        layout.prop(settings, "start_frame")
        layout.separator()
        layout.label(text="Key Reduction")
        layout.prop(settings, "quality", text="Quality")
        if settings.quality == "CUSTOM":
            layout.prop(settings, "custom_tolerance")
        import_row = layout.row()
        import_row.enabled = bool(settings.filepath) and settings.target_armature is not None
        import_row.enabled = import_row.enabled and not import_in_progress()
        import_row.operator("pandalip.import_animation", icon="ACTION")
