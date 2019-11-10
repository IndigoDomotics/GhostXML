#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
GhostXML Plugin
Authors: See (repo)

This plugin provides an engine which parses tag/value pairs into
transitive Indigo plugin device states.
"""

# TODO: Additional auth types: Oauth2, WSSE
# TODO: Make a new testing device that requires token auth
# TODO: Find a way to synchronize managed devices with the server (i.e., dev.lastChanged).
# TODO: validate URLs with quotes around them.
# TODO: when a user retrieves an XML payload but has selected JSON, do they get an error to the log?
# TODO: does the plugin work properly with URLs that include parameters?  (https://foo.com/bar/1234?user=***&pwd=***)
# TODO: if a device is enabled right before the runConcurrentThread sleep runs out, the device will update in comm start and immediately again in runConcurrentThread.

# ================================Stock Imports================================
# import datetime
import xml.etree.ElementTree as Etree
import logging
import os
from Queue import Queue
import re
import simplejson
import subprocess
import sys
import threading
import time as t

# =============================Third-party Imports=============================
import flatdict  # https://github.com/gmr/flatdict
try:
    import indigo  # only needed for IDE syntax checking
    import pydevd
except ImportError:
    pass

# ===============================Custom Imports================================
import iterateXML

__author__    = u"berkinet, DaveL17, GlennNZ, howartp"
__build__     = u""
__copyright__ = u"There is no copyright for the GhostXML code base."
__license__   = u"MIT"
__title__     = u"GhostXML Plugin for Indigo Home Control"
__version__   = u"0.4.36"

# Establish default plugin prefs; create them if they don't already exist.
kDefaultPluginPrefs = {
    u'configMenuServerTimeout': "15",  # Server timeout limit.
    u'oldDebugLevel': "20",            # Supports legacy debugging levels.
    u'showDebugInfo': False,           # Verbose debug logging?
    u'showDebugLevel': "20",           # Debugging level.
}


class Plugin(indigo.PluginBase):
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.pluginIsInitializing = True
        self.pluginIsShuttingDown = False
        self.master_trigger_dict  = {'disabled': Queue()}

        # ============================ Configure Logging ==============================
        self.debugLevel = int(self.pluginPrefs['showDebugLevel'])
        try:
            if self.debugLevel < 10:
                self.debugLevel *= 10
        except ValueError:
            self.debugLevel = 30

        self.plugin_file_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d\t%(levelname)-10s\t%(name)s.%(funcName)-28s %(msg)s', datefmt='%Y-%m-%d %H:%M:%S'))

        self.indigo_log_handler.setLevel(20)
        self.logger.info(u"")
        self.logger.info(u"{0:{1}^130}".format(" Initializing New Plugin Session ", "="))
        self.logger.info(u"{0:<30} {1}".format("Plugin name:", pluginDisplayName))
        self.logger.info(u"{0:<30} {1}".format("Plugin version:", pluginVersion))
        self.logger.info(u"{0:<30} {1}".format("Plugin ID:", pluginId))
        self.logger.info(u"{0:<30} {1}".format("Indigo version:", indigo.server.version))
        self.logger.info(u"{0:<30} {1}".format("Python version:", sys.version.replace('\n', '')))
        self.logger.info(u"{0:<30} {1}".format("Process ID:", os.getpid()))
        self.logger.info(u"{0:{1}^130}".format("", "="))
        self.indigo_log_handler.setLevel(self.debugLevel)

        # ================================== Other ====================================
        self.managedDevices = {}  # Managed list of plugin devices

        # Adding support for remote debugging in PyCharm. Other remote debugging
        # facilities can be added, but only one can be run at a time.
        # try:
        #     pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True, suspend=False)
        # except ImportError:
        #     pass

        self.pluginIsInitializing = False

    def __del__(self):

        indigo.PluginBase.__del__(self)

    # =============================================================================
    # =============================== Indigo Methods ===============================
    # =============================================================================
    def closedPrefsConfigUi(self, valuesDict, userCancelled):

        current_debug_level = {10: 'Debug', 20: 'Info', 30: 'Warning', 40: 'Error', 50: 'Critical'}

        if not userCancelled:

            # Ensure that self.pluginPrefs includes any recent changes.
            for k in valuesDict:
                self.pluginPrefs[k] = valuesDict[k]

            self.debugLevel = int(valuesDict.get('showDebugLevel', "30"))
            self.indigo_log_handler.setLevel(self.debugLevel)

            indigo.server.log(u"Debugging on (Level: {0} ({1})".format(current_debug_level[self.debugLevel], self.debugLevel))

            if self.debugLevel == 10:
                self.logger.debug(u"valuesDict: {0} ".format(valuesDict))

            self.logger.debug(u"User prefs saved.")

        else:
            self.logger.debug(u"User prefs dialog cancelled.")

        return True

    # =============================================================================
    def deviceStartComm(self, dev):

        dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Starting")

        # =============== Update legacy authentication settings ===============
        new_props = dev.pluginProps
        auth_type = new_props.get('useDigest', 'None')
        try:
            use_auth = new_props['useAuth']

            # If 'useAuth' was 'false', set 'useDigest' to 'None'. If useAuth was 'true' we
            # leave 'useDigest' alone.
            if not use_auth:
                new_props['useDigest'] = 'None'
        except KeyError:
            pass

        if auth_type in ('False', 'false', False):
            new_props['useDigest'] = 'Basic'

        elif auth_type in ('True', 'true', True):
            new_props['useDigest'] = 'Digest'

        if new_props != dev.pluginProps:
            dev.replacePluginPropsOnServer(new_props)
            self.sleep(2)

        # Check for changes to the device's default states.
        dev.stateListOrDisplayStateIdChanged()

        # Add device instance to dict of managed devices
        self.managedDevices[dev.id] = PluginDevice(self, dev)

        # Force refresh of device when comm started
        if int(dev.pluginProps['refreshFreq']) == 0:
            dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Manual")
        else:
            dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Started")
            # DaveL17 - removed next line because devices could be refreshed twice in the
            # first 2 seconds upon plugin (or device) restart. It doesn't appear to be
            # necessary as a device will check within 2 seconds of deviceStartComm.
            # self.managedDevices[dev.id].queue.put(dev)

        self.logger.debug(u"[{0}] Communication started.".format(dev.name))

    # =============================================================================
    def deviceStopComm(self, dev):

        # Join the related thread. There must be a timeout set because the threads may
        # never terminate on their own.
        self.managedDevices[dev.id].dev_thread.join(0.25)

        # Delete the device from the list of managed devices.
        del self.managedDevices[dev.id]

        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
        self.logger.debug(u"[{0}] Communication stopped.".format(dev.name))

    # =============================================================================
    def getDeviceConfigUiXml(self, typeId, devId):

        current_freq  = indigo.devices[devId].pluginProps.get('refreshFreq', '15')
        list_of_freqs = []
        xml           = self.devicesTypeDict[typeId]["ConfigUIRawXml"]
        root          = Etree.fromstring(xml)

        if typeId == 'GhostXMLdevice':

            # Get current list of refresh frequencies from the XML file.
            for item in root.findall('Field'):
                if item.attrib['id'] == 'refreshFreq':
                    for child in item.getchildren():
                        list_of_freqs = [int(grandchild.attrib['value']) for grandchild in child.getchildren() if child.tag == 'List']

            # If the current refresh frequency is different from the default, it has
            # been set through a custom refresh frequency action. So we add a "Custom"
            # option that will display when the dialog opens.
            if current_freq not in list_of_freqs:
                for item in root.findall('Field'):
                    if item.attrib['id'] == 'refreshFreq':
                        for child in item.getchildren():
                            if child.tag == 'List':
                                option = Etree.fromstring('<Option value="{0}">Custom ({0} seconds)</Option>'.format(current_freq))
                                child.append(option)

            return Etree.tostring(root)

    # =============================================================================
    def getDeviceStateList(self, dev):
        """
        Assign data keys to device state names (Indigo)

        The getDeviceStateList() method pulls out all the keys in self.finalDict and
        assigns them to device states. It returns the modified stateList which is then
        written back to the device in the main thread. This method is automatically
        called by

            stateListOrDisplayStateIdChanged()

        and by Indigo when Triggers and Control Pages are built. Note that it's not
        possible to override Indigo's sorting of devices states which will present them
        as A, B, a, b.

        -----

        :param dev:
        :return state_list:
        """

        # This statement goes out and gets the existing state list for dev from Devices.xml.
        state_list = indigo.PluginBase.getDeviceStateList(self, dev)

        # If there are no managed devices, return the existing states.
        if dev.id not in self.managedDevices.keys():
            for key in dev.states:
                dynamic_state = self.getDeviceStateDictForStringType(unicode(key), unicode(key), unicode(key))
                state_list.append(dynamic_state)

            return state_list

        # If there are managed devices, return the keys that are in finalDict.
        else:
            for key in sorted(self.managedDevices[dev.id].finalDict.keys()):
                dynamic_state = self.getDeviceStateDictForStringType(unicode(key), unicode(key), unicode(key))
                state_list.append(dynamic_state)

        return state_list

# =============================================================================
    def runConcurrentThread(self):

        # This sleep will execute only when the plugin is started/restarted. It gives
        # the Indigo server a chance to catch up if it needs to. Five seconds may be
        # overkill.
        self.sleep(5)

        try:
            while not self.pluginIsShuttingDown:

                # Iterate devices to see if an update is required.
                for devId in self.managedDevices:
                    dev = self.managedDevices[devId].device

                    # TODO: Move this to a method.
                    # If a device has failed multiple times, disable it and notify the user.
                    retries = int(dev.pluginProps.get('maxRetries', 10))
                    if self.managedDevices[devId].bad_calls >= retries:
                        if dev.enabled:

                            # Add the disabled device to the trigger queue and disable the device.
                            self.master_trigger_dict['disabled'].put(dev.id)

                            self.logger.critical(u"Disabling device: [{0}] {1} because it has failed {2} times.".format(dev.id, dev.name, retries))
                            indigo.device.enable(devId, value=False)
                            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)

                    # If time_to_update returns True, add device to its queue.
                    else:
                        if self.time_to_update(dev):
                            self.managedDevices[devId].queue.put(dev)

                self.process_triggers()

                self.sleep(2)

        except self.StopThread:
            self.indigo_log_handler.setLevel(20)
            self.logger.info(u'Stopping main thread.')
            self.indigo_log_handler.setLevel(self.debugLevel)

    # =============================================================================
    def sendDevicePing(self, dev_id=0, suppress_logging=False):

        indigo.server.log(u"GhostXML Plugin devices do not support the ping function.")
        return {'result': 'Failure'}

    # =============================================================================
    def shutdown(self):

        self.pluginIsShuttingDown = True
        self.indigo_log_handler.setLevel(20)
        self.logger.info(u'Shutdown complete.')

    # =============================================================================
    def startup(self):

        # =========================== Audit Indigo Version ============================
        min_ver = 7
        ver     = self.versStrToTuple(indigo.server.version)
        if ver[0] < min_ver:
            self.stopPlugin(u"The Matplotlib plugin requires Indigo version {0} or above.".format(min_ver), isError=True)

        # Initialize all plugin devices to ensure that they're in the proper state.
        # We can't use managedDevices here because they may not yet have showed up.
        for dev in indigo.devices.itervalues("self"):
            if not dev.enabled:
                dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Disabled")
            else:
                dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Initialized")

            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def triggerStartProcessing(self, trigger):

        self.master_trigger_dict[trigger.pluginProps['disabledDevice']] = trigger.id

    # =============================================================================
    def triggerStopProcessing(self, trigger):

        pass

    # =============================================================================
    def validateDeviceConfigUi(self, valuesDict, typeID, devId):

        error_msg_dict = indigo.Dict()
        sub_list       = (('subA', '[A]'), ('subB', '[B]'), ('subC', '[C]'), ('subD', '[D]'), ('subE', '[E]'))
        token_url      = valuesDict['tokenUrl']
        url            = valuesDict['sourceXML']
        url_list       = ('file:///', 'http://', 'https://')
        use_digest     = valuesDict['useDigest']
        var_list       = [var.id for var in indigo.variables]

        try:
            _ = int(valuesDict['maxRetries'])
        except ValueError:
            error_msg_dict['maxRetries'] = u"You must enter an integer."
            error_msg_dict['showAlertText'] = u"Max Retries Error.\n\nThe value must be an integer."
            return False, valuesDict, error_msg_dict

        # Test the source URL/Path for proper prefix.
        if not url.startswith(url_list):
            error_msg_dict['sourceXML'] = u"You must supply a valid URL/Path."
            error_msg_dict['showAlertText'] = u"URL/Path Error.\n\nA valid URL/Path starts with:\n'http://',\n'https://', or\n'file:///'."
            return False, valuesDict, error_msg_dict

        # Test the token URL/Path for proper prefix.
        if use_digest == 'Token' and not token_url.startswith(url_list):
            error_msg_dict['sourceXML'] = u"You must supply a valid Token URL."
            error_msg_dict['showAlertText'] = u"Token Error.\n\nA valid URL/Path starts with:\n'http://',\n'https://', or\n'file:///'."
            return False, valuesDict, error_msg_dict

        # Test the variable substitution IDs and indexes. If substitutions aren't
        # enabled, we can skip this bit.
        if valuesDict['doSubs']:

            for sub in sub_list:

                # Ensure that the values entered in the substitution fields are valid Indigo
                # variable IDs.
                if valuesDict[sub[0]].isspace() or valuesDict[sub[0]] == "":
                    pass
                elif int(valuesDict[sub[0]]) not in var_list:
                    error_msg_dict[sub[0]] = u"You must supply a valid variable ID."
                    error_msg_dict['showAlertText'] = u"Variable {0} Error\n\nYou must supply a valid Indigo variable ID number to perform substitutions (or leave the field " \
                                                      u"blank).".format(sub[0].replace('sub', ''))
                    return False, valuesDict, error_msg_dict

        return True, valuesDict, error_msg_dict

    # =============================================================================
    # =============================== Plugin Methods ==============================
    # =============================================================================
    def adjust_refresh_time(self, valuesDict):
        """
        Programmatically Adjust the refresh time for an individual device

        The adjust_refresh_time method is used to adjust the refresh frequency of an
        individual GhostXML device by calling an Indigo Action. For example, user
        creates an Indigo Trigger that fires--based on some criteria like the value
        of a GhostXML state, which in turn calls an Indigo Action Item to adjust the
        refresh frequency. In other words, the user can increase/decrease the frequency
        based on some condition.

        -----

        :param indigo.Dict() valuesDict:
        :return:
        """
        dev = self.managedDevices[valuesDict.deviceId].device

        new_props = dev.pluginProps
        new_props['refreshFreq'] = int(valuesDict.props['new_refresh_freq'])
        dev.replacePluginPropsOnServer(new_props)

        return True

    # =============================================================================
    def comms_kill_all(self):
        """
        Disable communication of all plugin devices

        comms_kill_all() sets the enabled status of all plugin devices to false.

        -----

        """

        for dev in indigo.devices.itervalues("self"):

            try:
                indigo.device.enable(dev, value=False)
            except Exception as sub_error:
                self.logger.critical(u"Exception when trying to kill all comms. Error: {0} (Line {1})".format(sub_error, sys.exc_traceback.tb_lineno))

        return True

    # =============================================================================
    def comms_unkill_all(self):
        """
        Enable communication of all plugin devices

        comms_unkill_all() sets the enabled status of all plugin devices to true.

        -----

        """

        for dev in indigo.devices.itervalues("self"):

            try:
                indigo.device.enable(dev, value=True)
            except Exception as sub_error:
                self.logger.critical(u"Exception when trying to unkill all comms. Error: {0} (Line {1})".format(sub_error, sys.exc_traceback.tb_lineno))

        return True

    # =============================================================================
    def get_device_list(self, filter="", typeId=0, valuesDict=None, targetId=0):

        return [(dev.id, dev.name) for dev in indigo.devices.itervalues(filter="self")]

    # =============================================================================
    def process_triggers(self):
        """
        Process plugin triggers

        -----

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

    # =============================================================================
    def refreshDataAction(self, valuesDict):
        """
        Legacy callback to Refresh Data for All Devices

        This method supports the old callback name.

        -----

        :return:
        """
        self.logger.warning(u"You are using an outdated plugin Action Item. Please update it.")
        self.refresh_data_action(valuesDict)

    # =============================================================================
    def refreshDataForDevAction(self, valuesDict):
        """
        Legacy callback to Refresh Data for a Specified Device

        This method supports the old callback name.


        -----

        :return:
        """
        self.logger.warning(u"You are using an outdated plugin Action Item. Please update it.")
        self.refresh_data_for_dev_action(valuesDict)

    # =============================================================================
    def refresh_data_action(self, valuesDict):
        """
        Initiate data refresh based on menu call

        The refresh_data_action() method refreshes data for all devices based on a plugin
        menu call.

        -----

        :param valuesDict:
        """
        self.refresh_data()
        return True, valuesDict

    # =============================================================================
    def refresh_data(self):
        """
        The refresh_data() method controls the updating of all plugin devices

        Initiate a data refresh based on a normal plugin cycle.

        -----

        """

        # If there are no devices created or all devices are disabled.
        if len(self.managedDevices) == 0:
            self.logger.warning(u"No GhostXML devices have been created.")
            return True

        # Iterate devices to see if an update is required.
        try:
            for devId in self.managedDevices:
                dev = self.managedDevices[devId].device
                self.managedDevices[devId].queue.put(dev)

            return True

        except Exception as sub_error:
            self.logger.critical(u"Error refreshing devices. Please check settings.")
            self.logger.critical(unicode(sub_error))
            return False

    # =============================================================================
    def refresh_data_for_dev_action(self, valuesDict):
        """
        Initiate a device refresh based on an Indigo Action call

        The refresh_data_for_dev_action() method refreshes data for a selected device
        based on a plugin action call.

        -----

        :param valuesDict:
        """

        dev = self.managedDevices[valuesDict.deviceId].device
        self.managedDevices[dev.id].queue.put(dev)

        return True

    # TODO: It appears this method is no longer used.
    # =============================================================================
    def stop_sleep(self, start_sleep):
        """
        Update device sleep value as warranted

        The stop_sleep() method accounts for changes to the user upload interval
        preference. The plugin checks every 2 seconds to see if the sleep interval
        should be updated.

        -----

        :param start_sleep:
        """

        total_sleep = float(self.pluginPrefs.get('configMenuUploadInterval', 300))

        if t.time() - start_sleep > total_sleep:
            return True

        return False

    # =============================================================================
    def time_to_update(self, dev):
        """
        Determine if a device is ready for a refresh

        Returns True if the device is ready to be updated, else returns False.

        -----

        :param dev:
        """
        # If device has a deviceTimestamp key and is enabled.
        if "deviceTimestamp" in dev.states.iterkeys() and dev.enabled:

            # If the refresh frequency is zero, the device is a manual only refresh.
            if int(dev.pluginProps.get("refreshFreq", 300)) == 0:
                return False

            # If the refresh frequency is not zero, test to see if the device is ready for a refresh.
            else:
                t_since_upd = int(t.time() - float(dev.states["deviceTimestamp"]))

                # If it's time for the device to be updated.
                if int(t_since_upd) > int(dev.pluginProps.get("refreshFreq", 300)):
                    return True

                # If it's not time for the device to be updated.
                return False

        # If the device does not have a timestamp key and/or is disabled.
        else:
            return False


