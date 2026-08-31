"""Create a reproducible Phase B.5 A/B comparison from a real PandaLip file.

Run with the reference .blend already open, for example:

blender --background --factory-startup PandaLip_Controller_Test.blend \
  --python tests/blender/real_data_ab_evaluation.py -- \
  Panda-lip_Test_Voice.pandalip dist/phase_b5 --render --save-blend
"""

from __future__ import annotations

from array import array
import bisect
import html
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Sequence

import bpy

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from panda_lip_blender import importer  # noqa: E402
from panda_lip_blender.constants import BONE_NAMES, CHANNELS  # noqa: E402
from panda_lip_blender.reduction import measure_error  # noqa: E402
from panda_lip_blender.validation import load_pandalip  # noqa: E402
from tests.phase_b5_analysis import FeatureWindow, select_feature_windows  # noqa: E402

MODE_SPECS = (
    ("ORIGINAL", None),
    ("HIGH", 0.0025),
    ("MIDDLE", 0.01),
    ("LOW", 0.02),
)
START_FRAME = 0
TARGET_NAME = "PandaLip"
FACE_NAME = "M_Miyuki_Face"
SHAPE_KEYS = {
    "A": "Fcl_MTH_A",
    "I": "Fcl_MTH_I",
    "U": "Fcl_MTH_U",
    "E": "Fcl_MTH_E",
    "O": "Fcl_MTH_O",
}
CHANNEL_COLORS = {
    "A": "#ef5350",
    "I": "#66bb6a",
    "U": "#42a5f5",
    "E": "#ffa726",
    "O": "#ab47bc",
}


def parse_arguments() -> tuple[Path, Path, bool, bool]:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(arguments) < 2:
        raise RuntimeError(
            "Expected: -- INPUT.pandalip OUTPUT_DIR [--render] [--save-blend]"
        )
    input_path = Path(arguments[0]).resolve()
    output_dir = Path(arguments[1]).resolve()
    return input_path, output_dir, "--render" in arguments, "--save-blend" in arguments


def validate_character_rig(target: bpy.types.Object, face: bpy.types.Object) -> dict[str, object]:
    if target.type != "ARMATURE":
        raise AssertionError(f"{TARGET_NAME} is not an Armature")
    missing_bones = [name for name in BONE_NAMES.values() if target.pose.bones.get(name) is None]
    if missing_bones:
        raise AssertionError(f"Missing controller bones: {missing_bones}")
    if face.type != "MESH" or face.data.shape_keys is None:
        raise AssertionError(f"{FACE_NAME} has no Shape Keys")
    missing_shapes = [name for name in SHAPE_KEYS.values() if face.data.shape_keys.key_blocks.get(name) is None]
    if missing_shapes:
        raise AssertionError(f"Missing facial Shape Keys: {missing_shapes}")
    animation_data = face.data.shape_keys.animation_data
    if animation_data is None:
        raise AssertionError(f"{FACE_NAME} Shape Keys have no Drivers")

    driver_map: dict[str, dict[str, str]] = {}
    for curve in animation_data.drivers:
        for channel, shape_name in SHAPE_KEYS.items():
            if curve.data_path != f'key_blocks["{shape_name}"].value':
                continue
            targets = [target for variable in curve.driver.variables for target in variable.targets]
            if len(targets) != 1:
                raise AssertionError(f"Unexpected Driver target count for {shape_name}")
            driver_target = targets[0]
            expected_bone = BONE_NAMES[channel]
            if (
                driver_target.id != target
                or driver_target.bone_target != expected_bone
                or driver_target.transform_type != "LOC_X"
                or driver_target.transform_space != "LOCAL_SPACE"
            ):
                raise AssertionError(f"Unexpected Driver mapping for {shape_name}")
            driver_map[channel] = {
                "shape_key": shape_name,
                "bone": expected_bone,
                "transform": "LOCAL_SPACE LOC_X",
            }
    if set(driver_map) != set(CHANNELS):
        raise AssertionError("AIUEO Driver mapping is incomplete")
    return {"target": target.name, "face": face.name, "drivers": driver_map}


