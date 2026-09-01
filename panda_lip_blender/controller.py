"""Create and recognize the standard Panda Lip controller armature."""

from __future__ import annotations

import math
from collections.abc import Iterable

import bpy

from .constants import (
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

_CHANNEL_ROWS = {
    "A": 0.50,
    "I": 0.25,
    "U": 0.00,
    "E": -0.25,
    "O": -0.50,
}
_EPSILON = 1.0e-6


def _has_standard_limit(pose_bone: bpy.types.PoseBone) -> bool:
    for constraint in pose_bone.constraints:
        if constraint.type != "LIMIT_LOCATION" or constraint.owner_space != "LOCAL":
            continue
        enabled = (
            constraint.use_min_x,
            constraint.use_max_x,
            constraint.use_min_y,
            constraint.use_max_y,
            constraint.use_min_z,
            constraint.use_max_z,
        )
        values = (
            constraint.min_x,
            constraint.max_x,
            constraint.min_y,
            constraint.max_y,
            constraint.min_z,
            constraint.max_z,
        )
        if constraint.use_transform_limit and all(enabled) and all(
            math.isclose(value, expected, abs_tol=_EPSILON)
            for value, expected in zip(values, (0.0, 1.0, 0.0, 0.0, 0.0, 0.0), strict=True)
        ):
            return True
    return False


def controller_structure_error(candidate: bpy.types.Object | None) -> str | None:
    """Return why an object is not a usable standard controller, or ``None``."""

    if candidate is None or candidate.type != "ARMATURE":
        return "object is not an Armature"
    root = candidate.data.bones.get(ROOT_BONE_NAME)
    if root is None or root.parent is not None:
        return f"missing unparented {ROOT_BONE_NAME}"
    for channel in CHANNELS:
        bone_name = BONE_NAMES[channel]
        bone = candidate.data.bones.get(bone_name)
        if bone is None:
            return f"missing {bone_name}"
        if bone.parent is None or bone.parent.name != ROOT_BONE_NAME:
            return f"{bone_name} is not parented to {ROOT_BONE_NAME}"
        pose_bone = candidate.pose.bones.get(bone_name)
        if pose_bone is None or not _has_standard_limit(pose_bone):
            return f"{bone_name} has no standard Local Limit Location"
    return None


def find_existing_controller(scene: bpy.types.Scene) -> bpy.types.Object | None:
    """Find a structurally valid controller in the current scene."""

    candidates = [obj for obj in scene.objects if controller_structure_error(obj) is None]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda obj: (obj.name != CONTROLLER_OBJECT_NAME, obj.name.casefold()),
    )


def _append_segment(
    vertices: list[tuple[float, float, float]],
    edges: list[tuple[int, int]],
    start: tuple[float, float],
    end: tuple[float, float],
) -> None:
    offset = len(vertices)
    vertices.extend(((start[0], start[1], 0.0), (end[0], end[1], 0.0)))
    edges.append((offset, offset + 1))


def _letter_segments(letter: str) -> Iterable[tuple[tuple[float, float], tuple[float, float]]]:
    left, right = -0.38, 0.38
    bottom, middle, top = -0.42, 0.0, 0.42
    if letter == "A":
        return (
            ((left, bottom), (0.0, top)),
            ((0.0, top), (right, bottom)),
            ((-0.20, middle), (0.20, middle)),
        )
    if letter == "I":
        return (
            ((left, top), (right, top)),
            ((0.0, top), (0.0, bottom)),
            ((left, bottom), (right, bottom)),
        )
    if letter == "U":
        return (
            ((left, top), (left, bottom)),
            ((left, bottom), (right, bottom)),
            ((right, bottom), (right, top)),
        )
    if letter == "E":
        return (
            ((left, top), (left, bottom)),
            ((left, top), (right, top)),
            ((left, middle), (0.25, middle)),
            ((left, bottom), (right, bottom)),
        )
    return (
        ((left, top), (right, top)),
        ((right, top), (right, bottom)),
        ((right, bottom), (left, bottom)),
        ((left, bottom), (left, top)),
    )


def _create_menu_widget(collection: bpy.types.Collection) -> bpy.types.Object:
    vertices: list[tuple[float, float, float]] = []
    edges: list[tuple[int, int]] = []
    _append_segment(vertices, edges, (0.0, -5.0), (0.0, 5.0))
    for channel, row in zip(CHANNELS, (5.0, 2.5, 0.0, -2.5, -5.0), strict=True):
        _append_segment(vertices, edges, (2.5, row), (12.5, row))
        for start, end in _letter_segments(channel):
            _append_segment(
                vertices,
                edges,
                (14.0 + start[0], row + start[1]),
                (14.0 + end[0], row + end[1]),
            )
    mesh = bpy.data.meshes.new(MENU_WIDGET_NAME)
    mesh.from_pydata(vertices, edges, [])
    mesh.update()
    widget = bpy.data.objects.new(MENU_WIDGET_NAME, mesh)
    collection.objects.link(widget)
    return widget


