# -*- coding: utf-8 -*-
__author__ = 'pmalczak@gmail.com'

import pandas as pd

from gnucash.file.account_solver import GnuAccountsSolver
from transactions_classifier.nn.obtain_model_a import read_model
from .write.save_gnucash_log import save_gnucash_log
from .write.write_transactions_as_log_file import write_transactions_as_log_file


iban_mappings = {
    '91922600050051124530000010': 'Rozliczenia:PLN:Agata Kruk',
    '22114020040000390278255957': 'Rozliczenia:PLN:Ewa Cymbor',

    '23114020040000350202832330': 'Aktywa:PLN:mbank_logs:23 eKonto (karta 5896)',
    '29114020040000390203424987': 'Aktywa:PLN:mbank_logs:29 eMax FF',
    '56114020040000350239788930': 'Aktywa:PLN:mbank_logs:56 eMax FEG',
    '43114020040000380239788920': 'Aktywa:PLN:mbank_logs:43 eMax plus',
    '34114020040000330239779142': 'Aktywa:PLN:mbank_logs:34 eMax zakup',

    '46114020040000310236992796': 'Aktywa:PLN:m_GM:46 eKonto',
    '23114020040000370241189039': 'Aktywa:PLN:m_GM:23 eMax Plus FEG',
    '50114020040000330241189040': 'Aktywa:PLN:m_GM:50 eMax Plus FD',
    '96114020040000310240630463': 'Aktywa:PLN:m_GM:96 eMax Plus FM',

    '26234000091290401000003553': 'Aktywa:PLN:BNP PARIBAS:26-rach',
    '06102010681230722311220258': 'Aktywa:PLN:PKO BP:PM',
    '49249000050000410085257842': 'Aktywa:PLN:Alior:49',

    '45102010680000190200000083': 'Inwestycje:OBLIGACJE SKARBOWE',

    '86234000385160101041103000': 'Karty:3665-MC',

    '24188000090000001150613000': 'Aktywa:EUR:DEGIRO',
    '56114020040000371215483217': 'Aktywa:EUR:m_GM:56 eKonto',
    '63114020040000381215513209': 'Aktywa:EUR:mbank_logs:63 eKonto',
}


def proc_mbank_transactions(mbank_transactions: pd.DataFrame,
                            gnucash_file, model_file, working_directory, gnu_log_file):

    gnu_account_solver = GnuAccountsSolver(gnucash_file=gnucash_file, iban_mappings=iban_mappings)

    model = read_model(model_file)
    log_content = write_transactions_as_log_file(model, mbank_transactions, gnu_account_solver)

    result = ''
    if log_content:
        result = save_gnucash_log(working_directory / gnu_log_file, log_content)
    return result
