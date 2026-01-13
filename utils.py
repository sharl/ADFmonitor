# -*- coding: utf-8 -*-
import os
import sys


def resource_path(path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.path.abspath('.'), path)
