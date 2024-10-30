# FIXME - the latest version of FlatDict (4.0.0) doesn't presently work with the plugin. Reverting to the old version.
# FIXME -  as of 2024-10-30, FlatDict v4.0.0 still does not work with the plugin.
# """
# FlatDict is a dict object that allows for single level, delimited key/value pair mapping of nested dictionaries.
# """
# try:
#     from collections.abc import MutableMapping
# except ImportError:  # pragma: nocover
#     from collections import MutableMapping
# import sys
#
# __version__ = '4.0.0'
#
# NO_DEFAULT = object()
#
#
# class FlatDict(MutableMapping):
#     """:class:`~flatdict.FlatDict` is a dictionary object that allows for
#     single level, delimited key/value pair mapping of nested dictionaries.
#     The default delimiter value is ``:`` but can be changed in the constructor
#     or by calling :meth:`FlatDict.set_delimiter`.
#
#     """
#     _COERCE = dict
#
#     def __init__(self, value=None, delimiter=':', dict_class=dict):
#         super(FlatDict, self).__init__()
#         self._values = dict_class()
#         self._delimiter = delimiter
#         self.update(value)
#
#     def __contains__(self, key):
#         """Check to see if the key exists, checking for both delimited and
#         not delimited key values.
#
#         :param mixed key: The key to check for
#
#         """
#         if self._has_delimiter(key):
#             pk, ck = key.split(self._delimiter, 1)
#             return pk in self._values and ck in self._values[pk]
#         return key in self._values
#
#     def __delitem__(self, key):
#         """Delete the item for the specified key, automatically dealing with
#         nested children.
#
#         :param mixed key: The key to use
#         :raises: KeyError
#
#         """
#         if key not in self:
#             raise KeyError
#         if self._has_delimiter(key):
#             pk, ck = key.split(self._delimiter, 1)
#             del self._values[pk][ck]
#             if not self._values[pk]:
#                 del self._values[pk]
#         else:
#             del self._values[key]
#
#     def __eq__(self, other):
#         """Check for equality against the other value
#
#         :param other: The value to compare
#         :type other: FlatDict
#         :rtype: bool
#         :raises: TypeError
#
#         """
#         if isinstance(other, dict):
#             return self.as_dict() == other
#         elif not isinstance(other, self.__class__):
#             raise TypeError
#         return self.as_dict() == other.as_dict()
#
#     def __ne__(self, other):
#         """Check for inequality against the other value
#
#         :param other: The value to compare
#         :type other: dict or FlatDict
#         :rtype: bool
#
#         """
#         return not self.__eq__(other)
#
#     def __getitem__(self, key):
#         """Get an item for the specified key, automatically dealing with
#         nested children.
#
#         :param mixed key: The key to use
#         :rtype: mixed
#         :raises: KeyError
#
#         """
#         values = self._values
#         key = [key] if isinstance(key, int) else key.split(self._delimiter)
#         for part in key:
#             values = values[part]
#         return values
#
#     def __iter__(self):
#         """Iterate over the flat dictionary key and values
#
#         :rtype: Iterator
#         :raises: RuntimeError
#
#         """
#         return iter(self.keys())
#
#     def __len__(self):
#         """Return the number of items.
#
#         :rtype: int
#
#         """
#         return len(self.keys())
#
#     def __reduce__(self):
#         """Return state information for pickling
#
#         :rtype: tuple
#
#         """
#         return type(self), (self.as_dict(), self._delimiter)
#
#     def __repr__(self):
#         """Return the string representation of the instance.
#
#         :rtype: str
#
#         """
#         return '<{} id={} {}>"'.format(self.__class__.__name__, id(self),
#                                        str(self))
#
#     def __setitem__(self, key, value):
#         """Assign the value to the key, dynamically building nested
#         FlatDict items where appropriate.
#
#         :param mixed key: The key for the item
#         :param mixed value: The value for the item
#         :raises: TypeError
#
#         """
#         if isinstance(value, self._COERCE) and not isinstance(value, FlatDict):
#             value = self.__class__(value, self._delimiter)
#         if self._has_delimiter(key):
#             pk, ck = key.split(self._delimiter, 1)
#             if pk not in self._values:
#                 self._values[pk] = self.__class__({ck: value}, self._delimiter)
#                 return
#             elif not isinstance(self._values[pk], FlatDict):
#                 raise TypeError(
#                     'Assignment to invalid type for key {}'.format(pk))
#             self._values[pk][ck] = value
#         else:
#             self._values[key] = value
#
#     def __str__(self):
#         """Return the string value of the instance.
#
#         :rtype: str
#
#         """
#         return '{{{}}}'.format(', '.join(
#             ['{!r}: {!r}'.format(k, self[k]) for k in self.keys()]))
#
#     def as_dict(self):
#         """Return the :class:`~flatdict.FlatDict` as a :class:`dict`
#
#         :rtype: dict
#
#         """
#         out = dict({})
#         for key in self.keys():
#             if self._has_delimiter(key):
#                 pk, ck = key.split(self._delimiter, 1)
#                 if self._has_delimiter(ck):
#                     ck = ck.split(self._delimiter, 1)[0]
#                 if isinstance(self._values[pk], FlatDict) and pk not in out:
#                     out[pk] = {}
#                 if isinstance(self._values[pk][ck], FlatDict):
#                     out[pk][ck] = self._values[pk][ck].as_dict()
#                 else:
#                     out[pk][ck] = self._values[pk][ck]
#             else:
#                 out[key] = self._values[key]
#         return out
#
#     def clear(self):
#         """Remove all items from the flat dictionary."""
#         self._values.clear()
#
#     def copy(self):
#         """Return a shallow copy of the flat dictionary.
#
#         :rtype: flatdict.FlatDict
#
#         """
#         return self.__class__(self.as_dict(), delimiter=self._delimiter)
#
#     def get(self, key, d=None):
#         """Return the value for key if key is in the flat dictionary, else
#         default. If default is not given, it defaults to ``None``, so that this
#         method never raises :exc:`KeyError`.
#
#         :param mixed key: The key to get
#         :param mixed d: The default value
#         :rtype: mixed
#
#         """
#         try:
#             return self.__getitem__(key)
#         except KeyError:
#             return d
#
#     def items(self):
#         """Return a copy of the flat dictionary's list of ``(key, value)``
#         pairs.
#
#         .. note:: CPython implementation detail: Keys and values are listed in
#             an arbitrary order which is non-random, varies across Python
#             implementations, and depends on the flat dictionary's history of
#             insertions and deletions.
#
#         :rtype: list
#
#         """
#         return [(k, self.__getitem__(k)) for k in self.keys()]
#
#     def iteritems(self):
#         """Return an iterator over the flat dictionary's (key, value) pairs.
#         See the note for :meth:`flatdict.FlatDict.items`.
#
#         Using ``iteritems()`` while adding or deleting entries in the flat
#         dictionary may raise :exc:`RuntimeError` or fail to iterate over all
#         entries.
#
#         :rtype: Iterator
#         :raises: RuntimeError
#
#         """
#         for item in self.items():
#             yield item
#
#     def iterkeys(self):
#         """Iterate over the flat dictionary's keys. See the note for
#         :meth:`flatdict.FlatDict.items`.
#
#         Using ``iterkeys()`` while adding or deleting entries in the flat
#         dictionary may raise :exc:`RuntimeError` or fail to iterate over all
#         entries.
#
#         :rtype: Iterator
#         :raises: RuntimeError
#
#         """
#         for key in self.keys():
#             yield key
#
#     def itervalues(self):
#         """Return an iterator over the flat dictionary's values. See the note
#         :meth:`flatdict.FlatDict.items`.
#
#         Using ``itervalues()`` while adding or deleting entries in the flat
#         dictionary may raise a :exc:`RuntimeError` or fail to iterate over all
#         entries.
#
#         :rtype: Iterator
#         :raises: RuntimeError
#
#         """
#         for value in self.values():
#             yield value
#
#     def keys(self):
#         """Return a copy of the flat dictionary's list of keys.
#         See the note for :meth:`flatdict.FlatDict.items`.
#
#         :rtype: list
#
#         """
#         keys = []
#
#         for key, value in self._values.items():
#             if isinstance(value, (FlatDict, dict)):
#                 nested = [
#                     self._delimiter.join([str(key), str(k)])
#                     for k in value.keys()]
#                 keys += nested if nested else [key]
#             else:
#                 keys.append(key)
#
#         return keys
#
#     def pop(self, key, default=NO_DEFAULT):
#         """If key is in the flat dictionary, remove it and return its value,
#         else return default. If default is not given and key is not in the
#         dictionary, :exc:`KeyError` is raised.
#
#         :param mixed key: The key name
#         :param mixed default: The default value
#         :rtype: mixed
#
#         """
#         if key not in self and default != NO_DEFAULT:
#             return default
#         value = self[key]
#         self.__delitem__(key)
#         return value
#
#     def setdefault(self, key, default):
#         """If key is in the flat dictionary, return its value. If not,
#         insert key with a value of default and return default.
#         default defaults to ``None``.
#
#         :param mixed key: The key name
#         :param mixed default: The default value
#         :rtype: mixed
#
#         """
#         if key not in self:
#             self.__setitem__(key, default)
#         return self.__getitem__(key)
#
#     def set_delimiter(self, delimiter):
#         """Override the default or passed in delimiter with a new value. If
#         the requested delimiter already exists in a key, a :exc:`ValueError`
#         will be raised.
#
#         :param str delimiter: The delimiter to use
#         :raises: ValueError
#
#         """
#         for key in self.keys():
#             if delimiter in key:
#                 raise ValueError('Key {!r} collides with delimiter {!r}', key,
#                                  delimiter)
#         self._delimiter = delimiter
#         for key in self._values.keys():
#             if isinstance(self._values[key], FlatDict):
#                 self._values[key].set_delimiter(delimiter)
#
#     def update(self, other=None, **kwargs):
#         """Update the flat dictionary with the key/value pairs from other,
#         overwriting existing keys.
#
#         ``update()`` accepts either another flat dictionary object or an
#         iterable of key/value pairs (as tuples or other iterables of length
#         two). If keyword arguments are specified, the flat dictionary is then
#         updated with those key/value pairs: ``d.update(red=1, blue=2)``.
#
#         :param iterable other: Iterable of key, value pairs
#         :rtype: None
#
#         """
#         [self.__setitem__(k, v) for k, v in dict(other or kwargs).items()]
#
#     def values(self):
#         """Return a copy of the flat dictionary's list of values. See the note
#         for :meth:`flatdict.FlatDict.items`.
#
#         :rtype: list
#
#         """
#         return [self.__getitem__(k) for k in self.keys()]
#
#     def _has_delimiter(self, key):
#         """Checks to see if the key contains the delimiter.
#
#         :rtype: bool
#
#         """
#         return isinstance(key, str) and self._delimiter in key
#
#
# class FlatterDict(FlatDict):
#     """Like :class:`~flatdict.FlatDict` but also coerces lists and sets
#      to child-dict instances with the offset as the key. Alternative to
#      the implementation added in v1.2 of FlatDict.
#
#     """
#     _COERCE = list, tuple, set, dict, FlatDict
#     _ARRAYS = list, set, tuple
#
#     def __init__(self, value=None, delimiter=':', dict_class=dict):
#         self.original_type = type(value)
#         if self.original_type in self._ARRAYS:
#             value = {str(i): v for i, v in enumerate(value)}
#         super(FlatterDict, self).__init__(value, delimiter, dict_class)
#
#     def __setitem__(self, key, value):
#         """Assign the value to the key, dynamically building nested
#         FlatDict items where appropriate.
#
#         :param mixed key: The key for the item
#         :param mixed value: The value for the item
#         :raises: TypeError
#
#         """
#         if isinstance(value, self._COERCE) and \
#                 not isinstance(value, FlatterDict):
#             value = self.__class__(value, self._delimiter)
#         if self._has_delimiter(key):
#             pk, ck = key.split(self._delimiter, 1)
#             if pk not in self._values:
#                 self._values[pk] = self.__class__({ck: value}, self._delimiter)
#                 return
#             if getattr(self._values[pk], 'original_type',
#                        None) in self._ARRAYS:
#                 try:
#                     k, cck = ck.split(self._delimiter, 1)
#                     int(k)
#                 except ValueError:
#                     raise TypeError(
#                         'Assignment to invalid type for key {}{}{}'.format(
#                             pk, self._delimiter, ck))
#                 self._values[pk][k][cck] = value
#                 return
#             elif not isinstance(self._values[pk], FlatterDict):
#                 raise TypeError(
#                     'Assignment to invalid type for key {}'.format(pk))
#             self._values[pk][ck] = value
#         else:
#             self._values[key] = value
#
#     def as_dict(self):
#         """Return the :class:`~flatdict.FlatterDict` as a nested
#         :class:`dict`.
#
#         :rtype: dict
#
#         """
#         out = {}
#         for key in self.keys():
#             if self._has_delimiter(key):
#                 pk, ck = key.split(self._delimiter, 1)
#                 if self._has_delimiter(ck):
#                     ck = ck.split(self._delimiter, 1)[0]
#                 if isinstance(self._values[pk], FlatterDict) and pk not in out:
#                     if self._values[pk].original_type == tuple:
#                         out[pk] = tuple(self._child_as_list(pk))
#                     elif self._values[pk].original_type == list:
#                         out[pk] = self._child_as_list(pk)
#                     elif self._values[pk].original_type == set:
#                         out[pk] = set(self._child_as_list(pk))
#                     elif self._values[pk].original_type == dict:
#                         out[pk] = self._values[pk].as_dict()
#             else:
#                 if isinstance(self._values[key], FlatterDict):
#                     out[key] = self._values[key].original_type()
#                 else:
#                     out[key] = self._values[key]
#         return out
#
#     def _child_as_list(self, pk, ck=None):
#         """Returns a list of values from the child FlatterDict instance
#         with string based integer keys.
#
#         :param str pk: The parent key
#         :param str ck: The child key, optional
#         :rtype: list
#
#         """
#         if ck is None:
#             subset = self._values[pk]
#         else:
#             subset = self._values[pk][ck]
#         # Check if keys has delimiter, which implies deeply nested dict
#         keys = subset.keys()
#         if any(self._has_delimiter(k) for k in keys):
#             out = []
#             split_keys = {k.split(self._delimiter)[0] for k in keys}
#             for k in sorted(split_keys, key=lambda x: int(x)):
#                 if subset[k].original_type == tuple:
#                     out.append(tuple(self._child_as_list(pk, k)))
#                 elif subset[k].original_type == list:
#                     out.append(self._child_as_list(pk, k))
#                 elif subset[k].original_type == set:
#                     out.append(set(self._child_as_list(pk, k)))
#                 elif subset[k].original_type == dict:
#                     out.append(subset[k].as_dict())
#             return out
#
#         # Python prior 3.6 does not guarantee insertion order, remove it after
#         # EOL python 3.5 - 2020-09-13
#         if sys.version_info[0:2] < (3, 6):  # pragma: nocover
#             return [subset[k] for k in sorted(keys, key=lambda x: int(x))]
#         else:
#             return [subset[k] for k in keys]
#
"""
FlatDict is a dict object that allows for single level, delimited key/value
pair mapping of nested dictionaries.
"""

