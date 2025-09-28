# -*- coding: utf-8 -*-
__author__ = "pmalczak@gmail.com"

formatter = lambda x: f"       {x:,}".replace(",", " ")

int_formatter = lambda x: x.to_string(
    formatters={col: formatter for col in x.select_dtypes(include="int").columns})
