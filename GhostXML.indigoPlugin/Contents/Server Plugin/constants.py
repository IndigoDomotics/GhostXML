"""
Repository of application constants

The constants.py file contains all application constants and is imported as a
library. References are denoted as constants by the use of all caps.
"""


def __init__():
    pass


CHARS_TO_REPLACE = {'_ghostxml_': '_', '+': '_plus_', '-': '_minus_', 'true': 'True', 'false':
                    'False', ' ': '_', ':': '_colon_', '.': '_dot_', '@': 'at_'}

CHARS_TO_REMOVE = ['/', '(', ')']

CURRENT_DEBUG_LEVEL = {10: 'Debug', 20: 'Info', 30: 'Warning', 40: 'Error', 50: 'Critical'}
