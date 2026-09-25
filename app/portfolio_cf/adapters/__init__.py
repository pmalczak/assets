# -*- coding: utf-8 -*-
from __future__ import annotations

from portfolio_cf.adapters.bonds import adapt_bonds_ledger
from portfolio_cf.adapters.catalog import adapt_catalog_ledger
from portfolio_cf.adapters.degiro import adapt_degiro_ledger
from portfolio_cf.adapters.deposits import adapt_deposits_ledger
from portfolio_cf.adapters.robo import adapt_robo_ledger
from portfolio_cf.adapters.xtb import adapt_xtb_ledger

__all__ = [
    "adapt_bonds_ledger",
    "adapt_catalog_ledger",
    "adapt_degiro_ledger",
    "adapt_deposits_ledger",
    "adapt_robo_ledger",
    "adapt_xtb_ledger",
]
