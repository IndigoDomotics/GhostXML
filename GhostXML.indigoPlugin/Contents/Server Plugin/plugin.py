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
    import pydevd  # noqa
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
__version__   = "2022.3.1"


# =============================================================================
class Plugin(indigo.PluginBase):
    """
    Standard Indigo Plugin Class

    :param indigo.PluginBase:
    """
    def __init__(self, plugin_id="", plugin_display_name="", plugin_version="", plugin_prefs=None):
        """
        Plugin initialization

        :param str plugin_id:
        :param str plugin_display_name:
        :param str plugin_version:
        :param indigo.Dict plugin_prefs:
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

        log_format = '%(asctime)s.%(msecs)03d\t%(levelname)-10s\t%(name)s.%(funcName)-28s %(message)s'
        self.plugin_file_handler.setFormatter(logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S'))
        self.indigo_log_handler.setLevel(self.debug_level)

        # ============================= Remote Debugging ==============================
        # try:
        #     pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True, suspend=False)
        # except:
        #     pass

        self.plugin_is_initializing = False

    # =============================================================================
    def log_plugin_environment(self):
        """
        Log pluginEnvironment information when plugin is first started

        This information will be printed to the Event Log regardless of the current logging level set in config
        preferences.
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
    def __del__(self):
        """
        Called when a device is deleted
        """
        indigo.PluginBase.__del__(self)

    # =============================================================================
    # =============================== Indigo Methods ==============================
    # =============================================================================
    def closedDeviceConfigUi(self, values_dict: indigo.Dict=None, user_cancelled: bool=False, type_id: str="", dev_id: int=0):  # noqa
        """
        Standard Indigo method called when the device configuration dialog is closed

        :param indigo.Dict values_dict:
        :param bool user_cancelled:
        :param str type_id:
        :param int dev_id:
        """
        dev = indigo.devices[dev_id]

        # Replace device to list of managed devices to ensure any configuration changes are used.
        self.managed_devices[dev.id] = PluginDevice(self, dev)

    # =============================================================================
    def closedPrefsConfigUi(self, values_dict=None, user_cancelled=False):  # noqa
        """
        Standard Indigo method called when plugin preferences dialog is closed.

        :param indigo.Dict values_dict:
        :param bool user_cancelled:
        :return:
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
    def device_deleted(self, dev=None):
        """
        Remove deleted device from managed list of devices

        =====
        :param indigo.Device dev:
        """
        self.logger.debug(f"{dev.name} [{dev.id}] deleted.")
        if dev.id in self.managed_devices:
            del self.managed_devices[dev.id]

    # =============================================================================
    def deviceStartComm(self, dev=None):  # noqa
        """
        Standard Indigo method called when the device is enabled

        :param indigo.Device dev:
        """
        self.logger.debug(f"{dev.name} communication starting.")

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
            self.logger.debug(f"{dev.name} does not have a URL/Path value set. Disabling.")
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

        self.logger.debug(f"[{dev.name}] communication started.")

    # =============================================================================
    def deviceStopComm(self, dev=None):  # noqa
        """
        Standard Indigo method called when the device is disabled

        :param indigo.Device dev:
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

            self.logger.debug(f"[{dev.name}] communication stopped.")

        except KeyError:
            self.logger.warning(
                f"{dev.name} - Problem removing device from managed device list. Consider restarting the plugin."
            )

    # =============================================================================
    def getDeviceConfigUiXml(self, type_id="", dev_id=0):  # noqa
        """
        Standard Indigo method called when device config dialog is opened

        :param str type_id:
        :param int dev_id:
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

    # =============================================================================
    def getDeviceStateList(self, dev=None):  # noqa
        """
        Assign data keys to device state names (Indigo)

        The getDeviceStateList() method pulls out all the keys in self.finalDict and assigns them to device states. It
        returns the modified stateList which is then written back to the device in the main thread. This method is
        automatically called by stateListOrDisplayStateIdChanged() and by Indigo when Triggers and Control Pages are
        built. Note that it's not possible to override Indigo's sorting of devices states which will present them as A,
        B, a, b.

        :param indigo.Device dev:
        :return state_list:
        """
        def parse_the_states(k, v):
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
        # self.logger.debug(f"self.managedDevices: {self.managedDevices}")
        state_list = indigo.PluginBase.getDeviceStateList(self, dev)

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
            self.logger.debug(f"[getDeviceStateList / self.managed_devices] = {self.managed_devices}")
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

    # =============================================================================
    def wakeUp(self):  # noqa
        """
        Standard Indigo method called when Indigo receives a system wakeup call
        """
        self.logger.debug("wakeUp method called")
        indigo.PluginBase.wakeUp(self)
        self.prepare_to_sleep = False

    # =============================================================================
    def prepareToSleep(self):  # noqa
        """
        Standard Indigo method called when Indigo receives a system sleep call
        """
        self.logger.debug("prepareToSleep method called")
        indigo.PluginBase.prepareToSleep(self)
        self.prepare_to_sleep = True

    # =============================================================================
    def runConcurrentThread(self):  # noqa
        """
        Standard Indigo method that runs continuously when plugin is enabled
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
                                self.logger.debug(f"Time to update: [{dev.name}]")
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
    def sendDevicePing(dev_id=0, suppress_logging=False):  # noqa
        """
        Standard Indigo method called when a plugin device receives a ping request

        :param int dev_id:
        :param bool suppress_logging:
        """
        indigo.server.log("GhostXML Plugin devices do not support the ping function.")
        return {'result': 'Failure'}

    # =============================================================================
    def shutdown(self):
        """
        Standard Indigo method called when the plugin is disabled
        """
        self.plugin_is_shutting_down = True
        self.indigo_log_handler.setLevel(20)
        self.logger.info('Shutdown complete.')

    # =============================================================================
    def startup(self):
        """
        Standard Indigo method called when the plugin is first started
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
    def triggerStartProcessing(self, trigger):  # noqa
        """
        Standard Indigo method called when a plugin trigger is enabled

        :param indigo.Trigger trigger:
        """
        self.logger.info(f"Trigger [{trigger.name}] started.")
        self.master_trigger_dict[trigger.pluginProps['disabledDevice']] = trigger.id

    # =============================================================================
    def triggerStopProcessing(self, trigger):  # noqa
        """
        Standard Indigo method called when a plugin trigger is disabled

        :param indigo.Trigger trigger:
        """
        self.logger.info(f"Trigger [{trigger.name}] stopped.")

    # =============================================================================
    def validateDeviceConfigUi(self, values_dict=None, type_id="", dev_id=0):  # noqa
        """
        Standard Indigo method called when device config dialog is closed

        :param indigo.Dict values_dict:
        :param str type_id:
        :param int dev_id:
        :return:
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
        var_list   = [var.id for var in indigo.variables]

        def are_subs_valid(subs, e_dict):
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
            # if int(values_dict['timeout']) >= refresh_freq and refresh_freq != 0:
            if int(values_dict['timeout']) >= refresh_freq != 0:
                error_msg_dict['timeout'] = "The timeout value cannot be greater than the refresh frequency."
                error_msg_dict['refreshFreq'] = "The refresh frequency cannot be greater than the timeout value."
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

        # Test the token URL/Path for proper prefix.
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
    def adjust_refresh_time(self, values_dict=None):
        """
        Programmatically Adjust the refresh time for an individual device

        The adjust_refresh_time method is used to adjust the refresh frequency of an individual GhostXML device by
        calling an Indigo Action. For example, user creates an Indigo Trigger that fires--based on some criteria like
        the value of a GhostXML state, which in turn calls an Indigo Action Item to adjust the refresh frequency. In
        other words, the user can increase/decrease the frequency based on some condition.

        :param indigo.Dict values_dict:
        :return:
        """
        dev       = self.managed_devices[values_dict.deviceId].device
        new_props = dev.pluginProps
        new_props['refreshFreq'] = int(values_dict.props['new_refresh_freq'])
        dev.replacePluginPropsOnServer(new_props)

    # =============================================================================
    @staticmethod
    def comms_kill_all():
        """
        Disable communication of all plugin devices

        comms_kill_all() sets the enabled status of all plugin devices to False.
        """
        for dev in indigo.devices.iter("self"):
            if dev.enabled:
                indigo.device.enable(dev, value=False)
        return True

    # =============================================================================
    @staticmethod
    def comms_unkill_all():
        """
        Enable communication of all plugin devices

        comms_unkill_all() sets the enabled status of all plugin devices to True.
        """
        for dev in indigo.devices.iter("self"):
            if not dev.enabled:
                indigo.device.enable(dev, value=True)
        return True

    # =============================================================================
    @staticmethod
    def get_device_list(filter="", type_id=0, values_dict=None, target_id=0):  # noqa
        """
        Return a list of plugin devices for use in dropdown menus

        Returns a list of plugin devices for use in dropdown menus in the form of
        [(dev.id, dev.name), (dev.id, dev.name)]

        :param str filter:
        :param int type_id:
        :param indigo.Dict values_dict:
        :param int target_id:
        :return list:
        """
        return [(dev.id, dev.name) for dev in indigo.devices.iter(filter="self")]

    # =============================================================================
    def _log_environment_info(self):
        """
        Write interesting information to the log on startup.
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
    def _process_bad_calls(self, dev=None, retries=0):
        """
        If a device has made too many unsuccessful attempts

        :param indigo.Device dev:
        :param int retries:
        :return:
        """
        if dev.enabled:
            # Add the device to the trigger queue and disable it.
            self.master_trigger_dict['disabled'].put(dev.id)

            self.logger.critical(f"Disabling device: [{dev.id}] {dev.name} because it has failed {retries} times.")
            indigo.device.enable(dev.id, value=False)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
            return True

    # =============================================================================
    def _process_triggers(self):
        """
        Process plugin triggers

        :return:
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
    def refreshDataAction(self, values_dict=None):  # noqa
        """
        Legacy callback to Refresh Data for All Devices

        This method supports the old callback name.

        :param indigo.Dict values_dict:
        :return:
        """
        self.logger.warning("You are using an outdated plugin Action Item. Please update it.")
        self.refresh_data_action(values_dict)

    # =============================================================================
    def refreshDataForDevAction(self, values_dict=None):  # noqa
        """
        Legacy callback to Refresh Data for a Specified Device

        This method supports the old callback name.

        :param indigo.Dict values_dict:
        :return:
        """
        self.logger.warning("You are using an outdated plugin Action Item. Please update it.")
        self.refresh_data_for_dev_action(values_dict)

    # =============================================================================
    def refresh_data_action(self, values_dict=None):  # noqa
        """
        Initiate data refresh based on menu call

        The refresh_data_action() method refreshes data for all devices based on a plugin menu call.

        :param indigo.Dict values_dict:
        """
        self.refresh_data()

    # =============================================================================
    def refresh_data(self):
        """
        The refresh_data() method controls the updating of all plugin devices

        Initiate a data refresh based on a normal plugin cycle.
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
    def refresh_data_for_dev_action(self, values_dict=None):
        """
        Initiate a device refresh based on an Indigo Action call

        The refresh_data_for_dev_action() method refreshes data for a selected device based on a plugin action call.

        :param indigo.Dict values_dict:
        """
        dev = self.managed_devices[values_dict.deviceId].device
        self.managed_devices[dev.id].queue.put(dev)

    # =============================================================================
    @staticmethod
    def _time_to_update(dev=None):  # noqa
        """
        Determine if a device is ready for a refresh

        Returns True if the device is ready to be updated, else returns False.

        :param indigo.Device dev:
        """
        # 2022-02-15 DaveL17 - Refactored for simplicity. See GitHub for prior code.
        # If device has a deviceTimestamp key and is enabled, test to see if the device is ready for a refresh.
        if "deviceTimestamp" in dev.states and dev.enabled:
            t_since_upd = int(t.time() - float(dev.states["deviceTimestamp"]))

            if int(t_since_upd) > int(dev.pluginProps.get("refreshFreq", 300)) > 0:
                return True

        # If the device does not have a timestamp key, is not ready for a refresh, or is disabled.
        return False


# =============================================================================
class PluginDevice:
    """
    Create device object and corresponding queue

    The PluginDevice class is used to create an object to store data related to each enabled plugin device. The object
    contains an instance of the Indigo device and a command queue.
    """

    # =============================================================================
    def __init__(self, plugin, device):
        """
        Title Placeholder

        :param Plugin plugin:
        :param indigo.Device device:
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
    def __str__(self):
        """
        Title Placeholder

        Body placeholder
        """
        return f"[{self.device.id:>11}] {self.dev_thread:<46} {self.queue:<40}"

    # =============================================================================
    def _initiate_device_update(self, update_queue=None):
        """
        Initiate an update of the device

        The _initiate_device_update method keeps the device thread alive and is used as a bridge between the Plugin
        class and the device class.

        :param Queue update_queue:
        :return:
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
    def get_the_data(self, dev=None):
        """
        The get_the_data() method is used to retrieve target data files.

        The get_the_data() method is used to construct the relevant API URL, sends the call to the data source via
        curl, and returns the result. The URL can be sent using auth as required (basic, digest) or without auth. In
        addition, Indigo substitutions are processed as required such that the user can modify the URL based on
        variable values.

        :param indigo.Device dev:
        :return XML' or class 'JSON result:
        """
        return_code = 0
        result      = ""
        err         = ""
        try:
            auth_type   = dev.pluginProps.get('useDigest', 'None')
            curl_array  = dev.pluginProps.get('curlArray', '')
            password    = dev.pluginProps.get('digestPass', '')
            subber      = self.host_plugin.substitute
            url         = dev.pluginProps['sourceXML']
            username    = dev.pluginProps.get('digestUser', '')

            if dev.pluginProps.get('disableGlobbing', False):
                glob_off = 'g'
            else:
                glob_off = ''

            # Format any needed URL substitutions
            if dev.pluginProps.get('doSubs', False):
                self.logger.debug(f"[{dev.name}] URL: {url} (before substitution)")
                url = subber(url.replace("[A]", f"%%v:{dev.pluginProps['subA']}%%"))
                url = subber(url.replace("[B]", f"%%v:{dev.pluginProps['subB']}%%"))
                url = subber(url.replace("[C]", f"%%v:{dev.pluginProps['subC']}%%"))
                url = subber(url.replace("[D]", f"%%v:{dev.pluginProps['subD']}%%"))
                url = subber(url.replace("[E]", f"%%v:{dev.pluginProps['subE']}%%"))
                self.logger.debug(f"[{dev.name}] URL: {url} (after substitution)")

            # Added by DaveL17 - 2020 10 09
            # Format any needed Raw Curl substitutions
            if dev.pluginProps.get('curlSubs', False):
                self.logger.debug(f"[{dev.name}] Raw Curl: {curl_array} (before substitution)")
                curl_array = subber(curl_array.replace("[A]", f"%%v:{dev.pluginProps['curlSubA']}%%"))
                curl_array = subber(curl_array.replace("[B]", f"%%v:{dev.pluginProps['curlSubB']}%%"))
                curl_array = subber(curl_array.replace("[C]", f"%%v:{dev.pluginProps['curlSubC']}%%"))
                curl_array = subber(curl_array.replace("[D]", f"%%v:{dev.pluginProps['curlSubD']}%%"))
                curl_array = subber(curl_array.replace("[E]", f"%%v:{dev.pluginProps['curlSubE']}%%"))
                self.logger.debug(f"[{dev.name}] Raw Curl: {curl_array} (after substitution)")

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
                    proc = requests.get(url, auth=HTTPDigestAuth(username, password))
                # ===============================  Basic Auth  ================================
                case 'Basic':
                    call_type = 'request'
                    basic = HTTPBasicAuth(username, password)
                    proc = requests.get(url, auth=basic)
            # ===============================  Bearer Auth  ===============================
                case 'Bearer':
                    call_type = 'request'
                    token = dev.pluginProps['token']
                    proc = requests.get(url, headers={'Authorization': f'Bearer {token}'})
                # ===============================  Token Auth  ================================
                # berkinet and DaveL17
                case 'Token':
                    a_url     = dev.pluginProps['tokenUrl']
                    call_type = 'request'
                    data = {"pwd": password, "remember": 1}
                    headers = {'Content-Type': 'application/json'}

                    # Get the token
                    response = requests.post(a_url, json=data, headers=headers)
                    reply = response.json()
                    token = reply["access_token"]

                    url = f"{a_url}?access_token={token}"
                    proc = requests.get(url)
                # =================================  No Auth  =================================
                case _:
                    if url.startswith('file'):
                        # If the locator is a reference to a file, requests won't handle it.
                        call_type = 'file'
                        url = url.replace('file://', '')
                        url = url.replace('%20', ' ')
                        with open(url, 'r') as infile:
                            proc = bytes(infile.read(), 'utf-8')
                    else:
                        call_type = 'request'
                        proc = requests.get(url, timeout=5)

            # =============================================================================
            # The following code adds a timeout function to the call.
            # Added by GlennNZ and DaveL17 2018-07-18
            duration   = int(dev.pluginProps.get('timeout', '5'))
            timer_kill = threading.Timer(duration, self.kill_curl, [proc])
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
                        self.host_plugin.logger.debug(f"[{dev.name}] curl error {curl_err}.")

                        # for Indigo event log
                        err_msg = curl_code.get(f"{return_code}", "Unknown code message.")
                        self.host_plugin.logger.debug(f"[{dev.name}] - Return code: {return_code} - {err_msg}]")
                case "request":
                    if return_code != 200:
                        self.logger.warning(f"{dev.name} - [{return_code}] {http_code[return_code]}")
            return result

        except IOError:
            self.logger.warning(f"[{dev.name}] IOError:  Skipping until next scheduled poll.")
            self.logger.debug(f"[{dev.name}] Device is offline. No data to return. Returning dummy dict.")
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No comm")
            return '{"GhostXML": "IOError"}'

        except Exception:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception(f"General exception: {return_code}")
            return '{"GhostXML": "General Exception"}'

    # =============================================================================
    def _clean_the_keys(self, input_data=None):
        """
        Ensure that state names are valid for Indigo

        Some dictionaries may have keys that contain problematic characters which Indigo doesn't like as state names.
        Let's get those characters out of there.

        :param dict input_data:
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
    def kill_curl(self, proc=None):
        """
        Kill curl calls that have timed out

        The kill_curl method will kill the passed curl call if it has timed out. Added by GlennNZ and DaveL17 2018-07-19

        :param subprocess.Popen proc:
        """
        try:
            self.logger.debug('Timeout for Curl Subprocess. Killed by timer.')
            proc.kill()

        except OSError as sub_error:
            if "OSError: [Errno 3]" in str(sub_error):
                self.logger.debug(
                    "OSError No. 3: No such process. This is a result of the plugin trying to kill a process that is no "
                    "longer running."
                )
            else:
                self.logger.exception('General exception:')

        except Exception:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception('General exception:')

    # =============================================================================
    def parse_the_json(self, dev=None, root=None):
        """
        Parse JSON data

        The parse_the_json() method contains the steps to convert the JSON file into a flat dict.

        https://github.com/gmr/flatdict
        class flatdict.FlatDict(value=None, delimiter=None, former_type=<type 'dict'>)

        :param indigo.Device dev:
        :param JSON root:
        :return self.jsonRawData:
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
            self.logger.debug(f"[{dev.name}] Parse Error:")
            self.logger.debug(f"[{dev.name}] jsonRawData { self.json_raw_data}")

            # If we let it, an exception here will kill the device's thread. Therefore, we have to return something
            # that the device can use in order to keep the thread alive.
            self.logger.warning(
                f"{dev.name} - There was a parse error. Will continue to poll. Check the plugin log for more "
                f"information."
            )
            self.old_device_states['parse_error'] = True
            return self.old_device_states

        except Exception:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception('General exception:')
            return self.old_device_states

    # =============================================================================
    def parse_state_values(self, dev=None):
        """
        Parse data values to device states

        The parse_state_values() method walks through the dict and assigns the corresponding value to each device state.

        :param indigo.Device dev:
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
                f"[{dev.name}] Error parsing state values.\n{self.final_dict}\nReason: {sub_error}"
            )
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
            state_list.append({'key': 'deviceIsOnline', 'value': False, 'uiValue': "Error"})

        except Exception as subError:
            # Add wider exception testing to test errors
            self.logger.exception(f'General exception: {subError}')

        dev.updateStatesOnServer(state_list)

    # =============================================================================
    def refresh_data_for_dev(self, dev=None):
        """
        Initiate refresh of device as required

        If a device is both configured and enabled, initiate a refresh.

        :param indigo.Device dev:
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
                    self.logger.warning(f"{dev.name}: The plugin only supports XML and JSON data sources.")
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
                    elif dev.states.get("Response", "") == "No data to return.":
                        dev.updateStateOnServer('deviceIsOnline', value=False, uiValue='Error')
                        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                        self.bad_calls += 1
                    else:
                        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Updated")
                        self.logger.info(f"{dev.name} updated.")
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
                    f"[{dev.name}] Device not available for update [Enabled: {dev.enabled}, Configured: "
                    f"{dev.configured}]"
                )
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        except KeyError:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception(f"General exception: {dev.name}")

    # =============================================================================
    def strip_namespace(self, dev=None, root=None):
        """
        Strip XML namespace from payload

        The strip_namespace() method strips any XML namespace values, and loads into self.rawData.

        :param indigo.Device dev:
        :param JSON root:
        :return self.rawData:
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
                    self.logger.warning(f"{dev.name} - There was a problem decoding the payload object.")

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
                f"[{dev.name}] Error parsing source data: {sub_error}.  Skipping until  next  scheduled poll."
            )
            self.raw_data = d_root
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No data")
            return self.raw_data

        except Exception:  # noqa
            # Add wider exception testing to test errors
            self.logger.exception('General exception:')
            return self.raw_data
