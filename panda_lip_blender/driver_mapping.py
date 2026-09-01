"""Create, recognize, and remove generic Panda Lip Shape Key drivers."""

from __future__ import annotations

from dataclasses import dataclass

import bpy

from .constants import (
    BONE_NAMES,
    CHANNELS,
    DRIVER_VARIABLE_PREFIX,
    MAPPING_PROPERTY_NAMES,
)
from .controller import controller_structure_error


class DriverMappingError(ValueError):
    """Raised when a Driver Mapping request cannot be applied safely."""


@dataclass(frozen=True, slots=True)
class DriverMappingResult:
    created: tuple[str, ...]
    reused: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DriverRemovalResult:
    removed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MappingStatus:
    code: str
    label: str
    icon: str


def settings_mappings(settings: bpy.types.PropertyGroup) -> dict[str, str]:
    """Read the five persisted mapping names from Scene settings."""

    return {
        channel: getattr(settings, MAPPING_PROPERTY_NAMES[channel])
        for channel in CHANNELS
    }


def _validate_source(source: bpy.types.Object | None) -> bpy.types.Object:
    if source is None:
        raise DriverMappingError("Select a Source Armature")
    error = controller_structure_error(source)
    if error is not None:
        raise DriverMappingError(f"Source Armature is not a valid Panda Lip Controller: {error}")
    return source


def _validate_target(target: bpy.types.Object | None) -> bpy.types.Key:
    if target is None:
        raise DriverMappingError("Select a Target Mesh")
    if target.type != "MESH":
        raise DriverMappingError("Target must be a Mesh Object")
    shape_keys = target.data.shape_keys
    if shape_keys is None or len(shape_keys.key_blocks) <= 1:
        raise DriverMappingError("Target Mesh must have at least one Shape Key besides Basis")
    return shape_keys


def _value_driver(
    shape_keys: bpy.types.Key,
    key_block: bpy.types.ShapeKey,
) -> bpy.types.FCurve | None:
    animation_data = shape_keys.animation_data
    if animation_data is None:
        return None
    data_path = key_block.path_from_id("value")
    return next(
        (
            fcurve
            for fcurve in animation_data.drivers
            if fcurve.data_path == data_path and fcurve.array_index == 0
        ),
        None,
    )


def _variable_name(channel: str) -> str:
    return f"{DRIVER_VARIABLE_PREFIX}{channel}"


def is_pandalip_driver(
    fcurve: bpy.types.FCurve,
    source: bpy.types.Object,
    channel: str,
) -> bool:
    """Return whether an F-Curve exactly matches Panda Lip's driver signature."""

    driver = fcurve.driver
    if driver.type != "SCRIPTED" or driver.use_self:
        return False
    if len(driver.variables) != 1:
        return False
    variable = driver.variables[0]
    expected_name = _variable_name(channel)
    if variable.name != expected_name or driver.expression != expected_name:
        return False
    if variable.type != "TRANSFORMS" or len(variable.targets) != 1:
        return False
    target = variable.targets[0]
    return (
        target.id is source
        and target.bone_target == BONE_NAMES[channel]
        and target.transform_type == "LOC_X"
        and target.transform_space == "LOCAL_SPACE"
    )


def _pandalip_driver_channel(
    fcurve: bpy.types.FCurve,
    source: bpy.types.Object,
) -> str | None:
    return next(
        (channel for channel in CHANNELS if is_pandalip_driver(fcurve, source, channel)),
        None,
    )


def _validate_mappings(
    shape_keys: bpy.types.Key,
    mappings: dict[str, str],
) -> tuple[tuple[str, bpy.types.ShapeKey], ...]:
    selected = [(channel, mappings.get(channel, "")) for channel in CHANNELS]
    selected = [(channel, name) for channel, name in selected if name]
    if not selected:
        raise DriverMappingError("Map at least one AIUEO channel to a Shape Key")

    names = [name for _channel, name in selected]
    if len(names) != len(set(names)):
        raise DriverMappingError("Each Shape Key can be mapped to only one AIUEO channel")

    basis = shape_keys.key_blocks[0]
    result: list[tuple[str, bpy.types.ShapeKey]] = []
    for channel, name in selected:
        key_block = shape_keys.key_blocks.get(name)
        if key_block is None:
            raise DriverMappingError(f'Shape Key "{name}" does not exist on the Target Mesh')
        if key_block.name == basis.name:
            raise DriverMappingError("Basis cannot be used as a Driver Mapping target")
        result.append((channel, key_block))
    return tuple(result)


