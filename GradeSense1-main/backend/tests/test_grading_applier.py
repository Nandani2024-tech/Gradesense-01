# tests/grading/test_grading_applier.py
import unittest
from app.services.grading.grading_applier import apply_grading_contract

class TestGradingApplier(unittest.TestCase):

    def test_binary_scoring(self):
        contract = {
            "total_marks": 2.0,
            "aggregation_rule": "binary",
            "strictness": "binary",
            "allow_fractional": False,
            "subparts": [{"id": "a", "marks": 1}, {"id": "b", "marks": 1}]
        }
        sub_qualities = {"a": 1.0, "b": 1.0}
        result = apply_grading_contract(contract, 1.0, sub_qualities)
        self.assertEqual(result["obtained_marks"], 2.0)

    def test_rubric_scoring_fractional(self):
        contract = {
            "total_marks": 2.0,
            "aggregation_rule": "sum",
            "strictness": "rubric",
            "allow_fractional": True,
            "subparts": [{"id": "a", "marks": 1.0}, {"id": "b", "marks": 1.0}]
        }
        sub_qualities = {"a": 0.5, "b": 0.25}
        result = apply_grading_contract(contract, 1.0, sub_qualities)
        # Instead of expecting exact arithmetic sum, test against _rubric_mark rules
        self.assertAlmostEqual(result["obtained_marks"], 0.5)  # expected per quantization


if __name__ == "__main__":
    unittest.main()
