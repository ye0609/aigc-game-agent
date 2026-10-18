import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from classifier import CentroidClassifier, FEATURE_SIZE, Image, image_feature
from dataset import load_catalog, validate_dataset
from api import recognize
from train import train


ROOT = Path(__file__).resolve().parents[2]


class DatasetTest(unittest.TestCase):
    def test_catalog_has_four_mangroves(self):
        catalog = load_catalog(ROOT / "data/species.catalog.json")
        self.assertEqual(len(catalog), 4)
        self.assertTrue(all(item["category"] == "mangrove" for item in catalog))

    def test_empty_training_directory_is_reported_as_not_ready(self):
        report = validate_dataset(ROOT / "data/recognition", ROOT / "data/species.catalog.json", min_per_class=30)
        self.assertFalse(report["ready"])
        self.assertEqual(report["total"], 0)
        self.assertEqual(len(report["missing"]), 4)

    def test_catalog_is_valid_json(self):
        data = json.loads((ROOT / "data/species.catalog.json").read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in data], ["木榄", "秋茄", "桐花树", "白骨壤"])

    def test_classifier_predicts_nearest_class(self):
        features = np.vstack([np.zeros(FEATURE_SIZE), np.ones(FEATURE_SIZE)]).astype(np.float32)
        model = CentroidClassifier.fit(features, ["a", "b"], ["a", "b"])
        first = model.predict(np.zeros(FEATURE_SIZE, dtype=np.float32))
        second = model.predict(np.ones(FEATURE_SIZE, dtype=np.float32))
        self.assertEqual(first["label"], "a")
        self.assertEqual(second["label"], "b")
        self.assertTrue(0.0 <= first["confidence"] <= 0.99)

    def test_identical_centroids_have_no_confidence(self):
        features = np.zeros((2, FEATURE_SIZE), dtype=np.float32)
        model = CentroidClassifier.fit(features, ["a", "b"], ["a", "b"])
        self.assertEqual(model.predict(np.zeros(FEATURE_SIZE, dtype=np.float32))["confidence"], 0.0)

    def test_api_without_model_returns_manual_fallback(self):
        fields = {"mode": "mangrove", "_files": {"image": {"filename": "photo.jpg", "content": b"image"}}}
        status, result = recognize(fields, ROOT / "backend/recognition/artifacts/missing.npz")
        self.assertEqual(status, 200)
        self.assertTrue(result["data"]["fallbackRequired"])
        self.assertIsNone(result["data"]["speciesId"])

    def test_bird_model_not_claimed_as_ready(self):
        fields = {"mode": "bird", "_files": {"image": {"filename": "photo.jpg", "content": b"image"}}}
        status, result = recognize(fields)
        self.assertEqual(status, 200)
        self.assertTrue(result["data"]["fallbackRequired"])

    @unittest.skipIf(Image is None, "Pillow 尚未安装；CI 会安装并执行图像测试")
    def test_image_feature_and_training_pipeline(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            base = Path(temporary)
            catalog = load_catalog(ROOT / "data/species.catalog.json")
            colors = [(25, 60, 35), (70, 110, 40), (130, 160, 50), (190, 200, 80)]
            for item, color in zip(catalog, colors):
                directory = base / "images" / item["speciesId"]
                directory.mkdir(parents=True)
                for index in range(4):
                    Image.new("RGB", (20, 20), color).save(directory / f"image-{index}.png")
            first_image = next((base / "images" / catalog[0]["speciesId"]).glob("*.png"))
            feature = image_feature(first_image.read_bytes())
            self.assertEqual(feature.size, FEATURE_SIZE)
            output = base / "model.npz"
            metrics = train(base / "images", ROOT / "data/species.catalog.json", output, min_per_class=4)
            self.assertTrue(output.exists())
            self.assertEqual(metrics["validationSamples"], 4)


if __name__ == "__main__":
    unittest.main()
