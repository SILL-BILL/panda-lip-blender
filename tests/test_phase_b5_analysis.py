from __future__ import annotations

import unittest

from tests.phase_b5_analysis import select_feature_windows


class PhaseB5AnalysisTests(unittest.TestCase):
    def test_selects_reproducible_feature_windows(self) -> None:
        times = tuple(index * 0.01 for index in range(180))
        weights: list[tuple[float, float, float, float, float]] = []
        for index in range(len(times)):
            row = [0.0] * 5
            if 10 <= index <= 16:
                row[0] = (0.0, 0.2, 0.6, 1.0, 0.6, 0.2, 0.0)[index - 10]
            if 30 <= index <= 36:
                row[1] = (0.0, 0.02, 0.06, 0.1, 0.06, 0.02, 0.0)[index - 30]
            if 50 <= index <= 70:
                row[2] = 0.4
            if 90 <= index <= 95:
                row[(index - 90) % 5] = 0.7
            if 130 <= index <= 150:
                row[3] = 0.3
            weights.append(tuple(row))  # type: ignore[arg-type]

        first = select_feature_windows(times, weights, ("A", "I", "U", "E", "O"))
        second = select_feature_windows(times, weights, ("A", "I", "U", "E", "O"))

        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {
                "short_pronunciation",
                "large_opening",
                "small_mouth",
                "rapid_transition",
                "long_vocalization",
                "zero_return",
                "long_silence",
                "continuous_speech",
            },
        )
        self.assertEqual(first["large_opening"].center_index, 13)
        self.assertEqual(first["small_mouth"].dominant_channel, "I")
        self.assertTrue(90 <= first["rapid_transition"].center_index <= 95)
        self.assertTrue(first["long_silence"].end_index > first["long_silence"].start_index)

    def test_rejects_invalid_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "equal length"):
            select_feature_windows((0.0,), (), ("A", "I", "U", "E", "O"))


if __name__ == "__main__":
    unittest.main()
