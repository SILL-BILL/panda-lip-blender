from __future__ import annotations

import math
import unittest
from pathlib import Path

from panda_lip_blender.validation import (
    PandaLipValidationError,
    load_pandalip,
    validate_document,
)
from tests.helpers import copy_document, valid_document

FIXTURES = Path(__file__).parent / "fixtures"


class ValidationTests(unittest.TestCase):
    def test_valid_pandalip_and_boundary_weights(self) -> None:
        data = validate_document(valid_document())
        self.assertEqual(len(data.samples), 3)
        self.assertEqual(data.samples[0].weights[0], 0.0)
        self.assertEqual(data.samples[1].weights[0], 1.0)

    def test_invalid_json(self) -> None:
        with self.assertRaisesRegex(PandaLipValidationError, "Invalid PandaLip JSON"):
            load_pandalip(FIXTURES / "invalid_json.pandalip")

    def test_wrong_version(self) -> None:
        document = copy_document()
        document["version"] = 2
        with self.assertRaisesRegex(PandaLipValidationError, "version 1"):
            validate_document(document)

    def test_missing_top_level_channels(self) -> None:
        document = copy_document()
        del document["channels"]
        with self.assertRaisesRegex(PandaLipValidationError, "channels"):
            validate_document(document)

    def test_wrong_channel_order(self) -> None:
        document = copy_document()
        document["channels"] = ["I", "A", "U", "E", "O"]
        with self.assertRaisesRegex(PandaLipValidationError, "exactly"):
            validate_document(document)

    def test_missing_sample_channel(self) -> None:
        document = copy_document()
        del document["samples"][1]["E"]
        with self.assertRaisesRegex(PandaLipValidationError, r"samples\[1\]\.E"):
            validate_document(document)

    def test_empty_samples(self) -> None:
        document = copy_document()
        document["samples"] = []
        with self.assertRaisesRegex(PandaLipValidationError, "non-empty"):
            validate_document(document)

    def test_non_increasing_sample_time(self) -> None:
        document = copy_document()
        document["samples"][2]["time"] = 0.01
        with self.assertRaisesRegex(PandaLipValidationError, "strictly increasing"):
            validate_document(document)

    def test_invalid_weights(self) -> None:
        for value in (-0.01, 1.01, math.nan, math.inf, "one", True):
            with self.subTest(value=value):
                document = copy_document()
                document["samples"][1]["A"] = value
                with self.assertRaises(PandaLipValidationError):
                    validate_document(document)

    def test_formal_metadata_is_validated(self) -> None:
        mutations = (
            ("audio", "duration", -1),
            ("audio", "sample_rate", 0),
            ("analysis", "mode", "other"),
            ("analysis", "hop_seconds", 0),
            ("analysis", "sensitivity", 1.1),
        )
        for section, field, value in mutations:
            with self.subTest(path=f"{section}.{field}"):
                document = copy_document()
                document[section][field] = value
                with self.assertRaises(PandaLipValidationError):
                    validate_document(document)

    def test_file_checks_extension_and_existence(self) -> None:
        with self.assertRaisesRegex(PandaLipValidationError, "extension"):
            load_pandalip("missing.json")
        with self.assertRaisesRegex(PandaLipValidationError, "does not exist"):
            load_pandalip("missing.pandalip")

    def test_unknown_fields_are_accepted(self) -> None:
        document = copy_document()
        document["future_metadata"] = {"enabled": True}
        document["samples"][0]["confidence"] = 0.9
        data = validate_document(document)
        self.assertIn("future_metadata", data.document)

    def test_file_round_trip(self) -> None:
        self.assertEqual(len(load_pandalip(FIXTURES / "aiueo_ramp.pandalip").samples), 7)


if __name__ == "__main__":
    unittest.main()
