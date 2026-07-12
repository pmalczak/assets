# -*- coding: utf-8 -*-
from importers.data_model_generic import GenericStructureClass


class CashFlowEventCls(GenericStructureClass):
    ASSET_ID = "asset_id"
    DATE = "date"
    AMOUNT = "amount"
    CATEGORY = "category"
    SOURCE = "source"
    DESCRIPTION = "description"

    COLUMN_ORDER = (
        ASSET_ID,
        DATE,
        AMOUNT,
        CATEGORY,
        SOURCE,
        DESCRIPTION,
    )

    def expected_columns(self) -> set:
        return set(self.COLUMN_ORDER)


CashFlowEvent = CashFlowEventCls()
