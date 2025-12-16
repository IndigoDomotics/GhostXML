"""
Plugin Tests that Require IOM Access

Some tests are much easier to perform by using commands available in the IOM that are not yet supported by the Indigo
integration API. These tests are meant to be run through an installed, enabled, and running plugin instance. To run the
tests, developers should create an Indigo Action item that calls the hidden action to run the tests. For example,

    plugin_id = "com.fogbert.indigoplugin.GhostXML"
    plugin = indigo.server.getPlugin(plugin_id)

    try:
        if indigo.PluginInfo.isRunning(plugin):
            plugin.executeAction("my_tests")  # this is the hidden action to run the tests
        else:
            indigo.server.log("Plugin not enabled.")
    except Exception as err:
        indigo.server.log(f"{err}")

"""
from datetime import datetime
import indigo  # noqa
import logging
import os
from unittest import TestCase
from unittest.mock import MagicMock
import dotenv

dotenv.load_dotenv()
LOGGER = logging.getLogger("Plugin")
REFRESH_DATA_FOR_DEVICE_ACTION = int(os.getenv("REFRESH_DATA_FOR_DEVICE_ACTION"))
REFRESH_DATA_FOR_ALL_DEVICES_ACTION = int(os.getenv("REFRESH_DATA_FOR_ALL_DEVICES_ACTION"))
ADJUST_DEVICE_REFRESH_TIME_ACTION = int(os.getenv("ADJUST_DEVICE_REFRESH_TIME_ACTION"))
DEVICE_DISABLED_TRIGGER = int(os.getenv("DEVICE_DISABLED_TRIGGER"))
VALIDATE_DEVICE_CONFIG_UI_DEVICE = int(os.getenv("VALIDATE_DEVICE_CONFIG_UI_DEVICE"))
test_case = TestCase()


