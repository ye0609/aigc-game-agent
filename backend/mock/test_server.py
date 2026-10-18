import unittest

from server import MockHandler, MANGROVES


class ContractSmokeTest(unittest.TestCase):
    def test_species_catalog_has_four_mangroves(self):
        self.assertEqual(len(MANGROVES), 4)

    def test_contract_routes_are_present(self):
        routes = {"/api/recognition/species", "/api/knowledge/ask", "/api/knowledge/explain", "/api/audio/tts", "/api/reports"}
        source = MockHandler.route.__code__.co_consts
        for route in routes:
            self.assertIn(route, source)


if __name__ == "__main__":
    unittest.main()