def frame_to_source_index(frames: Sequence[float], frame: float) -> int:
    insertion = bisect.bisect_left(frames, frame)
    candidates = [index for index in (insertion - 1, insertion) if 0 <= index < len(frames)]
    index = min(candidates, key=lambda item: abs(frames[item] - frame))
    if not math.isclose(frames[index], frame, abs_tol=0.001):
        raise AssertionError(f"Generated key frame {frame} is not a source sample frame")
    return index


def graph_stats(times: Sequence[float], kept_indices: Sequence[int]) -> dict[str, float | int]:
    key_times = [times[index] for index in kept_indices]
    gaps = [
        current - previous
        for previous, current in zip(key_times[:-1], key_times[1:], strict=True)
    ]
    duration = max(times[-1] - times[0], 1e-12)
    return {
        "keys": len(kept_indices),
        "keys_per_second": len(kept_indices) / duration,
        "mean_key_gap_seconds": 0.0 if not gaps else sum(gaps) / len(gaps),
        "median_key_gap_seconds": 0.0 if not gaps else statistics.median(gaps),
        "maximum_key_gap_seconds": 0.0 if not gaps else max(gaps),
    }


def prominent_peak_metrics(
    times: Sequence[float],
    reference: Sequence[float],
    reconstructed: Sequence[float],
    kept_indices: Sequence[int],
) -> dict[str, float | int]:
    hop = statistics.median(
        current - previous
        for previous, current in zip(times[:-1], times[1:], strict=True)
    )
    prominence_radius = max(1, round(0.1 / hop))
    match_radius = max(1, round(0.05 / hop))
    peaks: list[int] = []
    for index in range(1, len(reference) - 1):
        if not (
            reference[index] > reference[index - 1]
            and reference[index] >= reference[index + 1]
            and reference[index] >= 0.1
        ):
            continue
        left_floor = min(reference[max(0, index - prominence_radius) : index + 1])
        right_floor = min(
            reference[index : min(len(reference), index + prominence_radius + 1)]
        )
        if reference[index] - max(left_floor, right_floor) >= 0.05:
            peaks.append(index)

    kept = set(kept_indices)
    center_errors = [abs(reference[index] - reconstructed[index]) for index in peaks]
    time_shifts: list[float] = []
    amplitude_differences: list[float] = []
    for index in peaks:
        start = max(0, index - match_radius)
        end = min(len(reference) - 1, index + match_radius)
        reduced_peak = max(range(start, end + 1), key=lambda item: reconstructed[item])
        time_shifts.append(abs(times[reduced_peak] - times[index]))
        amplitude_differences.append(abs(reconstructed[reduced_peak] - reference[index]))
    ordered_shifts = sorted(time_shifts)
    return {
        "definition": "value >= 0.1 and 100ms-neighborhood prominence >= 0.05",
        "count": len(peaks),
        "exact_key_retention": 1.0 if not peaks else sum(index in kept for index in peaks) / len(peaks),
        "center_max_error": max(center_errors, default=0.0),
        "matched_peak_mean_amplitude_difference": (
            0.0 if not amplitude_differences else sum(amplitude_differences) / len(amplitude_differences)
        ),
        "matched_peak_max_amplitude_difference": max(amplitude_differences, default=0.0),
        "matched_peak_mean_time_shift_seconds": (
            0.0 if not time_shifts else sum(time_shifts) / len(time_shifts)
        ),
        "matched_peak_p95_time_shift_seconds": (
            0.0
            if not ordered_shifts
            else ordered_shifts[round((len(ordered_shifts) - 1) * 0.95)]
        ),
        "matched_peak_max_time_shift_seconds": max(time_shifts, default=0.0),
    }


