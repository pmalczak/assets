# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from data_step.data_step import DATA_STEP

_APP_ROOT = Path(__file__).resolve().parent.parent


def get_data_steps_root(start: Path | None = None) -> Path:
    """Zwraca katalog data_steps w korzeniu projektu (nie app/data_steps)."""
    return DATA_STEP.find_data_step_root(start=start or _APP_ROOT)


def get_nbp_fx_cache_dir(start: Path | None = None) -> Path:
    """Katalog cache kursów NBP: ``data_steps/fx`` (nie root ``data_steps``)."""
    path = get_data_steps_root(start=start) / "fx"
    path.mkdir(parents=True, exist_ok=True)
    return path
