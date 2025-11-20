# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"


class RevolutFileStateCls:
    CLOSED = 'ZAKOŃCZONO'
    PENDING = 'PENDING'
    REVERTED = 'REVERTED'

    def __init__(self):
        return

    def values(self) -> list:
        return [self.CLOSED, self.PENDING, self.REVERTED]


RevolutFileState = RevolutFileStateCls()
