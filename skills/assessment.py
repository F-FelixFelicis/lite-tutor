"""Pure assessment helpers shared by the API and tests.

Objective question types are graded deterministically.  Only open-ended answers
need an LLM, which prevents the UI and the persisted learning record from
disagreeing about whether an answer was correct.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple


GradeResult = Tuple[str, List[str], str]


def _normalise(value: Any) -> str:
    return re.sub(r"[\s，,。；;：:、.!！？?()（）]+", "", str(value or "")).lower()


def _truth_value(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    normalised = _normalise(value)
    if normalised in {"true", "正确", "对", "是", "yes", "1"}:
        return True
    if normalised in {"false", "错误", "错", "否", "no", "0"}:
        return False
    return None


def grade_structured_answer(
    question_type: str,
    answer: str,
    expected_answer: Any,
) -> Optional[GradeResult]:
    """Grade an objective answer, or return ``None`` for an open answer."""

    q_type = (question_type or "").strip().lower()

    if q_type == "choice":
        expected = re.sub(r"[^A-Z]", "", str(expected_answer or "").upper())
        actual = re.sub(r"[^A-Z]", "", str(answer or "").upper())
        if not expected:
            return None
        passed = actual == expected
        feedback = (
            f"回答正确，正确选项是 {expected}。"
            if passed
            else f"回答不正确，正确选项是 {expected}。"
        )
        return ("校验通过" if passed else "校验未通过", [expected] if passed else [], feedback)

    if q_type == "true_false":
        expected = _truth_value(expected_answer)
        actual = _truth_value(answer)
        if expected is None:
            return None
        passed = actual is expected
        label = "正确" if expected else "错误"
        feedback = f"判断正确，答案是“{label}”。" if passed else f"判断不正确，答案是“{label}”。"
        return ("校验通过" if passed else "校验未通过", [label] if passed else [], feedback)

    if q_type == "fill":
        if isinstance(expected_answer, str):
            expected_items = [part for part in re.split(r"[;,；、]", expected_answer) if part.strip()]
        else:
            expected_items = [str(item) for item in (expected_answer or []) if str(item).strip()]
        if not expected_items:
            return None

        normalised_answer = _normalise(answer)
        matched = [item for item in expected_items if _normalise(item) in normalised_answer]
        passed = len(matched) == len(expected_items)
        if passed:
            feedback = "填空正确，所有关键答案都已覆盖。"
        else:
            missing = [item for item in expected_items if item not in matched]
            feedback = "还缺少：" + "、".join(missing) + "。"
        return ("校验通过" if passed else "校验未通过", matched, feedback)

    return None
