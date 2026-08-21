# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd

from evaluators.broker_snapshot import BrokerSnapshotEvaluator
from evaluators.evaluate_broker_degiro import DegiroSnapshotEvaluator
from evaluators.evaluate_broker_revolut import RevolutRoboSnapshotEvaluator
from evaluators.evaluate_broker_traderepublic import TradeRepublicSnapshotEvaluator
from evaluators.evaluate_broker_xtb import XtbSnapshotEvaluator

BROKER_SNAPSHOT_EVALUATORS: tuple[BrokerSnapshotEvaluator, ...] = (
    DegiroSnapshotEvaluator(),
    XtbSnapshotEvaluator(),
    RevolutRoboSnapshotEvaluator(),
    TradeRepublicSnapshotEvaluator(),
)


def resolve_broker_snapshot_evaluator(
    assets_file_row: pd.Series,
) -> BrokerSnapshotEvaluator | None:
    for evaluator in BROKER_SNAPSHOT_EVALUATORS:
        if evaluator.matches(assets_file_row):
            return evaluator
    return None
