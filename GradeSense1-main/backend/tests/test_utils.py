# tests/grading/test_utils.py
import unittest
from app.services.grading.utils import _to_float, _normalize_sub_id, _normalize_quality, _extract_attempt_k_of_n

class TestUtils(unittest.TestCase):

    def test_to_float(self):
        self.assertEqual(_to_float("3.5"), 3.5)
        self.assertEqual(_to_float(None, 5.0), 5.0)
        self.assertEqual(_to_float("abc", 1.0), 1.0)

    def test_normalize_sub_id(self):
        self.assertEqual(_normalize_sub_id(" A-1 "), "a1")
        self.assertEqual(_normalize_sub_id(None), "")

    def test_normalize_quality(self):
        self.assertEqual(_normalize_quality(50), 0.5)
        self.assertEqual(_normalize_quality(0.8), 0.8)
        self.assertEqual(_normalize_quality(None), None)
        self.assertEqual(_normalize_quality(150), 1.0)

    def test_extract_attempt_k_of_n(self):
        self.assertEqual(_extract_attempt_k_of_n("Attempt any 3 out of 5 questions"), (3, 5))
        self.assertEqual(_extract_attempt_k_of_n("Attempt any two questions"), (2, None))
        self.assertEqual(_extract_attempt_k_of_n("No info here"), (None, None))

if __name__ == "__main__":
    unittest.main()
