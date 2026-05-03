"""
The purpose of this __init__ files is to allow the `tests` folder to function as a module.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'GhostXML.indigoPlugin', 'Contents', 'Server Plugin'))

__all__ = [
    'test_xml',
    'test_plugin'
]