class PluginDevice(object):
    """
    Create device object and corresponding queue

    The PluginDevice class is used to create an object to store data related to each
    enabled plugin device. The object contains an instance of the Indigo device and a
    command queue.
    """

    # =============================================================================
    def __init__(self, plugin, device):

        self.pluginDeviceIsInitializing = True

        self.device      = device
        self.host_plugin = plugin

        self.bad_calls         = 0
        self.finalDict         = {}
        self.jsonRawData       = ''
        self.rawData           = ''
        self.old_device_states = {}

        self.queue      = Queue(maxsize=0)
        self.dev_thread = threading.Thread(name=self.device.id, target=self.initiate_device_update, args=(self.queue,))
        self.dev_thread.start()

        self.pluginDeviceIsInitializing = False

    # =============================================================================
    def __str__(self):

        return u"[{0:>11}] {1:<46} {2:<40}".format(self.device.id, self.dev_thread, self.queue)

    # =============================================================================
    def initiate_device_update(self, q):
        """
        Initiate an update of the device

        The initiate_device_update method keeps the device thread alive and is used as
        a bridge between the Plugin class and the device class.

        -----

        :param queue q:
        :return:
        """
        while True:
            t.sleep(1)
            while not q.empty():
                task = q.get()
                self.refresh_data_for_dev(task)

    # =============================================================================
    def get_the_data(self, dev):
        """
        The get_the_data() method is used to retrieve target data files.

        The get_the_data() method is used to construct the relevant API URL, sends
        the call to the data source via curl, and returns the result. The URL can
        be sent using auth as required (basic, digest) or without auth. In addition,
        Indigo substitutions are processed as required such that the user can modify
        the URL based on variable values.

        -----

        :param dev
        :return result:
        """

        try:
            curl_array  = dev.pluginProps.get('curlArray', '')
            url        = dev.pluginProps['sourceXML']
            username   = dev.pluginProps.get('digestUser', '')
            password   = dev.pluginProps.get('digestPass', '')
            auth_type  = dev.pluginProps.get('useDigest', 'None')

            # Format any needed substitutions
            if dev.pluginProps.get('doSubs', False):
                self.host_plugin.logger.debug(u"[{0}] URL: {1}  (before substitution)".format(dev.name, url))
                url = self.host_plugin.substitute(url.replace("[A]", "%%v:" + dev.pluginProps['subA'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[B]", "%%v:" + dev.pluginProps['subB'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[C]", "%%v:" + dev.pluginProps['subC'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[D]", "%%v:" + dev.pluginProps['subD'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[E]", "%%v:" + dev.pluginProps['subE'] + "%%"))
                self.host_plugin.logger.debug(u"[{0}] URL: {1}  (after substitution)".format(dev.name, url))

            # Initiate curl call to data source.

            # =============================================================================
            # Added by GlennNZ - 2018 12 06
            # if using raw Curl - don't worry about auth_Type or much else
            if auth_type == "Raw":
                self.host_plugin.logger.debug(u'/usr/bin/curl -vsk {0} {1}'.format(curl_array, url))
                proc = subprocess.Popen('/usr/bin/curl -vsk ' + curl_array + ' ' + url, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            # =============================================================================

            # Digest auth
            elif auth_type == 'Digest':
                proc = subprocess.Popen(["curl", '-vs', '--digest', '-u', username + ':' + password, url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Basic auth
            elif auth_type == 'Basic':
                proc = subprocess.Popen(["curl", '-vs', '-u', username + ':' + password, url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Token auth
            # Added by berkinet and DaveL17 2018-06-18
            elif auth_type == 'Token':
                # We need to get a token to get started
                a_url    = dev.pluginProps['tokenUrl']
                curl_arg = "/usr/bin/curl -vsk -H 'Content-Type: application/json' -X POST --data-binary '{ \"pwd\": \"" + password + "\", \"remember\": 1 }' '} ' " + a_url

                proc = subprocess.Popen(curl_arg, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

                reply_in = proc.communicate()
                reply    = simplejson.loads(reply_in[0])
                token    = (reply["access_token"])

                # Now, add the token to the end of the url
                url  = "{0}?access_token={1}".format(url, token)
                proc = subprocess.Popen(["curl", '-vsk', url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # No auth
            else:
                proc = subprocess.Popen(["curl", '-vs', url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # =============================================================================
            # The following code adds a timeout function to the call.
            # Added by GlennNZ and DaveL17 2018-07-18
            # cmd = ""
            duration   = int(dev.pluginProps.get('timeout', '5'))
            timer_kill = threading.Timer(duration, self.kill_curl, [proc])
            try:
                timer_kill.start()
                result, err = proc.communicate()

                self.host_plugin.logger.debug(u'HTTPS CURL result: {0}'.format(err))
                self.host_plugin.logger.debug(u'ReturnCode: {0}'.format(proc.returncode))

            finally:
                timer_kill.cancel()
            # =============================================================================

            # TODO: Get more specific on what the proc.returncode is.  For example, this error:
            #  2019-05-28 22:59:02.650	GhostXML Warning	[607047935] curl error *   Trying 162.58.33.179... * TCP_NODELAY set .
            #  doesn't give the user much information on why the call was unsuccessful.
            if int(proc.returncode) != 0:
                self.host_plugin.logger.warning(u"[{0}] curl error {1}. [Return code: {2}".format(dev.name, err.replace('\n', ' '), proc.returncode))

            return result

        except IOError:

            self.host_plugin.logger.warning(u"[{0}] IOError:  Skipping until next scheduled poll.".format(dev.name))
            self.host_plugin.logger.debug(u"[{0}] Device is offline. No data to return. Returning dummy dict.".format(dev.name))
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No comm")
            return '{"GhostXML": "IOError"}'

        except:

            # Add wider exception testing to test errors
            self.host_plugin.logger.exception(u'curl array related error')

    # =============================================================================
    def clean_the_keys(self, input_data):
        """
        Ensure that state names are valid for Indigo

        Some dictionaries may have keys that contain problematic characters which
        Indigo doesn't like as state names. Let's get those characters out of there.

        -----

        :param input_data:
        """

        try:
            # Some characters need to be replaced with a valid replacement value because
            # simply deleting them could cause problems. Add additional k/v pairs to
            # chars_to_replace as needed.

            chars_to_replace = {'_ghostxml_': '_', '+': '_plus_', '-': '_minus_', 'true': 'True', 'false': 'False', ' ': '_'}
            chars_to_replace = dict((re.escape(k), v) for k, v in chars_to_replace.iteritems())
            pattern          = re.compile("|".join(chars_to_replace.keys()))

            for key in input_data.iterkeys():
                new_key = pattern.sub(lambda m: chars_to_replace[re.escape(m.group(0))], key)
                input_data[new_key] = input_data.pop(key)

            # Some characters can simply be eliminated. If something here causes problems,
            # remove the element from the set and add it to the replacement dict above.
            chars_to_remove = {'/', '(', ')'}

            for key in input_data.iterkeys():
                new_key = ''.join([c for c in key if c not in chars_to_remove])
                input_data[new_key] = input_data.pop(key)

            # Indigo will not accept device state names that begin with a number, so
            # inspect them and prepend any with the string "No_" to force them to
            # something that Indigo will accept.
            temp_dict = {}

            for key in input_data.keys():
                if key[0].isdigit():
                    temp_dict[u'No_{0}'.format(key)] = input_data[key]
                else:
                    temp_dict[key] = input_data[key]

            input_data = temp_dict

            self.jsonRawData = input_data

        except ValueError as sub_error:
            self.host_plugin.logger.critical(u'Error cleaning dictionary keys: {0}'.format(sub_error))

    # =============================================================================
    def kill_curl(self, proc):
        """
        Kill curl calls that have timed out

        The kill_curl method will kill the passed curl call if it has timed out.
        Added by GlennNZ and DaveL17 2018-07-19

        -----

        :param proc:
        """

        self.host_plugin.logger.debug(u'Timeout for Curl Subprocess. Killed by timer.')

        proc.kill()

    # =============================================================================
    def parse_the_json(self, dev, root):
        """
        Parse JSON data

        The parse_the_json() method contains the steps to convert the JSON file into a
        flat dict.

        http://github.com/gmr/flatdict
        class flatdict.FlatDict(value=None, delimiter=None, former_type=<type 'dict'>)

        -----

        :param dev:
        :param root:
        :return self.jsonRawData:
        """

        self.old_device_states = dict(dev.states)

        try:
            parsed_simplejson = simplejson.loads(root)

            # If List flattens once - with addition of No_ to the beginning (Indigo appears
            # to not allow DeviceNames to start with Numbers) then flatDict runs - and
            # appears to run correctly (as no longer list - dict) if isinstance(list) then
            # will flatten list down to dict.

            if isinstance(parsed_simplejson, list):

                parsed_simplejson = dict((u"No_" + unicode(i), v) for (i, v) in enumerate(parsed_simplejson))

            self.jsonRawData = flatdict.FlatDict(parsed_simplejson, delimiter='_ghostxml_')

            dev.updateStateOnServer('parse_error', value=False)

            return self.jsonRawData

        except ValueError as sub_error:
            self.host_plugin.logger.debug(u"[{0}] Parse Error: {1}".format(dev.name, sub_error))
            self.host_plugin.logger.debug(u"[{0}] jsonRawData {1}".format(dev.name, self.jsonRawData))

            # If we let it, an exception here will kill the device's thread. Therefore, we
            # have to return something that the device can use in order to keep the thread
            # alive.
            self.host_plugin.logger.warning("There was a parse error. Will continue to poll.")
            self.old_device_states['parse_error'] = True
            return self.old_device_states

    # =============================================================================
    def parse_state_values(self, dev):
        """
        Parse data values to device states

        The parse_state_values() method walks through the dict and assigns the
        corresponding value to each device state.

        -----

        :param dev:
        """

        state_list  = []
        sorted_list = sorted(self.finalDict.iterkeys())

        for key in sorted_list:
            try:

                state_list.append({'key': unicode(key), 'value': unicode(self.finalDict[key]), 'uiValue': unicode(self.finalDict[key])})

            except ValueError as sub_error:
                self.host_plugin.logger.critical(u"[{0}] Error parsing key/value pair: {1} = {2}. Reason: {3}".format(dev.name, key, self.finalDict[key], sub_error))
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                state_list.append({'key': 'deviceIsOnline', 'value': False, 'uiValue': "Error"})

        dev.updateStatesOnServer(state_list)

    # =============================================================================
    def refresh_data_for_dev(self, dev):
        """
        Initiate refresh of device as required

        If a device is both configured and enabled, initiate a refresh.

        -----

        :param dev:
        """

        if dev.configured and dev.enabled:

            # Get the data.
            self.rawData = self.get_the_data(dev)

            dev.updateStateOnServer('deviceIsOnline', value=dev.states['deviceIsOnline'], uiValue="Processing")

            update_time = t.strftime("%m/%d/%Y at %H:%M")
            dev.updateStateOnServer('deviceLastUpdated', value=update_time)
            dev.updateStateOnServer('deviceTimestamp', value=t.time())

            # Throw the data to the appropriate module to flatten it.
            if dev.pluginProps['feedType'] == "XML":
                self.rawData = self.strip_namespace(dev, self.rawData)
                self.finalDict = iterateXML.iterateMain(self.rawData)

            elif dev.pluginProps['feedType'] == "JSON":
                self.finalDict = self.parse_the_json(dev, self.rawData)
                self.clean_the_keys(self.finalDict)

            else:
                self.host_plugin.logger.warning(u"{0}: The plugin only supports XML and JSON data sources.".format(dev.name))

            if self.finalDict is not None:
                # Create the device states.
                dev.stateListOrDisplayStateIdChanged()

                # Put the final values into the device states.
                self.parse_state_values(dev)

                if "GhostXML" in dev.states:
                    dev.updateStateOnServer('deviceIsOnline', value=False, uiValue=dev.states['GhostXML'])
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                    self.bad_calls += 1
                elif dev.states.get("parse_error", False):
                    dev.updateStateOnServer('deviceIsOnline', value=False, uiValue='Error')
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                    self.bad_calls += 1
                else:
                    dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Updated")
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                    dev.setErrorStateOnServer(None)
                    self.bad_calls = 0

            else:
                # Set the Timestamp so that the seconds-since-update code doesn't keep checking
                # a dead link / invalid URL every 5 seconds - it will keep checking on it's
                # normal schedule. BUT don't set the "lastUpdated" value so humans can see when
                # it last successfully updated.
                dev.updateStateOnServer('deviceTimestamp', value=t.time())
                dev.setErrorStateOnServer("Error")
                self.bad_calls += 1

        else:
            self.host_plugin.logger.debug(u"[{0}] Device not available for update [Enabled: {1}, Configured: {2}]".format(dev.name, dev.enabled, dev.configured))
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def strip_namespace(self, dev, root):
        """
        Strip XML namespace from payload

        The strip_namespace() method strips any XML namespace values, and loads into
        self.rawData.

        -----

        :param dev:
        :param root:
        :return self.rawData:
        """

        try:
            if root == "":
                root = '<?xml version="1.0" encoding="UTF-8"?><Emptydict><Response>No data to return.</Response></Emptydict>'

            # Remove namespace stuff if it's in there. There's probably a more
            # comprehensive re.sub() that could be run, but it also could do *too* much.
            self.rawData = ''
            self.rawData = re.sub(' xmlns="[^"]+"', '', root)
            self.rawData = re.sub(' xmlns:xsi="[^"]+"', '', self.rawData)
            self.rawData = re.sub(' xmlns:xsd="[^"]+"', '', self.rawData)
            self.rawData = re.sub(' xsi:noNamespaceSchemaLocation="[^"]+"', '', self.rawData)

            return self.rawData

        except ValueError as sub_error:
            self.host_plugin.logger.warning(u"[{0}] Error parsing source data: {1}. Skipping until next scheduled poll.".format(dev.name, unicode(sub_error)))
            self.rawData = '<?xml version="1.0" encoding="UTF-8"?><Emptydict><Response>No data to return.</Response></Emptydict>'
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No data")
            return self.rawData
    # =============================================================================