def aggregate_metrics(
    channel_metrics: dict[str, dict[str, object]], sample_count: int
) -> dict[str, float | int]:
    source_keys = sample_count * len(CHANNELS)
    reduced_keys = sum(int(metrics["key_count"]) for metrics in channel_metrics.values())
    peak_count = sum(int(metrics["peak_count"]) for metrics in channel_metrics.values())
    retained_peaks = sum(int(metrics["retained_peak_count"]) for metrics in channel_metrics.values())
    prominent_count = sum(
        int(metrics["prominent_peaks"]["count"]) for metrics in channel_metrics.values()
    )
    prominent_retained = sum(
        round(
            int(metrics["prominent_peaks"]["count"])
            * float(metrics["prominent_peaks"]["exact_key_retention"])
        )
        for metrics in channel_metrics.values()
    )
    return {
        "source_keys": source_keys,
        "reduced_keys": reduced_keys,
        "reduction_percent": 100.0 * (1.0 - reduced_keys / source_keys),
        "mean_absolute_error": sum(
            float(metrics["mean_absolute_error"]) for metrics in channel_metrics.values()
        )
        / len(CHANNELS),
        "rms_error": math.sqrt(
            sum(float(metrics["rms_error"]) ** 2 for metrics in channel_metrics.values())
            / len(CHANNELS)
        ),
        "max_absolute_error": max(
            float(metrics["max_absolute_error"]) for metrics in channel_metrics.values()
        ),
        "peak_max_error": max(
            float(metrics["peak_max_error"]) for metrics in channel_metrics.values()
        ),
        "peak_key_retention": 1.0 if peak_count == 0 else retained_peaks / peak_count,
        "peak_count": peak_count,
        "near_zero_max_error": max(
            float(metrics["near_zero_max_error"]) for metrics in channel_metrics.values()
        ),
        "prominent_peak_count": prominent_count,
        "prominent_peak_exact_key_retention": (
            1.0 if prominent_count == 0 else prominent_retained / prominent_count
        ),
        "prominent_peak_center_max_error": max(
            float(metrics["prominent_peaks"]["center_max_error"])
            for metrics in channel_metrics.values()
        ),
        "prominent_peak_matched_max_amplitude_difference": max(
            float(metrics["prominent_peaks"]["matched_peak_max_amplitude_difference"])
            for metrics in channel_metrics.values()
        ),
        "prominent_peak_matched_max_time_shift_seconds": max(
            float(metrics["prominent_peaks"]["matched_peak_max_time_shift_seconds"])
            for metrics in channel_metrics.values()
        ),
    }


def evaluate_feature(
    feature: FeatureWindow,
    reference_rows: Sequence[Sequence[float]],
    reduced_rows: Sequence[Sequence[float]],
) -> dict[str, object]:
    indices = range(feature.start_index, feature.end_index + 1)
    errors = [
        abs(reference_rows[index][channel] - reduced_rows[index][channel])
        for index in indices
        for channel in range(len(CHANNELS))
    ]
    active_indices = [
        index
        for index in range(feature.start_index, feature.end_index + 1)
        if max(reference_rows[index]) >= 0.05
    ]
    dominant_matches = [
        max(range(len(CHANNELS)), key=lambda item: reference_rows[index][item])
        == max(range(len(CHANNELS)), key=lambda item: reduced_rows[index][item])
        for index in active_indices
    ]
    channel_peaks: dict[str, dict[str, float | int]] = {}
    for channel_index, channel in enumerate(CHANNELS):
        feature_indices = range(feature.start_index, feature.end_index + 1)
        reference_peak = max(feature_indices, key=lambda item: reference_rows[item][channel_index])
        reduced_peak = max(feature_indices, key=lambda item: reduced_rows[item][channel_index])
        channel_peaks[channel] = {
            "reference_index": reference_peak,
            "reduced_index": reduced_peak,
            "index_shift": reduced_peak - reference_peak,
            "reference_value": reference_rows[reference_peak][channel_index],
            "reduced_value": reduced_rows[reduced_peak][channel_index],
            "amplitude_difference": abs(
                reduced_rows[reduced_peak][channel_index]
                - reference_rows[reference_peak][channel_index]
            ),
        }
    return {
        "mean_absolute_error": sum(errors) / len(errors),
        "rms_error": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "max_absolute_error": max(errors),
        "active_dominant_channel_match": (
            1.0 if not dominant_matches else sum(dominant_matches) / len(dominant_matches)
        ),
        "channel_peaks": channel_peaks,
    }


