"""
OverLang Types — Core dataclasses for .over workflow specs.

OverStep: single workflow step (action → outputs).
OverWorkflow: full workflow (intent → artifact → receipt → value).
"""

from dataclasses import dataclass, field


@dataclass
class OverStep:
    step_num: int
    action: str
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    receipt: bool = True


@dataclass
class OverWorkflow:
    name: str = ""
    intent: str = ""
    steps: list[OverStep] = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    receipts: list = field(default_factory=list)
    value_claim: str = ""
