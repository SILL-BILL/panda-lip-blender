"""Blender class registration kept separate from the lightweight entry point."""

from __future__ import annotations

import bpy
from bpy.props import PointerProperty

from .operators import (
    PANDALIP_OT_create_controller,
    PANDALIP_OT_create_drivers,
    PANDALIP_OT_import,
    PANDALIP_OT_remove_drivers,
    PANDALIP_OT_select_file,
)
from .panels import PANDALIP_PT_import
from .properties import PANDALIP_PG_settings

CLASSES = (
    PANDALIP_PG_settings,
    PANDALIP_OT_select_file,
    PANDALIP_OT_create_controller,
    PANDALIP_OT_create_drivers,
    PANDALIP_OT_remove_drivers,
    PANDALIP_OT_import,
    PANDALIP_PT_import,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.panda_lip_settings = PointerProperty(type=PANDALIP_PG_settings)


def unregister() -> None:
    del bpy.types.Scene.panda_lip_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
