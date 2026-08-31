"""Panda Lip Blender Extension entry point."""

from __future__ import annotations


def register() -> None:
    # Keep bpy imports lazy so the format and timing modules remain testable with
    # a normal Python interpreter.
    from .registration import register as register_extension

    register_extension()


def unregister() -> None:
    from .registration import unregister as unregister_extension

    unregister_extension()
