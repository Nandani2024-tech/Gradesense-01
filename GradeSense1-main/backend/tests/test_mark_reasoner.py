import unittest
from app.layers.ai_structured.mark_reasoner import resolve_marks

class TestMarkReasoner(unittest.TestCase):

    def test_resolve_simple_mark(self):
        # Update test to use expected question_structure format
        structure = {
            "questions": [
                {"number": 1, "marks": 5.0, "answer": "Sample answer"}
            ]
        }
        result = resolve_marks(structure)
        # Check if the result contains the resolved structure and marks
        self.assertIn("resolved_structure", result)
        self.assertEqual(result["effective_total_marks"], 5.0)

    def test_resolve_with_conflict(self):
        # Update test to use expected question_structure format
        structure = {
            "questions": [
                {"number": 1, "marks": 4.0, "answer": "A"},
                {"number": 2, "marks": 6.0, "answer": "B"}
            ]
        }
        result = resolve_marks(structure)
        self.assertEqual(result["effective_total_marks"], 10.0)

if __name__ == "__main__":
    unittest.main()
