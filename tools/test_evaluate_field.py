import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.evaluate_field import evaluate, read_manifest


class FieldEvaluationTest(unittest.TestCase):
    def test_known_accuracy_and_unknown_fallback_are_separate(self):
        rows = [
            {"image": Path("known.jpg"), "speciesId": "mangrove-kandelia-obovata",
             "siteId": "a", "treeId": "1"},
            {"image": Path("unknown.jpg"), "speciesId": "unknown",
             "siteId": "b", "treeId": "2"},
        ]
        responses = [
            {"speciesId": "mangrove-kandelia-obovata", "confidence": 0.9,
             "fallbackRequired": False},
            {"speciesId": "mangrove-avicennia-marina", "confidence": 0.4,
             "fallbackRequired": True},
        ]
        with patch("tools.evaluate_field.upload", side_effect=responses):
            report = evaluate(rows, "http://127.0.0.1:5173", None)
        self.assertEqual(report["knownTop1Accuracy"], 1.0)
        self.assertEqual(report["fallbackRate"], 0.5)
        self.assertEqual(report["unknownFallbackRate"], 1.0)
        self.assertEqual(report["rawTop1Confusion"]["unknown"],
                         {"mangrove-avicennia-marina": 1})
        self.assertEqual(report["decisionConfusion"]["unknown"], {"fallback": 1})

    def test_manifest_rejects_training_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "photo.jpg").write_bytes(b"fixture")
            manifest = root / "manifest.csv"
            manifest.write_text(
                "image,speciesId,siteId,treeId,split\n"
                "photo.jpg,mangrove-kandelia-obovata,a,1,train\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "test"):
                read_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
