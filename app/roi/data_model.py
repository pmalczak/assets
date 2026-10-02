# -*- coding: utf-8 -*-
from importers.data_model_generic import GenericStructureClass


class CashFlowEventCls(GenericStructureClass):
    ASSET_ID = "asset_id"
    DATE = "date"
    AMOUNT = "amount"
    QUANTITY = "quantity"
    UNIT_PRICE = "unit_price"
    CATEGORY = "category"
    SOURCE = "source"
    DESCRIPTION = "description"
    TITLE = "title"
    COUNTERPARTY = "counterparty"
    ACCOUNT_NUMBER = "account_number"

    COLUMN_ORDER = (
        ASSET_ID,
        DATE,
        AMOUNT,
        QUANTITY,
        UNIT_PRICE,
        CATEGORY,
        SOURCE,
        DESCRIPTION,
        TITLE,
        COUNTERPARTY,
        ACCOUNT_NUMBER,
    )

    def expected_columns(self) -> set:
        return set(self.COLUMN_ORDER)


CashFlowEvent = CashFlowEventCls()
