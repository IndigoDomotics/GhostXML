#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
GhostXML Plugin
Authors: See (repo)

This plugin provides an engine which parses tag/value pairs into
transitive Indigo plugin device states.
"""

# TODO: Make a new testing device that requires token auth

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
import indigoPluginUpdateChecker
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
__version__   = u"0.4.14"

# Establish default plugin prefs; create them if they don't already exist.
kDefaultPluginPrefs = {
    u'configMenuServerTimeout': "15",  # Server timeout limit.
    u'showDebugInfo': False,           # Verbose debug logging?
    u'showDebugLevel': "20",           # Debugging level.
    u'updaterEmail': "",               # Email to notify of plugin updates.
    u'updaterEmailsEnabled': False     # Notification of plugin updates wanted.
}


class Plugin(indigo.PluginBase):
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.pluginIsInitializing = True
        self.pluginIsShuttingDown = False

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
        self.logger.info(u"{0:=^130}".format(" Initializing New Plugin Session "))
        self.logger.info(u"{0:<30} {1}".format("Plugin name:", pluginDisplayName))
        self.logger.info(u"{0:<30} {1}".format("Plugin version:", pluginVersion))
        self.logger.info(u"{0:<30} {1}".format("Plugin ID:", pluginId))
        self.logger.info(u"{0:<30} {1}".format("Indigo version:", indigo.server.version))
        self.logger.info(u"{0:<30} {1}".format("Python version:", sys.version.replace('\n', '')))
        self.logger.info(u"{0:<30} {1}".format("Process ID:", os.getpid()))
        self.logger.info(u"{0:=^130}".format(""))
        self.indigo_log_handler.setLevel(self.debugLevel)

        # ========================== Plugin Update Checker ============================
        self.updater              = indigoPluginUpdateChecker.updateChecker(self, "https://raw.githubusercontent.com/indigodomotics/GhostXML/master/ghostXML_version.html")
        self.updaterEmailsEnabled = self.pluginPrefs.get('updaterEmailsEnabled', False)

        # ================================== Other ====================================
        self.managedDevices = {}  # Managed list of plugin devices

        # Adding support for remote debugging in PyCharm. Other remote debugging
        # facilities can be added, but only one can be run at a time.
        # try:
        #     pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True, suspend=False)
        # except:
        #     pass

        self.pluginIsInitializing = False

    def __del__(self):

        indigo.PluginBase.__del__(self)

    # =============================== Indigo Methods ===============================

    def closedPrefsConfigUi(self, valuesDict, userCancelled):

        current_debug_level = {10: 'Debug', 20: 'Info', 30: 'Warning', 40: 'Error', 50: 'Critical'}

        if userCancelled:
            self.logger.debug(u"User prefs dialog cancelled.")

        if not userCancelled:
            self.debugLevel = int(valuesDict.get('showDebugLevel', "30"))
            self.indigo_log_handler.setLevel(self.debugLevel)
            self.logger.debug(u"User prefs saved.")

            indigo.server.log(u"Debugging on (Level: {0} ({1})".format(current_debug_level[self.debugLevel], self.debugLevel))

            if int(self.pluginPrefs['showDebugLevel']) == 10:
                self.logger.debug(u"valuesDict: {0} ".format(valuesDict))

        return True

    def deviceStartComm(self, dev):

        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Starting")

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

        if auth_type in ['False', 'false', False]:
            new_props['useDigest'] = 'Basic'

        elif auth_type in ['True', 'true', True]:
            new_props['useDigest'] = 'Digest'

        if new_props != dev.pluginProps:
            dev.replacePluginPropsOnServer(new_props)
            self.sleep(2)
        # =====================================================================

        # Check for changes to the device's default states.
        dev.stateListOrDisplayStateIdChanged()

        # Add device instance to dict of managed devices
        self.managedDevices[dev.id] = PluginDevice(self, dev)

        # Force refresh of device when comm started
        if int(dev.pluginProps['refreshFreq']) == 0:
            dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Manual")
        else:
            dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Started")
            self.managedDevices[dev.id].queue.put(dev)

        self.logger.debug(u"Started: {0}".format(self.managedDevices[dev.id]))

    def deviceStopComm(self, dev):

        # Join the related thread. There must be a timeout set because the threads may
        # never terminate on their own.
        self.managedDevices[dev.id].dev_thread.join(0.25)

        # Delete the device from the list of managed devices.
        del self.managedDevices[dev.id]

        dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="Disabled")
        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
        self.logger.debug(u"Stopped: [{0:>11}]".format(dev.id))

    def getDeviceConfigUiXml(self, typeId, devId):

        current_freq  = indigo.devices[devId].pluginProps.get('refreshFreq', '15')
        list_of_freqs = []
        XML           = self.devicesTypeDict[typeId]["ConfigUIRawXml"]
        root          = Etree.fromstring(XML)

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

        if dev.enabled:

            # If there are no managed devices, returns the existing states
            if dev.id not in self.managedDevices.keys():
                return indigo.PluginBase.getDeviceStateList(self, dev)

            # This statement goes out and gets the existing state list for dev.
            state_list = indigo.PluginBase.getDeviceStateList(self, dev)

            if state_list is not None:

                # Iterate the tags in final_dict into device state keys.
                # Example: dynamic_state = self.getDeviceStateDictForStringType(key, u'Trigger Test Label', u'State Label')
                # ================================================================================================
                # Added a sort so the keys show up in alpha order on lists elsewhere.  DaveL17 2018-07-23
                # ================================================================================================
                for key in sorted(self.managedDevices[dev.id].finalDict.keys()):
                    dynamic_state = self.getDeviceStateDictForStringType(unicode(key), unicode(key), unicode(key))
                    state_list.append(dynamic_state)

            return state_list

        # =============================================================================
        # I think all the blocked code below can go away.  DaveL17 2018-07-23
        #
        # Rationale: With the following code included, we wind up with the three 'hard-
        # coded" device states: (deviceIsOnline, deviceLastUpdated, deviceTimestamp)
        # appearing twice in trigger and control page lists. With the code excluded,
        # all my test devices still work as expected, but there's not longer a doubling
        # up on these states. I sent the plugin a JSON file with an error, and it
        # didn't seem to have any troubles.
        #
        # Also, the 'else' is only reached if the device is disabled. Do we need to do
        # anything if the device is disabled? Perhaps not.

        #     # Inspect existing state list to new one to see if the state list needs to be
        #     # updated. If it doesn't, we can save some effort here.
        #     interim_state_list = [thing['Key'] for thing in state_list]
        #     for thing in [u'deviceIsOnline', u'deviceLastUpdated', ]:
        #         interim_state_list.remove(thing)
        #
        #     # Resolves issue with deviceIsOnline and deviceLastUpdated states disappearing
        #     # if there's a fault in the JSON data we receive, as state_list MUST contain
        #     # all desired states when it returns
        #
        #     try:
        #         state_list.append(self.getDeviceStateDictForStringType('deviceIsOnline', 'Device Online?', 'Device Online?'))
        #         state_list.append(self.getDeviceStateDictForStringType('deviceLastUpdated', 'Device Last Updated', 'Device Last Updated'))
        #         state_list.append(self.getDeviceStateDictForStringType('deviceTimestamp', 'Device Timestamp', 'Device Timestamp'))
        #
        #     except KeyError:
        #         # Ignore this error as we expect it to happen when all is healthy
        #         pass
        #
        #     return state_list
        #
        # else:
        #     state_list = indigo.PluginBase.getDeviceStateList(self, dev)
        #
        #     # Iterate the device states into trigger and control page labels when the
        #     # device is called.
        #     for state in dev.states:
        #         dynamic_state = self.getDeviceStateDictForStringType(state, state, state)
        #         state_list.append(dynamic_state)
        #
        #     try:
        #         state_list.append(self.getDeviceStateDictForStringType('deviceIsOnline', 'Device Online?', 'Device Online?'))
        #         state_list.append(self.getDeviceStateDictForStringType('deviceLastUpdated', 'Device Last Updated', 'Device Last Updated'))
        #         state_list.append(self.getDeviceStateDictForStringType('deviceTimestamp', 'Device Timestamp', 'Device Timestamp'))
        #
        #     except KeyError:
        #         # Ignore this error as we expect it to happen when all is healthy
        #         pass
        #
        #     return state_list
# =============================================================================

    def runConcurrentThread(self):

        # This sleep will execute only when the plugin is started/restarted. It gives
        # the Indigo server a chance to catch up if it needs to. Five seconds may be
        # overkill.
        self.sleep(5)

        try:
            while not self.pluginIsShuttingDown:

                # Check to see if there is an update to the plugin available.
                try:
                    self.updater.checkVersionPoll()
                except Exception as sub_error:
                    self.logger.warning(u"Update checker error: {0}".format(sub_error))

                # Iterate devices to see if an update is required.
                for devId in self.managedDevices:
                    dev = self.managedDevices[devId].device

                    # If a device has failed 10 times, disable it and notify the user.
                    if self.managedDevices[devId].bad_calls >= 10:
                        indigo.device.enable(devId, value=False)
                        self.logger.critical(u"[{0}] Disabling {1} because it has failed 10 times.".format(dev.id, dev.name))

                    # If time_to_update returns True, add device to its queue.
                    else:
                        if self.time_to_update(dev):
                            self.managedDevices[devId].queue.put(dev)

                self.sleep(2)

        except self.StopThread:
            self.indigo_log_handler.setLevel(20)
            self.logger.info(u'Stopping main thread.')
            self.indigo_log_handler.setLevel(self.debugLevel)

    def shutdown(self):

        self.pluginIsShuttingDown = True
        self.indigo_log_handler.setLevel(20)
        self.logger.info(u'Shutdown complete.')

    def startup(self):

        # Initialize all plugin devices to ensure that they're in the proper state.
        # We can't use managedDevices here because they may not yet have showed up.
        for dev in indigo.devices.itervalues("self"):
            if not dev.enabled:
                dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="Disabled")

            else:
                dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Initialized")
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        # See if there is a plugin update and whether the user wants to be notified.
        try:
            self.updater.checkVersionPoll()
        except Exception as sub_error:
            self.logger.warning(u"Update checker error: {0}".format(sub_error))

    def validateDeviceConfigUi(self, valuesDict, typeID, devId):

        error_msg_dict = indigo.Dict()
        sub_list       = [('subA', '[A]'), ('subB', '[B]'), ('subC', '[C]'), ('subD', '[D]'), ('subE', '[E]')]
        token_url      = valuesDict['tokenUrl']
        url            = valuesDict['sourceXML']
        url_list       = ('file:///', 'http://', 'https://')
        use_digest     = valuesDict['useDigest']
        var_list       = [var.id for var in indigo.variables]

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
                    error_msg_dict['showAlertText'] = u"Variable {0} Error\n\nYou must supply a valid Indigo variable ID number to perform substitutions (or leave the field blank).".format(sub[0].replace('sub', ''))
                    return False, valuesDict, error_msg_dict

        return True, valuesDict, error_msg_dict

    def validatePrefsConfigUi(self, valuesDict):

        error_msg_dict = indigo.Dict()
        update_email   = valuesDict['updaterEmail']
        update_wanted  = valuesDict['updaterEmailsEnabled']

        # Test plugin update notification settings.
        try:
            if update_wanted and not update_email:
                error_msg_dict['updaterEmail'] = u"If you want to be notified of updates, you must supply an email address."
                error_msg_dict['showAlertText'] = u"Updater Email Error:\n\nThe plugin requires a valid email address in order to notify of plugin updates."
                return False, valuesDict, error_msg_dict

            elif update_wanted and "@" not in update_email:
                error_msg_dict['updaterEmail'] = u"Valid email addresses have at least one @ symbol in them (initiate_device_update@bar.com)."
                error_msg_dict['showAlertText'] = u"Updater Email Error:\n\nThe plugin requires a valid email address in order to notify of plugin updates (email address must " \
                                                  u"contain an '@' sign."

                return False, valuesDict, error_msg_dict

        except Exception as sub_error:
            self.logger.warning(u"Plugin configuration error: {0}".format(sub_error))

        return True, valuesDict

    # =============================== Plugin Methods ===============================

    def check_version_now(self):
        """
        Check to ensure that the plugin is the most current version

        The check_version_now() method is called if user selects "Check For Plugin
        Updates..." Indigo menu item. It is only called by user request.

        -----

        """

        try:
            self.updater.checkVersionNow()
        except Exception as sub_error:
            self.logger.warning(u"Update checker error: {0}".format(sub_error))

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

    def refreshDataAction(self, valuesDict):
        """
        Legacy callback to Refresh Data for All Devices

        This method supports the old callback name.

        -----

        :return:
        """
        self.logger.warning(u"You are using an outdated plugin Action Item. Please update it.")
        self.refresh_data_action(valuesDict)

    def refreshDataForDevAction(self, valuesDict):
        """
        Legacy callback to Refresh Data for a Specified Device

        This method supports the old callback name.


        -----

        :return:
        """
        self.logger.warning(u"You are using an outdated plugin Action Item. Please update it.")
        self.refresh_data_for_dev_action(valuesDict)

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


class PluginDevice(object):
    """
    Create device object and corresponding queue

    The PluginDevice class is used to create an object to store data related to each
    enabled plugin device. The object contains an instance of the Indigo device and a
    command queue.

    -----

    """
    def __init__(self, plugin, device):

        self.pluginDeviceIsInitializing = True

        self.device      = device
        self.host_plugin = plugin

        self.bad_calls   = 0
        self.finalDict   = {}
        self.jsonRawData = ''
        self.rawData     = ''

        self.queue      = Queue(maxsize=0)
        self.dev_thread = threading.Thread(name=self.device.id, target=self.initiate_device_update, args=(self.queue,))
        self.dev_thread.start()

        self.pluginDeviceIsInitializing = False

    def __str__(self):

        return u"[{0:>11}] {1:<46} {2:<40}".format(self.device.id, self.dev_thread, self.queue)

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
            t.sleep(0.1)
            while not q.empty():
                task = q.get()
                self.refresh_data_for_dev(task)

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

        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Download")

        try:
            url       = dev.pluginProps['sourceXML']
            username  = dev.pluginProps.get('digestUser', '')

            # Add capacity to run very raw curl command
            useRawCurl    = dev.pluginProps.get('useRawCurl',False)
            curlArray   = dev.pluginProps.get('curlArray','')
            # Curl data to pass - space seperated

            password  = dev.pluginProps.get('digestPass', '')
            auth_type = dev.pluginProps.get('useDigest', 'None')

            # Format any needed substitutions
            if dev.pluginProps.get('doSubs', False):
                self.host_plugin.logger.debug(u"[{0}] URL: {1}  (before substitution)".format(dev.id, url))
                url = self.host_plugin.substitute(url.replace("[A]", "%%v:" + dev.pluginProps['subA'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[B]", "%%v:" + dev.pluginProps['subB'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[C]", "%%v:" + dev.pluginProps['subC'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[D]", "%%v:" + dev.pluginProps['subD'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[E]", "%%v:" + dev.pluginProps['subE'] + "%%"))
                self.host_plugin.logger.debug(u"[{0}] URL: {1}  (after substitution)".format(dev.id, url))

            # Initiate curl call to data source.

            # if using raw Curl - don't worry about auth_Type or much else
            if useRawCurl:
                self.host_plugin.logger.debug(u'/usr/bin/curl -vsk '+curlArray+' ' +url)

                proc = subprocess.Popen('/usr/bin/curl -vsk '+curlArray+ ' '+url,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
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
                a_url = dev.pluginProps['tokenUrl']
                curl_arg = "/usr/bin/curl -vsk -H 'Content-Type: application/json' -X POST --data-binary '{ \"pwd\": \"" + password + "\", \"remember\": 1 }' '} ' " + a_url

                proc = subprocess.Popen(curl_arg, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

                reply_in = proc.communicate()
                reply = simplejson.loads(reply_in[0])
                token = (reply["access_token"])

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

            if int(proc.returncode) != 0:
                self.host_plugin.logger.warning(u"[{0}] curl error {1}.".format(dev.id, err.replace('\n', ' ')))

            return result

        except IOError:

            self.host_plugin.logger.warning(u"[{0}] IOError:  Skipping until next scheduled poll.".format(dev.id))
            self.host_plugin.logger.debug(u"[{0}] Device is offline. No data to return. Returning dummy dict.".format(dev.id))
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No comm")
            return '{"GhostXML": "IOError"}'

        except:
            # Add wider exception testing to test errors
            self.host_plugin.logger.exception(u'curl array related error')


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

        try:
            parsed_simplejson = simplejson.loads(root)

            # If List flattens once - with addition of No_ to the beginning (Indigo appears
            # to not allow DeviceNames to start with Numbers) then flatDict runs - and
            # appears to run correctly (as no longer list - dict) if isinstance(list) then
            # will flatten list down to dict.

            if isinstance(parsed_simplejson, list):

                parsed_simplejson = dict((u"No_" + unicode(i), v) for (i, v) in enumerate(parsed_simplejson))

            self.jsonRawData = flatdict.FlatDict(parsed_simplejson, delimiter='_ghostxml_')

            return self.jsonRawData

        except ValueError as sub_error:
            self.host_plugin.logger.debug(u"[{0}] Parse Error: {1}".format(dev.id, sub_error))
            self.host_plugin.logger.debug(u"[{0}] jsonRawData {0}".format(dev.id, self.jsonRawData))

            # If we let it, an exception here will kill the device's thread. Therefore, we
            # have to return something that the device can use in order to keep the thread
            # alive.
            self.jsonRawData = {'parse_error': "There was a parse error. Will continue to poll."}
            return self.jsonRawData

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

                state_list.append({'key': unicode(key), 'value': unicode(self.finalDict[key])})

            except ValueError as sub_error:
                self.host_plugin.logger.critical(u"[{0}] Error parsing key/value pair: {1} = {2}. Reason: {3}".format(dev.id, key, self.finalDict[key], sub_error))
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                state_list.append({'key': 'deviceIsOnline', 'value': True, 'uiValue': "Error"})

        dev.updateStatesOnServer(state_list)

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

            # Throw the data to the appropriate module to flatten it.
            dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Processing")

            update_time = t.strftime("%m/%d/%Y at %H:%M")
            dev.updateStateOnServer('deviceLastUpdated', value=update_time)
            dev.updateStateOnServer('deviceTimestamp', value=t.time())

            if dev.pluginProps['feedType'] == "XML":
                self.rawData = self.strip_namespace(dev, self.rawData)
                self.finalDict = iterateXML.iterateMain(self.rawData)

            elif dev.pluginProps['feedType'] == "JSON":
                self.finalDict = self.parse_the_json(dev, self.rawData)
                self.clean_the_keys(self.finalDict)

            else:
                self.host_plugin.logger.warning(u"{0}: The plugin only supports XML and JSON data sources.".format(dev.id))

            if self.finalDict is not None:
                # Create the device states.
                dev.stateListOrDisplayStateIdChanged()

                # Put the final values into the device states.
                self.parse_state_values(dev)

                if "GhostXML" in dev.states:
                    dev.updateStateOnServer('deviceIsOnline', value=False, uiValue=dev.states['GhostXML'])
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                    self.bad_calls += 1
                elif "parse_error" in dev.states:
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
            self.host_plugin.logger.debug(u"[{0}] Device not available for update [Enabled: {1}, Configured: {2}]".format(dev.id, dev.enabled, dev.configured))
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

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
            self.host_plugin.logger.warning(u"[{0}] Error parsing source data: {1}. Skipping until next scheduled poll.".format(dev.id, unicode(sub_error)))
            self.rawData = '<?xml version="1.0" encoding="UTF-8"?><Emptydict><Response>No data to return.</Response></Emptydict>'
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No data")
            return self.rawData
