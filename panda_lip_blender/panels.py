"""Panda Lip sidebar panel."""

from __future__ import annotations

import bpy

from .constants import CHANNELS, MAPPING_PROPERTY_NAMES
from .driver_mapping import mapping_status
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
        import_box.prop(settings, "filepath", text="File")
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

        driver_box = layout.box()
        driver_box.label(text="Driver Mapping")
        driver_box.prop(settings, "target_armature", text="Source")
        driver_box.prop(settings, "driver_target_mesh", text="Target Mesh")
        target = settings.driver_target_mesh
        shape_keys = (
            target.data.shape_keys
            if target is not None and target.type == "MESH"
            else None
        )
        for channel in CHANNELS:
            property_name = MAPPING_PROPERTY_NAMES[channel]
            row = driver_box.row(align=True)
            if shape_keys is not None:
                row.prop_search(
                    settings,
                    property_name,
                    shape_keys,
                    "key_blocks",
                    text=channel,
                )
            else:
                row.prop(settings, property_name, text=channel)
            status = mapping_status(
                settings.target_armature,
                target,
                channel,
                getattr(settings, property_name),
            )
            row.label(text=status.label, icon=status.icon)
        create_row = driver_box.row()
        create_row.enabled = (
            settings.target_armature is not None
            and target is not None
            and any(
                getattr(settings, MAPPING_PROPERTY_NAMES[channel])
                for channel in CHANNELS
            )
        )
        create_row.operator("pandalip.create_drivers", icon="DRIVER")
        driver_box.operator("pandalip.remove_drivers", icon="X")
