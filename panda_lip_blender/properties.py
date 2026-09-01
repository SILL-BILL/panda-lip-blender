"""Scene settings shown by the Panda Lip N-panel."""

from __future__ import annotations

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty


def _armature_poll(_settings: object, candidate: bpy.types.Object) -> bool:
    return candidate.type == "ARMATURE"


def _mesh_poll(_settings: object, candidate: bpy.types.Object) -> bool:
    return candidate.type == "MESH"


class PANDALIP_PG_settings(bpy.types.PropertyGroup):
    filepath: StringProperty(
        name="PandaLip File",
        description="PandaLip v1 JSON file to import",
        subtype="FILE_PATH",
        default="",
    )
    target_armature: PointerProperty(
        name="Target Armature",
        description="Armature containing the CTRL_Lip_A/I/U/E/O pose bones",
        type=bpy.types.Object,
        poll=_armature_poll,
    )
    start_frame: IntProperty(
        name="Start Frame",
        description="Frame that corresponds to PandaLip time 0.0 seconds",
        default=1,
    )
    quality: EnumProperty(
        name="Quality",
        description="Key Reduction quality; Original keeps every PandaLip sample",
        items=(
            ("ORIGINAL", "Original", "No reduction; keep every PandaLip sample"),
            ("HIGH", "High", "Quality priority; maximum error 0.0025"),
            ("MIDDLE", "Middle", "Balanced; maximum error 0.01"),
            ("LOW", "Low", "Reduction priority; maximum error 0.02"),
            ("CUSTOM", "Custom", "Use a custom maximum-error tolerance"),
        ),
        default="ORIGINAL",
    )
    custom_tolerance: FloatProperty(
        name="Tolerance",
        description="Maximum allowed difference from the Original curve at source sample times",
        default=0.01,
        min=0.0,
        max=1.0,
        precision=4,
    )
    driver_target_mesh: PointerProperty(
        name="Target Mesh",
        description="Mesh containing the Shape Keys driven by the Panda Lip Controller",
        type=bpy.types.Object,
        poll=_mesh_poll,
    )
    driver_shape_key_a: StringProperty(
        name="A Shape Key",
        description="Shape Key driven by CTRL_Lip_A; leave empty to skip",
        default="",
    )
    driver_shape_key_i: StringProperty(
        name="I Shape Key",
        description="Shape Key driven by CTRL_Lip_I; leave empty to skip",
        default="",
    )
    driver_shape_key_u: StringProperty(
        name="U Shape Key",
        description="Shape Key driven by CTRL_Lip_U; leave empty to skip",
        default="",
    )
    driver_shape_key_e: StringProperty(
        name="E Shape Key",
        description="Shape Key driven by CTRL_Lip_E; leave empty to skip",
        default="",
    )
    driver_shape_key_o: StringProperty(
        name="O Shape Key",
        description="Shape Key driven by CTRL_Lip_O; leave empty to skip",
        default="",
    )
