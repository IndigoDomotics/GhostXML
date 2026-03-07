# noqa pylint: disable=too-many-lines, line-too-long, invalid-name, unused-argument, redefined-builtin, broad-except, logging-fstring-interpolation, wildcard-import

"""
GhostXML Indigo Plugin
Authors: See (repo)

This plugin provides an engine which parses tag/value pairs into transitive Indigo plugin device states.
"""

# =============================== Stock Imports ===============================
import json
import logging
import os
import platform
from queue import Queue  # import queue
import re
import subprocess
import sys
import threading
import time as t
import xml.etree.ElementTree as Etree
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

# ============================ Third-party Imports ============================
import flatdict  # https://github.com/gmr/flatdict - flatdict deprecated Python 2 in v4.0.0
import iterateXML
try:
    import indigo  # noqa
except ImportError:
    pass

# ===============================Custom Imports================================
from constants import *  # noqa
from curlcodes import codes as curl_code  # noqa
from httpcodes import codes as http_code  # noqa
from plugin_defaults import kDefaultPluginPrefs  # noqa

__author__    = "berkinet, DaveL17, GlennNZ, howartp"
__build__     = ""
__copyright__ = "There is no copyright for the GhostXML code base."
__license__   = "MIT"
__title__     = "GhostXML Plugin for Indigo Home Control"
__version__   = "2025.2.1"