try:
    import indigo  # noqa
except ImportError:
    pass

__version__ = '1.2.0'


class FlatDict(dict):
    """:py:class:`~flatdict.FlatDict` is a dictionary object that allows for
    single level, delimited key/value pair mapping of nested dictionaries.
    The default delimiter value is ``:`` but can be changed in the constructor
    or by calling
    :py:class:`FlatDict.set_delimiter <flatdict.FlatDict.set_delimiter>`.

    """

    # The default delimiter value
    DELIMITER = ':'

    def __init__(self, value=None, delimiter=None, former_type=dict):
        super(FlatDict, self).__init__()

        self._values     = {}
        self._delimiter  = delimiter or self.DELIMITER
        self.former_type = former_type

        if isinstance(value, dict):
            for key in value.keys():
                # =============================
                # Added by DaveL17 - 2018-06-20
                # Note that flatdict will return an empty dict for empty lists and dicts --
                # i.e, {} for any ( [], {} ) and, and this will result in no device state
                # being created. By changing the value to 'None', we can coerce the state to
                # exist in the device after parsing.

                if value[key] in ([], {}):
                    value[key] = None
                # =============================
                self.__setitem__(key, value[key])

    def __contains__(self, key):
        if self._delimiter not in key:
            return key in self._values
        parent, child = key.split(self._delimiter, 1)
        return parent in self._values and child in self._values[parent]

    def __delitem__(self, key):
        if self._delimiter not in key:
            del self._values[key]
        else:
            parent, child = key.split(self._delimiter, 1)
            if parent in self._values and child in self._values[parent]:
                del self._values[parent][child]
                if not self._values[parent]:
                    del self._values[parent]

    def __getitem__(self, key):
        if self._delimiter not in key:
            return self._values[key]
        parent, child = key.split(self._delimiter, 1)
        if parent in self._values and child in self._values[parent]:
            return self._values[parent][child]
        else:
            raise KeyError(key)

    def __iter__(self):
        for key in self.keys():
            yield key

    def __len__(self):
        return len(self.keys())

    def __repr__(self):
        values = {}
        for key in self.keys():
            values[key] = self.__getitem__(key)
        return values.__repr__()

    def __setitem__(self, key, value):
        former_type = type(value)
        if isinstance(value, (list, tuple)):
            value = dict((str(i), v) for (i, v) in enumerate(value))
        if isinstance(value, dict) and not isinstance(value, FlatDict):
            value = FlatDict(value, self._delimiter, former_type=former_type)
        if self._delimiter in key:
            parent_key, child_key = key.split(self._delimiter, 1)
            if parent_key not in self._values:
                self._values[parent_key] = FlatDict(delimiter=self._delimiter)
            parent = self._values.get(parent_key)
            if not isinstance(parent, FlatDict):
                raise TypeError(
                    'Top level node is not a FlatDict: {0}'.format(
                        parent_key, type(self._values[parent_key])))
            self._values[parent_key][child_key] = value
        else:
            self._values[key] = value

    def __str__(self):
        values = {}
        for key in self.keys():
            values[key] = self.__getitem__(key)
        return values.__str__()

    def _key(self, parent, child):
        return self._delimiter.join([parent, child])

    def as_dict(self):
        """Return the flat dictionary as a dictionary.

        :rtype: dict

        """
        dict_out = {}
        for key in self._values.keys():
            value = self._values[key]
            if isinstance(value, FlatDict):
                if value.former_type == list:
                    dict_out[key] = [v for k, v in sorted(value.items())]
                    pass
                elif value.former_type == tuple:
                    dict_out[key] = tuple(v for k, v in sorted(value.items()))
                    pass
                elif value.former_type == dict:
                    dict_out[key] = value.as_dict()
            else:
                dict_out[key] = value
        return dict_out

    def clear(self):
        """Remove all items from the flat dictionary."""
        self._values.clear()

    def copy(self):
        """Return a shallow copy of the flat dictionary.

        :rtype: flatdict.FlatDict

        """
        values = {}
        for key in self.keys():
            values[key] = self.__getitem__(key)
        return values

    def get(self, key, d=None):
        """Return the value for key if key is in the flat dictionary, else
        default. If default is not given, it defaults to ``None``, so that this
        method never raises a ``KeyError``.

        :param mixed key: The key to get
        :param mixed d: The default value
        :rtype: mixed

        """
        if key not in self.keys():
            return self._values.get(key, d)
        return self.__getitem__(key)

    def has_key(self, key):
        """Check to see if the flat dictionary has a specific key.

        :param mixed key: The key to check for
        :rtype: bool

        """
        return key in self.keys()

    def items(self):
        """Return a copy of the flat dictionary's list of ``(key, value)``
        pairs.

        .. note:: CPython implementation detail: Keys and values are listed in \
        an arbitrary order which is non-random, varies across Python \
        implementations, and depends on the flat dictionary's history of \
        insertions and deletions.

        :rtype: list

        """
        items = list()
        for key in self.keys():
            items.append((key, self.__getitem__(key)))
        return items

    def iteritems(self):
        """Return an iterator over the flat dictionary's (key, value) pairs.
        See the note for :py:class:`FlatDict.items() <flatdict.FlatDict.items>`.

        Using ``iteritems()`` while adding or deleting entries in the flat
        dictionary may raise a ``RuntimeError`` or fail to iterate over all
        entries.

        :rtype: Iterator
        :raises: RuntimeError

        """
        for item in self.items():
            yield item

    def iterkeys(self):
        """Return an iterator over the flat dictionary's keys. See the note for
        :py:class:`FlatDict.items() <flatdict.FlatDict.items>`.

        Using ``iterkeys()`` while adding or deleting entries in the flat
        dictionary may raise a ``RuntimeError`` or fail to iterate over all
        entries.

        :rtype: Iterator
        :raises: RuntimeError

        """

        for key in self.keys():
            yield key

    def itervalues(self):
        """Return an iterator over the flat dictionary's values. See the note
        for :py:class:`FlatDict.items() <flatdict.FlatDict.items>`.

        Using ``itervalues()`` while adding or deleting entries in the flat
        dictionary may raise a ``RuntimeError`` or fail to iterate over all
        entries.

        :rtype: Iterator
        :raises: RuntimeError

        """
        for key in self.keys():
            yield self.__getitem__(key)

    def keys(self):
        """Return a copy of the flat dictionary's list of keys. See the note for
        :py:class:`FlatDict.items() <flatdict.FlatDict.items>`.

        :rtype: list

        """
        keys = list()
        for key in self._values.keys():
            if isinstance(self._values[key], FlatDict):
                child_keys = self._values[key].keys()
                for child in child_keys:
                    keys.append(self._key(key, child))
            else:
                keys.append(key)
        return keys

    def pop(self, key, default=None):
        """If key is in the flat dictionary, remove it and return its value,
        else return default. If default is not given and key is not in the
        dictionary, a ``KeyError`` is raised.

        :param mixed key: The key name
        :param mixed default: The default value
        :rtype: mixed

        """
        if key not in self.keys() and key not in self._values:
            return default
        if key in self._values:
            return self._values.pop(key, default)
        value = self.__getitem__(key)
        self.__delitem__(key)
        return value

    # 2020-01-10 DaveL17 changed default parameter to default=None in response to
    # PyCharm syntax checking; "Signature of method 'FlatDict.setdefault()' does
    # not match signature of base method in class 'dict'"
    def setdefault(self, key, default=None):
        """ If key is in the flat dictionary, return its value. If not,
        insert key with a value of default and return default.
        default defaults to ``None``.

        :param mixed key: The key name
        :param mixed default: The default value
        :rtype: mixed

        """
        if key not in self:
            self.__setitem__(key, default)
        return self.__getitem__(key)

    def set_delimiter(self, delimiter):
        """Override the default or passed in delimiter with a new value.

        :param str delimiter: The delimiter to use

        """
        self._delimiter = delimiter
        for key in self._values.keys():
            if isinstance(self._values[key], FlatDict):
                self._values[key].set_delimiter(delimiter)

    def update(self, other=None, **kwargs):
        """Update the flat dictionary with the key/value pairs from other,
        overwriting existing keys.

        ``update()`` accepts either another flat dictionary object or an
        iterable of key/value pairs (as tuples or other iterables of length
        two). If keyword arguments are specified, the flat dictionary is then
        updated with those key/value pairs: ``d.update(red=1, blue=2)``.

        :rtype: None

        """
        values = other or kwargs
        if values:
            for key in values:
                self.__setitem__(key, values[key])

    def values(self):
        """Return a copy of the flat dictionary's list of values. See the note
        for :py:class:`FlatDict.items() <flatdict.FlatDict.items>`.

        :rtype: list

        """
        values = list()
        for key in self.keys():
            values.append(self.__getitem__(key))
        return values
