import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SITES_PATH = DATA / "sites.json"
SCHEMA_PATH = DATA / "sites.schema.json"
SOURCES_PATH = ROOT / "docs" / "sites.sources.md"

ALLOWED_FIELDS = {
    "siteId",
    "name",
    "latitude",
    "longitude",
    "type",
    "description",
    "route",
    "birdWatchingShelters",
}
EXPECTED_IDS = {"gaoqiao", "texing", "jinniu"}
ZHANJIANG_LAT = (20.0, 21.8)
ZHANJIANG_LON = (109.5, 110.8)


class SiteDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.sites = json.loads(SITES_PATH.read_text(encoding="utf-8"))

    def test_has_three_expected_sites(self):
        self.assertIsInstance(self.sites, list)
        self.assertEqual(3, len(self.sites))
        self.assertEqual(EXPECTED_IDS, {site["siteId"] for site in self.sites})

    def test_each_site_matches_schema(self):
        validator = Draft202012Validator(self.schema)
        for site in self.sites:
            with self.subTest(site=site.get("siteId")):
                errors = sorted(validator.iter_errors(site), key=lambda error: list(error.path))
                self.assertFalse(errors, [error.message for error in errors])

    def test_coordinates_are_in_zhanjiang_and_not_fake(self):
        for site in self.sites:
            with self.subTest(site=site["siteId"]):
                lat, lon = site["latitude"], site["longitude"]
                self.assertIsNotNone(lat)
                self.assertIsNotNone(lon)
                self.assertTrue(ZHANJIANG_LAT[0] <= lat <= ZHANJIANG_LAT[1], lat)
                self.assertTrue(ZHANJIANG_LON[0] <= lon <= ZHANJIANG_LON[1], lon)
                self.assertFalse(lat == 0 and lon == 0)

    def test_route_and_shelters_are_arrays(self):
        for site in self.sites:
            with self.subTest(site=site["siteId"]):
                self.assertIsInstance(site["route"], list)
                self.assertIsInstance(site["birdWatchingShelters"], list)

    def test_empty_navigation_data_is_labeled(self):
        for site in self.sites:
            if not site["route"] or not site["birdWatchingShelters"]:
                with self.subTest(site=site["siteId"]):
                    self.assertIn("待现场 GPS 校准", site["description"])

    def test_route_points_are_valid_if_present(self):
        for site in self.sites:
            for point in site["route"]:
                with self.subTest(site=site["siteId"], point=point):
                    self.assertTrue(ZHANJIANG_LAT[0] <= point["latitude"] <= ZHANJIANG_LAT[1])
                    self.assertTrue(ZHANJIANG_LON[0] <= point["longitude"] <= ZHANJIANG_LON[1])

    def test_shelters_have_names_if_present(self):
        for site in self.sites:
            for shelter in site["birdWatchingShelters"]:
                with self.subTest(site=site["siteId"], shelter=shelter):
                    self.assertTrue(shelter["name"].strip())

    def test_source_document_lists_every_site(self):
        self.assertTrue(SOURCES_PATH.is_file())
        text = SOURCES_PATH.read_text(encoding="utf-8")
        for site in self.sites:
            self.assertIn(site["name"], text)

    def test_no_custom_fields(self):
        for site in self.sites:
            with self.subTest(site=site["siteId"]):
                self.assertLessEqual(set(site), ALLOWED_FIELDS)


if __name__ == "__main__":
    unittest.main()