class TestPlugin(TestCase):
    """ Docstring placeholder"""
    def __init__(self):
        super().__init__()

    # =============================================================================
    @staticmethod
    def test_plugin_actions(plugin):  # noqa
        """
        Test plugin actions to ensure the actions execute successfully.

        This method runs at least one instance of every type of plugin action. If the action executes successfully,
        `None` is returned. It will fail on the first test fail instance.

        :param plugin: The plugin instance
        """
        for action in [REFRESH_DATA_FOR_DEVICE_ACTION,
                       REFRESH_DATA_FOR_ALL_DEVICES_ACTION,
                       ADJUST_DEVICE_REFRESH_TIME_ACTION
                       ]:
            try:
                result = indigo.actionGroup.execute(action)
                test_case.assertIsNone(result, f"Action group {action} execute didn't return None")
                return True, None
            except AssertionError as error:
                return False, error

    # =============================================================================
    @staticmethod
    def test_plugin_triggers(plugin):  # noqa
        """
        Test plugin triggers to ensure the triggers execute successfully.

        This method runs at least one instance of every type of plugin trigger. If the trigger executes successfully,
        `None` is returned. It will fail on the first test fail instance.

        :param plugin: The plugin instance
        """
        for action in [DEVICE_DISABLED_TRIGGER]:
            try:
                result = indigo.trigger.execute(action)
                test_case.assertIsNone(result, f"Action group {action} execute didn't return None")
                return True, None
            except AssertionError as error:
                return False, error

    @staticmethod
    def test_indigo_methods(plugin):
        """
        Test plugin base methods to ensure they work as expected.

        This method tests selected base methods (there is no intention of testing them all). If the tests execute
        successfully, (True, None) is returned. It will fail on the first test fail instance. NOTE: your IDE may say
        that the tested methods are unresolved; they will resolve when the tests are run as this file is imported into
        the plugin.

        :param plugin: The plugin instance
        """
        try:
            # ===================================== Validate Device Config UI =====================================
            dev = indigo.devices[VALIDATE_DEVICE_CONFIG_UI_DEVICE]
            values_dict = {'curlSubs': False,
                           'disableLogging': False,
                           'doSubs': False,
                           'maxRetries': "10",
                           'refreshFreq': "300",
                           'sourceXML': "https://httpbin.org/basic-auth/username/password",
                           'subA': "",
                           'subB': "",
                           'subC': "",
                           'subD': "",
                           'subE': "",
                           'timeout': "10",
                           'token': "",
                           'tokenUrl': "",
                           'useDigest': "None"
                           }
            # This test should validate:
            result = plugin.validate_device_config_ui(values_dict, dev.deviceTypeId, dev.id)
            test_case.assertTrue(result[0], "Validation should pass but it failed.")

            # This test should return False because the timeout value must be a real number
            values_dict['timeout'] = "None"
            result = plugin.validate_device_config_ui(values_dict, dev.deviceTypeId, dev.id)
            test_case.assertFalse(result[0], "Validation should fail but it passed.")
            values_dict['timeout'] = "10"

            # This test should return False because the timeout value cannot be greater than the refresh frequency.
            values_dict['refreshFreq'] = "1"
            result = plugin.validate_device_config_ui(values_dict, dev.deviceTypeId, dev.id)
            test_case.assertFalse(result[0], "Validation should fail but it passed.")
            values_dict['refreshFreq'] = "300"

            # This test should return False because max retries must be an integer.
            values_dict['maxRetries'] = "None"
            result = plugin.validate_device_config_ui(values_dict, dev.deviceTypeId, dev.id)
            test_case.assertFalse(result[0], "Validation should fail but it passed.")
            values_dict['maxRetries'] = "10"

            # This test should return False because the source URL/Path doesn't start with the proper prefix.
            values_dict['sourceXML'] = "www.google.com"
            result = plugin.validate_device_config_ui(values_dict, dev.deviceTypeId, dev.id)
            test_case.assertFalse(result[0], "Validation should fail but it passed.")
            values_dict['sourceXML'] = "https://httpbin.org/basic-auth/username/password"

            # This test should return False because the token URL/Path doesn't start with the proper prefix.
            values_dict['useDigest'] = "Token"
            values_dict['tokenUrl'] = "www.google.com"
            result = plugin.validate_device_config_ui(values_dict, dev.deviceTypeId, dev.id)
            test_case.assertFalse(result[0], "Validation should fail but it passed.")
            values_dict['useDigest'] = "None"
            values_dict['tokenUrl'] = ""

            # This test should return False because the bearer token can not be an empty string.
            values_dict['useDigest'] = "Bearer"
            result = plugin.validate_device_config_ui(values_dict, dev.deviceTypeId, dev.id)
            test_case.assertFalse(result[0], "Validation should fail but it passed.")
            values_dict['useDigest'] = "None"

            # This test should return True because the substitution value is invalid. We are not testing the actual
            # substitutions here, just the field validation.
            values_dict['doSubs'] = True
            values_dict['subA'] = "0"
            result = plugin.validate_device_config_ui(values_dict, dev.deviceTypeId, dev.id)
            test_case.assertFalse(result[0], "Validation should fail but it passed.")
            values_dict['doSubs'] = False
            values_dict['subA'] = ""

            return True, None
        except AssertionError as error:
            return False, error

    @staticmethod
    def test_plugin_methods(plugin):
        """
        Test plugin methods to ensure they work as expected.

        This method tests selected methods (there is no intention of testing them all). If the tests execute
        successfully, (True, None) is returned. It will fail on the first test fail instance. NOTE: your IDE may say
        that the tested methods are unresolved; they will resolve when the tests are run as this file is imported into
        the plugin.

        :param plugin: The plugin instance
        """
        try:
            test_dev = MagicMock()  # Mocked device
            test_dev.enabled = True
            # ===================================== _time_to_update() =====================================
            # Dev does not need a refresh
            test_dev.states = {'deviceTimestamp': int(datetime.now().timestamp())}
            test_case.assertFalse(plugin._time_to_update(test_dev), "Plugin incorrectly found device needed refresh.")

            # Dev does not have a 'deviceTimestamp' state.
            test_dev.states = {}
            test_case.assertFalse(plugin._time_to_update(test_dev), "Plugin should have handled no 'deviceTimestamp' state exists.")

            # Dev is not enabled
            test_dev.enabled = False
            test_case.assertFalse(plugin._time_to_update(test_dev), "Plugin should have handled a disabled device.")

            # ===================================== get_device_list() =====================================
            result = plugin.get_device_list()
            test_case.assertIsInstance(result, list, "Method did not return a list.")
            test_case.assertTrue(result, "Method returned an empty list.")
            for dev in result:
                test_case.assertIsInstance(dev[0], int, "Device list contains invalid dev.id.")
                test_case.assertIsInstance(dev[1], str, "Device list contains invalid dev.name.")

            # ===================================== _log_environment_info() =====================================
            result = plugin._log_environment_info()
            test_case.assertIsNone(result, "Method did not complete successfully.")

            return True, None
        except AssertionError as error:
            return False, error
