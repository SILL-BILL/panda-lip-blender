"""Maximum-error-bounded simplification for LINEAR animation curves."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

ERROR_EPSILON = 1e-12
REDUCTION_MODES = ("ORIGINAL", "HIGH", "MIDDLE", "LOW", "CUSTOM")
PRESET_TOLERANCES = {
    "HIGH": 0.0025,
    "MIDDLE": 0.01,
    "LOW": 0.02,
}


@dataclass(frozen=True, slots=True)
class CurveErrorMetrics:
    mean_absolute_error: float
    rms_error: float
    max_absolute_error: float
    peak_max_error: float
    peak_key_retention: float
    peak_count: int
    zero_mean_absolute_error: float
    zero_max_absolute_error: float
    zero_sample_count: int


def resolve_tolerance(mode: str, custom_tolerance: float) -> float | None:
    """Resolve a UI quality mode to its maximum absolute-error tolerance."""

    if mode == "ORIGINAL":
        return None
    if mode in PRESET_TOLERANCES:
        return PRESET_TOLERANCES[mode]
    if mode != "CUSTOM":
        raise ValueError(f"Unknown Key Reduction mode: {mode}")
    if not math.isfinite(custom_tolerance) or not 0.0 <= custom_tolerance <= 1.0:
        raise ValueError("Custom Tolerance must be finite and within 0..1")
    return custom_tolerance


def simplify_indices(
    times: Sequence[float], values: Sequence[float], tolerance: float
) -> tuple[int, ...]:
    """Return sample indices for an error-bounded piecewise-linear curve.

    This is an RDP-style top-down simplifier using vertical interpolation error
    instead of perpendicular geometric distance. A segment is accepted only
    when every original sample within it differs from the segment's LINEAR
    interpolation by no more than ``tolerance``.
    """

    if len(times) != len(values):
        raise ValueError("times and values must have the same length")
    if not times:
        raise ValueError("a curve must contain at least one sample")
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("tolerance must be finite and non-negative")

    previous_time = -math.inf
    for index, (time_value, curve_value) in enumerate(zip(times, values, strict=True)):
        if not math.isfinite(time_value) or time_value <= previous_time:
            raise ValueError("sample times must be finite and strictly increasing")
        if not math.isfinite(curve_value):
            raise ValueError(f"curve value at index {index} must be finite")
        previous_time = time_value

    sample_count = len(times)
    if sample_count == 1:
        return (0,)

    keep = bytearray(sample_count)
    keep[0] = 1
    keep[-1] = 1

    # Pre-anchor only sharp local features whose error against their immediate
    # neighbors already exceeds tolerance. These points cannot be safely
    # represented by that local span, and anchoring them avoids RDP's quadratic
    # edge-splitting case on rapid 0/1 alternation. Smooth minor extrema remain
    # eligible for normal error-bounded reduction.
    anchors = [0]
    for index in range(1, sample_count - 1):
        time_span = times[index + 1] - times[index - 1]
        ratio = (times[index] - times[index - 1]) / time_span
        interpolated = values[index - 1] + (values[index + 1] - values[index - 1]) * ratio
        if abs(values[index] - interpolated) > tolerance + ERROR_EPSILON:
            keep[index] = 1
            anchors.append(index)
    anchors.append(sample_count - 1)
    segments = list(zip(anchors, anchors[1:]))

    while segments:
        first, last = segments.pop()
        if last <= first + 1:
            continue
        time_span = times[last] - times[first]
        value_start = values[first]
        value_delta = values[last] - value_start
        maximum_error = -1.0
        maximum_index = -1
        for index in range(first + 1, last):
            ratio = (times[index] - times[first]) / time_span
            interpolated = value_start + value_delta * ratio
            error = abs(values[index] - interpolated)
            if error > maximum_error:
                maximum_error = error
                maximum_index = index
        if maximum_error > tolerance + ERROR_EPSILON:
            keep[maximum_index] = 1
            segments.append((maximum_index, last))
            segments.append((first, maximum_index))

    return tuple(index for index, is_kept in enumerate(keep) if is_kept)


def reconstruct_values(
    times: Sequence[float], values: Sequence[float], kept_indices: Sequence[int]
) -> tuple[float, ...]:
    """Evaluate a reduced LINEAR curve at every original sample time."""

    if len(times) != len(values):
        raise ValueError("times and values must have the same length")
    if not kept_indices:
        raise ValueError("kept_indices must not be empty")
    if kept_indices[0] != 0 or kept_indices[-1] != len(times) - 1:
        raise ValueError("the first and last samples must be retained")

    reconstructed = [0.0] * len(times)
    if len(times) == 1:
        reconstructed[0] = float(values[0])
        return tuple(reconstructed)

    for first, last in zip(kept_indices, kept_indices[1:]):
        if last <= first:
            raise ValueError("kept_indices must be strictly increasing")
        time_span = times[last] - times[first]
        value_start = values[first]
        value_delta = values[last] - value_start
        for index in range(first, last + 1):
            ratio = (times[index] - times[first]) / time_span
            reconstructed[index] = value_start + value_delta * ratio
    return tuple(reconstructed)


def local_peak_indices(values: Sequence[float]) -> tuple[int, ...]:
    """Return strict local maxima, including a single edge of flat plateaus."""

    peaks: list[int] = []
    for index in range(1, len(values) - 1):
        left = values[index - 1]
        center = values[index]
        right = values[index + 1]
        if (center > left and center >= right) or (center >= left and center > right):
            peaks.append(index)
    return tuple(peaks)


def measure_error(
    reference: Sequence[float],
    reconstructed: Sequence[float],
    kept_indices: Sequence[int],
    *,
    zero_epsilon: float = 1e-12,
) -> CurveErrorMetrics:
    """Measure reference-sample errors and exact local-peak key retention."""

    if len(reference) != len(reconstructed) or not reference:
        raise ValueError("reference and reconstructed curves must be non-empty and equal length")
    errors = [abs(original - reduced) for original, reduced in zip(reference, reconstructed, strict=True)]
    mean_absolute_error = sum(errors) / len(errors)
    rms_error = math.sqrt(sum(error * error for error in errors) / len(errors))
    max_absolute_error = max(errors)

    peaks = local_peak_indices(reference)
    kept = set(kept_indices)
    retained_peaks = sum(index in kept for index in peaks)
    peak_errors = [errors[index] for index in peaks]
    zero_errors = [
        error for original, error in zip(reference, errors, strict=True) if abs(original) <= zero_epsilon
    ]
    return CurveErrorMetrics(
        mean_absolute_error=mean_absolute_error,
        rms_error=rms_error,
        max_absolute_error=max_absolute_error,
        peak_max_error=max(peak_errors, default=0.0),
        peak_key_retention=1.0 if not peaks else retained_peaks / len(peaks),
        peak_count=len(peaks),
        zero_mean_absolute_error=0.0 if not zero_errors else sum(zero_errors) / len(zero_errors),
        zero_max_absolute_error=max(zero_errors, default=0.0),
        zero_sample_count=len(zero_errors),
    )