def _create_switch_widget(collection: bpy.types.Collection) -> bpy.types.Object:
    extent = 0.18
    vertices = [
        (x, y, z)
        for x in (-extent, extent)
        for y in (-extent, extent)
        for z in (-extent * 0.29, extent * 0.29)
    ]
    edges = (
        (0, 1),
        (0, 2),
        (0, 4),
        (1, 3),
        (1, 5),
        (2, 3),
        (2, 6),
        (3, 7),
        (4, 5),
        (4, 6),
        (5, 7),
        (6, 7),
    )
    faces = (
        (0, 1, 3, 2),
        (4, 6, 7, 5),
        (0, 4, 5, 1),
        (2, 3, 7, 6),
        (0, 2, 6, 4),
        (1, 5, 7, 3),
    )
    mesh = bpy.data.meshes.new(SWITCH_WIDGET_NAME)
    mesh.from_pydata(vertices, edges, faces)
    mesh.update()
    widget = bpy.data.objects.new(SWITCH_WIDGET_NAME, mesh)
    collection.objects.link(widget)
    return widget


def _configure_widget(widget: bpy.types.Object) -> None:
    widget[CONTROLLER_VERSION_KEY] = CONTROLLER_VERSION
    widget.hide_render = True
    widget.hide_select = True
    widget.hide_viewport = True
    widget.display_type = "WIRE"
    widget.hide_set(True)


def _remove_created_data(
    collection: bpy.types.Collection | None,
    objects: Iterable[bpy.types.Object],
    armature: bpy.types.Armature | None,
    meshes: Iterable[bpy.types.Mesh],
) -> None:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
    for obj in objects:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    if armature is not None and armature.name in bpy.data.armatures:
        bpy.data.armatures.remove(armature)
    for mesh in meshes:
        if mesh.name in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)
    if collection is not None and collection.name in bpy.data.collections:
        bpy.data.collections.remove(collection)


def create_controller(context: bpy.types.Context) -> bpy.types.Object:
    """Create one independent controller at the 3D cursor."""

    collection: bpy.types.Collection | None = None
    armature: bpy.types.Armature | None = None
    created_objects: list[bpy.types.Object] = []
    created_meshes: list[bpy.types.Mesh] = []
    try:
        collection = bpy.data.collections.new(CONTROLLER_COLLECTION_NAME)
        collection[CONTROLLER_VERSION_KEY] = CONTROLLER_VERSION
        context.scene.collection.children.link(collection)

        armature = bpy.data.armatures.new(CONTROLLER_OBJECT_NAME)
        armature.display_type = "OCTAHEDRAL"
        controller = bpy.data.objects.new(CONTROLLER_OBJECT_NAME, armature)
        created_objects.append(controller)
        collection.objects.link(controller)
        controller.location = context.scene.cursor.location
        controller.show_in_front = True
        controller[CONTROLLER_VERSION_KEY] = CONTROLLER_VERSION

        for obj in context.selected_objects:
            obj.select_set(False)
        controller.select_set(True)
        context.view_layer.objects.active = controller
        bpy.ops.object.mode_set(mode="EDIT")

        root = armature.edit_bones.new(ROOT_BONE_NAME)
        root.head = (0.0, 0.0, 0.0)
        root.tail = (0.0, 0.0, 0.10)
        root.use_deform = False
        for channel in CHANNELS:
            bone = armature.edit_bones.new(BONE_NAMES[channel])
            bone.head = (0.25, 0.0, _CHANNEL_ROWS[channel])
            bone.tail = (0.25, 0.0, _CHANNEL_ROWS[channel] + 0.50)
            bone.parent = root
            bone.use_connect = False
            bone.use_deform = False
        bpy.ops.object.mode_set(mode="OBJECT")

        menu_widget = _create_menu_widget(collection)
        switch_widget = _create_switch_widget(collection)
        created_objects.extend((menu_widget, switch_widget))
        created_meshes.extend((menu_widget.data, switch_widget.data))
        _configure_widget(menu_widget)
        _configure_widget(switch_widget)

        root_pose = controller.pose.bones[ROOT_BONE_NAME]
        root_pose.custom_shape = menu_widget
        for channel in CHANNELS:
            pose_bone = controller.pose.bones[BONE_NAMES[channel]]
            pose_bone.custom_shape = switch_widget
            pose_bone.lock_location = (False, True, True)
            pose_bone.lock_rotation = (True, True, True)
            pose_bone.lock_rotations_4d = True
            pose_bone.lock_rotation_w = True
            pose_bone.lock_scale = (True, True, True)
            limit = pose_bone.constraints.new("LIMIT_LOCATION")
            limit.name = "Panda Lip 0..1"
            limit.owner_space = "LOCAL"
            limit.use_min_x = True
            limit.use_max_x = True
            limit.min_x = 0.0
            limit.max_x = 1.0
            limit.use_min_y = True
            limit.use_max_y = True
            limit.min_y = 0.0
            limit.max_y = 0.0
            limit.use_min_z = True
            limit.use_max_z = True
            limit.min_z = 0.0
            limit.max_z = 0.0
            limit.use_transform_limit = True

        controller.select_set(True)
        context.view_layer.objects.active = controller
        return controller
    except Exception:
        _remove_created_data(collection, created_objects, armature, created_meshes)
        raise
