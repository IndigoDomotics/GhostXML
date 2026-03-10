"""
Unittests for the Indigo Plugin GhostXML.

These tests are directed at features and functions of the GhostXML plugin. They do not test other aspects of its
functionality--for example, the tests presume that an API command message is properly formatted since improperly
formatted command messages are handled by the IWS. As a part of confirming the test results, you should check the
Indigo events log to ensure that the output is expected. If this file becomes large, test classes can be split out into
individual test files.

All the tests in this file are meant to be run from the IDE (preferred) or from the command line (note that running it
from the command line will require some local package installs).

In PyCharm, locate /Tests/test.py, right-click and select `Run`. Alternatively, you can run each test class
individually.
"""
import os
import string
import sys
import unittest
import xml.etree.ElementTree as ET  # noqa
import httpx
import dotenv
import constants  # noqa
from curlcodes import codes as curlcodes  # noqa
from httpcodes import codes as httpcodes # noqa
import plugin_defaults  # noqa
from indigo_devices_filters import DEVICE_FILTERS  # noqa
sys.path.insert(1, '../')  # Server Plugin folder


class TestApiCommands(unittest.TestCase):
    """
    The TestApiCommands class contains unit tests for the plugin that are run through the Indigo API.
    """
    @classmethod
    def setUpClass(cls):
        """ Docstring placeholder """
        dotenv.load_dotenv()
        cls.api_secret: str = os.environ["API_SECRET"]
        cls.api_url: str = os.environ["SERVER_API_URL"]
        cls.api_base: str = os.environ["SERVER_API_BASE"]

    def send_api_command(self, msg: dict) -> httpx.Response:
        """ Docstring placeholder """
        headers = {'Authorization': f'Bearer {self.api_secret}'}
        return httpx.post(self.api_url, headers=headers, json=msg, verify=False)

    def send_api_base(self, feed: str, obj_id: int) -> httpx.Response:
        """
        For example, `self.send_api_base("indigo.devices", obj_id)`
        """
        headers = {'Authorization': f'Bearer {self.api_secret}'}
        url = f"{self.api_base}{feed}/{obj_id}"
        return httpx.get(url, headers=headers, verify=False)

    def test_refresh_data_for_device_action(self):
        """ Docstring placeholder """
        obj_id = 515336428
        message = {
            "id": self._testMethodName,
            "message": "indigo.actionGroup.execute",
            "objectId": obj_id
        }
        response = self.send_api_command(message)
        self.assertEqual(response.status_code, 200,
                         f"Expected status code: 200 -- got {response.status_code}: "
                         f"{httpcodes[response.status_code]} instead.")
        self.assertIsInstance(response.json(), dict)
        self.assertIn("success", response.json())
        # TODO: test that action actually ran.

    def test_refresh_data_for_all_devices_action(self):
        """ Docstring placeholder """
        obj_id = 99288135
        message = {
            "id": self._testMethodName,
            "message": "indigo.actionGroup.execute",
            "objectId": obj_id
        }
        response = self.send_api_command(message)
        self.assertEqual(response.status_code, 200, "Did not receive the expected status code: 200")
        self.assertIsInstance(response.json(), dict)
        self.assertIn("success", response.json())
        # TODO: test that action actually ran.

    def test_adjust_device_refresh_time_action(self):
        """ Docstring placeholder """
        obj_id = 433890464
        message = {
            "id": self._testMethodName,
            "message": "indigo.actionGroup.execute",
            "objectId": obj_id
        }
        response = self.send_api_command(message)
        self.assertEqual(response.status_code, 200, "Did not receive the expected status code: 200")
        self.assertIsInstance(response.json(), dict)
        self.assertIn("success", response.json())
        # TODO: test that action actually ran.


class TestConstants(unittest.TestCase):
    """
    Test constants.py file for structure and syntax.
    """
    def test_constants(self):
        """ Test constants file """
        chars_replace = constants.CHARS_TO_REPLACE
        self.assertIsInstance(chars_replace, dict, "Imported element is not a dict.")
        for key in chars_replace:
            self.assertIsInstance(key, str, f"Constants key [{key}] is not a string.")
            self.assertIsInstance(chars_replace[key], str, f"Constants [{key}] value is not a string.")

        chars_remove = constants.CHARS_TO_REMOVE
        self.assertIsInstance(chars_remove, list, "CHARS_TO_REMOVE is not a list.")
        for item in chars_remove:
            self.assertIsInstance(item, str, f"CHARS_TO_REMOVE[{item}] is not a string.")

        debug_labels = constants.DEBUG_LABELS
        self.assertIsInstance(debug_labels, dict, "DEBUG_LEVELS is not a dict.")
        for key in debug_labels:
            self.assertIsInstance(key, int, f"Debug levels key [{key}] is not an int.")
            self.assertIsInstance(debug_labels[key], str, f"Debug levels [{key}] value is not a string.")


