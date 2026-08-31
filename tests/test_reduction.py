from __future__ import annotations

import math
import random
import unittest

from panda_lip_blender.reduction import (
    PRESET_TOLERANCES,
    measure_error,
    reconstruct_values,
    resolve_tolerance,
    simplify_indices,
)
from tests.synthetic import benchmark_patterns


class ReductionTests(unittest.TestCase):
    def assert_error_bounded(
        self, times: tuple[float, ...], values: tuple[float, ...], tolerance: float
    ) -> tuple[int, ...]:
        indices = simplify_indices(times, values, tolerance)
        reconstructed = reconstruct_values(times, values, indices)
        metrics = measure_error(values, reconstructed, indices)
        self.assertLessEqual(metrics.max_absolute_error, tolerance + 1e-12)
        return indices

    def test_first_and_last_keys_are_always_retained(self) -> None:
        times = (0.0, 0.01, 0.02, 0.03)
        values = (0.0, 0.2, 0.1, 0.0)
        indices = self.assert_error_bounded(times, values, 1.0)
        self.assertEqual(indices, (0, 3))

    def test_constant_and_zero_curves_reduce_to_endpoints(self) -> None:
        times = tuple(index * 0.01 for index in range(100))
        for value in (0.0, 0.5, 1.0):
            with self.subTest(value=value):
                values = (value,) * len(times)
                self.assertEqual(simplify_indices(times, values, 0.0), (0, 99))

    def test_exact_ramp_reduces_to_endpoints(self) -> None:
        times = tuple(index * 0.01 for index in range(101))
        values = tuple(index / 100.0 for index in range(101))
        self.assertEqual(simplify_indices(times, values, 0.0), (0, 100))

    def test_hold_retains_linear_corners(self) -> None:
        times, values = benchmark_patterns()["hold"]
        indices = self.assert_error_bounded(times, values, 0.0)
        self.assertLessEqual(len(indices), 4)
        self.assertIn(10, indices)
        self.assertIn(30, indices)

    def test_short_peak_is_retained(self) -> None:
        times, values = benchmark_patterns()["short_peak"]
        indices = self.assert_error_bounded(times, values, 0.05)
        self.assertIn(values.index(max(values)), indices)

    def test_small_motion_respects_tolerance(self) -> None:
        times, values = benchmark_patterns()["small_motion"]
        high_indices = self.assert_error_bounded(times, values, 0.01)
        low_indices = self.assert_error_bounded(times, values, 0.05)
        self.assertGreaterEqual(len(high_indices), len(low_indices))

    def test_rapid_transition_respects_tolerance(self) -> None:
        times, values = benchmark_patterns()["rapid_transition"]
        indices = self.assert_error_bounded(times, values, 0.02)
        self.assertGreaterEqual(len(indices), 5)

    def test_tolerance_boundary_is_inclusive(self) -> None:
        times = (0.0, 0.5, 1.0)
        values = (0.0, 0.1, 0.0)
        indices = simplify_indices(times, values, 0.1)
        reconstructed = reconstruct_values(times, values, indices)
        self.assertEqual(indices, (0, 2))
        self.assertTrue(math.isclose(max(abs(a - b) for a, b in zip(values, reconstructed)), 0.1))

    def test_zero_and_one_weights_are_preserved_when_required(self) -> None:
        times = (0.0, 0.01, 0.02)
        values = (0.0, 1.0, 0.0)
        indices = self.assert_error_bounded(times, values, 0.05)
        self.assertEqual(indices, (0, 1, 2))

    def test_irregular_subframe_times_are_not_modified(self) -> None:
        times = (100.0, 100.24, 100.48, 100.72)
        values = (0.0, 0.5, 1.0, 0.0)
        indices = self.assert_error_bounded(times, values, 0.01)
        self.assertEqual(tuple(times[index] for index in indices), (100.0, 100.48, 100.72))

    def test_five_channels_are_independently_bounded(self) -> None:
        times = tuple(index * 0.01 for index in range(20))
        channels = tuple(
            tuple(((index * multiplier) % 7) / 6.0 for index in range(20))
            for multiplier in range(1, 6)
        )
        for channel in channels:
            self.assert_error_bounded(times, channel, 0.02)

    def test_randomized_curves_obey_max_error_contract(self) -> None:
        randomizer = random.Random(20260831)
        for tolerance in (0.0, 0.0025, 0.01, 0.02, 0.1):
            for _case in range(20):
                times = tuple(index * 0.01 for index in range(100))
                values = tuple(randomizer.random() for _index in times)
                self.assert_error_bounded(times, values, tolerance)

    def test_long_rapid_alternation_avoids_pathological_splitting(self) -> None:
        sample_count = 10_000
        times = tuple(index * 0.01 for index in range(sample_count))
        values = tuple(float(index % 2) for index in range(sample_count))
        indices = self.assert_error_bounded(times, values, 0.02)
        self.assertEqual(len(indices), sample_count)

    def test_invalid_input_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            simplify_indices((0.0,), (0.0, 1.0), 0.01)
        with self.assertRaises(ValueError):
            simplify_indices((0.0, 0.0), (0.0, 1.0), 0.01)
        with self.assertRaises(ValueError):
            simplify_indices((0.0, 0.01), (0.0, 1.0), -0.01)

    def test_quality_presets_and_custom_tolerance(self) -> None:
        self.assertIsNone(resolve_tolerance("ORIGINAL", 0.5))
        self.assertEqual(resolve_tolerance("HIGH", 0.5), PRESET_TOLERANCES["HIGH"])
        self.assertEqual(resolve_tolerance("MIDDLE", 0.5), PRESET_TOLERANCES["MIDDLE"])
        self.assertEqual(resolve_tolerance("LOW", 0.5), PRESET_TOLERANCES["LOW"])
        self.assertEqual(resolve_tolerance("CUSTOM", 0.0375), 0.0375)
        with self.assertRaises(ValueError):
            resolve_tolerance("CUSTOM", 1.1)


if __name__ == "__main__":
    unittest.main()
