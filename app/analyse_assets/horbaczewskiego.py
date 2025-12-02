# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

from analyse_assets.data_model import AssetRw
from analyse_assets.select_asset import select_asset


def horbaczewskiego(df: pd.DataFrame, fout: Path, result: dict) -> pd.DataFrame:
    #
    m1   = (
        (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "07124067263111001055248115") # PEKAOSA - ARKADIUSZ GĄCIARZ KREDYT
        | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "33124067261111001052301556")  # ARKADIUSZ GĄCIARZ -ROR
    )
    m2 = (
        (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "28114020040000390279513454")
        | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "41102052421283117588515063")  #
        | (df[AssetRw.MBANK_ACCOUNT_NUMBER] == "45105000996029010194551607")  # TAURON
    )
    m3 = (
        (df[AssetRw.MBANK_TITLE].str.contains("DEPOZYT NOTARIALNY") &
         df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("KANCELARIA NOTARIALNA NATALIA ŁYSZCZAK ANNA PIKUŁA-SZUBA")) |

        (df[AssetRw.MBANK_TITLE].str.contains("ZALICZKA MIESZKANIE") &
         df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("BEDEKIER JACEK STANISŁAW           I BEDEKIER JUSTYNA")) |

        (df[AssetRw.MBANK_TITLE].str.contains("ZA MIESZKANIE") &
         df[AssetRw.MBANK_TRANSACTION_PARTY].str.contains("FILIP MALCZAK  UL.KIEMLICZÓW 9 M.4"))
    )
    m4 = (
        (df[AssetRw.MBANK_TITLE] == "TAURON HORBACZEWSKIEGO  ")
    ) #

    selector = m1 | m2 | m3 | m4
    return select_asset(df, selector, fout, result)
