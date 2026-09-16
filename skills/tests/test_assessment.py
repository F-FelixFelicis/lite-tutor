import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assessment import grade_structured_answer


class StructuredAssessmentTests(unittest.TestCase):
    def test_choice_is_deterministic(self):
        passed = grade_structured_answer("choice", "a", "A")
        failed = grade_structured_answer("choice", "B", "A")
        self.assertEqual(passed[0], "校验通过")
        self.assertEqual(failed[0], "校验未通过")

    def test_true_false_accepts_chinese_labels(self):
        self.assertEqual(
            grade_structured_answer("true_false", "正确", True)[0],
            "校验通过",
        )
        self.assertEqual(
            grade_structured_answer("true_false", "错误", True)[0],
            "校验未通过",
        )

    def test_fill_requires_every_expected_blank(self):
        self.assertEqual(
            grade_structured_answer("fill", "栈；回溯", ["栈", "回溯"])[0],
            "校验通过",
        )
        result = grade_structured_answer("fill", "栈", ["栈", "回溯"])
        self.assertEqual(result[0], "校验未通过")
        self.assertIn("回溯", result[2])

    def test_open_answer_is_delegated(self):
        self.assertIsNone(
            grade_structured_answer("short_answer", "我的解释", None)
        )


if __name__ == "__main__":
    unittest.main()
