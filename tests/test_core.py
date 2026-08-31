from __future__ import annotations

import math
import unittest

from panda_lip_blender.core import action_base_name, effective_fps, times_to_frames


class TimingTests(unittest.TestCase):
    def test_common_frame_rates(self) -> None:
        for fps in (24, 30, 60):
            with self.subTest(fps=fps):
                self.assertEqual(times_to_frames((0.0, 1.0), 1, fps, 1.0), (1.0, 1.0 + fps))

    def test_fps_base_is_used(self) -> None:
        rate = effective_fps(30, 1.001)
        self.assertTrue(math.isclose(rate, 29.970029970029973))
        frames = times_to_frames((0.0, 1.0), 100, 30, 1.001)
        self.assertTrue(math.isclose(frames[0], 100.0))
        self.assertTrue(math.isclose(frames[1], 129.97002997002997))

    def test_start_frame_and_subframes_are_preserved(self) -> None:
        frames = times_to_frames((0.0, 0.01), 100, 24, 1.0)
        self.assertEqual(frames[0], 100.0)
        self.assertTrue(math.isclose(frames[1], 100.24))
        self.assertNotEqual(frames[1], round(frames[1]))

    def test_invalid_rate_is_rejected(self) -> None:
        for fps, fps_base in ((0, 1), (24, 0), (math.inf, 1), (24, math.nan)):
            with self.subTest(fps=fps, fps_base=fps_base):
                with self.assertRaises(ValueError):
                    effective_fps(fps, fps_base)

    def test_action_name_uses_file_stem(self) -> None:
        self.assertEqual(action_base_name("C:/take/voice.001.pandalip"), "PandaLip_voice.001")


if __name__ == "__main__":
    unittest.main()
