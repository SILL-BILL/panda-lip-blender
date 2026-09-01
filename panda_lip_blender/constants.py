"""Shared Panda Lip controller conventions."""

from __future__ import annotations

CHANNELS = ("A", "I", "U", "E", "O")
BONE_NAMES = {channel: f"CTRL_Lip_{channel}" for channel in CHANNELS}
ROOT_BONE_NAME = "PandaLip_Root"
CONTROLLER_OBJECT_NAME = "PandaLip"
CONTROLLER_COLLECTION_NAME = "PandaLip"
MENU_WIDGET_NAME = "cs_PL_Menu"
SWITCH_WIDGET_NAME = "cs_PL_Switch"
CONTROLLER_VERSION_KEY = "pandalip_controller_version"
CONTROLLER_VERSION = 1
ACTION_PREFIX = "PandaLip_"
ACTION_GROUP = "Panda Lip"
