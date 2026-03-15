# tests/grading/test_question_classifier.py
import unittest
from app.services.grading.question_classifier import classify_question_type

class TestQuestionClassifier(unittest.TestCase):

    def test_mcq_detection(self):
        q = {"question_text": "Choose the correct option: (A) Cat (B) Dog"}
        self.assertEqual(classify_question_type(q), "mcq")

    def test_fill_blank_detection(self):
        q = {"question_text": "Fill in the blank: The capital of France is ___."}
        self.assertEqual(classify_question_type(q), "fill_blank")

    def test_short_answer_detection(self):
        q = {"question_text": "Explain the process of photosynthesis in 50 words."}
        self.assertEqual(classify_question_type(q), "short_answer")

if __name__ == "__main__":
    unittest.main()
