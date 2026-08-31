"""Benchmark a five-minute, 10 ms PandaLip import inside Blender."""

from __future__ import annotations

import ctypes
import json
import math
import sys
import time
from pathlib import Path
from unittest import mock

import bpy

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from panda_lip_blender import importer  # noqa: E402
from panda_lip_blender.constants import BONE_NAMES, CHANNELS  # noqa: E402
from panda_lip_blender.reduction import measure_error  # noqa: E402
from tests.synthetic import speech_like_weights  # noqa: E402

SAMPLE_COUNT = 30_000
HOP_SECONDS = 0.01
START_FRAME = 100


class ProcessMemoryCountersEx(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def process_memory() -> dict[str, int] | None:
    """Read Windows process memory without requiring psutil."""

    if sys.platform != "win32":
        return None
    counters = ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    get_current_process = ctypes.windll.kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCountersEx),
        ctypes.c_ulong,
    )
    get_process_memory_info.restype = ctypes.c_bool
    process = get_current_process()
    succeeded = get_process_memory_info(
        process, ctypes.byref(counters), counters.cb
    )
    if not succeeded:
        return None
    return {
        "working_set": int(counters.WorkingSetSize),
        "peak_working_set": int(counters.PeakWorkingSetSize),
        "private_usage": int(counters.PrivateUsage),
    }


def write_long_fixture(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            "{\n"
            '  "format":"PandaLip",\n'
            '  "version":1,\n'
            '  "time_unit":"seconds",\n'
            '  "audio":{"duration":300.0,"sample_rate":48000,"channel_count":1},\n'
            '  "analysis":{"algorithm":"long-duration-benchmark","mode":"speech",'
            '"profile":"japanese_neutral_v1","profile_version":1,"sample_rate":16000,'
            '"frame_seconds":0.03,"hop_seconds":0.01,"sensitivity":0.5,'
            '"smoothing_ms":0.0},\n'
            '  "channels":["A","I","U","E","O"],\n'
            '  "samples":[\n'
        )
        for index in range(SAMPLE_COUNT):
            weights = speech_like_weights(index)
            sample = {"time": index * HOP_SECONDS}
            sample.update(dict(zip(CHANNELS, weights, strict=True)))
            if index:
                stream.write(",\n")
            stream.write("    ")
            stream.write(json.dumps(sample, separators=(",", ":"), allow_nan=False))
        stream.write("\n  ]\n}\n")


