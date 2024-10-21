"""
This module receives the XML data as a string and returns a dictionary (finalDict) which contains key/value pairs which
represent the source XML. It is an amalgam of bits and pieces across the web.

Credit for XmlDictConfig(): https://code.activestate.com/recipes/410469-xml-as-dictionary/
Credit for update_shim(): https://stackoverflow.com/users/3871670/adam-clark
Credit for flatten_dict(): https://codereview.stackexchange.com/users/1659/winston-ewert
"""
from xml.etree import ElementTree

try:
    import indigo  # noqa
except ImportError:
    pass


class XmlDictConfig(dict):
    """ placeholder docstring """

    def __init__(self, parent_element):
        super().__init__()

        if parent_element.items():
            self.update_shim(dict(parent_element.items()))

        for element in parent_element:
            if len(element):
                a_dict = XmlDictConfig(element)

                if element.items():
                    a_dict.update_shim(dict(element.items()))
                self.update_shim({element.tag: a_dict})

            elif element.items():
                # This line added to handle when value and attribs are both present.
                self.update_shim({element.tag: element.text})
                # This line added to create a unique element.tag for attribs.
                element_tag_attribs = element.tag + '_A_t_t_r_i_b_s'
                # This line modded to use new element.tag + '_Attribs'.
                self.update_shim({element_tag_attribs: dict(element.items())})
            else:
                # WAS: _self.update_shim({element.tag: element.text.strip()})_ with strip(), the function will choke on
                # some XML. 'NoneType' object has no attribute 'strip'.
                self.update_shim({element.tag: element.text})

    def update_shim(self, a_dict):  # noqa
        """ placeholder docstring """

        temp_dict = a_dict.copy()

        for key in temp_dict.keys():
            if key in self:
                value = self.pop(key)

                # if type(value) is not list:
                if not isinstance(value, list):
                    list_of_dicts = []  # noqa
                    list_of_dicts.append(value)
                    list_of_dicts.append(a_dict[key])
                    self.update({key: list_of_dicts})
                else:
                    value.append(a_dict[key])
                    self.update({key: value})
            else:
                self.update(a_dict)


def flatten_dict(d_to_flatten):
    """ placeholder docstring """

    def expand(key, value):

        if isinstance(value, dict):
            return [(key + '_' + k, v) for k, v in flatten_dict(value).items()]
        else:
            return [(key, value)]

    items = [item for k, v in d_to_flatten.items() for item in expand(k, v)]
    return dict(items)


def iterate_main(root):  # noqa
    """ placeholder docstring """

    try:
        root         = ElementTree.fromstring(root)
        xml_dict     = XmlDictConfig(root)
        flatxml_dict = flatten_dict(xml_dict)
        final_dict   = {}

        for (key, value) in flatxml_dict.items():

            final_dict[key] = value

            # See if any 'value' is another list. These lists may contain information for more values we want--for
            # example, when there are multiple instances of the same tag (with different attributes or values.)
            if isinstance(value, list):

                # If any lists found contain a dictionary, iterate over that dictionary and make more key/value pairs.
                # Also, this may need more counters depending on the depth of the source XML data.  Right now it only
                # goes so deep.
                counter = 1
                for value_item in value:

                    if isinstance(value_item, dict):
                        for (value_key1, value1) in value_item.items():
                            new_key1 = f"{key}_{counter}_{value_key1}"
                            final_dict[new_key1] = value1

                            if isinstance(value1, dict):
                                for (value_key2, value2) in value1.items():
                                    new_key2 = f"{key}_{counter}_{value_key1}_{value_key2}"
                                    final_dict[new_key2] = value2

                                if isinstance(value2, dict):
                                    for (value_key3, value3) in value2.items():
                                        new_key3 = f"{key}_{counter}_{value_key2}_{value_key3}"
                                        final_dict[new_key3] = value3
                    counter += 1

        # We may be left with values that contain lists of duplicates. Take the first one and leave the rest.
        for (key, value) in final_dict.items():
            if isinstance(value, list):
                final_dict[key] = value[0]

        # Find any remaining dicts, and delete them. This operation should ultimately determine if all the dict items
        # have already been pulled out to ensure that we don't lose anything.
        iter_dict = final_dict.copy()
        for (key, value) in iter_dict.items():
            if isinstance(value, dict):

                del final_dict[key]

        # Now that we're done, get rid of the placeholder Attribs tag component since we don't need it anymore.
        iter_dict = final_dict.copy()
        for (key, value) in iter_dict.items():
            del final_dict[key]
            key = key.replace('_A_t_t_r_i_b_s', "")
            final_dict[key] = value

    except Exception as err:  # noqa
        indigo.server.log(f"{err}", isError=True)
        indigo.server.log('There was a parse error. Check XML source.')
        final_dict = {'Response': 'Parse error. Check XML source.'}

    return final_dict
