import json
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator

from server import (
    BIRDS,
    MANGROVES,
    MockHandler,
    RequestTooLargeError,
    choose_species,
    has_valid_bearer_token,
    parse_body,
    validate_bind_security,
)


class ContractSmokeTest(unittest.TestCase):
    def test_species_catalog_has_four_mangroves(self):
        self.assertEqual(len(MANGROVES), 4)

    def test_mock_uses_uploaded_image_filename(self):
        species = choose_species("mangrove", {"_files": {"image": {"filename": "秋茄.jpg"}}})
        self.assertEqual(species["name"], "秋茄")

    def test_all_contract_endpoints_return_the_shared_envelope(self):
        handler = object.__new__(MockHandler)
        calls = [
            ("/api/recognition/species", {"mode": "mangrove", "_files": {"image": {"filename": "秋茄.jpg", "content": b"image"}}}),
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

    def test_knowledge_answers_follow_the_question(self):
        handler = object.__new__(MockHandler)
        cases = [
            ("红树有几种", "4 种", "knowledge/mangrove-species.md"),
            ("为什么红树林能防风浪", "波浪", "knowledge/ecosystem.md"),
            ("蓝碳是什么", "蓝碳", "knowledge/blue-carbon.md"),
            ("黑脸琵鹭是什么", "黑脸琵鹭", "knowledge/birds.md"),
        ]
        for question, expected, source in cases:
            with self.subTest(question=question):
                status, result = handler.route("/api/knowledge/ask", {"question": question})
                self.assertEqual(status, 200)
                self.assertIn(expected, result["data"]["answer"])
                self.assertIn(source, result["data"]["sources"])

    def test_knowledge_does_not_invent_an_answer_for_unknown_questions(self):
        handler = object.__new__(MockHandler)
        status, result = handler.route("/api/knowledge/ask", {"question": "今天天气怎么样"})
        self.assertEqual(status, 200)
        self.assertIn("没有收录", result["data"]["answer"])
        self.assertEqual(result["data"]["sources"], [])

    def test_invalid_recognition_request_returns_contract_error(self):
        handler = object.__new__(MockHandler)
        status, result = handler.route("/api/recognition/species", {"mode": "mangrove"})
        self.assertEqual(status, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_REQUEST")

    def test_recognition_requires_nonempty_image_field(self):
        handler = object.__new__(MockHandler)
        cases = [
            {"mode": "mangrove", "_files": {"photo": {"filename": "秋茄.jpg", "content": b"image"}}},
            {"mode": "mangrove", "_files": {"image": {"filename": "秋茄.jpg", "content": b""}}},
        ]
        for fields in cases:
            with self.subTest(fields=fields):
                status, result = handler.route("/api/recognition/species", fields)
                self.assertEqual(status, 400)
                self.assertFalse(result["success"])

    def test_reports_require_finite_coordinates_in_range(self):
        handler = object.__new__(MockHandler)
        base = {"type": "litter", "latitude": "20.1", "longitude": "110.2"}
        status, _ = handler.route("/api/reports", base)
        self.assertEqual(status, 200)
        for field, value in (("latitude", "north"), ("latitude", "91"), ("longitude", "181"), ("longitude", "NaN")):
            with self.subTest(field=field, value=value):
                status, result = handler.route("/api/reports", {**base, field: value})
                self.assertEqual(status, 400)
                self.assertFalse(result["success"])

    def test_observation_reports_require_a_catalog_species(self):
        handler = object.__new__(MockHandler)
        fields = {"type": "observation", "speciesId": "benthic-unknown", "latitude": "20.1", "longitude": "110.2"}
        status, result = handler.route("/api/reports", fields)
        self.assertEqual(status, 400)
        self.assertFalse(result["success"])

    def test_observation_reports_reject_non_string_species_id(self):
        handler = object.__new__(MockHandler)
        fields = {"type": "observation", "speciesId": [], "latitude": "20.1", "longitude": "110.2"}
        status, result = handler.route("/api/reports", fields)
        self.assertEqual(status, 400)
        self.assertFalse(result["success"])

    def test_oversized_request_is_rejected_before_body_read(self):
        class FakeHandler:
            headers = {"Content-Length": "5", "Content-Type": "application/json"}
            rfile = BytesIO(b"{}   ")

        with patch("server.MAX_REQUEST_BYTES", 4):
            with self.assertRaises(RequestTooLargeError):
                parse_body(FakeHandler())

    def test_tts_rejects_oversized_text(self):
        handler = object.__new__(MockHandler)
        status, result = handler.route(
            "/api/audio/tts",
            {"text": "x" * 2001, "language": "zh-CN"},
        )
        self.assertEqual(status, 400)
        self.assertFalse(result["success"])

    def test_nonlocal_bind_requires_api_token(self):
        with self.assertRaises(ValueError):
            validate_bind_security("0.0.0.0", "")
        validate_bind_security("0.0.0.0", "local-dev-token")
        validate_bind_security("127.0.0.1", "")

    def test_bearer_token_is_required_when_configured(self):
        self.assertFalse(has_valid_bearer_token("", "local-dev-token"))
        self.assertFalse(has_valid_bearer_token("Bearer wrong", "local-dev-token"))
        self.assertTrue(has_valid_bearer_token("Bearer local-dev-token", "local-dev-token"))
        handler = object.__new__(MockHandler)
        handler.server = SimpleNamespace(api_token="local-dev-token")
        handler.headers = {"Authorization": "Bearer wrong"}
        self.assertFalse(handler.authorized())
        handler.headers = {"Authorization": "Bearer local-dev-token"}
        self.assertTrue(handler.authorized())

    def test_cors_only_allows_explicit_origins(self):
        from server import allowed_cors_origin

        self.assertEqual(allowed_cors_origin("null", ""), "null")
        self.assertIsNone(allowed_cors_origin("https://evil.example", ""))
        self.assertEqual(
            allowed_cors_origin("https://demo.example", "https://demo.example"),
            "https://demo.example",
        )
        self.assertIsNone(
            allowed_cors_origin("https://evil.example", "https://demo.example")
        )

    def test_http_enforces_auth_and_request_size(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        server.api_token = "local-dev-token"
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address

        def request(method, path, body=None, headers=None):
            connection = HTTPConnection(host, port, timeout=3)
            try:
                connection.request(method, path, body=body, headers=headers or {})
                response = connection.getresponse()
                response.read()
                return response.status
            finally:
                connection.close()

        try:
            self.assertEqual(request("GET", "/api/health"), 401)
            self.assertEqual(request("GET", "/api/health", headers={"Authorization": "Bearer local-dev-token"}), 200)
            with patch("server.MAX_REQUEST_BYTES", 4):
                self.assertEqual(
                    request(
                        "POST",
                        "/api/knowledge/ask",
                        body=b"12345",
                        headers={
                            "Authorization": "Bearer local-dev-token",
                            "Content-Type": "application/json",
                        },
                    ),
                    413,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_examples_validate_against_json_schemas(self):
        root = Path(__file__).resolve().parents[2]
        examples = [
            ("data/species.schema.json", "data/species.example.json", False),
            ("data/sites.schema.json", "data/sites.example.json", True),
        ]
        for schema_path, example_path, is_array in examples:
            with self.subTest(path=example_path):
                schema = json.loads((root / schema_path).read_text(encoding="utf-8"))
                example = json.loads((root / example_path).read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)
                items = example if is_array else [example]
                validator = Draft202012Validator(schema)
                for item in items:
                    validator.validate(item)

    def test_mock_species_ids_and_names_exist_in_shared_catalog(self):
        root = Path(__file__).resolve().parents[2]
        catalog = json.loads((root / "data/species.catalog.json").read_text(encoding="utf-8"))
        by_id = {item["speciesId"]: item for item in catalog}
        self.assertEqual(len(by_id), len(catalog), "catalog speciesId 必须唯一")
        for mock_species in [*MANGROVES.values(), *BIRDS.values()]:
            with self.subTest(speciesId=mock_species["speciesId"]):
                self.assertIn(mock_species["speciesId"], by_id)
                self.assertEqual(mock_species["name"], by_id[mock_species["speciesId"]]["name"])


if __name__ == "__main__":
    unittest.main()
