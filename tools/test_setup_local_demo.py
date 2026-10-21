import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools import setup_local_demo as setup


class ManifestTest(unittest.TestCase):
    def test_production_manifest_matches_experiment_report(self):
        manifest = json.loads(setup.MANIFEST.read_text(encoding="utf-8"))
        report = json.loads(setup.REPORT.read_text(encoding="utf-8"))
        self.assertEqual(manifest["modelVersion"], "resnet18-expanded-onnx-v1")
        self.assertEqual(manifest["sha256"], report["modelSha256"])
        self.assertEqual(manifest["bytes"], report["modelBytes"])
        self.assertEqual(manifest["classes"], report["classes"])
        self.assertIs(report["readyForDemo"], False)
        self.assertGreaterEqual(report["developmentAccuracy"], 0.75)
        self.assertGreaterEqual(report["developmentSamples"], 20)

    def test_production_manifest_classes_match_catalog(self):
        manifest = json.loads(setup.MANIFEST.read_text(encoding="utf-8"))
        catalog = json.loads((setup.ROOT / "data/species.catalog.json").read_text(encoding="utf-8"))
        expected = {item["speciesId"] for item in catalog if item["category"] == "mangrove"}
        self.assertEqual(set(manifest["classes"]), expected)

    def test_verify_manifest_rejects_tampered_model(self):
        labels = json.loads(setup.MANIFEST.read_text(encoding="utf-8"))["classes"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.onnx"
            model.write_bytes(b"tiny fixture")
            digest = hashlib.sha256(model.read_bytes()).hexdigest()
            manifest = {
                "modelVersion": "resnet18-expanded-onnx-v1",
                "sha256": digest,
                "bytes": model.stat().st_size,
                "classes": labels,
            }
            report = {
                "modelSha256": digest,
                "modelBytes": model.stat().st_size,
                "readyForDemo": False,
                "developmentAccuracy": 0.9,
                "developmentSamples": 29,
                "classes": labels,
            }
            manifest_path = root / "manifest.json"
            report_path = root / "report.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            report_path.write_text(json.dumps(report), encoding="utf-8")
            setup.verify_manifest_and_report(manifest_path, report_path, model)
            model.write_bytes(b"tampered fixture")
            with self.assertRaises(SystemExit):
                setup.verify_manifest_and_report(manifest_path, report_path, model)

    def test_sha256_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.bin"
            path.write_bytes(b"abc")
            self.assertEqual(setup.sha256_file(path), hashlib.sha256(b"abc").hexdigest())
