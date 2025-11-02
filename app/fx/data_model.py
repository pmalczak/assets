# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from importers.assets.data_model import AssetsDef
from importers.data_model_generic import GenericStructureClass


class LastFxCls(GenericStructureClass):
    FX = 'fx'
    DATE = AssetsDef.VALUE_DATE
    CURRENCY = AssetsDef.CURRENCY

    def expected_columns(self) -> set:
        result = {
            self.FX,
            self.DATE,
            self.CURRENCY,
        }
        return result


LastFx = LastFxCls()
