import unittest
import json
from pathlib import Path

from server import MockHandler, MANGROVES, choose_species


class ContractSmokeTest(unittest.TestCase):
    def test_species_catalog_has_four_mangroves(self):
        self.assertEqual(len(MANGROVES), 4)

    def test_mock_uses_uploaded_image_filename(self):
        species = choose_species("mangrove", {"_files": {"image": {"filename": "秋茄.jpg"}}})
        self.assertEqual(species["name"], "秋茄")

    def test_all_contract_endpoints_return_the_shared_envelope(self):
        handler = object.__new__(MockHandler)
        calls = [
            ("/api/recognition/species", {"mode": "mangrove", "_files": {"image": {"filename": "秋茄.jpg"}}}),
            ("/api/knowledge/ask", {"question": "为什么红树林能防风浪？"}),
            ("/api/knowledge/explain", {"speciesId": "mangrove-bruguiera-gymnorrhiza"}),
            ("/api/audio/tts", {"text": "欢迎来到红树林。", "language": "zh-CN"}),
            ("/api/reports", {"type": "observation", "speciesId": "mangrove-bruguiera-gymnorrhiza", "latitude": "20.12", "longitude": "110.32"}),
        ]
        for path, fields in calls:
            with self.subTest(path=path):
                status, result = handler.route(path, fields)
                self.assertEqual(status, 200)
                self.assertEqual(set(result), {"requestId", "success", "data", "error"})
                self.assertTrue(result["success"])
                self.assertIsNone(result["error"])

    def test_invalid_recognition_request_returns_contract_error(self):
        handler = object.__new__(MockHandler)
        status, result = handler.route("/api/recognition/species", {"mode": "mangrove"})
        self.assertEqual(status, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_REQUEST")

    def test_shared_json_files_parse(self):
        root = Path(__file__).resolve().parents[2]
        for relative_path in (
            "data/species.schema.json",
            "data/species.example.json",
            "data/sites.schema.json",
            "data/sites.example.json",
        ):
            with self.subTest(path=relative_path):
                json.loads((root / relative_path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