# =============================================================================
class Plugin(indigo.PluginBase):
    """Standard Indigo Plugin Class for the GhostXML plugin.

    Manages plugin lifecycle, device communication, data retrieval, and state updates for all
    GhostXML devices. Inherits from indigo.PluginBase.
    """
    def __init__(self, plugin_id: str = "", plugin_display_name: str = "", plugin_version: str = "",
                 plugin_prefs: indigo.Dict = None):
        """Initialize the plugin, set up instance attributes, and configure logging.

        Args:
            plugin_id (str): The unique plugin identifier.
            plugin_display_name (str): The display name of the plugin.
            plugin_version (str): The current version string of the plugin.
            plugin_prefs (indigo.Dict): The plugin's stored preferences dictionary.
        """
        super().__init__(plugin_id, plugin_display_name, plugin_version, plugin_prefs)

        # ============================ Instance Attributes =============================
        self.plugin_is_initializing   = True
        self.debug_level              = int(self.pluginPrefs.get('showDebugLevel', '30'))
        self.master_trigger_dict      = {'disabled': Queue()}
        self.plugin_is_shutting_down  = False
        self.managed_devices          = {}  # Managed list of plugin devices
        self.changing_managed_devices = False
        self.prepare_to_sleep         = False

        # =============================== Debug Logging ================================
        try:
            if self.debug_level < 10:
                self.debug_level *= 10
        except ValueError:
            self.debug_level = 30

        self.plugin_file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt='%Y-%m-%d %H:%M:%S'))
        self.indigo_log_handler.setLevel(self.debug_level)

        self.plugin_is_initializing = False

    # =============================================================================
    def log_plugin_environment(self) -> None:
        """Log plugin environment information when the plugin is first started.

        Output is sent to the Indigo Event Log via ``indigo.server.log`` regardless of the
        current logging level configured in plugin preferences.
        """
        # Send to `indigo.server.log` to ensure it gets logged regardless of the current logging
        # level.
        indigo.server.log(f"{' Plugin Environment Information ':{'='}^135}")
        indigo.server.log(f"{'Plugin name:':<31} {self.pluginDisplayName}")
        indigo.server.log(f"{'Plugin version:':<31} {self.pluginVersion}")
        indigo.server.log(f"{'Plugin ID:':<31} {self.pluginId}")
        indigo.server.log(f"{'Indigo version:':<31} {indigo.server.version}")
        sys_version = sys.version.replace('\n', '')
        indigo.server.log(f"{'Python version:':<31} {sys_version}")
        indigo.server.log(f"{'Mac OS Version:':<31} {platform.mac_ver()[0]}")
        indigo.server.log(f"{'Process ID:':<31} {os.getpid()}")
        indigo.server.log("=" * 135)

    # =============================================================================
    def __del__(self) -> None:
        """Destructor called when the plugin object is garbage collected.
        """
        indigo.PluginBase.__del__(self)

    # =============================================================================
    # =============================== Indigo Methods ==============================
    # =============================================================================
    def closed_device_config_ui(self, values_dict: indigo.Dict = None, user_cancelled: bool = False, type_id: str = "", dev_id: int = 0) -> None:  # noqa
        """Standard Indigo method called when the device configuration dialog is closed.

        Replaces the device in the managed devices list to ensure any configuration changes
        take effect immediately.

        Args:
            values_dict (indigo.Dict): The dialog field values at the time of closure.
            user_cancelled (bool): True if the user cancelled the dialog.
            type_id (str): The device type identifier.
            dev_id (int): The Indigo device ID.
        """
        dev = indigo.devices[dev_id]

        # Replace device to list of managed devices to ensure any configuration changes are used.
        self.managed_devices[dev.id] = PluginDevice(self, dev)

    # =============================================================================
    def closed_prefs_config_ui(self, values_dict: indigo.Dict = None, user_cancelled: bool = False) -> indigo.Dict:  # noqa
        """Standard Indigo method called when the plugin preferences dialog is closed.

        If the dialog was not cancelled, updates ``self.pluginPrefs`` with the new values and
        applies the updated logging level.

        Args:
            values_dict (indigo.Dict): The dialog field values at the time of closure.
            user_cancelled (bool): True if the user cancelled the dialog.

        Returns:
            indigo.Dict: The (possibly updated) values dictionary.
        """
        if not user_cancelled:
            # Ensure that self.pluginPrefs includes any recent changes.
            for k in values_dict:
                self.pluginPrefs[k] = values_dict[k]

            # Debug Logging
            self.debug_level = int(values_dict.get('showDebugLevel', "30"))
            self.indigo_log_handler.setLevel(self.debug_level)
            indigo.server.log(f"Logging level: {DEBUG_LABELS[self.debug_level]} ({self.debug_level})")
            self.logger.debug("Plugin prefs saved.")

        else:
            self.logger.debug("Plugin prefs cancelled.")

        return values_dict

    # =============================================================================
    def device_deleted(self, dev: indigo.Device = None) -> None:
        """Standard Indigo method called when a device is deleted.

        Removes the device from the managed devices dictionary.

        Args:
            dev (indigo.Device): The Indigo device that was deleted.
        """
        self.logger.debug("%s %s deleted." % (dev.name, dev.id))
        self.managed_devices.pop(dev.id, None)
        if dev.id in self.managed_devices:
            del self.managed_devices[dev.id]

    # =============================================================================
    def device_start_comm(self, dev: indigo.Device = None) -> None:  # noqa
        """Standard Indigo method called when a device is enabled.

        Adds the device to the managed devices list, migrates any legacy authentication
        settings, validates device configuration, and forces an initial state refresh.

        Args:
            dev (indigo.Device): The Indigo device starting communication.
        """
        self.logger.debug("%s communication starting." % dev.name)
        self.managed_devices[dev.id] = PluginDevice(self, dev)

        dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Starting")

        # =============== Update legacy authentication settings ===============
        new_props = dev.pluginProps
        auth_type = new_props.get('useDigest', 'None')
        try:
            use_auth = new_props['useAuth']

            # If 'useAuth' was 'false', set 'useDigest' to 'None'. If useAuth was 'true' we leave 'useDigest' alone.
            if not use_auth:
                new_props['useDigest'] = 'None'
        except KeyError:
            pass

        match auth_type:
            case 'False' | 'false' | False:
                new_props['useDigest'] = 'Basic'
            case 'True' | 'true' | True:
                new_props['useDigest'] = 'Digest'

        if new_props != dev.pluginProps:
            dev.replacePluginPropsOnServer(new_props)
            self.sleep(2)

        # 2021-01-08 DaveL17 We were mistakenly saving this to pluginProps and not sharedProps.
        # This updates devices with the "disable logging" setting already checked.
        shared_props = dev.sharedProps
        if dev.pluginProps['disableLogging']:
            shared_props['sqlLoggerIgnoreStates'] = "*"
        else:
            shared_props['sqlLoggerIgnoreStates'] = ""

        # If device does not have a URL/Path, it cannot possibly work.
        try:
            if dev.pluginProps['sourceXML'] == "":
                raise KeyError
        except KeyError:
            self.logger.debug("%s does not have a URL/Path value set. Disabling." % dev.name)
            indigo.device.enable(dev, value=False)

        dev.replaceSharedPropsOnServer(shared_props)
        dev.stateListOrDisplayStateIdChanged()

        # Add device to list of managed devices
        self.changing_managed_devices = True
        self.managed_devices[dev.id] = PluginDevice(self, dev)
        self.changing_managed_devices = False

        # Force refresh of device when comm started
        if int(dev.pluginProps.get('refreshFreq', 0)) == 0:
            dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Manual")
        else:
            dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Started")

        self.logger.debug("[%s] communication started." % dev.name)

    # =============================================================================
    def device_stop_comm(self, dev: indigo.Device = None) -> None:  # noqa
        """Standard Indigo method called when a device is disabled.

        Joins the device's update thread, removes it from the managed devices list, and
        updates the device's state icon to reflect the disabled condition.

        Args:
            dev (indigo.Device): The Indigo device stopping communication.
        """
        # =============================================================================
        try:
            # Join the related thread. There must be a timeout set because the threads may never terminate on their own.
            self.managed_devices[dev.id].dev_thread.join(0.25)

            # Delete the device from the list of managed devices.
            self.changing_managed_devices = True
            del self.managed_devices[dev.id]
            self.changing_managed_devices = False

            # Update the device's icon to reflect the stopped condition.
            dev.setErrorStateOnServer("")
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

            dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Disabled")

            self.logger.debug("[%s] communication stopped." % dev.name)

        except KeyError:
            self.logger.warning(
                "%s - Problem removing device from managed device list. Consider restarting the plugin." % dev.name
            )

    # =============================================================================
    def get_device_state_list(self, dev: indigo.Device = None) -> list:  # noqa
        """Standard Indigo method that returns the list of states for a device.

        Pulls keys from ``self.final_dict`` and maps them to Indigo device state definitions.
        For ``GhostXMLdevice`` types all states are stored as strings. For ``GhostXMLdeviceTrue``
        types each value is inspected and mapped to the most appropriate Indigo state type
        (int, float, bool, or string). Called automatically by ``stateListOrDisplayStateIdChanged()``
        and by Indigo when building Triggers and Control Pages.

        Note:
            Indigo sorts device states as A, B, a, b and this ordering cannot be overridden.

        Args:
            dev (indigo.Device): The Indigo device whose state list is being built.

        Returns:
            list: The updated list of Indigo device state dictionaries.
        """
        def parse_the_states(k: str, v) -> list:
            b_key = f"{k}_bool"  # boolean key
            u_key = f"{k}"

            try:
                # Integers
                _ = int(v)  # Try int; if it fails move on to the next one.
                state_list.append(self.getDeviceStateDictForNumberType(u_key, u_key, u_key))
            except (TypeError, ValueError):
                try:
                    # Floats
                    _ = float(v)  # Try float; if it fails move on to the next one.
                    state_list.append(self.getDeviceStateDictForNumberType(u_key, u_key, u_key))
                except (TypeError, ValueError):
                    try:
                        # Bools - we create a state for the original data (in string form) and for the boolean
                        # representation.
                        match v.lower():
                            case 'on' | 'off' | 'open' | 'locked' | 'up' | 'armed' | 'closed' | 'unlocked' | 'down' | \
                                 'disarmed':
                                state_list.append(self.getDeviceStateDictForBoolOnOffType(u_key, u_key, u_key))
                                state_list.append(self.getDeviceStateDictForBoolOnOffType(b_key, b_key, b_key))
                            case 'yes' | 'no':
                                state_list.append(self.getDeviceStateDictForBoolYesNoType(u_key, u_key, u_key))
                                state_list.append(self.getDeviceStateDictForBoolYesNoType(b_key, b_key, b_key))
                            case 'true' | 'false':
                                state_list.append(self.getDeviceStateDictForBoolTrueFalseType(u_key, u_key, u_key))
                                state_list.append(self.getDeviceStateDictForBoolTrueFalseType(b_key, b_key, b_key))
                            case _:
                                state_list.append(self.getDeviceStateDictForStringType(u_key, u_key, u_key))
                    except (AttributeError, TypeError, ValueError):
                        state_list.append(self.getDeviceStateDictForStringType(u_key, u_key, u_key))

            return state_list

        # This statement goes out and gets the existing state list for dev from Devices.xml. It seems like it's calling
        # itself, but the structure was recommended by Matt:
        # https://forums.indigodomo.com/viewtopic.php?f=108&t=12898#p87456
        # 2021-02-19 DaveL17 disabled logging message as it's only useful for development debugging.
        # self.logger.debug("self.managedDevices: %s" % self.managedDevices)
        state_list = indigo.PluginBase.get_device_state_list(self, dev)

        # ========================= Custom States as Strings ==========================
        if dev.deviceTypeId == 'GhostXMLdevice':
            # If dev is not listed in managed devices, return the existing states.
            if dev.id not in self.managed_devices:
                for key in dev.states:
                    dynamic_state = self.getDeviceStateDictForStringType(f"{key}", f"{key}", f"{key}")
                    state_list.append(dynamic_state)

            # If there are managed devices, return the keys that are in finalDict.
            else:
                for key in sorted(self.managed_devices[dev.id].final_dict):
                    dynamic_state = self.getDeviceStateDictForStringType(f"{key}", f"{key}", f"{key}")
                    state_list.append(dynamic_state)

        # ======================== Custom States as True Type =========================
        try:
            self.logger.debug("[get_device_state_list / self.managed_devices] = %s" % self.managed_devices)
            if dev.deviceTypeId == 'GhostXMLdeviceTrue':
                # If there are no managed devices, return the existing states.
                if dev.id not in self.managed_devices:
                    for key in dev.states:
                        value = dev.states[key]
                        state_list = parse_the_states(k=key, v=value)

                # If there are managed devices, return the keys that are in finalDict.
                else:
                    for key in sorted(self.managed_devices[dev.id].final_dict):
                        value = self.managed_devices[dev.id].final_dict[key]
                        state_list = parse_the_states(k=key, v=value)

            return state_list
        except Exception:
            self.logger.exception("General exception.")

    def get_device_config_ui_xml(self, type_id: str = "", dev_id: int = 0) -> bytes | None:  # noqa
        """Standard Indigo method called when the device configuration dialog is opened.

        Dynamically adds a "Custom" refresh frequency option to the dialog's frequency list
        when the device's current refresh frequency does not match any of the predefined values.

        Args:
            type_id (str): The device type identifier.
            dev_id (int): The Indigo device ID.

        Returns:
            bytes | None: The (possibly modified) XML configuration UI as a UTF-8 encoded byte
            string, or None if the device type is not handled.
        """
        current_freq = indigo.devices[dev_id].pluginProps.get('refreshFreq', '15')
        freqs        = []
        xml          = self.devicesTypeDict[type_id]["ConfigUIRawXml"]
        root         = Etree.fromstring(xml)

        # 2022-02-11 converted elem.getchildren() to list(elem) for Python 3.
        if type_id in ('GhostXMLdevice', 'GhostXMLdeviceTrue'):

            # Get current list of refresh frequencies from the XML file.
            for item in root.findall('Field'):
                if item.attrib['id'] == 'refreshFreq':
                    for child in list(item):
                        freqs = [int(grandchild.attrib['value']) for grandchild in list(child) if child.tag == 'List']

            # If the current refresh frequency is different from the default, it has been set through a custom refresh
            # frequency action. So we add a "Custom" option that will display when the dialog opens.
            if current_freq not in freqs:
                for item in root.findall('Field'):
                    if item.attrib['id'] == 'refreshFreq':
                        for child in list(item):
                            if child.tag == 'List':
                                option = Etree.fromstring(
                                    f"<Option value='{current_freq}'>Custom ({current_freq} seconds)</Option>"
                                )
                                child.append(option)

            return Etree.tostring(root)
        return None
    # =============================================================================

    # =============================================================================
    @staticmethod
    def manage_plugin_devices(values_dict: indigo.Dict = None, menu_id: str = "") -> tuple:  # noqa
        """Callback for the "Manage Plugin Devices" menu item.

        Enables or disables each plugin device based on the checkbox values submitted by
        the user. If the user selects Cancel, no action is taken.

        Args:
            values_dict (indigo.Dict): Dialog field values keyed by ``d_<dev_id>`` for each device.
            menu_id (str): The menu item identifier.

        Returns:
            tuple: A ``(True, values_dict)`` tuple confirming success.
        """
        # Iterate values_dict
        for dev in values_dict:
            # If dev starts with 'd_', it's a device field.
            if dev.startswith('d_'):
                # Convert key to dev_id
                dev_id = int(dev.replace('d_', ''))
                dev_enabled: bool = values_dict[dev]
                # Enable/Disable device as requested.
                if dev_enabled:
                    indigo.device.enable(dev_id, True)
                else:
                    indigo.device.enable(dev_id, False)

        return True, values_dict

    # =============================================================================
    @staticmethod
    def get_menu_action_config_ui_xml(menu_id: str) -> str | None:
        """Standard Indigo method that returns dynamic XML for a menu action's configuration dialog.

        Builds and returns an XML configuration UI for the given menu action. Currently handles
        the ``manage_plugin_devices`` menu item, generating a checkbox list of all plugin devices.

        Args:
            menu_id (str): The identifier of the menu action whose UI XML is being requested.

        Returns:
            str: A UTF-8 XML declaration string defining the ConfigUI, or None if the menu_id
            is not handled.
        """
        if menu_id == "manage_plugin_devices":
            my_devs = [dev for dev in indigo.devices.iter("self")]

            # Main '<ConfigUI>' node
            config_ui = Etree.Element("ConfigUI")

            # Dialog instructions
            field = Etree.SubElement(config_ui, "Field", id="instructions", type="label")
            label = Etree.SubElement(field, "Label")
            label.text = "Enable/disable individual plugin devices. Only GhostXML devices are shown."

            # Separator
            field = Etree.SubElement(config_ui, "Field", id="sep01", type="separator")

            # List the checkbox followed by the device name - [x] My GhostXML Device
            for dev in my_devs:
                field = Etree.SubElement(config_ui, "Field", id=f"d_{dev.id}", type="checkbox", defaultValue=f"{dev.enabled}")
                label = Etree.SubElement(field, "Label")
                label.text = ""
                description = Etree.SubElement(field, "Description")
                description.text = f"{dev.name}"

            # Convert the tree to a string
            return Etree.tostring(config_ui, encoding='utf-8', xml_declaration=True).decode()

        return None

    # =============================================================================
    def wake_up(self) -> None:  # noqa
        """Standard Indigo method called when Indigo receives a system wake-up call.
        """
        self.logger.debug("wake_up method called")
        indigo.PluginBase.wake_up(self)
        self.prepare_to_sleep = False

    # =============================================================================
    def prepareToSleep(self) -> None:  # noqa
        """Standard Indigo method called when Indigo receives a system sleep call.
        """
        self.logger.debug("prepareToSleep method called")
        indigo.PluginBase.prepareToSleep(self)
        self.prepare_to_sleep = True

    # =============================================================================
    def run_concurrent_thread(self) -> None:  # noqa
        """Standard Indigo method that runs continuously while the plugin is enabled.

        Iterates managed devices every two seconds to check whether each device is due for a
        data refresh, dispatches updates to device queues, processes triggers, and handles
        excessive bad calls by disabling the offending device.
        """
        self.sleep(1)

        try:
            while not self.plugin_is_shutting_down:
                # If the dict of managed devices is not being changed.
                if not self.changing_managed_devices and not self.prepare_to_sleep:
                    # Iterate devices to see if an update is required.

                    for dev_id in self.managed_devices:
                        dev = self.managed_devices[dev_id].device

                        # 2019-12-22 DaveL17
                        # If device name has changed in Indigo, update the copy in managedDevices.
                        if dev.name != indigo.devices[dev_id].name:
                            self.managed_devices[dev_id].device.name = indigo.devices[dev_id].name

                        # If a device has failed too many times, disable it and notify the user.
                        retries = int(dev.pluginProps.get('maxRetries', 10))
                        if self.managed_devices[dev_id].bad_calls >= retries:
                            self._process_bad_calls(dev, retries)

                        # If _time_to_update returns True, add device to its queue.
                        else:
                            if self._time_to_update(dev):
                                self.logger.debug("Time to update: [%s]" % dev.name)
                                self.managed_devices[dev_id].queue.put(dev)

                self._process_triggers()
                self.sleep(2)

        except self.StopThread:
            self.indigo_log_handler.setLevel(20)
            self.logger.info('Stopping main thread.')
            self.indigo_log_handler.setLevel(self.debug_level)

        except RuntimeError:
            self.logger.warning("Timed out waiting for the Indigo server. Will continue to try.")

        except Exception:
            self.logger.exception("General exception")

    # =============================================================================
    @staticmethod
    def sendDevicePing(dev_id: int = 0, suppress_logging: bool = False) -> dict:  # noqa
        """Standard Indigo method called when a plugin device receives a ping request.

        GhostXML devices do not support the ping function.

        Args:
            dev_id (int): The Indigo device ID receiving the ping.
            suppress_logging (bool): Whether to suppress the log message.

        Returns:
            dict: A result dictionary with ``{'result': 'Failure'}``.
        """
        indigo.server.log("GhostXML Plugin devices do not support the ping function.")
        return {'result': 'Failure'}

    # =============================================================================
    def shutdown(self) -> None:
        """Standard Indigo method called when the plugin is disabled.
        """
        self.plugin_is_shutting_down = True
        self.indigo_log_handler.setLevel(20)
        self.logger.info('Shutdown complete.')

    # =============================================================================
    def startup(self) -> None:
        """Standard Indigo method called when the plugin is first started.

        Validates the minimum required Indigo version and initializes the display state of all
        plugin devices.
        """
        # =========================== Audit Indigo Version ============================
        min_ver = 2022
        ver     = self.versStrToTuple(indigo.server.version)
        if ver[0] < min_ver:
            self.stopPlugin(f"The GhostXML plugin requires Indigo version {min_ver} or  above.", isError=True)

        # Initialize all plugin devices to ensure that they're in the proper state. We can't use managedDevices here
        # because they may not yet have showed up.
        for dev in indigo.devices.iter("self"):
            if not dev.enabled:
                dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Disabled")
            else:
                dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Initialized")

            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def trigger_start_processing(self, trigger: indigo.Trigger) -> None:  # noqa
        """Standard Indigo method called when a plugin trigger is enabled.

        Args:
            trigger (indigo.Trigger): The Indigo trigger that is starting.
        """
        self.logger.info("Trigger [%s] started." % trigger.name)
        self.master_trigger_dict[trigger.pluginProps['disabledDevice']] = trigger.id

    # =============================================================================
    def trigger_stop_processing(self, trigger: indigo.Trigger) -> None:  # noqa
        """Standard Indigo method called when a plugin trigger is disabled.

        Args:
            trigger (indigo.Trigger): The Indigo trigger that is stopping.
        """
        self.logger.info("Trigger [%s] stopped." % trigger.name)

    # =============================================================================
    @staticmethod
    def validate_device_config_ui(values_dict: indigo.Dict = None, type_id: str = "", dev_id: int = 0) -> tuple:  # noqa
        """Standard Indigo method called to validate the device configuration dialog on close.

        Validates timeout, refresh frequency, max retries, source URL, token settings, and
        variable substitution IDs. Also applies SQL logging preferences to the device's shared
        props.

        Args:
            values_dict (indigo.Dict): The dialog field values to validate.
            type_id (str): The device type identifier.
            dev_id (int): The Indigo device ID.

        Returns:
            tuple: ``(True, values_dict, error_msg_dict)`` if valid, or
            ``(False, values_dict, error_msg_dict)`` with populated errors if validation fails.
        """
        error_msg_dict = indigo.Dict()
        sub_list = (('subA', '[A]'), ('subB', '[B]'), ('subC', '[C]'), ('subD', '[D]'), ('subE', '[E]'))
        curl_sub_list  = (('curlSubA', '[A]'), ('curlSubB', '[B]'), ('curlSubC', '[C]'), ('curlSubD', '[D]'),
                          ('curlSubE', '[E]')
                          )
        dev        = indigo.devices[dev_id]
        token      = values_dict['token']
        token_url  = values_dict['tokenUrl']
        url        = values_dict['sourceXML']
        url_list   = ('file:///', 'http://', 'https://', 'ftp://')   # noqa
        use_digest = values_dict['useDigest']
        var_list   = indigo.variables

        def are_subs_valid(subs: tuple, e_dict: indigo.Dict) -> indigo.Dict:
            """Test whether an Indigo variable substitution field contains a valid variable ID.

            Args:
                subs (tuple): A ``(field_key, label)`` pair where field_key names the dialog field.
                e_dict (indigo.Dict): The error message dictionary to populate on failure.

            Returns:
                indigo.Dict: The error dictionary, updated with any new validation errors.
            """
            try:
                # Ensure that values entered into the substitution fields are valid Indigo variable IDs.
                if values_dict[subs[0]].isspace() or values_dict[subs[0]] == "":
                    pass
                elif int(values_dict[subs[0]]) not in var_list:
                    e_dict[subs[0]] = "Please enter a valid variable ID."
            except ValueError:
                e_dict[subs[0]] = "Please enter a valid variable ID."

            return e_dict

        # The timeout value must be a real number.
        try:
            _ = float(values_dict['timeout'])
        except ValueError:
            error_msg_dict['timeout'] = "The timeout value must be a real number."

        # The timeout value must be less than the refresh frequency.
        try:
            refresh_freq = int(values_dict['refreshFreq'])
            if int(values_dict['timeout']) >= refresh_freq != 0:
                error_msg_dict['timeout'] = "The timeout value cannot be greater than the refresh frequency."
                error_msg_dict['refreshFreq'] = "The refresh frequency must be less than or equal to the timeout value."
        except ValueError:
            error_msg_dict['timeout'] = "The timeout value must be a real number."

        # Max retries must be an integer.
        try:
            _ = int(values_dict['maxRetries'])
        except ValueError:
            error_msg_dict['maxRetries'] = "The max retries value must be an integer."

        # Test the source URL/Path for proper prefix.
        if not url.startswith(url_list):
            error_msg_dict['sourceXML'] = "Please enter a valid URL/Path."

        # Test the token URL/Path for proper prefix.
        if use_digest == 'Token' and not token_url.startswith(url_list):
            error_msg_dict['tokenUrl'] = "You must supply a valid Token URL."

        # Test the bearer token value to ensure it's not empty.
        if use_digest == 'Bearer' and token.replace(" ", "") == "":
            error_msg_dict['token'] = (
                "You must supply a Token value. The plugin does not attempt to ensure that the token is valid."
            )

        # Test the variable substitution IDs and indexes for URL subs. If substitutions aren't enabled, we can skip
        # this bit.
        if values_dict['doSubs']:
            for sub in sub_list:
                error_msg_dict = are_subs_valid(subs=sub, e_dict=error_msg_dict)

        # Test the variable substitution IDs and indexes for curl subs. If substitutions aren't enabled, we can skip
        # this bit.
        if values_dict['curlSubs']:
            for c_sub in curl_sub_list:
                error_msg_dict = are_subs_valid(subs=c_sub, e_dict=error_msg_dict)

        if len(error_msg_dict) > 0:
            error_msg_dict['showAlertText'] = (
                """
                Configuration Errors\n\nThere are one or more settings that need to be" "corrected. Fields requiring
                attention will be highlighted.
                """
            )
            return False, values_dict, error_msg_dict

        # ===========================  Disable SQL Logging  ===========================
        # If the user elects to disable SQL logging, we need to set the property 'sqlLoggerIgnoreStates' to "*".
        # 2021-01-08 DaveL17 - we were mistakenly saving this to pluginProps instead of sharedProps.
        # sharedProps is correct.
        shared_props = dev.sharedProps
        if values_dict['disableLogging']:
            shared_props['sqlLoggerIgnoreStates'] = "*"
        else:
            shared_props['sqlLoggerIgnoreStates'] = ""

        dev.replaceSharedPropsOnServer(shared_props)

        return True, values_dict, error_msg_dict

    # =============================================================================
    # =============================== Plugin Methods ==============================
    # =============================================================================
    def adjust_refresh_time(self, values_dict: indigo.Dict = None) -> None:
        """Programmatically adjust the refresh frequency for an individual device.

        Called via an Indigo Action. Allows the refresh rate to be changed dynamically—for
        example, a Trigger can fire based on a GhostXML state value and call this action to
        increase or decrease the polling frequency in response.

        Args:
            values_dict (indigo.Dict): The action values dict. Must include ``deviceId`` and
                ``props['new_refresh_freq']``.
        """
        dev       = self.managed_devices[values_dict.deviceId].device
        new_props = dev.pluginProps
        new_props['refreshFreq'] = int(values_dict.props['new_refresh_freq'])
        dev.replacePluginPropsOnServer(new_props)

    # =============================================================================
    @staticmethod
    def comms_kill_all() -> bool:
        """Disable communication for all plugin devices.

        Sets the enabled status of every GhostXML device to False.

        Returns:
            bool: Always returns True.
        """
        for dev in indigo.devices.iter("self"):
            if dev.enabled:
                indigo.device.enable(dev, value=False)
        return True

    # =============================================================================
    @staticmethod
    def comms_unkill_all() -> bool:
        """Enable communication for all plugin devices.

        Sets the enabled status of every GhostXML device to True.

        Returns:
            bool: Always returns True.
        """
        for dev in indigo.devices.iter("self"):
            if not dev.enabled:
                indigo.device.enable(dev, value=True)
        return True

    # =============================================================================
    @staticmethod
    def get_device_list(filter: str = "", type_id: int = 0, values_dict: indigo.Dict = None, target_id: int = 0) -> list:  # noqa
        """Return a list of plugin devices for use in dropdown menus.

        Args:
            filter (str): An Indigo device filter string (unused; all plugin devices returned).
            type_id (int): The device type ID (unused).
            values_dict (indigo.Dict): The current dialog values (unused).
            target_id (int): The target device ID (unused).

        Returns:
            list: A list of ``(dev.id, dev.name)`` tuples for all plugin devices.
        """
        return [(dev.id, dev.name) for dev in indigo.devices.iter(filter="self")]

    # =============================================================================
    def _log_environment_info(self) -> None:
        """Write plugin and system environment details to the log on startup.
        """
        self.indigo_log_handler.setLevel(20)
        self.logger.info("")
        self.logger.info(f"{' Initializing New Plugin Session ':{'='}^130}")
        self.logger.info(f"{'Plugin name:':<31} {self.pluginDisplayName}")
        self.logger.info(f"{'Plugin version:':<31} {self.pluginVersion}")
        self.logger.info(f"{'Plugin ID:':<31} {self.pluginId}")
        self.logger.info(f"{'Indigo version:':<31} {indigo.server.version}")
        sys_version = sys.version.replace('\n', '')
        self.logger.info(f"{'Python version:':<31} {sys_version}")
        self.logger.info(f"{'Flatdict version:':<31} {flatdict.__version__}")
        self.logger.info(f"{'Process ID:':<31} {os.getpid()}")
        self.logger.info("=" * 130)
        self.indigo_log_handler.setLevel(self.debug_level)

    # =============================================================================
    def _process_bad_calls(self, dev: indigo.Device = None, retries: int = 0) -> bool | None:
        """Disable a device that has exceeded its maximum number of consecutive failed calls.

        Adds the device to the disabled trigger queue, logs a critical message, disables the
        device in Indigo, and updates its state icon to the tripped state.

        Args:
            dev (indigo.Device): The device that has exceeded its retry limit.
            retries (int): The configured maximum number of retries.

        Returns:
            bool | None: True if the device was disabled, None if it was already disabled.
        """
        if dev.enabled:
            # Add the device to the trigger queue and disable it.
            self.master_trigger_dict['disabled'].put(dev.id)

            self.logger.critical(
                "Disabling device: [%s] %s because it has failed %s times." % (dev.id, dev.name, retries)
            )
            indigo.device.enable(dev.id, value=False)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return True
        return None

    # =============================================================================
    def _process_triggers(self) -> bool:
        """Process any pending plugin triggers.

        Drains the disabled-devices queue and fires the corresponding Indigo trigger for each
        device ID found in the queue, provided the trigger is enabled.

        Returns:
            bool: Always returns True.
        """
        try:
            disabled_devices_queue = self.master_trigger_dict['disabled']

            # Process any device IDs in the disable devices queue.
            while not disabled_devices_queue.empty():
                dev_id     = disabled_devices_queue.get()
                trigger_id = self.master_trigger_dict[str(dev_id)]

                if indigo.triggers[trigger_id].enabled:
                    indigo.trigger.execute(trigger_id)

        except KeyError:
            pass

        return True

    # =============================================================================
    def refreshDataAction(self, values_dict: indigo.Dict = None) -> None:  # noqa
        """Legacy callback to refresh data for all devices.

        Retained for backwards compatibility with old Action Item configurations. Delegates to
        ``refresh_data_action()``. Users should update their Action Items to use the new name.

        Args:
            values_dict (indigo.Dict): The action values dictionary.
        """
        self.logger.warning("You are using an outdated plugin Action Item. Please update it.")
        self.refresh_data_action(values_dict)

    # =============================================================================
    def refreshDataForDevAction(self, values_dict: indigo.Dict = None) -> None:  # noqa
        """Legacy callback to refresh data for a specified device.

        Retained for backwards compatibility with old Action Item configurations. Delegates to
        ``refresh_data_for_dev_action()``. Users should update their Action Items to use the new name.

        Args:
            values_dict (indigo.Dict): The action values dictionary.
        """
        self.logger.warning("You are using an outdated plugin Action Item. Please update it.")
        self.refresh_data_for_dev_action(values_dict)

    # =============================================================================
    def refresh_data_action(self, values_dict: indigo.Dict = None) -> None:  # noqa
        """Initiate a data refresh for all devices via a plugin menu or action call.

        Args:
            values_dict (indigo.Dict): The action values dictionary (unused).
        """
        self.refresh_data()

    # =============================================================================
    def refresh_data(self) -> bool:
        """Initiate a data refresh for all managed plugin devices.

        Adds each managed device to its own update queue. If no devices are active, logs a
        warning and returns early.

        Returns:
            bool: True on success, False if a KeyError occurs during iteration.
        """
        # If there are no devices created or all devices are disabled.
        if len(self.managed_devices) == 0:
            self.logger.warning("No GhostXML devices to refresh.")
            return True

        # Iterate devices to see if an update is required.
        try:
            for dev_id in self.managed_devices:
                dev = self.managed_devices[dev_id].device
                self.managed_devices[dev_id].queue.put(dev)

            return True

        except KeyError:  # noqa
            self.logger.exception("Error refreshing devices. Please check settings.")
            return False

    # =============================================================================
    def refresh_data_for_dev_action(self, values_dict: indigo.Dict = None) -> None:
        """Initiate a data refresh for a single device via an Indigo Action call.

        Args:
            values_dict (indigo.Dict): The action values dictionary. Must include ``deviceId``.
        """
        dev = self.managed_devices[values_dict.deviceId].device
        self.managed_devices[dev.id].queue.put(dev)

    # =============================================================================
    @staticmethod
    def _time_to_update(dev: indigo.Device = None) -> bool:  # noqa
        """Determine whether a device is due for a data refresh.

        Compares the time elapsed since the device's last update against its configured refresh
        frequency. Returns False if the device has no timestamp, is disabled, or is not yet due.

        Args:
            dev (indigo.Device): The device to evaluate.

        Returns:
            bool: True if the device should be refreshed now, False otherwise.
        """
        # 2022-02-15 DaveL17 - Refactored for simplicity. See GitHub for prior code.
        # If device has a deviceTimestamp key and is enabled, test to see if the device is ready for a refresh.
        if "deviceTimestamp" in dev.states and dev.enabled:
            t_since_upd = int(t.time() - float(dev.states["deviceTimestamp"]))

            if int(t_since_upd) > int(dev.pluginProps.get("refreshFreq", 300)) > 0:
                return True

        # If the device does not have a timestamp key, is not ready for a refresh, or is disabled.
        return False

    def my_tests(self, action: indigo.PluginAction = None) -> None:  # noqa
        """Run the plugin's unit test suite via a plugin action item.

        Imports the ``iom_tests`` module, instantiates the test class, and runs all test
        groups (actions, triggers, Indigo methods, plugin methods). Results are logged as
        warnings.

        Args:
            action (indigo.PluginAction): The Indigo action that triggered the test run.
        """
        from Tests import iom_tests  # test_devices
        tests = iom_tests.TestPlugin()

        def process_test_result(result: list, name: str) -> None:
            if result[0] is True:
                self.logger.warning("%s tests passed." % name)
            else:
                self.logger.warning("%s tests failed." % result[1])

        # ===================================== Plugin Action =====================================
        test = tests.test_plugin_actions(self)
        process_test_result(test, "Plugin Actions")

        # ===================================== Plugin Action =====================================
        test = tests.test_plugin_triggers(self)
        process_test_result(test, "Plugin Triggers")

        # ===================================== Indigo Methods =====================================
        test = tests.test_indigo_methods(self)
        process_test_result(test, "Indigo Methods")

        # ===================================== Plugin Methods =====================================
        test = tests.test_plugin_methods(self)
        process_test_result(test, "Plugin Methods")