def write_graph_svg(
    path: Path,
    feature: FeatureWindow,
    times: Sequence[float],
    curve_data: dict[str, dict[str, dict[str, object]]],
) -> None:
    width = 1500
    height = 1040
    left = 120
    right = 35
    top = 85
    row_height = 215
    plot_width = width - left - right
    plot_height = 160
    start = feature.start_index
    end = feature.end_index
    time_start = times[start]
    time_end = times[end]
    time_span = max(time_end - time_start, 1e-9)

    def x_position(index: int) -> float:
        return left + (times[index] - time_start) / time_span * plot_width

    def y_position(row: int, value: float) -> float:
        row_top = top + row * row_height
        return row_top + plot_height - max(0.0, min(1.0, value)) * plot_height

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#202124"/>',
        f'<text x="{left}" y="38" fill="#f1f3f4" font-family="Segoe UI" font-size="24">'
        f'Phase B.5 Curve / Key A/B — {html.escape(feature.key)} '
        f'({time_start:.2f}s–{time_end:.2f}s)</text>',
    ]
    legend_x = left
    for channel in CHANNELS:
        parts.append(
            f'<text x="{legend_x}" y="68" fill="{CHANNEL_COLORS[channel]}" '
            f'font-family="Segoe UI" font-size="17">● {channel}</text>'
        )
        legend_x += 70

    for row, (mode, _tolerance) in enumerate(MODE_SPECS):
        row_top = top + row * row_height
        parts.append(
            f'<text x="20" y="{row_top + 24}" fill="#f1f3f4" '
            f'font-family="Segoe UI" font-size="18">{mode.title()}</text>'
        )
        for grid_value in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = y_position(row, grid_value)
            parts.append(
                f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" '
                'stroke="#44474a" stroke-width="1"/>'
            )
        for index in range(start, end + 1, max(1, (end - start) // 10)):
            x = x_position(index)
            parts.append(
                f'<line x1="{x:.2f}" y1="{row_top}" x2="{x:.2f}" '
                f'y2="{row_top + plot_height}" stroke="#343638" stroke-width="1"/>'
            )

        for channel in CHANNELS:
            channel_data = curve_data[mode][channel]
            values = channel_data["reconstructed"]
            kept_indices = channel_data["kept_indices"]
            points = " ".join(
                f"{x_position(index):.2f},{y_position(row, values[index]):.2f}"
                for index in range(start, end + 1)
            )
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="{CHANNEL_COLORS[channel]}" '
                'stroke-width="2" stroke-linejoin="round"/>'
            )
            for index in kept_indices:
                if start <= index <= end:
                    parts.append(
                        f'<circle cx="{x_position(index):.2f}" '
                        f'cy="{y_position(row, values[index]):.2f}" r="3" '
                        f'fill="{CHANNEL_COLORS[channel]}" stroke="#202124" stroke-width="1"/>'
                    )
        key_count = sum(
            sum(start <= index <= end for index in curve_data[mode][channel]["kept_indices"])
            for channel in CHANNELS
        )
        parts.append(
            f'<text x="{width - 170}" y="{row_top + 20}" fill="#bdc1c6" '
            f'font-family="Segoe UI" font-size="15">{key_count} keys</text>'
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def save_render_result(path: Path, scene: bpy.types.Scene) -> None:
    image = bpy.data.images.get("Render Result")
    if image is None:
        raise AssertionError("Blender did not produce a Render Result")
    image.save_render(str(path), scene=scene)


def read_pixels(path: Path) -> tuple[int, int, array[float]]:
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        width, height = image.size
        pixels = array("f", [0.0]) * (width * height * 4)
        image.pixels.foreach_get(pixels)
        return width, height, pixels
    finally:
        bpy.data.images.remove(image)


def pixel_difference(reference_path: Path, comparison_path: Path) -> dict[str, object]:
    width, height, reference = read_pixels(reference_path)
    other_width, other_height, comparison = read_pixels(comparison_path)
    if (width, height) != (other_width, other_height):
        raise AssertionError("Rendered comparison images have different dimensions")

    def region_metrics(x_start: int, x_end: int, y_start: int, y_end: int) -> dict[str, float]:
        total = 0.0
        squared = 0.0
        maximum = 0.0
        changed = 0
        count = 0
        for y in range(y_start, y_end):
            for x in range(x_start, x_end):
                pixel_start = (y * width + x) * 4
                for component in range(3):
                    difference = abs(reference[pixel_start + component] - comparison[pixel_start + component])
                    total += difference
                    squared += difference * difference
                    maximum = max(maximum, difference)
                    changed += difference > 1.0 / 255.0
                    count += 1
        return {
            "mean_absolute_difference": total / count,
            "rms_difference": math.sqrt(squared / count),
            "max_difference": maximum,
            "fraction_above_one_8bit_step": changed / count,
        }

    return {
        "dimensions": [width, height],
        "full_frame": region_metrics(0, width, 0, height),
        "mouth_roi": region_metrics(
            round(width * 0.30),
            round(width * 0.70),
            round(height * 0.03),
            round(height * 0.32),
        ),
    }


def main() -> None:
    input_path, output_dir, render_stills, save_blend = parse_arguments()
    output_dir.mkdir(parents=True, exist_ok=True)
    stills_dir = output_dir / "stills"
    if render_stills:
        stills_dir.mkdir(parents=True, exist_ok=True)

    data = load_pandalip(input_path)
    scene = bpy.context.scene
    target = bpy.data.objects.get(TARGET_NAME)
    face = bpy.data.objects.get(FACE_NAME)
    if target is None or face is None:
        raise AssertionError(f"Reference file must contain {TARGET_NAME} and {FACE_NAME}")
    rig_report = validate_character_rig(target, face)
    rate = scene.render.fps / scene.render.fps_base
    times = tuple(sample.time for sample in data.samples)
    source_rows = tuple(sample.weights for sample in data.samples)
    frames = tuple(START_FRAME + time_value * rate for time_value in times)
    features = select_feature_windows(times, source_rows, CHANNELS)

    actions: dict[str, bpy.types.Action] = {}
    curve_data: dict[str, dict[str, dict[str, object]]] = {}
    mode_reports: dict[str, dict[str, object]] = {}
    action_mapping: dict[str, str] = {}

    for mode, expected_tolerance in MODE_SPECS:
        started = time.perf_counter()
        result = importer.import_pandalip_data(
            data,
            str(input_path),
            target,
            scene,
            START_FRAME,
            reduction_mode=mode,
        )
        total_import_seconds = time.perf_counter() - started
        action = target.animation_data.action
        if action is None:
            raise AssertionError(f"{mode} import did not assign an Action")
        if result.tolerance != expected_tolerance:
            raise AssertionError(f"Unexpected {mode} tolerance: {result.tolerance}")
        action.use_fake_user = True
        action["phase_b5_mode"] = mode
        action["phase_b5_tolerance"] = -1.0 if result.tolerance is None else result.tolerance
        action["phase_b5_source"] = input_path.name
        actions[mode] = action
        action_mapping[mode] = action.name

        curves = importer._action_fcurves(action)
        channel_reports: dict[str, dict[str, object]] = {}
        channel_curve_data: dict[str, dict[str, object]] = {}
        reconstructed_rows = [[0.0] * len(CHANNELS) for _ in times]
        for channel_index, channel in enumerate(CHANNELS):
            pose_bone = target.pose.bones[BONE_NAMES[channel]]
            curve = importer._find_fcurve(curves, pose_bone.path_from_id("location"), 0)
            if any(point.interpolation != "LINEAR" for point in curve.keyframe_points):
                raise AssertionError(f"{mode}/{channel} contains non-LINEAR keys")
            kept_indices = tuple(
                frame_to_source_index(frames, float(point.co.x)) for point in curve.keyframe_points
            )
            if kept_indices[0] != 0 or kept_indices[-1] != len(times) - 1:
                raise AssertionError(f"{mode}/{channel} did not retain First/Last")
            if len(set(kept_indices)) != len(kept_indices):
                raise AssertionError(f"{mode}/{channel} contains duplicate source keys")
            reference = tuple(row[channel_index] for row in source_rows)
            reconstructed = tuple(float(curve.evaluate(frame)) for frame in frames)
            for index, value in enumerate(reconstructed):
                reconstructed_rows[index][channel_index] = value
            metrics = measure_error(reference, reconstructed, kept_indices)
            allowed_error = 1e-5 if expected_tolerance is None else expected_tolerance + 1e-5
            if metrics.max_absolute_error > allowed_error:
                raise AssertionError(
                    f"{mode}/{channel} exceeded tolerance: "
                    f"{metrics.max_absolute_error} > {allowed_error}"
                )
            near_zero_errors = [
                abs(reference[index] - reconstructed[index])
                for index in range(len(times))
                if reference[index] <= 0.01
            ]
            retained_peak_count = round(metrics.peak_key_retention * metrics.peak_count)
            prominent_peaks = prominent_peak_metrics(
                times, reference, reconstructed, kept_indices
            )
            channel_reports[channel] = {
                "key_count": len(kept_indices),
                "reduction_percent": 100.0 * (1.0 - len(kept_indices) / len(times)),
                "mean_absolute_error": metrics.mean_absolute_error,
                "rms_error": metrics.rms_error,
                "max_absolute_error": metrics.max_absolute_error,
                "peak_max_error": metrics.peak_max_error,
                "peak_key_retention": metrics.peak_key_retention,
                "peak_count": metrics.peak_count,
                "retained_peak_count": retained_peak_count,
                "near_zero_sample_count": len(near_zero_errors),
                "near_zero_max_error": max(near_zero_errors, default=0.0),
                "prominent_peaks": prominent_peaks,
                "graph": graph_stats(times, kept_indices),
            }
            channel_curve_data[channel] = {
                "kept_indices": kept_indices,
                "reconstructed": reconstructed,
            }

        reduced_rows = tuple(tuple(row) for row in reconstructed_rows)
        feature_results = {
            key: evaluate_feature(feature, source_rows, reduced_rows)
            for key, feature in features.items()
        }
        aggregate = aggregate_metrics(channel_reports, len(times))
        if mode == "ORIGINAL" and aggregate["reduced_keys"] != aggregate["source_keys"]:
            raise AssertionError("Original does not exactly retain every Phase A key")
        mode_reports[mode] = {
            "action": action.name,
            "tolerance": result.tolerance,
            "sample_count": result.sample_count,
            "aggregate": aggregate,
            "channels": channel_reports,
            "features": feature_results,
            "performance": {
                "reduction_seconds": result.reduction_seconds,
                "key_generation_seconds": result.key_generation_seconds,
                "total_import_seconds": total_import_seconds,
            },
        }
        curve_data[mode] = channel_curve_data

    graph_artifacts: dict[str, str] = {}
    for feature_key in ("rapid_transition", "continuous_speech"):
        graph_path = output_dir / f"graph_{feature_key}.svg"
        write_graph_svg(graph_path, features[feature_key], times, curve_data)
        graph_artifacts[feature_key] = str(graph_path)

    visual_report: dict[str, object] = {}
    rendered_paths: dict[str, dict[str, Path]] = {}
    original_render_percentage = scene.render.resolution_percentage
    if render_stills:
        scene.render.resolution_percentage = 50
        for feature_key, feature in features.items():
            rendered_paths[feature_key] = {}
            visual_report[feature_key] = {
                "time": feature.center_time,
                "reference_weights": dict(zip(CHANNELS, source_rows[feature.center_index], strict=True)),
                "presets": {},
            }
            for mode, _tolerance in MODE_SPECS:
                target.animation_data.action = actions[mode]
                frame = frames[feature.center_index]
                integer_frame = math.floor(frame)
                scene.frame_set(integer_frame, subframe=frame - integer_frame)
                bpy.context.view_layer.update()
                shape_values = {
                    channel: float(face.data.shape_keys.key_blocks[shape_name].value)
                    for channel, shape_name in SHAPE_KEYS.items()
                }
                path = stills_dir / f"{feature_key}__{mode.lower()}.png"
                bpy.ops.render.render()
                save_render_result(path, scene)
                rendered_paths[feature_key][mode] = path
                visual_report[feature_key]["presets"][mode] = {
                    "shape_key_values": shape_values,
                    "image": str(path),
                }
            original_path = rendered_paths[feature_key]["ORIGINAL"]
            for mode in ("HIGH", "MIDDLE", "LOW"):
                visual_report[feature_key]["presets"][mode]["pixel_difference_from_original"] = (
                    pixel_difference(original_path, rendered_paths[feature_key][mode])
                )
        scene.render.resolution_percentage = original_render_percentage

    for marker in list(scene.timeline_markers):
        if marker.name.startswith("B5_"):
            scene.timeline_markers.remove(marker)
    for feature_key, feature in features.items():
        scene.timeline_markers.new(
            "B5_" + feature_key,
            frame=round(frames[feature.center_index]),
        )

    target.animation_data.action = actions["ORIGINAL"]
    scene.frame_set(START_FRAME)
    bpy.context.view_layer.update()
    comparison_blend: str | None = None
    if save_blend:
        comparison_path = output_dir / "PandaLip_PhaseB5_AB.blend"
        instructions = bpy.data.texts.get("PHASE_B5_README") or bpy.data.texts.new("PHASE_B5_README")
        instructions.clear()
        instructions.write(
            "Phase B.5 real-data A/B comparison\n"
            f"Source: {input_path}\n"
            f"Start Frame: {START_FRAME}; FPS: {scene.render.fps}/{scene.render.fps_base}\n"
            "Assign one of these Actions to PandaLip and play with the existing audio:\n"
            + "\n".join(f"  {mode}: {action_mapping[mode]}" for mode, _ in MODE_SPECS)
            + "\nTimeline markers prefixed B5_ identify evaluated feature frames.\n"
        )
        bpy.ops.wm.save_as_mainfile(filepath=str(comparison_path), copy=True)
        comparison_blend = str(comparison_path)

    editor = scene.sequence_editor
    strips = list(editor.strips) if editor is not None and hasattr(editor, "strips") else []
    sound_strips = [
        {
            "name": strip.name,
            "frame_start": float(strip.frame_start),
            "frame_duration": int(strip.frame_final_duration),
            "filepath": bpy.path.abspath(strip.sound.filepath),
        }
        for strip in strips
        if strip.type == "SOUND"
    ]
    report = {
        "input": {
            "path": str(input_path),
            "file_size_bytes": input_path.stat().st_size,
            "format": "PandaLip",
            "version": 1,
            "duration_seconds": data.document["audio"]["duration"],
            "samples": len(data.samples),
            "first_sample_time": times[0],
            "last_sample_time": times[-1],
            "channels": list(CHANNELS),
            "analysis": {
                "algorithm": data.document["analysis"]["algorithm"],
                "mode": data.document["analysis"]["mode"],
                "profile": data.document["analysis"]["profile"],
                "hop_seconds": data.document["analysis"]["hop_seconds"],
                "smoothing_ms": data.document["analysis"]["smoothing_ms"],
            },
        },
        "blender": {
            "version": bpy.app.version_string,
            "reference_blend": bpy.data.filepath,
            "fps": scene.render.fps,
            "fps_base": scene.render.fps_base,
            "effective_fps": rate,
            "start_frame": START_FRAME,
            "camera": None if scene.camera is None else scene.camera.name,
            "render_engine": scene.render.engine,
            "sound_strips": sound_strips,
        },
        "rig": rig_report,
        "action_mapping": action_mapping,
        "features": {key: feature.to_dict() for key, feature in features.items()},
        "modes": mode_reports,
        "visual": visual_report,
        "artifacts": {
            "comparison_blend": comparison_blend,
            "graphs": graph_artifacts,
            "stills_directory": str(stills_dir) if render_stills else None,
        },
    }
    report_path = output_dir / "phase_b5_real_data_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PANDALIP_PHASE_B5_REPORT=" + str(report_path))


if __name__ == "__main__":
    main()
