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

DEBUG_LABELS = {
    10: "Debugging Messages",
    20: "Informational Messages",
    30: "Warning Messages",
    40: "Error Messages",
    50: "Critical Errors Only"
}
