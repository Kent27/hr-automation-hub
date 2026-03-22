from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import date
from typing import Dict


@dataclass
class AutomationResult:
    automation: str
    ran: bool
    processed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    message: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class Automation(ABC):
    name: str

    @abstractmethod
    def should_run(self, run_date: date) -> bool:
        raise NotImplementedError

    @abstractmethod
    def run(self, run_date: date) -> AutomationResult:
        raise NotImplementedError
