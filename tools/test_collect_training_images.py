import csv
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import collect_training_images as collector


class DatasetManifestTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.species_id = "mangrove-kandelia-obovata"
        self.relative = f"{self.species_id}/IMG_0001.jpg"
        self.content = b"licensed-image-bytes"
        self.row = {
            "image": self.relative,
            "group_id": "inat-observation-123",
            "source_type": "iNaturalist",
            "species_name": "Kandelia obovata",
            "observation_id": "123",
            "photo_id": "456",
            "file_page": "https://www.inaturalist.org/observations/123",
            "photo_url": "https://example.org/image.jpg",
            "license": "cc-by",
            "artist": "Example photographer",
            "photographer_id": "789",
            "observed_on": "2026-10-18",
            "sha256": hashlib.sha256(self.content).hexdigest(),
        }
        self.write_manifests()
        self.original_root = collector.DATA_ROOT
        collector.DATA_ROOT = self.root

    def tearDown(self):
        collector.DATA_ROOT = self.original_root
        self.temp.cleanup()

    def write_manifests(self, source_rows=None, group_rows=None):
        source_rows = source_rows if source_rows is not None else [self.row]
        group_rows = group_rows if group_rows is not None else [
            {"image": self.relative, "group_id": self.row["group_id"]}
        ]
        with (self.root / "sources.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=collector.SOURCE_FIELDS)
            writer.writeheader()
            writer.writerows(source_rows)
        with (self.root / "groups.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["image", "group_id"])
            writer.writeheader()
            writer.writerows(group_rows)

    def test_existing_images_are_verified_without_network_access(self):
        path = self.root / self.relative
        path.parent.mkdir()
        path.write_bytes(self.content)
        self.assertEqual(collector.verify_existing(), 1)

    def test_missing_image_restores_only_matching_checksum(self):
        with patch.object(collector, "get_bytes", return_value=self.content):
            self.assertEqual(collector.verify_existing(restore_missing=True), 1)
        self.assertEqual((self.root / self.relative).read_bytes(), self.content)

    def test_checksum_mismatch_rejects_restored_image(self):
        with patch.object(collector, "get_bytes", return_value=b"different-image"):
            with self.assertRaisesRegex(ValueError, "SHA-256 不一致"):
                collector.verify_existing(restore_missing=True)

    def test_modified_local_image_is_rejected(self):
        path = self.root / self.relative
        path.parent.mkdir()
        path.write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "SHA-256 与来源清单不一致"):
            collector.verify_existing()

    def test_mismatched_group_manifest_is_rejected(self):
        self.write_manifests(group_rows=[])
        with self.assertRaisesRegex(ValueError, "sources.csv 与 groups.csv"):
            collector.verify_existing()

    def test_failed_new_collection_does_not_replace_existing_files(self):
        (self.root / "sources.csv").unlink()
        (self.root / "groups.csv").unlink()
        with patch.object(collector, "candidates", side_effect=RuntimeError("network interrupted")):
            with self.assertRaisesRegex(RuntimeError, "network interrupted"):
                collector.collect_new()
        self.assertFalse((self.root / self.species_id).exists())
        self.assertFalse((self.root / "sources.csv").exists())


if __name__ == "__main__":
    unittest.main()