def main() -> None:
    target = bpy.data.objects.get("PandaLip")
    if target is None or target.type != "ARMATURE":
        raise AssertionError("Open PandaLip_Controller_Test.blend before running this benchmark")

    scene = bpy.context.scene
    scene.render.fps = 24
    scene.render.fps_base = 1.001
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    reduction_mode = arguments[0].upper() if arguments else "ORIGINAL"
    custom_tolerance = float(arguments[1]) if len(arguments) > 1 else 0.01
    fixture = REPOSITORY / "dist" / "long-duration-benchmark.pandalip"
    write_long_fixture(fixture)

    before = process_memory()
    started = time.perf_counter()
    try:
        result = importer.import_pandalip_file(
            str(fixture),
            target,
            scene,
            start_frame=START_FRAME,
            reduction_mode=reduction_mode,
            custom_tolerance=custom_tolerance,
        )
        elapsed = time.perf_counter() - started
        after = process_memory()

        action = target.animation_data.action
        if action is None or action.name != result.action_name:
            raise AssertionError("Generated Action was not assigned to the target Armature")
        curves = importer._action_fcurves(action)
        if len(curves) != len(CHANNELS):
            raise AssertionError(f"Expected 5 F-Curves, found {len(curves)}")
        if result.source_keyframe_count != SAMPLE_COUNT * len(CHANNELS):
            raise AssertionError("Unexpected source key count")

        rate = scene.render.fps / scene.render.fps_base
        channel_metrics: dict[str, dict[str, float | int]] = {}
        for channel_index, channel in enumerate(CHANNELS):
            pose_bone = target.pose.bones[BONE_NAMES[channel]]
            curve = importer._find_fcurve(
                curves, pose_bone.path_from_id("location"), 0
            )
            if reduction_mode == "ORIGINAL" and len(curve.keyframe_points) != SAMPLE_COUNT:
                raise AssertionError(f"Unexpected sample count for {channel}")
            previous_frame = -math.inf
            kept_indices: list[int] = []
            for point in curve.keyframe_points:
                if point.co.x <= previous_frame:
                    raise AssertionError(f"Frame order changed for {channel}")
                if point.interpolation != "LINEAR":
                    raise AssertionError(f"Non-linear key found for {channel}")
                previous_frame = point.co.x
                index = round((point.co.x - START_FRAME) / (HOP_SECONDS * rate))
                if not 0 <= index < SAMPLE_COUNT:
                    raise AssertionError(f"Key frame is outside the source range for {channel}")
                expected_frame = START_FRAME + index * HOP_SECONDS * rate
                expected_weight = speech_like_weights(index)[channel_index]
                if not math.isclose(point.co.x, expected_frame, abs_tol=0.001):
                    raise AssertionError(f"Subframe changed at {channel}[{index}]")
                if not math.isclose(point.co.y, expected_weight, abs_tol=1e-6):
                    raise AssertionError(f"Weight changed at {channel}[{index}]")
                kept_indices.append(index)
            if kept_indices[0] != 0 or kept_indices[-1] != SAMPLE_COUNT - 1:
                raise AssertionError(f"First/last keys were not retained for {channel}")

            reference = tuple(
                speech_like_weights(index)[channel_index] for index in range(SAMPLE_COUNT)
            )
            reconstructed = tuple(
                float(curve.evaluate(START_FRAME + index * HOP_SECONDS * rate))
                for index in range(SAMPLE_COUNT)
            )
            metrics = measure_error(reference, reconstructed, kept_indices)
            allowed_error = 1e-5 if result.tolerance is None else result.tolerance + 1e-5
            if metrics.max_absolute_error > allowed_error:
                raise AssertionError(
                    f"Maximum error exceeded tolerance for {channel}: "
                    f"{metrics.max_absolute_error} > {allowed_error}"
                )
            channel_metrics[channel] = {
                "source_keys": SAMPLE_COUNT,
                "reduced_keys": len(curve.keyframe_points),
                "reduction_percent": round(
                    100.0 * (1.0 - len(curve.keyframe_points) / SAMPLE_COUNT), 3
                ),
                "mean_error": metrics.mean_absolute_error,
                "rms_error": metrics.rms_error,
                "max_error": metrics.max_absolute_error,
                "peak_max_error": metrics.peak_max_error,
                "peak_key_retention": metrics.peak_key_retention,
                "zero_max_error": metrics.zero_max_absolute_error,
            }

        if not any(
            not math.isclose(point.co.x, round(point.co.x), abs_tol=1e-6)
            for curve in curves
            for point in curve.keyframe_points
        ):
            raise AssertionError("All retained samples were rounded to integer frames")

        # Inject a failure after one complete output curve has been populated.
        # The successful Action must remain assigned and the partial Action must
        # be removed even at long-duration scale.
        successful_action = action
        actions_before_failure = set(bpy.data.actions)
        original_set_curve_points = importer._set_curve_points
        completed_curves = 0

        def fail_after_partial_curve(*args: object, **kwargs: object) -> None:
            nonlocal completed_curves
            original_set_curve_points(*args, **kwargs)
            completed_curves += 1
            if completed_curves == 1:
                raise RuntimeError("injected long-duration failure")

        with mock.patch.object(
            importer, "_set_curve_points", side_effect=fail_after_partial_curve
        ):
            try:
                importer.import_pandalip_file(
                    str(fixture),
                    target,
                    scene,
                    start_frame=START_FRAME,
                    reduction_mode=reduction_mode,
                    custom_tolerance=custom_tolerance,
                )
            except RuntimeError as exc:
                if str(exc) != "injected long-duration failure":
                    raise
            else:
                raise AssertionError("Injected long-duration failure did not occur")
        if target.animation_data.action is not successful_action:
            raise AssertionError("Long-duration rollback did not restore the previous Action")
        if set(bpy.data.actions) != actions_before_failure:
            raise AssertionError("Long-duration rollback left a partial Action")

        aggregate_mean = sum(
            float(metrics["mean_error"]) for metrics in channel_metrics.values()
        ) / len(CHANNELS)
        aggregate_rms = math.sqrt(
            sum(float(metrics["rms_error"]) ** 2 for metrics in channel_metrics.values())
            / len(CHANNELS)
        )
        mib = 1024 * 1024
        payload = {
            "blender": bpy.app.version_string,
            "samples": SAMPLE_COUNT,
            "channels": len(CHANNELS),
            "source_keys": result.source_keyframe_count,
            "reduced_keys": result.keyframe_count,
            "reduction_percent": round(
                100.0 * (1.0 - result.keyframe_count / result.source_keyframe_count), 3
            ),
            "mode": result.reduction_mode,
            "tolerance": result.tolerance,
            "reduction_seconds": round(result.reduction_seconds, 3),
            "key_generation_seconds": round(result.key_generation_seconds, 3),
            "total_import_seconds": round(elapsed, 3),
            "mean_error": aggregate_mean,
            "rms_error": aggregate_rms,
            "max_error": max(float(metrics["max_error"]) for metrics in channel_metrics.values()),
            "peak_max_error": max(
                float(metrics["peak_max_error"]) for metrics in channel_metrics.values()
            ),
            "peak_key_retention": sum(
                float(metrics["peak_key_retention"]) for metrics in channel_metrics.values()
            )
            / len(CHANNELS),
            "zero_max_error": max(
                float(metrics["zero_max_error"]) for metrics in channel_metrics.values()
            ),
            "channel_metrics": channel_metrics,
            "action": result.action_name,
            "working_set_before_mib": None if before is None else round(before["working_set"] / mib, 1),
            "working_set_after_mib": None if after is None else round(after["working_set"] / mib, 1),
            "peak_working_set_mib": None if after is None else round(after["peak_working_set"] / mib, 1),
            "private_usage_after_mib": None if after is None else round(after["private_usage"] / mib, 1),
            "rollback_verified": True,
        }
        print("PANDALIP_LONG_BENCHMARK=" + json.dumps(payload, sort_keys=True))
    finally:
        fixture.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
