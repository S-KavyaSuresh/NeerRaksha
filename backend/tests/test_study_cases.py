import unittest

from fastapi.testclient import TestClient

from app.data.normalizer import normalized_name
from app.data.repository import StudyCaseRepository
from app.main import app


class StudyCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = StudyCaseRepository()
        cls.client = TestClient(app)

    def test_normalized_dam_names_match_file_names(self):
        self.assertEqual(normalized_name("HIRAKUD DAM"), normalized_name("hirakud_dam.tif"))

    def test_discovery_and_case_detail(self):
        cases = self.repository.list_study_cases()
        self.assertTrue(cases)
        self.assertTrue(all(case.dem_available for case in cases))
        case = self.repository.get_study_case(cases[0].case_id)
        self.assertIsNotNone(case.dem)
        self.assertTrue(case.data_quality.synthetic_data)

    def test_study_case_api(self):
        cases = self.client.get("/api/study-cases")
        self.assertEqual(cases.status_code, 200)
        case_id = cases.json()[0]["case_id"]
        self.assertEqual(self.client.get(f"/api/study-cases/{case_id}").status_code, 200)
        validation = self.client.get(f"/api/study-cases/{case_id}/validation")
        self.assertEqual(validation.status_code, 200)
        self.assertTrue(validation.json()["synthetic_data"])


if __name__ == "__main__":
    unittest.main()