class TestCurlCodes(unittest.TestCase):
    """
    Test `curlcodes.py` file for structure and syntax.
    """
    def test_curl_codes(self):
        """ Test curlcodes file """
        self.assertIsInstance(curlcodes, dict, "Imported element is not a dict.")
        for key in curlcodes:
            self.assertIsInstance(key, str, f"CURL codes key [{key}] is not a string.")
            self.assertIsInstance(curlcodes[key], str, f"CURL codes key [{key}] is not a string.")


class TestFlatDict(unittest.TestCase):
    """
    The TestFlatDict class is used to test the FlatDict module.
    """
    @classmethod
    def setUpClass(cls):
        cls.test_dict = {'a': 1, 'b': {'c': 3.7, 'd': 4, 'e': [1, 2, 3, 4], 'f': True}}

    def test_flat_dict(self):
        """ Test flat_dict module """
        import flatdict  # noqa
        self.assertIsInstance(flatdict.FlatDict(self.test_dict), flatdict.FlatDict,
                              "The flatdict module did not return a valid dict object.")


class TestHttpCodes(unittest.TestCase):
    """
    Test `httpcodes.py` file for structure and syntax.
    """
    def test_http_codes(self):
        """ Test httpcodes file """
        for key in httpcodes:
            self.assertIsInstance(key, int, f"HTTP Codes key [{key}] is not an int.")
            self.assertIsInstance(httpcodes[key], str, f"HTTP Codes [{key}] value is not a string.")
            self.assertFalse(httpcodes[key] == "", f"HTTP Codes [{key}] value shouldn't be an empty string.")


class TestPluginDefaults(unittest.TestCase):
    """
    The TestPluginDefaults class is used to test the `plugin_defaults.py` file.

    The `plugin_defaults.py` file contains the plugin's `kDefaultPluginPrefs` defaults.
    """
    def test_plugin_defaults(self):
        """ Docstring placeholder """
        prefs = plugin_defaults.kDefaultPluginPrefs
        self.assertIsInstance(prefs, dict, "Imported element is not a dict.")
        for key in prefs:
            # test the keys
            self.assertIsInstance(key, str, f"Preferences key [{key}] is not a string.")
            self.assertNotIn(' ', key, f"Preferences key [{key}] should not contain spaces.")
            self.assertFalse(any(char.isdigit() for char in key),
                             f"Preferences key [{key}] should not contain numbers.")
            self.assertFalse(any(char in string.punctuation for char in key),
                             f"Preferences key [{key}] should not contain punctuation.")
            self.assertFalse(key.lower().startswith('xml'),
                             f"Preferences key [{key}] should not start with 'xml'.")

            # test the values
            allowed_types = [str, int, float, bool]
            self.assertTrue(type(prefs[key]) in allowed_types,
                            f"Preferences key [{key}] value is not an allowed type.")


