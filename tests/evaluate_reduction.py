"""Evaluate candidate tolerances against deterministic synthetic AIUEO curves."""

from __future__ import annotations

import json
import time

from panda_lip_blender.constants import CHANNELS
from panda_lip_blender.reduction import measure_error, reconstruct_values, simplify_indices
from tests.synthetic import benchmark_patterns, speech_like_weights

CANDIDATE_TOLERANCES = (0.0025, 0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1)
LONG_SAMPLE_COUNT = 30_000


def evaluate_curve(
    times: tuple[float, ...], values: tuple[float, ...], tolerance: float
) -> dict[str, float | int]:
    started = time.perf_counter()
    indices = simplify_indices(times, values, tolerance)
    reduction_seconds = time.perf_counter() - started
    reconstructed = reconstruct_values(times, values, indices)
    metrics = measure_error(values, reconstructed, indices)
    return {
        "source_keys": len(values),
        "reduced_keys": len(indices),
        "reduction_percent": 100.0 * (1.0 - len(indices) / len(values)),
        "reduction_seconds": reduction_seconds,
        "mean_error": metrics.mean_absolute_error,
        "rms_error": metrics.rms_error,
        "max_error": metrics.max_absolute_error,
        "peak_max_error": metrics.peak_max_error,
        "peak_key_retention": metrics.peak_key_retention,
        "peak_count": metrics.peak_count,
        "zero_mean_error": metrics.zero_mean_absolute_error,
        "zero_max_error": metrics.zero_max_absolute_error,
    }


def aggregate(channel_results: dict[str, dict[str, float | int]]) -> dict[str, float | int]:
    source = sum(int(result["source_keys"]) for result in channel_results.values())
    reduced = sum(int(result["reduced_keys"]) for result in channel_results.values())
    sample_weight = sum(int(result["source_keys"]) for result in channel_results.values())
    return {
        "source_keys": source,
        "reduced_keys": reduced,
        "reduction_percent": 100.0 * (1.0 - reduced / source),
        "reduction_seconds": sum(float(result["reduction_seconds"]) for result in channel_results.values()),
        "mean_error": sum(float(result["mean_error"]) * int(result["source_keys"]) for result in channel_results.values()) / sample_weight,
        "rms_error": (
            sum(float(result["rms_error"]) ** 2 * int(result["source_keys"]) for result in channel_results.values())
            / sample_weight
        )
        ** 0.5,
        "max_error": max(float(result["max_error"]) for result in channel_results.values()),
        "peak_max_error": max(float(result["peak_max_error"]) for result in channel_results.values()),
        "peak_key_retention": sum(float(result["peak_key_retention"]) for result in channel_results.values()) / len(channel_results),
        "zero_max_error": max(float(result["zero_max_error"]) for result in channel_results.values()),
    }


def main() -> None:
    pattern_results: dict[str, dict[str, dict[str, float | int]]] = {}
    for tolerance in CANDIDATE_TOLERANCES:
        pattern_results[str(tolerance)] = {
            name: evaluate_curve(times, values, tolerance)
            for name, (times, values) in benchmark_patterns().items()
        }

    times = tuple(index * 0.01 for index in range(LONG_SAMPLE_COUNT))
    weights = tuple(speech_like_weights(index) for index in range(LONG_SAMPLE_COUNT))
    long_results: dict[str, object] = {}
    for tolerance in CANDIDATE_TOLERANCES:
        channels = {
            channel: evaluate_curve(
                times,
                tuple(sample[channel_index] for sample in weights),
                tolerance,
            )
            for channel_index, channel in enumerate(CHANNELS)
        }
        long_results[str(tolerance)] = {
            "aggregate": aggregate(channels),
            "channels": channels,
        }

    print(
        "PANDALIP_REDUCTION_EVALUATION="
        + json.dumps(
            {"patterns": pattern_results, "long_5min": long_results},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