# =============================================================================
class PluginDevice:
    """Represents a single managed GhostXML device and its associated update thread and queue.

    Stores the Indigo device instance, raw and parsed data, bad-call counter, and the
    per-device Queue/Thread pair used to dispatch asynchronous data refresh tasks.
    """

    # =============================================================================
    def __init__(self, plugin: Plugin, device: indigo.Device) -> None:
        """Initialize the PluginDevice, set up instance attributes, and start the update thread.

        Args:
            plugin (Plugin): The parent Plugin instance.
            device (indigo.Device): The Indigo device this object manages.
        """
        self.plugin_device_is_initializing = True

        self.device            = device
        self.host_plugin       = plugin
        self.bad_calls         = 0
        self.final_dict        = {}
        self.json_raw_data     = ''
        self.raw_data          = ''
        self.old_device_states = {}

        self.queue      = Queue(maxsize=0)
        self.dev_thread = threading.Thread(name=self.device.id, target=self._initiate_device_update, args=(self.queue,))
        self.dev_thread.start()

        self.plugin_device_is_initializing = False
        self.logger = logging.getLogger("Plugin")

    # =============================================================================
    def __str__(self) -> str:
        """Return a formatted string representation of the PluginDevice.

        Returns:
            str: A string showing the device ID, thread, and queue information.
        """
        return f"[{self.device.id:>11}] {self.dev_thread:<46} {self.queue:<40}"

    # =============================================================================
    def _initiate_device_update(self, update_queue: Queue = None) -> None:
        """Keep the device thread alive and dispatch updates from the queue.

        Runs as the device's background thread target. Polls the queue every 250ms and calls
        ``refresh_data_for_dev()`` for each task retrieved. Acts as a bridge between the Plugin
        class's main loop and the per-device refresh logic.

        Args:
            update_queue (Queue): The queue from which device refresh tasks are consumed.
        """
        try:
            while True:
                t.sleep(0.25)
                while not update_queue.empty():
                    # Set the class' debug level to the level set for the main plugin thread--otherwise, it will stay
                    # initiated at 5. We do this here in case the main plugin logger level has changed.
                    self.logger.setLevel(self.host_plugin.debug_level)
                    task = update_queue.get()
                    self.refresh_data_for_dev(task)

        except ValueError:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception("General exception:")

    # =============================================================================
    def get_the_data(self, dev: indigo.Device = None) -> str | bytes:
        """Retrieve raw data from the device's configured URL or file path.

        Constructs the API URL (applying any configured Indigo variable substitutions), selects
        the appropriate authentication method (Raw curl, Digest, Basic, Bearer, Token, or none),
        issues the request, and returns the raw response. A timer-based kill mechanism handles
        curl subprocess timeouts.

        Args:
            dev (indigo.Device): The Indigo device whose data source is being polled.

        Returns:
            str | bytes: The raw XML or JSON response body, or a JSON error sentinel string on
            failure.
        """
        return_code = 0
        result      = ""
        err         = ""
        try:
            auth_type  = dev.pluginProps.get('useDigest', 'None')
            call_type  = ""
            curl_array = dev.pluginProps.get('curlArray', '')
            password   = dev.pluginProps.get('digestPass', '')
            subber     = self.host_plugin.substitute
            url        = dev.pluginProps['sourceXML']
            username   = dev.pluginProps.get('digestUser', '')
            timeout    = int(dev.pluginProps.get('timeout', 5))

            if dev.pluginProps.get('disableGlobbing', False):
                glob_off = 'g'
            else:
                glob_off = ''

            # Format any needed URL substitutions
            if dev.pluginProps.get('doSubs', False):
                self.logger.debug("[%s] URL: %s (before substitution)" % (dev.name, url))
                url = subber(url.replace("[A]", f"%%v:{dev.pluginProps['subA']}%%"))
                url = subber(url.replace("[B]", f"%%v:{dev.pluginProps['subB']}%%"))
                url = subber(url.replace("[C]", f"%%v:{dev.pluginProps['subC']}%%"))
                url = subber(url.replace("[D]", f"%%v:{dev.pluginProps['subD']}%%"))
                url = subber(url.replace("[E]", f"%%v:{dev.pluginProps['subE']}%%"))
                self.logger.debug("[%s] URL: %s (after substitution)" % (dev.name, url))

            # Added by DaveL17 - 2020 10 09
            # Format any needed Raw Curl substitutions
            if dev.pluginProps.get('curlSubs', False):
                self.logger.debug("[%s] Raw Curl: %s (before substitution)" % (dev.name, curl_array))
                curl_array = subber(curl_array.replace("[A]", f"%%v:{dev.pluginProps['curlSubA']}%%"))
                curl_array = subber(curl_array.replace("[B]", f"%%v:{dev.pluginProps['curlSubB']}%%"))
                curl_array = subber(curl_array.replace("[C]", f"%%v:{dev.pluginProps['curlSubC']}%%"))
                curl_array = subber(curl_array.replace("[D]", f"%%v:{dev.pluginProps['curlSubD']}%%"))
                curl_array = subber(curl_array.replace("[E]", f"%%v:{dev.pluginProps['curlSubE']}%%"))
                self.logger.debug("[%s] Raw Curl: %s (after substitution)" % (dev.name, curl_array))

            # Initiate curl call to data source.
            # ================================  Curl Auth  ================================
            # GlennNZ
            match auth_type:
                case "Raw":
                    # Since this option is processing raw curl commands, it will need to remain a curl call via
                    # subprocess().
                    # v = [verbose] s = [silent] k = [insecure]
                    call_type = "curl"
                    proc = subprocess.Popen(
                        f'/usr/bin/curl -vsk{glob_off} {curl_array} {url}',
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        shell=True
                    )
                # ===============================  Digest Auth  ===============================
                case 'Digest':
                    call_type = 'request'
                    proc = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=timeout)
                # ===============================  Basic Auth  ================================
                case 'Basic':
                    call_type = 'request'
                    basic = HTTPBasicAuth(username, password)
                    proc = requests.get(url, auth=basic, timeout=timeout)
            # ===============================  Bearer Auth  ===============================
                case 'Bearer':
                    call_type = 'request'
                    token = dev.pluginProps['token']
                    proc = requests.get(url, headers={'Authorization': f'Bearer {token}'}, timeout=timeout)
                # ===============================  Token Auth  ================================
                # berkinet and DaveL17
                case 'Token':
                    a_url     = dev.pluginProps['tokenUrl']
                    call_type = 'request'
                    data = {"pwd": password, "remember": 1}
                    headers = {'Content-Type': 'application/json'}

                    # Get the token
                    response = requests.post(a_url, json=data, headers=headers, timeout=timeout)
                    reply = response.json()
                    token = reply["access_token"]

                    url = f"{a_url}?access_token={token}"
                    proc = requests.get(url, timeout=timeout)
                # =================================  No Auth  =================================
                case _:
                    if url.startswith('file'):
                        # If the locator is a reference to a file, requests won't handle it.
                        call_type = 'file'
                        url = url.replace('file://', '')
                        url = url.replace('%20', ' ')
                        with open(url, 'r', encoding="utf-8") as infile:
                            proc = bytes(infile.read(), 'utf-8')
                    else:
                        call_type = 'request'
                        proc = requests.get(url, timeout=timeout)

            # =============================================================================
            # The following code adds a timeout function to the call.
            # Added by GlennNZ and DaveL17 2018-07-18
            # duration   = int(dev.pluginProps.get('timeout', '5'))
            # timer_kill = threading.Timer(duration, self.kill_curl, [proc])
            timer_kill = threading.Timer(timeout, self.kill_curl, [proc])
            match call_type:
                case "file":
                    # Cases that used a local file as a source land here.
                    result = proc
                case "curl":
                    try:
                        # Cases that used the curl method land here.
                        timer_kill.start()
                        result, err = proc.communicate()
                        return_code = proc.returncode
                    finally:
                        timer_kill.cancel()
                case "request":
                    # Cases that used the requests library land here.
                    result = proc.text
                    return_code = proc.status_code

            # =============================================================================
            # 2021-01-03 DaveL17: Did a little more digging on exit codes and pulled codes from the man page. See
            # `curlcodes.py` for more information.
            match call_type:
                case "curl":
                    if return_code != 0:
                        # for plugin log (verbose error)
                        curl_err = err.replace(b'\n', b' ')
                        self.host_plugin.logger.debug("[%s] curl error %s." % (dev.name, curl_err))

                        # for Indigo event log
                        err_msg = curl_code.get(f"{return_code}", "Unknown code message.")
                        self.host_plugin.logger.debug("[%s] - Return code: %s - %s]" % (dev.name, return_code, err_msg))
                case "request":
                    if return_code != 200:
                        self.logger.warning("%s - [%s] %s", dev.name, return_code, http_code[return_code])
            return result

        except IOError:
            self.logger.warning("[%s] IOError:  Skipping until next scheduled poll." % dev.name)
            self.logger.debug("[%s] Device is offline. No data to return. Returning dummy dict." % dev.name)
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No comm")
            return '{"GhostXML": "IOError"}'

        except Exception:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception("General exception: %s" % return_code)
            return '{"GhostXML": "General Exception"}'

    # =============================================================================
    def _clean_the_keys(self, input_data: dict = None) -> dict | None:
        """Sanitize dictionary keys so they are valid Indigo device state names.

        Replaces problematic characters using the ``CHARS_TO_REPLACE`` mapping, removes
        characters in ``CHARS_TO_REMOVE``, and prepends ``No_`` to any key that begins with a
        digit (Indigo does not accept state names starting with a number).

        Args:
            input_data (dict): The dictionary whose keys need to be sanitized.

        Returns:
            dict | None: A new dictionary with sanitized keys, or None if an exception occurs.
        """
        try:
            chars_to_replace = dict((re.escape(k), v) for k, v in CHARS_TO_REPLACE.items())
            pattern     = re.compile("|".join(chars_to_replace))
            output_dict = {}

            for key in input_data:
                # Some characters need to be replaced in keys because simply deleting them could cause problems. Add
                # additional k/v pairs to chars_to_replace as needed.['9@a(b)' --> '9_at_a(b)']
                new_key = pattern.sub(lambda m: chars_to_replace[re.escape(m.group(0))], str(key))

                # Some characters can simply be eliminated. If something here causes problems, remove the element from
                # the set and add it to the replacement dict above. ['9_at_a(b)' --> '9_at_ab']
                new_key = ''.join([c for c in new_key if c not in CHARS_TO_REMOVE])

                # Indigo will not accept device state names that begin with a number, so inspect them and prepend any
                # with the string "No_" to force them to something that Indigo will accept. ['9_at_ab' --> 'No_9_at_ab']
                if new_key[0].isdigit():
                    new_key = f'No_{new_key}'

                output_dict[new_key] = input_data[key]

            return output_dict

        except RuntimeError:
            pass

        except ValueError:
            self.logger.exception('Error cleaning dictionary keys:')

        except Exception:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception('General exception:')

    # =============================================================================
    def kill_curl(self, proc: subprocess.Popen = None) -> None:
        """Kill a curl subprocess that has exceeded its timeout.

        Called by a threading.Timer when the configured timeout elapses. Silently ignores
        POSIX errno 3 ("No such process"), which occurs when the process has already exited.

        Args:
            proc (subprocess.Popen): The curl subprocess to terminate.
        """
        try:
            self.logger.debug('Timeout for Curl Subprocess. Killed by timer.')
            proc.kill()

        except OSError as sub_error:
            if "OSError: [Errno 3]" in str(sub_error):
                self.logger.debug(
                    "OSError No. 3: No such process. This is a result of the plugin trying to kill a process that is "
                    "no longer running."
                )
            else:
                self.logger.exception('General exception:')

        except Exception:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception('General exception:')

    # =============================================================================
    def parse_the_json(self, dev: indigo.Device = None, root: str = "") -> flatdict.FlatDict | dict:
        """Parse a raw JSON string into a flat dictionary.

        Deserializes the JSON payload and passes it through ``flatdict.FlatDict`` (using
        ``'_ghostxml_'`` as the delimiter) to produce a single-level key/value mapping. If the
        top-level JSON value is a list, it is first converted to a dict with ``No_<index>``
        keys. On parse failure the existing device states are returned so the device thread
        remains alive.

        Args:
            dev (indigo.Device): The Indigo device whose JSON data is being parsed.
            root (str): The raw JSON string to parse.

        Returns:
            flatdict.FlatDict | dict: The flattened data, or the previous device states dict
            if a parse error occurs.
        """
        self.old_device_states = dict(dev.states)

        # =============================  Drop UI States  ==============================
        # Drop the '.ui' states.
        keys = list(self.old_device_states)
        for key in keys:
            if key.endswith('.ui'):
                del self.old_device_states[key]

        try:
            parsed_json = json.loads(root)

            # If List flattens once - with addition of No_ to the beginning (Indigo does not allow DeviceNames to start
            # with numbers) then flatDict runs - and appears to run correctly (as no longer list - dict) if
            # isinstance(list) then will flatten list down to dict.

            if isinstance(parsed_json, list):
                parsed_json = dict(("No_" + f"{i}", v) for (i, v) in enumerate(parsed_json))

            self.json_raw_data = flatdict.FlatDict(parsed_json, delimiter='_ghostxml_')

            dev.updateStateOnServer('parse_error', value=False)

            return self.json_raw_data

        except (ValueError, json.decoder.JSONDecodeError):
            self.logger.debug("[%s] Parse Error:" % dev.name)
            self.logger.debug("[%s] jsonRawData %s" % (dev.name, self.json_raw_data))

            # If we let it, an exception here will kill the device's thread. Therefore, we have to return something
            # that the device can use in order to keep the thread alive.
            self.logger.warning(
                "%s - There was a parse error. Will continue to poll. "
                "Check the plugin log for more information." % dev.name
            )
            self.old_device_states['parse_error'] = True
            return self.old_device_states

        except Exception:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception('General exception:')
            return self.old_device_states

    # =============================================================================
    def parse_state_values(self, dev: indigo.Device = None) -> None:
        """Write values from ``self.final_dict`` to the corresponding Indigo device states.

        For ``GhostXMLdeviceTrue`` devices, string values that represent boolean concepts
        (e.g. "on", "true", "yes") also generate a companion ``<key>_bool`` state. For
        standard ``GhostXMLdevice`` devices all values are coerced to strings.

        Args:
            dev (indigo.Device): The Indigo device whose states are being updated.
        """
        state_list  = []
        sorted_list = [_ for _ in sorted(self.final_dict.keys()) if _ not in ('deviceIsOnline', 'parse_error')]

        try:
            if dev.deviceTypeId == 'GhostXMLdeviceTrue':
                # Parse all values into states as true type.
                for key in sorted_list:
                    value = self.final_dict[key]
                    if isinstance(value, str):
                        match value.lower():
                            case 'armed' | 'locked' | 'on' | 'open' | 'true' | 'up' | 'yes':
                                self.final_dict[f"{key}_bool"] = True
                                state_list.append({'key': f"{key}_bool", 'value': True})
                            case 'closed' | 'disarmed' | 'down' | 'false' | 'no' | 'off' | 'unlocked':
                                self.final_dict[f"{key}_bool"] = False
                                state_list.append({'key': f"{key}_bool", 'value': False})
                    state_list.append({'key': key, 'value': self.final_dict[key], 'uiValue': self.final_dict[key]})
            else:
                # Parse all values into states as strings.
                for key in sorted_list:
                    state_list.append(
                        {'key': key, 'value': str(self.final_dict[key]), 'uiValue': str(self.final_dict[key])}
                    )

        except ValueError as sub_error:
            self.logger.critical(
                "[%s] Error parsing state values.\n%s\nReason: %s" % (dev.name, self.final_dict, sub_error)
            )
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
            state_list.append({'key': 'deviceIsOnline', 'value': False, 'uiValue': "Error"})

        except Exception as subError:
            # Add wider exception testing to test errors
            self.logger.exception("General exception: %s" % subError)

        dev.updateStatesOnServer(state_list)

    # =============================================================================
    def refresh_data_for_dev(self, dev: indigo.Device = None) -> None:
        """Refresh data for a single device if it is configured and enabled.

        Retrieves raw data via ``get_the_data()``, routes it to the appropriate parser (XML or
        JSON), updates device states, and manages the bad-call counter and device status icon.

        Args:
            dev (indigo.Device): The Indigo device to refresh.
        """
        try:
            if dev.configured and dev.enabled:

                # Get the data.
                self.raw_data = self.get_the_data(dev)

                dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Processing")

                update_time = t.strftime("%m/%d/%Y at %H:%M")
                dev.updateStateOnServer('deviceLastUpdated', value=update_time)
                dev.updateStateOnServer('deviceTimestamp', value=t.time())

                # Throw the data to the appropriate module to flatten it.
                if dev.pluginProps['feedType'] == "XML":
                    self.raw_data = self.strip_namespace(dev, self.raw_data)
                    self.final_dict = iterateXML.iterate_main(self.raw_data)

                elif dev.pluginProps['feedType'] == "JSON":
                    self.final_dict = self.parse_the_json(dev, self.raw_data)
                    self.final_dict = self._clean_the_keys(self.final_dict)

                else:
                    self.logger.warning("%s: The plugin only supports XML and JSON data sources." % dev.name)
                    return

                if self.final_dict is not None:
                    # Create the device states.
                    dev.stateListOrDisplayStateIdChanged()

                    # Put the final values into the device states.
                    self.parse_state_values(dev)

                    if "GhostXML" in dev.states:
                        dev.updateStateOnServer(
                            'deviceIsOnline',
                            value=False,
                            uiValue=dev.states.get('GhostXML', 'G')
                        )
                        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                        self.bad_calls += 1
                    elif dev.states.get("parse_error", False):
                        dev.updateStateOnServer('deviceIsOnline', value=False, uiValue='Error')
                        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                        self.bad_calls += 1
                    # 2023-10-04 DaveL17 - update to include XML parse error.
                    elif dev.states.get("Response", "") in ["No data to return.", "Parse error. Check XML source."]:
                        dev.updateStateOnServer('deviceIsOnline', value=False, uiValue='Error')
                        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                        self.bad_calls += 1
                    else:
                        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Updated")
                        self.logger.info("%s updated." % dev.name)
                        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                        dev.setErrorStateOnServer(None)
                        self.bad_calls = 0

                else:
                    # Set the Timestamp so that the seconds-since-update code doesn't keep checking a dead link /
                    # invalid URL every 5 seconds - it will keep checking on its normal schedule. BUT don't set the
                    # "lastUpdated" value so humans can see when it last successfully updated.
                    dev.updateStateOnServer('deviceTimestamp', value=t.time())
                    dev.setErrorStateOnServer("Error")
                    self.bad_calls += 1

            else:
                self.logger.debug(
                    "[%s] Device not available for update "
                    "[Enabled: %s, Configured: %s]" % (dev.name, dev.enabled, dev.configured)
                )
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        except KeyError:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception("General exception: %s" % dev.name)

    # =============================================================================
    def strip_namespace(self, dev: indigo.Device = None, root: bytes | str = "") -> str:
        """Strip XML namespace declarations from a raw XML payload.

        Removes ``xmlns``, ``xmlns:xsi``, ``xmlns:xsd``, and ``xsi:noNamespaceSchemaLocation``
        attributes from the XML string so that the parser can handle the document without
        namespace-aware lookups. If ``root`` is empty, substitutes a default empty-document
        placeholder.

        Args:
            dev (indigo.Device): The Indigo device associated with this payload (used for
                logging).
            root (bytes | str): The raw XML payload as a string or bytes object.

        Returns:
            str: The namespace-stripped XML string, or the default empty-document placeholder
            on error.
        """
        d_root = (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<Emptydict>"
            "<Response>No data to return.</Response>"
            "</Emptydict>"
        )

        try:
            if root == "":
                root = d_root

            # root may be a bytes object or a string when it gets here. We want a string.
            if not isinstance(root, str):
                try:
                    root = root.decode('utf-8')
                except UnicodeDecodeError:
                    self.logger.warning("%s - There was a problem decoding the payload object." % dev.name)

            # Remove namespace stuff if it's in there. There's probably a more comprehensive re.sub() that could be
            # run, but it also could do *too* much.
            self.raw_data = ''
            # self.raw_data = re.sub(' xmlns="[^"]+"', '', root.decode('utf-8'))
            self.raw_data = re.sub(' xmlns="[^"]+"', '', root)
            self.raw_data = re.sub(' xmlns:xsi="[^"]+"', '', self.raw_data)
            self.raw_data = re.sub(' xmlns:xsd="[^"]+"', '', self.raw_data)
            self.raw_data = re.sub(' xsi:noNamespaceSchemaLocation="[^"]+"', '', self.raw_data)

            return self.raw_data

        except ValueError as sub_error:
            self.logger.warning(
                "[%s] Error parsing source data: %s. Skipping until next scheduled poll." % (dev.name, sub_error)
            )
            self.raw_data = d_root
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No data")
            return self.raw_data

        except Exception:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception('General exception:')
            return self.raw_data
