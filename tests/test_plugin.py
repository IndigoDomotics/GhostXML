"""
Unit tests for the GhostXML plugin.
"""
import dotenv
import httpx
import json
import os
import time
import textwrap
from tests.shared import APIBase
from tests.shared.utils import run_host_script

dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

BASE_PATH     = os.getenv('BASE_PATH')
DEVICE_FOLDER = int(os.getenv('DEVICE_FOLDER', 0))
PLUGIN_ID     = os.getenv('PLUGIN_ID')
URL_PREFIX    = os.getenv('URL_PREFIX')


# ===================================== Plugin Actions / Events =====================================
class TestGhostXMLCreateId(APIBase):
    """
    Placeholder
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    # ===================================== Helper Methods =====================================
    @staticmethod
    def _execute_action(
            action_id: str,
            deviceId: int = 0,
            props: dict = None,
            wait: bool = True,
            msg_id: str = "test-plugin-action",
            timeout: float = 5.0
    ) -> bool | httpx.Response:
        """Post a plugin.executeAction command to the Indigo Web Server API.

        Args:
            action_id (str): The Indigo action ID to execute.
            props (dict): Optional action props to include in the payload.
            wait (bool): Whether to wait for the action to complete before returning.
            msg_id (str): Value for the message ``id`` field, used to identify the call in logs.
            timeout (float): HTTP request timeout in seconds.

        Returns:
            bool | httpx.Response: The HTTP response, or False if the request failed.
        """
        try:
            message: dict = {
                "id":            msg_id,
                "message":       "plugin.executeAction",
                "pluginId":      os.getenv("PLUGIN_ID"),
                "actionId":      action_id,
                "waitUntilDone": wait,
            }
            if deviceId != 0:
                message["deviceId"] = deviceId
            if props is not None:
                message["props"] = props
            url = f"{os.getenv('URL_PREFIX')}/v2/api/command/?api-key={os.getenv('GOOD_API_KEY')}"
            return httpx.post(url, json=message, verify=False, timeout=timeout)
        except Exception:
            return False

    # ===================================== Plugin Actions =====================================
    def test_adjust_refresh_time_for_dev(self):
        """Verify that the 'adjust_refresh_time_for_dev' action item runs successfully."""
        config = {"new_refresh_freq": os.getenv("ADJUST_DEVICE_REFRESH_TIME")}
        result = self._execute_action("adjust_refresh_time_for_dev",
                                      deviceId=int(os.getenv("ADJUST_DEVICE_REFRESH_DEV")),
                                      props=config,
                                      wait=True,
                                      msg_id="test-plugin-adjust-refresh-time-for-dev"
                                      )
        self.assertEqual(result.status_code, 200, "The adjust_refresh_time_for_dev call was not successful.")

    # ----- test_log_plugin_information -----
    def test_log_plugin_information(self):
        """Verify that the 'refresh_data' action item runs successfully."""
        result = self._execute_action("refresh_data", msg_id="test_log_plugin_information")
        self.assertEqual(result.status_code, 200, "The log_plugin_information call was not successful.")

    # ----- test_refresh_data_for_dev -----
    def test_refresh_data_for_dev(self):
        """Verify that the 'refresh_data_for_dev' action item runs successfully."""
        result = self._execute_action("refresh_data_for_dev",
                                      deviceId=int(os.getenv("REFRESH_DATA_FOR_DEV")),
                                      msg_id="test-plugin-refresh-data-for-dev"
                                      )
        self.assertEqual(result.status_code, 200, "The refresh_data_for_dev call was not successful.")

    # ----- test_keep_alive_device_remains_enabled_after_failed_refresh -----
    def test_keep_alive_device_remains_enabled_after_failed_refresh(self):
        """Verify that a device with maxRetries=-1 remains enabled after a failed communication attempt.

        If the device is initially disabled, it is enabled before the test runs and disabled again
        afterward. If it is initially enabled, the enabled state is left unchanged after the test.
        """
        dev_id      = int(os.getenv("DEVICE_MAX_RETRIES_KEEP_ALIVE"))
        device      = self.get_indigo_object("devices", dev_id)
        was_enabled = device.get("enabled", False)

        if not was_enabled:
            script = textwrap.dedent(f"""\
                try:
                    indigo.device.enable({dev_id}, value=True)
                    return True
                except Exception as e:
                    return False
            """)
            run_host_script(script)
            time.sleep(1)

        self._execute_action("refresh_data_for_dev",
                             deviceId=dev_id,
                             msg_id="test-keep-alive-refresh",
                             timeout=15.0
                             )
        time.sleep(3)

        device = self.get_indigo_object("devices", dev_id)
        self.assertTrue(
            device.get("enabled", False),
            "Device with maxRetries=-1 should remain enabled after a failed refresh."
        )

        if not was_enabled:
            script = textwrap.dedent(f"""\
                try:
                    indigo.device.enable({dev_id}, value=False)
                    return True
                except Exception as e:
                    return False
            """)
            run_host_script(script)

    # ----- test_max_retries_keep_alive_value_is_valid -----
    def test_max_retries_keep_alive_value_is_valid(self):
        """Verify that maxRetries=-1 passes validate_device_config_ui without an error."""
        dev_id = int(os.getenv("DEVICE_MAX_RETRIES_KEEP_ALIVE"))
        script = textwrap.dedent(f"""\
            import json
            plugin = indigo.server.getPlugin("{PLUGIN_ID}")
            values = indigo.Dict({{
                "timeout": "5", "refreshFreq": "300", "maxRetries": "-1",
                "sourceXML": "https://httpbin.org/json", "useDigest": "None",
                "token": "", "tokenUrl": "", "doSubs": False, "curlSubs": False,
                "disableLogging": False,
                "subA": "", "subB": "", "subC": "", "subD": "", "subE": "",
                "curlSubA": "", "curlSubB": "", "curlSubC": "", "curlSubD": "", "curlSubE": ""
            }})
            result = plugin.validateDeviceConfigUi(values, "GhostXMLdevice", {dev_id})
            return json.dumps(dict(result[2]))
        """)
        errors = json.loads(run_host_script(script))
        self.assertNotIn("maxRetries", errors, "maxRetries=-1 should be valid (keep alive).")

    # ----- test_max_retries_below_keep_alive_is_invalid -----
    def test_max_retries_below_keep_alive_is_invalid(self):
        """Verify that maxRetries=-2 fails validate_device_config_ui."""
        dev_id = int(os.getenv("DEVICE_MAX_RETRIES_KEEP_ALIVE"))
        script = textwrap.dedent(f"""\
            import json
            plugin = indigo.server.getPlugin("{PLUGIN_ID}")
            values = indigo.Dict({{
                "timeout": "5", "refreshFreq": "300", "maxRetries": "-2",
                "sourceXML": "https://httpbin.org/json", "useDigest": "None",
                "token": "", "tokenUrl": "", "doSubs": False, "curlSubs": False,
                "disableLogging": False,
                "subA": "", "subB": "", "subC": "", "subD": "", "subE": "",
                "curlSubA": "", "curlSubB": "", "curlSubC": "", "curlSubD": "", "curlSubE": ""
            }})
            result = plugin.validateDeviceConfigUi(values, "GhostXMLdevice", {dev_id})
            return json.dumps(dict(result[2]))
        """)
        errors = json.loads(run_host_script(script))
        self.assertIn("maxRetries", errors, "maxRetries=-2 should be invalid.")

    # ----- test_max_retries_above_max_is_invalid -----
    def test_max_retries_above_max_is_invalid(self):
        """Verify that maxRetries=101 fails validate_device_config_ui."""
        dev_id = int(os.getenv("DEVICE_MAX_RETRIES_KEEP_ALIVE"))
        script = textwrap.dedent(f"""\
            import json
            plugin = indigo.server.getPlugin("{PLUGIN_ID}")
            values = indigo.Dict({{
                "timeout": "5", "refreshFreq": "300", "maxRetries": "101",
                "sourceXML": "https://httpbin.org/json", "useDigest": "None",
                "token": "", "tokenUrl": "", "doSubs": False, "curlSubs": False,
                "disableLogging": False,
                "subA": "", "subB": "", "subC": "", "subD": "", "subE": "",
                "curlSubA": "", "curlSubB": "", "curlSubC": "", "curlSubD": "", "curlSubE": ""
            }})
            result = plugin.validateDeviceConfigUi(values, "GhostXMLdevice", {dev_id})
            return json.dumps(dict(result[2]))
        """)
        errors = json.loads(run_host_script(script))
        self.assertIn("maxRetries", errors, "maxRetries=101 should be invalid.")

    # ----- test_adjust_refresh_time_invalid_value -----
    def test_adjust_refresh_time_invalid_value(self):
        """Verify that 'adjust_refresh_time_for_dev' returns 500 when passed a non-numeric refresh frequency."""
        config = {"new_refresh_freq": "not_a_number"}
        result = self._execute_action("adjust_refresh_time_for_dev",
                                      deviceId=int(os.getenv("ADJUST_DEVICE_REFRESH_DEV")),
                                      props=config,
                                      wait=True,
                                      msg_id="test-plugin-adjust-refresh-time-invalid-value"
                                      )
        self.assertEqual(result.status_code, 500, "The adjust_refresh_time_for_dev call should have failed.")
        print(result.json())

    # ----- test_refresh_data_for_dev_invalid_device -----
    def test_refresh_data_for_dev_invalid_device(self):
        """Verify that 'refresh_data_for_dev' returns 500 when passed an invalid device ID."""
        result = self._execute_action("refresh_data_for_dev",
                                      deviceId=0,
                                      msg_id="test_refresh_data_for_dev_invalid_device"
                                      )
        self.assertEqual(result.status_code, 500, "The refresh_data_for_dev call should have failed.")

    # ===================================== Plugin Events =====================================
    # ----- test_ghost_xml_device_disabled_trigger -----
    def test_ghost_xml_device_disabled_trigger(self):
        """Test the actions that fire when a device disabled trigger fires. This tests an internal trigger. It does not
        cover how devices are added to the trigger processing code."""
        script = textwrap.dedent(f"""
            try:
                indigo.trigger.execute({os.getenv('DEVICE_DISABLED_TRIGGER')})
                return True
            except Exception as e:
                return False
        """)
        r = run_host_script(script)
        self.assertTrue(r, f"The script did not return the expected result: {r}")


# ===================================== Devices =====================================
class TestDevices(APIBase):
    """Tests for plugin devices defined in Devices.xml."""

    @classmethod
    def setUpClass(cls):
        pass

    # ===================================== Helper Methods =====================================
    @staticmethod
    def payload(name: str = "", device_type_id: str = "", props: dict = None) -> str:
        """Generate a host script payload for creating a device via the Indigo Web Server API.

        Args:
            name (str): The quoted device name string passed to the host script.
            device_type_id (str): The Indigo device type ID from Devices.xml.
            props (dict): The device props dict passed to the host script.

        Returns:
            str: The host script payload.
        """
        return textwrap.dedent(f"""\
            try:
                import time
                indigo.device.create(protocol=indigo.kProtocol.Plugin,
                    name={name},
                    description='GhostXML unit test device',
                    pluginId={PLUGIN_ID},
                    deviceTypeId='{device_type_id}',
                    props={props},
                    folder={DEVICE_FOLDER}
                )
                time.sleep(1)
                return True
            except:
                return False
        """)

    # ----- confirm_creation -----
    @staticmethod
    def confirm_creation(name: str = "") -> str:
        """Generate a host script payload that confirms a device was created.

        Args:
            name (str): The quoted device name string passed to the host script.

        Returns:
            str: The host script payload.
        """
        return textwrap.dedent(f"""\
            if {name} in [dev.name for dev in indigo.devices.iter({PLUGIN_ID})]:
                return True
            else:
                return False
        """)

    # ----- delete_device -----
    @staticmethod
    def delete_device(name: str = "") -> str:
        """Generate a host script payload that deletes a device via the Indigo Web Server API.

        Args:
            name (str): The quoted device name string passed to the host script.

        Returns:
            str: The host script payload.
        """
        return textwrap.dedent(f"""\
            try:
                indigo.device.delete({name})
                return True
            except:
                return False
        """)

    # ----- create_and_delete_device -----
    def create_and_delete_device(self, name: str, device_type_id: str, props: dict):
        """Create a plugin device, confirm it exists, then delete it.

        Args:
            name (str): The quoted device name string passed to the host script.
            device_type_id (str): The Indigo device type ID from Devices.xml.
            props (dict): The device props dict passed to the host script.
        """
        host_script = self.payload(name, device_type_id, props)
        run_host_script(host_script)
        self.assertTrue(host_script, "Device creation successful.")

        host_script = self.confirm_creation(name)
        self.assertTrue(host_script, "Could not confirm the device was created.")

        host_script = self.delete_device(name)
        run_host_script(host_script)
        self.assertTrue(host_script, "Device deletion failed.")

    # ============================ GhostXML Device (String Type) ============================
    # ----- test_ghostxml_string_device_creation_xml -----
    def test_ghostxml_string_device_creation_xml(self):
        """Verify that a GhostXML Device (String Type) with an XML source can be created and
        deleted via the Indigo API."""
        my_props = {'feedType':        'XML',
                    'refreshFreq':     '300',
                    'timeout':         '5',
                    'maxRetries':      '10',
                    'disableLogging':  False,
                    'disableGlobbing': False,
                    'sourceXML':       'https://httpbin.org/xml',
                    'useDigest':       'None',
                    'doSubs':          False}
        self.create_and_delete_device("'ghostxml_unit_test_string_device_xml'", 'GhostXMLdevice', my_props)

    # ----- test_ghostxml_string_device_creation_json -----
    def test_ghostxml_string_device_creation_json(self):
        """Verify that a GhostXML Device (String Type) with a JSON source can be created and
        deleted via the Indigo API."""
        my_props = {'feedType':        'JSON',
                    'refreshFreq':     '300',
                    'timeout':         '5',
                    'maxRetries':      '10',
                    'disableLogging':  False,
                    'disableGlobbing': False,
                    'sourceXML':       'https://httpbin.org/json',
                    'useDigest':       'None',
                    'doSubs':          False}
        self.create_and_delete_device("'ghostxml_unit_test_string_device_json'", 'GhostXMLdevice', my_props)

    # ============================ GhostXML Device (Real Type) ==============================
    # ----- test_ghostxml_real_device_creation_xml -----
    def test_ghostxml_real_device_creation_xml(self):
        """Verify that a GhostXML Device (Real Type) with an XML source can be created and
        deleted via the Indigo API."""
        my_props = {'feedType':       'XML',
                    'refreshFreq':    '300',
                    'timeout':        '5',
                    'maxRetries':     '10',
                    'disableLogging': True,
                    'sourceXML':      'https://httpbin.org/xml',
                    'useDigest':      'None',
                    'doSubs':         False}
        self.create_and_delete_device("'ghostxml_unit_test_real_device_xml'", 'GhostXMLdeviceTrue', my_props)

    # ----- test_ghostxml_real_device_creation_json -----
    def test_ghostxml_real_device_creation_json(self):
        """Verify that a GhostXML Device (Real Type) with a JSON source can be created and
        deleted via the Indigo API."""
        my_props = {'feedType':       'JSON',
                    'refreshFreq':    '300',
                    'timeout':        '5',
                    'maxRetries':     '10',
                    'disableLogging': True,
                    'sourceXML':      'https://httpbin.org/json',
                    'useDigest':      'None',
                    'doSubs':         False}
        self.create_and_delete_device("'ghostxml_unit_test_real_device_json'", 'GhostXMLdeviceTrue', my_props)
