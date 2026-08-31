"""Reproducible feature-window selection for Phase B.5 A/B evaluation."""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class FeatureWindow:
    key: str
    center_index: int
    start_index: int
    end_index: int
    center_time: float
    start_time: float
    end_time: float
    activity: float
    dominant_channel: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _quantile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return float(ordered[index])


def _true_runs(mask: Sequence[bool]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, state in enumerate(mask):
        if state and start is None:
            start = index
        elif not state and start is not None:
            runs.append((start, index - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def _validate(
    times: Sequence[float],
    weights: Sequence[Sequence[float]],
    channels: Sequence[str],
) -> float:
    if not times or len(times) != len(weights):
        raise ValueError("times and weights must be non-empty and equal length")
    if not channels:
        raise ValueError("channels must not be empty")
    previous = -math.inf
    for index, (time_value, row) in enumerate(zip(times, weights, strict=True)):
        if not math.isfinite(time_value) or time_value <= previous:
            raise ValueError("times must be finite and strictly increasing")
        if len(row) != len(channels) or not all(math.isfinite(value) for value in row):
            raise ValueError(f"invalid weight row at index {index}")
        previous = time_value
    if len(times) == 1:
        return 0.01
    return statistics.median(
        current - previous
        for previous, current in zip(times[:-1], times[1:], strict=True)
    )


def select_feature_windows(
    times: Sequence[float],
    weights: Sequence[Sequence[float]],
    channels: Sequence[str],
) -> dict[str, FeatureWindow]:
    """Select deterministic lip-sync feature windows from real or synthetic data."""

    hop = _validate(times, weights, channels)
    sample_count = len(times)
    activity = [max(row) for row in weights]
    dominant = [max(range(len(channels)), key=lambda item: row[item]) for row in weights]

    def radius(seconds: float) -> int:
        return max(1, round(seconds / hop))

    def window(
        key: str,
        center: int,
        before_seconds: float,
        after_seconds: float,
        reason: str,
        *,
        explicit_start: int | None = None,
        explicit_end: int | None = None,
    ) -> FeatureWindow:
        start = max(0, center - radius(before_seconds)) if explicit_start is None else explicit_start
        end = (
            min(sample_count - 1, center + radius(after_seconds))
            if explicit_end is None
            else explicit_end
        )
        return FeatureWindow(
            key=key,
            center_index=center,
            start_index=start,
            end_index=end,
            center_time=float(times[center]),
            start_time=float(times[start]),
            end_time=float(times[end]),
            activity=float(activity[center]),
            dominant_channel=str(channels[dominant[center]]),
            reason=reason,
        )

    local_peaks = [
        index
        for index in range(1, sample_count - 1)
        if activity[index] > activity[index - 1] and activity[index] >= activity[index + 1]
    ]
    if not local_peaks:
        local_peaks = [max(range(sample_count), key=activity.__getitem__)]

    large_index = max(range(sample_count), key=activity.__getitem__)

    small_candidates: list[tuple[float, float, int]] = []
    neighborhood = radius(0.12)
    for index in local_peaks:
        if not 0.04 <= activity[index] <= 0.15:
            continue
        left_floor = min(activity[max(0, index - neighborhood) : index + 1])
        right_floor = min(activity[index : min(sample_count, index + neighborhood + 1)])
        prominence = activity[index] - max(left_floor, right_floor)
        if prominence >= 0.005:
            small_candidates.append((prominence, -abs(activity[index] - 0.1), index))
    small_index = (
        max(small_candidates)[2]
        if small_candidates
        else min(local_peaks, key=lambda item: abs(activity[item] - 0.1))
    )

    short_candidates: list[tuple[float, float, int, int, int, int]] = []
    high_cutoff = max(0.1, _quantile(activity, 0.75))
    for channel_index in range(len(channels)):
        curve = [row[channel_index] for row in weights]
        for index in range(1, sample_count - 1):
            if curve[index] <= curve[index - 1] or curve[index] < curve[index + 1]:
                continue
            if curve[index] < high_cutoff:
                continue
            half_height = curve[index] * 0.5
            left = index
            right = index
            while left > 0 and curve[left - 1] >= half_height:
                left -= 1
            while right + 1 < sample_count and curve[right + 1] >= half_height:
                right += 1
            width_seconds = (right - left + 1) * hop
            sharpness = curve[index] / max(width_seconds, hop)
            short_candidates.append((sharpness, curve[index], index, channel_index, left, right))
    if short_candidates:
        _, peak_value, short_index, short_channel, short_left, short_right = max(short_candidates)
        short_reason = (
            f"sharpest >=75th-percentile channel peak: {channels[short_channel]}="
            f"{peak_value:.6f}, half-height width={(short_right - short_left + 1) * hop:.3f}s"
        )
    else:
        short_index = large_index
        short_reason = "fallback to the largest opening; no qualifying short peak"

    rapid_radius = radius(0.15)
    active_floor = 0.05
    best_rapid: tuple[int, int, float, int] | None = None
    for center in range(rapid_radius, sample_count - rapid_radius):
        start = center - rapid_radius
        end = center + rapid_radius
        changes = sum(
            dominant[index] != dominant[index - 1]
            and activity[index] >= active_floor
            and activity[index - 1] >= active_floor
            for index in range(start + 1, end + 1)
        )
        distinct = len(set(dominant[start : end + 1]))
        mean_activity = sum(activity[start : end + 1]) / (end - start + 1)
        score = (changes, distinct, mean_activity, -center)
        if best_rapid is None or score > best_rapid:
            best_rapid = score
            rapid_index = center
    rapid_changes = [
        index
        for index in range(rapid_index - rapid_radius + 1, rapid_index + rapid_radius + 1)
        if dominant[index] != dominant[index - 1]
        and activity[index] >= active_floor
        and activity[index - 1] >= active_floor
    ]
    if rapid_changes:
        rapid_index = (rapid_changes[0] + rapid_changes[-1]) // 2

    sustained_floor = max(0.15, _quantile(activity, 0.35))
    sustained_runs: list[tuple[int, int]] = []
    run_start: int | None = None
    for index in range(sample_count):
        continues = activity[index] >= sustained_floor and (
            run_start is None or dominant[index] == dominant[index - 1]
        )
        if continues and run_start is None:
            run_start = index
        elif not continues and run_start is not None:
            sustained_runs.append((run_start, index - 1))
            run_start = index if activity[index] >= sustained_floor else None
    if run_start is not None:
        sustained_runs.append((run_start, sample_count - 1))
    sustained_start, sustained_end = max(
        sustained_runs or [(large_index, large_index)], key=lambda item: item[1] - item[0]
    )
    sustained_index = (sustained_start + sustained_end) // 2

    silence_threshold = max(0.03, _quantile(activity, 0.05))
    silence_runs = _true_runs([value <= silence_threshold for value in activity])
    silence_start, silence_end = max(
        silence_runs or [(0, 0)], key=lambda item: item[1] - item[0]
    )
    silence_index = (silence_start + silence_end) // 2

    pre_window = radius(0.15)
    return_candidates: list[tuple[float, int]] = []
    for start, _end in silence_runs:
        if start == 0:
            continue
        before = max(activity[max(0, start - pre_window) : start])
        return_candidates.append((before - activity[start], start))
    return_index = max(return_candidates)[1] if return_candidates else silence_start

    speech_runs = _true_runs([value > 0.05 for value in activity])
    conversation_start, conversation_end = max(
        speech_runs or [(0, sample_count - 1)], key=lambda item: item[1] - item[0]
    )
    conversation_index = (conversation_start + conversation_end) // 2

    return {
        "short_pronunciation": window(
            "short_pronunciation", short_index, 0.15, 0.15, short_reason
        ),
        "large_opening": window(
            "large_opening",
            large_index,
            0.15,
            0.15,
            f"global maximum mouth activity={activity[large_index]:.6f}",
        ),
        "small_mouth": window(
            "small_mouth",
            small_index,
            0.15,
            0.15,
            f"prominent local motion with activity={activity[small_index]:.6f}",
        ),
        "rapid_transition": window(
            "rapid_transition",
            rapid_index,
            0.15,
            0.15,
            "highest count of active dominant-channel changes in a 0.30s window",
        ),
        "long_vocalization": window(
            "long_vocalization",
            sustained_index,
            0.0,
            0.0,
            f"longest sustained dominant-vowel run above activity {sustained_floor:.6f}",
            explicit_start=sustained_start,
            explicit_end=sustained_end,
        ),
        "zero_return": window(
            "zero_return",
            return_index,
            0.15,
            0.15,
            f"largest drop into activity <= {silence_threshold:.6f}",
        ),
        "long_silence": window(
            "long_silence",
            silence_index,
            0.0,
            0.0,
            f"longest low-activity run <= {silence_threshold:.6f}",
            explicit_start=silence_start,
            explicit_end=silence_end,
        ),
        "continuous_speech": window(
            "continuous_speech",
            conversation_index,
            0.5,
            0.5,
            f"center of longest continuous activity run > 0.05 "
            f"({(conversation_end - conversation_start + 1) * hop:.3f}s)",
        ),
    }
