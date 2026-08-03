from __future__ import annotations

from typing import Literal

from .cases_v1 import load_cases as load_v1_cases
from .cases_v2 import load_cases as load_v2_cases
from .schemas import GoldenCase

SuiteVersion = Literal["1.0", "2.0"]


def load_suite(version: SuiteVersion = "2.0") -> list[GoldenCase]:
    if version == "1.0":
        return load_v1_cases()
    return load_v2_cases()
