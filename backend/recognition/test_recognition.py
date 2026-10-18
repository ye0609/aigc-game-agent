import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from classifier import CentroidClassifier, FEATURE_SIZE, Image, image_feature
from dataset import load_catalog, validate_dataset
from api import model_is_ready, recognize
from train import split_by_group, train


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
        mangroves = [item for item in data if item["category"] == "mangrove"]
        self.assertEqual([item["name"] for item in mangroves], ["木榄", "秋茄", "桐花树", "白骨壤"])

    def test_group_split_keeps_capture_groups_intact(self):
        files = {
            "class-a": [Path("a-1.jpg"), Path("a-2.jpg"), Path("a-3.jpg"), Path("a-4.jpg")],
        }
        groups = {
            files["class-a"][0]: "tree-1",
            files["class-a"][1]: "tree-1",
            files["class-a"][2]: "tree-2",
            files["class-a"][3]: "tree-2",
        }
        training, validation, train_groups, validation_groups = split_by_group(files, groups)
        self.assertEqual(train_groups["class-a"], 1)
        self.assertEqual(validation_groups["class-a"], 1)
        train_ids = {groups[path] for path in training["class-a"]}
        validation_ids = {groups[path] for path in validation["class-a"]}
        self.assertFalse(train_ids & validation_ids)

    def test_group_split_rejects_class_with_only_one_group(self):
        path = Path("only-tree.jpg")
        with self.assertRaisesRegex(ValueError, "至少需要 2 个"):
            split_by_group({"class-a": [path]}, {path: "tree-1"})

    def test_health_check_does_not_accept_corrupt_model_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            corrupt_model = Path(temporary) / "model.npz"
            corrupt_model.write_bytes(b"not a model")
            self.assertFalse(model_is_ready(corrupt_model))
            fields = {"mode": "mangrove", "_files": {"image": {"filename": "photo.jpg", "content": b"image"}}}
            status, result = recognize(fields, corrupt_model)
            self.assertEqual(status, 200)
            self.assertTrue(result["data"]["fallbackRequired"])

    def test_health_check_requires_ready_for_demo_metrics(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            output = Path(temporary) / "model.npz"
            labels = [
                "mangrove-bruguiera-gymnorrhiza",
                "mangrove-kandelia-obovata",
                "mangrove-aegiceras-corniculatum",
                "mangrove-avicennia-marina",
            ]
            features = np.zeros((4, FEATURE_SIZE), dtype=np.float32)
            CentroidClassifier.fit(features, labels, labels).save(output)
            (output.with_name("metrics.json")).write_text(
                json.dumps({"validationAccuracy": 0.42, "readyForDemo": False}),
                encoding="utf-8",
            )
            self.assertFalse(model_is_ready(output))
            fields = {"mode": "mangrove", "_files": {"image": {"filename": "photo.jpg", "content": b"image"}}}
            status, result = recognize(fields, output)
            self.assertEqual(status, 200)
            self.assertTrue(result["data"]["fallbackRequired"])

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
            with (base / "images" / "groups.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["image", "group_id"])
                writer.writeheader()
                for item in catalog:
                    for index in range(4):
                        writer.writerow({
                            "image": f"{item['speciesId']}/image-{index}.png",
                            "group_id": f"{item['speciesId']}-tree-{index}",
                        })
            first_image = next((base / "images" / catalog[0]["speciesId"]).glob("*.png"))
            feature = image_feature(first_image.read_bytes())
            self.assertEqual(feature.size, FEATURE_SIZE)
            output = base / "model.npz"
            metrics = train(base / "images", ROOT / "data/species.catalog.json", output, min_per_class=4)
            self.assertTrue(output.exists())
            self.assertTrue(model_is_ready(output))
            self.assertEqual(metrics["validationSamples"], 4)
            self.assertEqual(metrics["validationSplit"], "grouped-by-group_id")
            self.assertEqual(set(metrics["validationGroups"].values()), {1})


if __name__ == "__main__":
    unittest.main()
