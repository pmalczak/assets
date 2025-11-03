# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

from pathlib import Path

import pandas as pd

pd.options.mode.copy_on_write = True
pd.options.future.infer_string = True


def main():
    import chardet

    # input_file = Path(r'C:\Users\PiotrMalczak\Dropbox\INWESTYCJE\assets\p_re_pln\account-statement_2018-08-26_2025-11-03_pl-pl_790361.xlsx')

    x = [
        'Rodzaj,Produkt,Data rozpoczÄ™cia,Data zrealizowania,Opis,Kwota,OpĹ‚ata,Waluta,State,Saldo',
    ]

    # raw = pd.read_excel(input_file, header=None)

    def decode_cell(cell):
        if isinstance(cell, str):
            result = chardet.detect(cell)
            print(result)
            # try:
            #     return cell.encode('latin1').decode('utf-8')
            # except Exception as e:
            #     return cell
        else:
            raise ValueError
        return cell

    x = list(map(lambda x: decode_cell(x), x))
    # raw_decoded = raw.applymap(decode_cell)

    # Podziel kolumny po przecinku
    df = raw_decoded[0].str.split(',', expand=True)


def main_0():
    l = [
        'Jacek Jańczuk (Bank Spółdzielczy w Czyżewie)',
        'Dorota Kanach (Bank Spółdzielczy w Rzeszowie)',
        'Anna Karwat (Bank Spółdzielczy w Busku-Zdroju)',

        'Krzysztof Karwowski (Bank Spółdzielczy w Szczytnie)',

        'Tomasz Kasprzycki (Bank Spółdzielczy w Ropczycach)',

        'Dariusz Konofalski (Bank Spółdzielczy w Płońsku)',

        'Marek Kuklewski (Bank Spółdzielczy w Gogolinie)',

        'Łukasz Morzywołek (Bank Spółdzielczy w Rabie Wyżnej)',

        'Piotr Mulawa (Bank Spółdzielczy w Tarnogrodzie)',

        'Dorota Niewiadomska (Bank Spółdzielczy w Namysłowie)',

        'Mirosław Podebry (Bank Spółdzielczy w Cycowie)',

        'Piotr Żebrowski (Powiatowy Bank Spółdzielczy w Sokołowie Podlaskim)'
    ]

    l = list(map(lambda x: x.split(' '), l))
    for x in l:
        print(x[0])

    print()
    for x in l:
        print(x[1])

    l = list(map(lambda x: x[2:], l))
    l = list(map(lambda x: ' '.join(x), l))
    l = list(map(lambda x: x[1:-1], l))

    print()
    for x in l:
        print(x)

    return


if __name__ == '__main__':
    main()
