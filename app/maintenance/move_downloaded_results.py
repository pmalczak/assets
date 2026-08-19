# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ACTION_MOVED = "przeniesiony"
ACTION_DELETED_EMPTY = "usunięty (pusty)"
ACTION_SKIPPED = "pominięty"

KIND_MBANK = "mBank"
KIND_REVOLUT = "Revolut"
KIND_OBLIGACJE = "obligacje skarbowe"
KIND_TRADEREPUBLIC = "Trade Republic"
KIND_DEGIRO = "DEGIRO"

NO_DESTINATION = "—"

DISPLAY_COLUMNS = {
    "source": "Źródło",
    "destination": "Miejsce docelowe",
    "action": "Akcja",
    "kind": "Typ",
}


@dataclass(frozen=True)
class MoveResult:
    source: Path
    destination: Path | None
    action: str
    kind: str

    def to_row(self) -> dict[str, str]:
        return {
            "source": str(self.source),
            "destination": str(self.destination) if self.destination is not None else NO_DESTINATION,
            "action": self.action,
            "kind": self.kind,
        }


def results_to_dataframe(results: list[MoveResult]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame(columns=list(DISPLAY_COLUMNS.keys()))

    df = pd.DataFrame([result.to_row() for result in results])
    return df[list(DISPLAY_COLUMNS.keys())].rename(columns=DISPLAY_COLUMNS)
