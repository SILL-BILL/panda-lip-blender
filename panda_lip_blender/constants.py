"""Shared Panda Lip controller conventions."""

from __future__ import annotations

CHANNELS = ("A", "I", "U", "E", "O")
BONE_NAMES = {channel: f"CTRL_Lip_{channel}" for channel in CHANNELS}
ACTION_PREFIX = "PandaLip_"
ACTION_GROUP = "Panda Lip"
