# -*- coding: utf-8 -*-
"""Jawny status pokrycia CF instrumentu (brak CF ≠ ciche zero)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CoverageStatus(str, Enum):
    COVERED = "COVERED"
    UNCOVERED = "UNCOVERED"
    EXCLUDED = "EXCLUDED"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class InstrumentCoverage:
    instrument_id: str
    status: CoverageStatus
    reason: str = ""
    venue: str = ""

    def to_row(self) -> dict[str, str]:
        return {
            "instrument_id": self.instrument_id,
            "status": self.status.value,
            "reason": self.reason,
            "venue": self.venue,
        }