def _configure_pandalip_driver(
    fcurve: bpy.types.FCurve,
    source: bpy.types.Object,
    channel: str,
) -> None:
    driver = fcurve.driver
    driver.type = "SCRIPTED"
    driver.use_self = False
    while driver.variables:
        driver.variables.remove(driver.variables[0])
    variable = driver.variables.new()
    variable.name = _variable_name(channel)
    variable.type = "TRANSFORMS"
    target = variable.targets[0]
    target.id = source
    target.bone_target = BONE_NAMES[channel]
    target.transform_type = "LOC_X"
    target.transform_space = "LOCAL_SPACE"
    driver.expression = variable.name


def create_pandalip_drivers(
    source: bpy.types.Object | None,
    target: bpy.types.Object | None,
    mappings: dict[str, str],
) -> DriverMappingResult:
    """Create all requested drivers atomically, reusing exact matches."""

    valid_source = _validate_source(source)
    shape_keys = _validate_target(target)
    selected = _validate_mappings(shape_keys, mappings)

    reused: list[str] = []
    pending: list[tuple[str, bpy.types.ShapeKey]] = []
    for channel, key_block in selected:
        existing = _value_driver(shape_keys, key_block)
        if existing is None:
            pending.append((channel, key_block))
        elif is_pandalip_driver(existing, valid_source, channel):
            reused.append(key_block.name)
        else:
            raise DriverMappingError(
                f'Shape Key "{key_block.name}" already has a driver. '
                "Panda Lip did not modify it."
            )

    created: list[bpy.types.ShapeKey] = []
    try:
        for channel, key_block in pending:
            fcurve = key_block.driver_add("value")
            created.append(key_block)
            _configure_pandalip_driver(fcurve, valid_source, channel)
    except Exception as exc:
        for key_block in reversed(created):
            key_block.driver_remove("value")
        raise DriverMappingError(
            f"Driver creation failed; Panda Lip rolled back its changes: {exc}"
        ) from exc

    return DriverMappingResult(
        created=tuple(key_block.name for key_block in created),
        reused=tuple(reused),
    )


def remove_pandalip_drivers(
    source: bpy.types.Object | None,
    target: bpy.types.Object | None,
) -> DriverRemovalResult:
    """Remove only exact Panda Lip signatures for the selected Source/Target pair."""

    valid_source = _validate_source(source)
    shape_keys = _validate_target(target)
    removed: list[str] = []
    for key_block in tuple(shape_keys.key_blocks)[1:]:
        fcurve = _value_driver(shape_keys, key_block)
        if fcurve is None or _pandalip_driver_channel(fcurve, valid_source) is None:
            continue
        if key_block.driver_remove("value"):
            removed.append(key_block.name)
    return DriverRemovalResult(removed=tuple(removed))


def mapping_status(
    source: bpy.types.Object | None,
    target: bpy.types.Object | None,
    channel: str,
    shape_key_name: str,
) -> MappingStatus:
    """Return a compact state used by the N-panel."""

    if not shape_key_name:
        return MappingStatus("NOT_SET", "Not Set", "RADIOBUT_OFF")
    try:
        valid_source = _validate_source(source)
        shape_keys = _validate_target(target)
    except DriverMappingError:
        return MappingStatus("INVALID", "Invalid", "ERROR")
    key_block = shape_keys.key_blocks.get(shape_key_name)
    if key_block is None or key_block.name == shape_keys.key_blocks[0].name:
        return MappingStatus("INVALID", "Invalid", "ERROR")
    fcurve = _value_driver(shape_keys, key_block)
    if fcurve is None:
        return MappingStatus("READY", "Ready", "CHECKMARK")
    if is_pandalip_driver(fcurve, valid_source, channel):
        return MappingStatus("CONNECTED", "Connected", "LINKED")
    return MappingStatus("CONFLICT", "Conflict", "ERROR")
