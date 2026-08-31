"""Dependency-free validation for the formal PandaLip v1 format."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import CHANNELS


class PandaLipValidationError(ValueError):
    """Raised when a file is not a valid PandaLip v1 document."""


@dataclass(frozen=True, slots=True)
class PandaLipSample:
    time: float
    weights: tuple[float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class PandaLipData:
    samples: tuple[PandaLipSample, ...]
    document: dict[str, Any]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _number(
    value: Any,
    path: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    exclusive_minimum: float | None = None,
) -> float:
    if not _is_number(value):
        raise PandaLipValidationError(f"{path} must be a number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise PandaLipValidationError(f"{path} must be a finite number") from exc
    if not math.isfinite(result):
        raise PandaLipValidationError(f"{path} must be finite")
    if minimum is not None and result < minimum:
        raise PandaLipValidationError(f"{path} must be at least {minimum:g}")
    if maximum is not None and result > maximum:
        raise PandaLipValidationError(f"{path} must be at most {maximum:g}")
    if exclusive_minimum is not None and result <= exclusive_minimum:
        raise PandaLipValidationError(f"{path} must be greater than {exclusive_minimum:g}")
    return result


def _integer(value: Any, path: str, *, minimum: int | None = None) -> int:
    number = _number(value, path)
    if not number.is_integer():
        raise PandaLipValidationError(f"{path} must be an integer")
    result = int(number)
    if minimum is not None and result < minimum:
        raise PandaLipValidationError(f"{path} must be at least {minimum}")
    return result


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PandaLipValidationError(f"{path} must be an object")
    return value


def _require(mapping: dict[str, Any], fields: set[str], path: str) -> None:
    missing = sorted(fields.difference(mapping))
    if missing:
        prefix = f"{path}." if path else ""
        raise PandaLipValidationError(
            f"Missing required field(s): {', '.join(prefix + field for field in missing)}"
        )


def _nonempty_string(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value:
        raise PandaLipValidationError(f"{path} must be a non-empty string")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard numeric constant {value}")


def validate_document(document: Any) -> PandaLipData:
    """Validate and normalize a decoded PandaLip v1 JSON document.

    This mirrors ``pandalip-v1.schema.json`` and the analyzer's additional
    strictly-increasing-time rule. Unknown fields are deliberately retained and
    ignored for forward-compatible v1 metadata.
    """

    root = _object(document, "PandaLip root")
    _require(
        root,
        {"format", "version", "time_unit", "audio", "analysis", "channels", "samples"},
        "",
    )

    if root["format"] != "PandaLip":
        raise PandaLipValidationError("format must be 'PandaLip'")
    if isinstance(root["version"], bool) or root["version"] != 1:
        raise PandaLipValidationError("Only PandaLip version 1 is supported")
    if root["time_unit"] != "seconds":
        raise PandaLipValidationError("PandaLip v1 time_unit must be 'seconds'")

    audio = _object(root["audio"], "audio")
    _require(audio, {"duration", "sample_rate", "channel_count"}, "audio")
    _number(audio["duration"], "audio.duration", minimum=0.0)
    _integer(audio["sample_rate"], "audio.sample_rate", minimum=1)
    _integer(audio["channel_count"], "audio.channel_count", minimum=1)

    analysis = _object(root["analysis"], "analysis")
    analysis_fields = {
        "algorithm",
        "mode",
        "profile",
        "profile_version",
        "sample_rate",
        "frame_seconds",
        "hop_seconds",
        "sensitivity",
        "smoothing_ms",
    }
    _require(analysis, analysis_fields, "analysis")
    _nonempty_string(analysis["algorithm"], "analysis.algorithm")
    if not isinstance(analysis["mode"], str) or analysis["mode"] not in {"speech", "singing"}:
        raise PandaLipValidationError("analysis.mode must be 'speech' or 'singing'")
    _nonempty_string(analysis["profile"], "analysis.profile")
    _integer(analysis["profile_version"], "analysis.profile_version", minimum=1)
    _integer(analysis["sample_rate"], "analysis.sample_rate", minimum=1)
    _number(analysis["frame_seconds"], "analysis.frame_seconds", exclusive_minimum=0.0)
    _number(analysis["hop_seconds"], "analysis.hop_seconds", exclusive_minimum=0.0)
    _number(analysis["sensitivity"], "analysis.sensitivity", minimum=0.0, maximum=1.0)
    _number(analysis["smoothing_ms"], "analysis.smoothing_ms", minimum=0.0)

    if root["channels"] != list(CHANNELS):
        raise PandaLipValidationError("channels must be exactly ['A', 'I', 'U', 'E', 'O']")

    raw_samples = root["samples"]
    if not isinstance(raw_samples, list) or not raw_samples:
        raise PandaLipValidationError("samples must be a non-empty array")

    samples: list[PandaLipSample] = []
    previous_time = -1.0
    required_sample_fields = {"time", *CHANNELS}
    for index, raw_sample in enumerate(raw_samples):
        path = f"samples[{index}]"
        sample = _object(raw_sample, path)
        _require(sample, required_sample_fields, path)
        time = _number(sample["time"], f"{path}.time", minimum=0.0)
        if time <= previous_time:
            raise PandaLipValidationError("Sample times must be finite and strictly increasing")
        weights = tuple(
            _number(sample[channel], f"{path}.{channel}", minimum=0.0, maximum=1.0)
            for channel in CHANNELS
        )
        samples.append(PandaLipSample(time=time, weights=weights))  # type: ignore[arg-type]
        previous_time = time

    return PandaLipData(samples=tuple(samples), document=root)


def load_pandalip(filepath: str | Path) -> PandaLipData:
    """Read a UTF-8 ``.pandalip`` file and validate it before Blender changes."""

    path = Path(filepath)
    if path.suffix.lower() != ".pandalip":
        raise PandaLipValidationError("The selected file must use the .pandalip extension")
    if not path.exists():
        raise PandaLipValidationError(f"PandaLip file does not exist: {path}")
    if not path.is_file():
        raise PandaLipValidationError(f"PandaLip path is not a file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PandaLipValidationError(f"Could not read PandaLip file: {exc}") from exc
    try:
        document = json.loads(text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise PandaLipValidationError(
            f"Invalid PandaLip JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except ValueError as exc:
        raise PandaLipValidationError(f"Invalid PandaLip JSON: {exc}") from exc
    return validate_document(document)
