from __future__ import annotations

from copy import deepcopy
from typing import Any


def valid_document() -> dict[str, Any]:
    return {
        "format": "PandaLip",
        "version": 1,
        "time_unit": "seconds",
        "audio": {"duration": 0.02, "sample_rate": 48_000, "channel_count": 1},
        "analysis": {
            "algorithm": "lpc-formant-v1",
            "mode": "speech",
            "profile": "japanese_neutral_v1",
            "profile_version": 1,
            "sample_rate": 16_000,
            "frame_seconds": 0.03,
            "hop_seconds": 0.01,
            "sensitivity": 0.5,
            "smoothing_ms": 25.0,
        },
        "channels": ["A", "I", "U", "E", "O"],
        "samples": [
            {"time": 0.0, "A": 0.0, "I": 0.0, "U": 0.0, "E": 0.0, "O": 0.0},
            {"time": 0.01, "A": 1.0, "I": 0.5, "U": 0.25, "E": 0.0, "O": 1.0},
            {"time": 0.02, "A": 0.0, "I": 1.0, "U": 0.5, "E": 1.0, "O": 0.0},
        ],
    }


def copy_document() -> dict[str, Any]:
    return deepcopy(valid_document())
