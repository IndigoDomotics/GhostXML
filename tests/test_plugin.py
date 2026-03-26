"""
Placeholder
"""
import httpx
import os
from tests.shared import APIBase
from tests.shared.utils import run_host_script
import textwrap
import dotenv
dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

BASE_PATH = os.getenv('BASE_PATH')


class TestGhostXMLCreateId(APIBase):
    """
    Placeholder
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @staticmethod
    def _execute_action(action_id: str, deviceId: int = 0, props: dict = None, wait: bool = True, msg_id: str = "test-plugin-action", timeout: float = 5.0) -> bool | httpx.Response:
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
                                      wait=True
                                      )
        self.assertEqual(result.status_code, 200, "The adjust_refresh_time_for_dev call was not successful.")

    def test_log_plugin_information(self):
        """Verify that the 'refresh_data' action item runs successfully."""
        result = self._execute_action("refresh_data")
        self.assertEqual(result.status_code, 200, "The log_plugin_information call was not successful.")

    def test_refresh_data_for_dev(self):
        """Verify that the 'refresh_data_for_dev' action item runs successfully."""
        result = self._execute_action("refresh_data_for_dev", deviceId=int(os.getenv("REFRESH_DATA_FOR_DEV")))
        self.assertEqual(result.status_code, 200, "The refresh_data_for_dev call was not successful.")

    def test_adjust_refresh_time_invalid_value(self):
        """Verify that 'adjust_refresh_time_for_dev' returns 500 when passed a non-numeric refresh frequency."""
        config = {"new_refresh_freq": "not_a_number"}
        result = self._execute_action("adjust_refresh_time_for_dev",
                                      deviceId=int(os.getenv("ADJUST_DEVICE_REFRESH_DEV")),
                                      props=config,
                                      wait=True
                                      )
        self.assertEqual(result.status_code, 500, "The adjust_refresh_time_for_dev call should have failed.")

    def test_refresh_data_for_dev_invalid_device(self):
        """Verify that 'refresh_data_for_dev' returns 500 when passed an invalid device ID."""
        result = self._execute_action("refresh_data_for_dev", deviceId=0)
        self.assertEqual(result.status_code, 500, "The refresh_data_for_dev call should have failed.")

    # ===================================== Plugin Events =====================================
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
