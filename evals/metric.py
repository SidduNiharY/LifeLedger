from typing import Any

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase


class CategoryMatchMetric(BaseMetric):
    threshold: float = 1.0
    name: str = "Category match"

    def __init__(self, threshold: float = 1.0) -> None:
        self.threshold = threshold
        self.score: float = 0.0
        self.success: bool = False
        self.async_mode = False
        self.verbose_mode = False

    @property
    def __name__(self) -> str:
        return "Category match"

    def measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        self.score = 1.0 if test_case.actual_output == test_case.expected_output else 0.0
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        return self.measure(test_case, *args, **kwargs)

    def is_successful(self) -> bool:
        return bool(self.success)