class TestXml(unittest.TestCase):
    """
    The TestXml class is used to test the various XML files that are part of a standard Indigo plugin.

    The files tested are listed in the setUpClass method below. The tests include checks for required elements (like
    element `id` and `type` attributes) and syntax.
    """
    @classmethod
    def setUpClass(cls):
        cls.xml_files   = ['../Actions.xml', '../MenuItems.xml', '../Devices.xml', '../Events.xml']
        cls.field_types = ['button', 'checkbox', 'colorpicker', 'label', 'list', 'menu', 'separator', 'textfield']
        # cls.ui_paths    = ['DeviceActions', 'hidden', 'NotificationActions', None]
        # Load the plugin.py code into a var for testing later.
        with open('../plugin.py', 'r') as infile:
            cls.plugin_lines = infile.read()

    @staticmethod
    def get_item_name(xml_file: str, item_id: int):
        """ Docstring placeholder """
        tree = ET.parse(xml_file)
        return tree.getroot()

    def test_xml_files(self):
        """ Docstring placeholder """
        try:
            for file_type in self.xml_files:
                try:
                    root = self.get_item_name(file_type, 0)
                except FileNotFoundError:
                    print(f"\"{file_type}\" file not present.")
                    continue
                for item in root:
                    # Test the 'id' attribute (required):
                    node_id = item.get('id')
                    self.assertIsNotNone(node_id,
                                         f"\"{file_type}\" element \"{item.tag}\" attribute 'id' is required.")
                    self.assertIsInstance(node_id, str, "id names must be strings.")
                    self.assertNotIn(' ', node_id, f"`id` names should not contain spaces.")

                    # Test the 'deviceFilter' attribute:
                    dev_filter = item.get('deviceFilter')
                    self.assertIsInstance(node_id, str, "`deviceFilter` values must be strings.")
                    if dev_filter:  # None if not specified in item attributes
                        self.assertIn(dev_filter, DEVICE_FILTERS, "'deviceFilter' values must be strings.")

                    # Test the 'uiPath' attribute:
                    ui_path = item.get('uiPath')
                    self.assertIsInstance(node_id, str, "uiPath names must be strings.")
                    # TODO: the uiPath value can essentially be anything as plugins can create their own uiPaths.
                    # self.assertIn(ui_path, self.ui_paths)

                # Test items that have a 'Name' element. The reference to `root.tag[:-1]` takes the tag name and
                # converts it to the appropriate child element name. For example, `Actions` -> `Action`, etc.
                for thing in root.findall(f"./{root.tag[:-1]}/Name"):
                    self.assertIsInstance(thing.text, str, "Action names must be strings.")

                # Test items that have a 'CallBackMethod` element:
                for thing in root.findall(f"./{root.tag[:-1]}/CallbackMethod"):
                    self.assertIsInstance(thing.text, str, "Action callback names must be strings.")
                    # We can't directly access the plugin.py file from here, so we read it into a variable instead.
                    # We then search for the string `def <CALLBACK METHOD>` within the file as a proxy to doing a
                    # `dir()` to see if it's in there.
                    self.assertTrue(f"def {thing.text}" in self.plugin_lines,
                                    f"The callback method \"{thing.text}\" does not exist in the plugin.py file.")

                # Test items that have a 'configUI' element
                for thing in root.findall(f"./{root.tag[:-1]}/ConfigUI/SupportURL"):
                    self.assertIsInstance(thing.text, str, "Config UI support URLs must be strings.")
                    result = httpx.get(thing.text).status_code
                    self.assertEqual(result, 200,
                                     f"ERROR: Got status code {result} -> {httpcodes[result]}.")

                # Test Config UI `Field` elements
                for thing in root.findall(f"./{root.tag[:-1]}/ConfigUI/Field"):
                    # Required attributes. Will throw a KeyError if missing.
                    self.assertIsInstance(thing.attrib['id'], str, "Config UI field IDs must be strings.")
                    self.assertFalse(thing.attrib['id'] == "", "Config UI field IDs must not be an empty string.")
                    self.assertIsInstance(thing.attrib['type'], str, "Config UI field types must be strings.")
                    self.assertIn(thing.attrib['type'], self.field_types,
                                  f"Config UI field types must be one of {self.field_types}.")
                    # Optional attributes
                    self.assertIsInstance(thing.attrib.get('defaultValue', ""), str,
                                          "Config UI defaultValue types must be strings.")
                    self.assertIsInstance(thing.attrib.get('enabledBindingId', ""), str,
                                          "Config UI enabledBindingId types must be strings.")
                    self.assertIsInstance(thing.attrib.get('enabledBindingNegate', ""), str,
                                          "Config UI enabledBindingNegate types must be strings.")
                    self.assertIn(thing.attrib.get('hidden', "false"), ['true', 'false'],
                                  f"Config UI hidden attribute must be 'true' or 'false'.")
                    self.assertIn(thing.attrib.get('readonly', "false"), ['true', 'false'],
                                  f"Config UI readonly attribute must be 'true' or 'false'.")
                    self.assertIn(thing.attrib.get('secure', "false"), ['true', 'false'],
                                  f"Config UI secure attribute must be 'true' or 'false'.")
                    self.assertIsInstance(thing.attrib.get('tooltip', ""), str,
                                          "Config UI field tool tips must be strings.")
                    self.assertIsInstance(thing.attrib.get('visibleBindingId', ""), str,
                                          "Config UI visibleBindingId types must be strings.")
                    self.assertIsInstance(thing.attrib.get('visibleBindingValue', ""), str,
                                          "Config UI visibleBindingValue types must be strings.")

        except AssertionError as err:
            print(f"ERROR: {self._testMethodName}: {err}")
