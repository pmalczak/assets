#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = "pmalczak@gmail.com"
CACHED = 'cached'
REFRESHED = 'refreshed'
DEPENDENT = 'dependent'


class DoRefresh(Exception):
    pass


class DirectoryNotInDataCache(Exception):
    pass
