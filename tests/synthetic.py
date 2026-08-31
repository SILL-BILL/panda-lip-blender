"""Deterministic synthetic lip-sync curves used by tests and benchmarks."""

from __future__ import annotations

import math


def smoothstep(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def speech_like_weights(index: int) -> tuple[float, float, float, float, float]:
    """Return one synthetic 10 ms AIUEO sample with speech-like vowel pulses."""

    cycle_samples = 24
    cycle = index // cycle_samples
    phase = index % cycle_samples
    active_channel = cycle % 5
    amplitude = 0.72 + 0.07 * (cycle % 5)
    if cycle % 17 == 0:
        amplitude = 0.12

    if phase < 5:
        envelope = 0.0
    elif phase < 11:
        envelope = smoothstep((phase - 5) / 5.0)
    elif phase < 16:
        envelope = 0.96 + 0.04 * math.sin((phase - 11) * math.pi / 4.0)
    elif phase < 22:
        envelope = 1.0 - smoothstep((phase - 16) / 5.0)
    else:
        envelope = 0.0

    values = [0.0] * 5
    values[active_channel] = min(1.0, amplitude * envelope)
    return tuple(values)  # type: ignore[return-value]


def benchmark_patterns() -> dict[str, tuple[tuple[float, ...], tuple[float, ...]]]:
    """Canonical curve cases required by the Phase B evaluation."""

    def curve(values: tuple[float, ...]) -> tuple[tuple[float, ...], tuple[float, ...]]:
        return tuple(index * 0.01 for index in range(len(values))), values

    return {
        "ramp": curve(tuple(index / 20.0 for index in range(21)) + tuple(index / 20.0 for index in range(19, -1, -1))),
        "hold": curve(
            tuple(index / 10.0 for index in range(11))
            + (1.0,) * 20
            + tuple(index / 10.0 for index in range(9, -1, -1))
        ),
        "short_peak": curve((0.0, 0.0, 0.2, 0.9, 0.25, 0.0, 0.0)),
        "small_motion": curve((0.0, 0.0, 0.02, 0.06, 0.1, 0.06, 0.02, 0.0, 0.0)),
        "rapid_transition": curve((0.0, 1.0, 0.0, 0.85, 0.05, 1.0, 0.0)),
        "long_silence": curve((0.0,) * 500),
    }
