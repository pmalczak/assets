# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

import pandas as pd

pd.options.mode.copy_on_write = True
pd.options.future.infer_string = True


def main():
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
