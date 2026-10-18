import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SPECIES_DIR = DATA_DIR / "species"

ALLOWED_FIELDS = {
    "speciesId",
    "name",
    "aliases",
    "category",
    "protectionLevel",
    "images",
    "description",
    "audio",
    "languages",
}
ALLOWED_DESCRIPTION_FIELDS = {"habitat", "behavior", "conservation"}
ALLOWED_AUDIO_FIELDS = {"birdCall", "explanation"}


class SpeciesDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((DATA_DIR / "species.schema.json").read_text(encoding="utf-8"))
        cls.catalog = json.loads((DATA_DIR / "species.catalog.json").read_text(encoding="utf-8"))
        cls.files = sorted(SPECIES_DIR.glob("*.json"))

    def load(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_has_four_mangrove_records(self):
        self.assertEqual(4, len(self.files), [path.name for path in self.files])

    def test_each_record_matches_schema(self):
        validator = Draft202012Validator(self.schema)
        for path in self.files:
            with self.subTest(path=path.name):
                record = self.load(path)
                errors = sorted(validator.iter_errors(record), key=lambda error: list(error.path))
                self.assertFalse(errors, [error.message for error in errors])

    def test_file_name_and_catalog_are_consistent(self):
        catalog = {item["speciesId"]: item for item in self.catalog}
        file_ids = {path.stem for path in self.files}
        mangrove_ids = {
            species_id for species_id, item in catalog.items() if item["category"] == "mangrove"
        }
        self.assertEqual(mangrove_ids, file_ids)
        for path in self.files:
            record = self.load(path)
            with self.subTest(path=path.name):
                self.assertEqual(path.stem, record["speciesId"])
                self.assertEqual(catalog[record["speciesId"]]["name"], record["name"])
                self.assertEqual("mangrove", record["category"])

    def test_required_content_is_filled(self):
        for path in self.files:
            record = self.load(path)
            with self.subTest(path=path.name):
                self.assertNotIn("待", record["protectionLevel"])
                self.assertTrue(record["images"])
                self.assertTrue(record["audio"]["explanation"])
                self.assertEqual({"zh-CN", "zh-HK", "en-US"}, set(record["languages"]))
                for field in ALLOWED_DESCRIPTION_FIELDS:
                    self.assertTrue(record["description"][field].strip())
                    self.assertNotIn("待", record["description"][field])
                for language, text in record["languages"].items():
                    self.assertTrue(text.strip(), language)
                    self.assertNotIn("待", text, language)

    def test_media_paths_point_to_expected_directories(self):
        for path in self.files:
            record = self.load(path)
            with self.subTest(path=path.name):
                for image in record["images"]:
                    self.assertTrue(image.startswith(f"assets/species/{record['speciesId']}/"), image)
                self.assertTrue(
                    record["audio"]["explanation"].startswith(
                        f"assets/audio/{record['speciesId']}/"
                    ),
                    record["audio"]["explanation"],
                )

    def test_no_custom_fields(self):
        for path in self.files:
            record = self.load(path)
            with self.subTest(path=path.name):
                self.assertLessEqual(set(record), ALLOWED_FIELDS)
                self.assertLessEqual(set(record["description"]), ALLOWED_DESCRIPTION_FIELDS)
                self.assertLessEqual(set(record["audio"]), ALLOWED_AUDIO_FIELDS)


if __name__ == "__main__":
    unittest.main()
