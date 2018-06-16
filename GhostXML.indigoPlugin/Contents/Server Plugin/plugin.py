#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
GhostXML Plugin
Authors: See (repo)

This plugin provides an engine which parses tag/value pairs into
transitive Indigo plugin device states.
"""

# TODO: Add device name to logging entries so that we know what device is being updated. (Perhaps this should wait until update for Indigo 7?)
# TODO: Potential bugs for keys with empty list values {'key': []} will not produce a custom state?
# TODO: Recover gracefully when a user improperly selects digest auth (had a user try to use digest instead of basic).  Return code 401 "unauthorized"

# TODO: Add thread name to any logging lines where appropriate.


# Stock imports
import datetime
import logging
from Queue import Queue
import re
import simplejson
import subprocess
import sys
import threading
import time as t

# Third-party imports
import flatdict  # https://github.com/gmr/flatdict
import indigoPluginUpdateChecker
try:
    import indigo
except ImportError:
    pass

try:
    import pydevd
except ImportError:
    pass

# Custom imports
import iterateXML

__author__    = u"DaveL17, GlennNZ, howartp"
__build__     = u""
__copyright__ = u"There is no copyright for the GhostXML code base."
__license__   = u"MIT"
__title__     = u"GhostXML Plugin for Indigo Home Control"
__version__   = u"0.4.03"

# Establish default plugin prefs; create them if they don't already exist.
kDefaultPluginPrefs = {
    u'configMenuServerTimeout': "15",  # Server timeout limit.
    u'showDebugInfo': False,           # Verbose debug logging?
    u'showDebugLevel': "1",            # Low, Medium or High debug output.
    u'updaterEmail': "",               # Email to notify of plugin updates.
    u'updaterEmailsEnabled': False     # Notification of plugin updates wanted.
}


class Plugin(indigo.PluginBase):
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.pluginIsInitializing = True
        self.pluginIsShuttingDown = False

        # ============================ Configure Logging ==============================
        try:
            if int(self.pluginPrefs.get('showDebugLevel', '30')) < 10:
                self.pluginPrefs['showDebugLevel'] *= 10
        except ValueError:
            self.pluginPrefs['showDebugLevel'] = 30

        self.debugLevel = self.pluginPrefs['showDebugLevel']
        self.plugin_file_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d\t%(levelname)-10s\t%(name)s.%(funcName)-28s %(msg)s', datefmt='%Y-%m-%d %H:%M:%S'))

        self.indigo_log_handler.setLevel(20)
        self.logger.info(u"")
        self.logger.info(u"{0:=^130}".format(" Initializing New Plugin Session "))
        self.logger.info(u"{0:<30} {1}".format("Plugin name:", pluginDisplayName))
        self.logger.info(u"{0:<30} {1}".format("Plugin version:", pluginVersion))
        self.logger.info(u"{0:<30} {1}".format("Plugin ID:", pluginId))
        self.logger.info(u"{0:<30} {1}".format("Indigo version:", indigo.server.version))
        self.logger.info(u"{0:<30} {1}".format("Python version:", sys.version.replace('\n', '')))
        self.logger.info(u"{0:=^130}".format(""))

        self.indigo_log_handler.setLevel(self.debugLevel)

        self.prefServerTimeout    = int(self.pluginPrefs.get('configMenuServerTimeout', "15"))

        self.updater              = indigoPluginUpdateChecker.updateChecker(self, "https://raw.githubusercontent.com/indigodomotics/GhostXML/master/ghostXML_version.html")
        self.updaterEmailsEnabled = self.pluginPrefs.get('updaterEmailsEnabled', False)

        # A dict of plugin devices that will be used to hold a copy of each active
        # plugin device and a queue for processing device updates. The dict will be
        # (re)populated in self.deviceStartComm() method.
        self.managedDevices = {}

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

        if userCancelled:
            self.logger.debug(u"User prefs dialog cancelled.")

        if not userCancelled:
            self.debugLevel = int(valuesDict.get('showDebugLevel', "30"))
            self.indigo_log_handler.setLevel(self.debugLevel)
            self.logger.debug(u"User prefs saved.")

            indigo.server.log(u"Debugging on (Level: {0})".format(self.debugLevel))

            if int(self.pluginPrefs['showDebugLevel']) == 10:
                self.logger.debug(u"valuesDict: {0} ".format(valuesDict))

        return True

    def deviceStartComm(self, dev):

        # Check for changes to the device's default states.
        dev.stateListOrDisplayStateIdChanged()
        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Starting")

        # Add device instance to dict of managed devices
        self.managedDevices[dev.id] = PluginDevice(self, dev)

        self.logger.debug(u"Started: {0}".format(self.managedDevices[dev.id]))

        # Force refresh of device when comm started
        # self.managedDevices[dev.id].queue.put(dev)

    def deviceStopComm(self, dev):

        # Join the related thread
        self.managedDevices[dev.id].dev_thread.join(0.5)

        # and delete the device from the list of managed devices.
        del self.managedDevices[dev.id]

        dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="Disabled")
        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
        self.logger.debug(u"Stopped: {0}".format(dev.name))

    def getDeviceStateList(self, dev):
        """
        Assign data keys to device state names

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
            self.logger.debug(u"Pulling down existing state list.")

            # If there are no managed devices, returns the existing states
            if dev.id not in self.managedDevices.keys():
                return indigo.PluginBase.getDeviceStateList(self, dev)

            # This statement goes out and gets the existing state list for dev.
            state_list = indigo.PluginBase.getDeviceStateList(self, dev)

            if state_list is not None:

                # Iterate the tags in final_dict into device state keys.
                self.logger.debug(u"  Writing dynamic states to device.")

                # Example: dynamic_state = self.getDeviceStateDictForStringType(key, u'Trigger Test Label', u'State Label')
                for key in self.managedDevices[dev.id].finalDict.keys():
                    dynamic_state = self.getDeviceStateDictForStringType(key, key, key)
                    state_list.append(dynamic_state)

            # Inspect existing state list to new one to see if the state list needs to be
            # updated. If it doesn't, we can save some effort here.
            interim_state_list = [thing['Key'] for thing in state_list]
            for thing in [u'deviceIsOnline', u'deviceLastUpdated', ]:
                interim_state_list.remove(thing)

            # Compare existing states to new ones
            if not set(interim_state_list) == set(self.managedDevices[dev.id].finalDict.keys()):
                self.logger.debug(u"New states found.")
                self.logger.debug(u"Initial states: {0}".format(interim_state_list))  # existing states
                self.logger.debug(u"New states: {0}".format(self.managedDevices[dev.id].finalDict.keys()))  # new states

            else:
                self.logger.debug(u"No new states found.")

            # Resolves issue with deviceIsOnline and deviceLastUpdated states disappearing
            # if there's a fault in the JSON data we receive, as state_list MUST contain
            # all desired states when it returns

            try:
                state_list.append(self.getDeviceStateDictForStringType('deviceIsOnline', 'deviceIsOnline', 'deviceIsOnline'))
                state_list.append(self.getDeviceStateDictForStringType('deviceLastUpdated', 'deviceLastUpdated', 'deviceLastUpdated'))
                state_list.append(self.getDeviceStateDictForStringType('deviceTimestamp', 'deviceTimestamp', 'deviceTimestamp'))

            except KeyError:
                # Ignore this error as we expect it to happen when all is healthy
                pass

            self.logger.debug(u"Device needs update: {0}".format(self.managedDevices[dev.id].deviceNeedsUpdated))

            return state_list

        else:
            self.logger.debug(u"Device has been updated. Blow state list up to Trigger and Control Page labels.")
            state_list = indigo.PluginBase.getDeviceStateList(self, dev)

            # Iterate the device states into trigger and control page labels when the
            # device is called.
            for state in dev.states:
                dynamic_state = self.getDeviceStateDictForStringType(state, state, state)
                state_list.append(dynamic_state)

            try:
                state_list.append(self.getDeviceStateDictForStringType('deviceIsOnline', 'deviceIsOnline', 'deviceIsOnline'))
                state_list.append(self.getDeviceStateDictForStringType('deviceLastUpdated', 'deviceLastUpdated', 'deviceLastUpdated'))
                state_list.append(self.getDeviceStateDictForStringType('deviceTimestamp', 'deviceTimestamp', 'deviceTimestamp'))

            except KeyError:
                # Ignore this error as we expect it to happen when all is healthy
                pass

            return state_list

    def runConcurrentThread(self):

        self.sleep(5)

        try:
            while True:
                self.updater.checkVersionPoll()

                for devId in self.managedDevices:
                    dev = self.managedDevices[devId].device

                    if self.timeToUpdate(dev):
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
        self.indigo_log_handler.setLevel(self.debugLevel)

    def startup(self):

        # Initialize all plugin devices to ensure that they're in the proper state.
        for dev in indigo.devices.itervalues("self"):
            if not dev.enabled:
                dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="Disabled")

            else:
                dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Initialized")
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        # See if there is a plugin update and whether the user wants to be
        # notified.
        try:
            self.updater.checkVersionPoll()
        except Exception as sub_error:
            self.logger.warning(u"Update checker error: {0}".format(sub_error))

    def validateDeviceConfigUi(self, valuesDict, typeID, devId):

        error_msg_dict = indigo.Dict()
        url = valuesDict['sourceXML']
        url_list = ('file:///', 'http://', 'https://')

        # Test the source URL/Path for proper prefix.
        if not url.startswith(url_list):
            error_msg_dict['sourceXML'] = u"You must supply a valid URL/Path."
            error_msg_dict['showAlertText'] = u"URL/Path Error.\n\nA valid URL/Path starts with:\n'http://',\n'https://', or\n'file:///'."
            return False, valuesDict, error_msg_dict

        # Test the variable substitution IDs and indexes. If substitutions
        # aren't enabled, we can skip this bit.
        if valuesDict['doSubs']:

            sub_list = [('subA', '[A]'), ('subB', '[B]'), ('subC', '[C]'), ('subD', '[D]'), ('subE', '[E]')]
            var_list = [var.id for var in indigo.variables]

            for sub in sub_list:

                # Ensure that the values entered in the substitution fields are
                # valid Indigo variable IDs.
                if valuesDict[sub[0]].isspace() or valuesDict[sub[0]] == "":
                    pass
                elif int(valuesDict[sub[0]]) not in var_list:
                    error_msg_dict[sub[0]] = u"You must supply a valid variable ID."
                    error_msg_dict['showAlertText'] = u"Variable {0} Error\n\nYou must supply a valid Indigo variable ID number to perform substitutions (or leave the field blank).".format(sub[0].replace('sub', ''))
                    return False, valuesDict, error_msg_dict

                # Ensure that the proper substitution index is included in the
                # source URL.
                if valuesDict[sub[0]].strip() != "" and sub[1].strip() not in url:
                    error_msg_dict[sub[0]] = u"Please add a substitution index to the source URL for this variable ID."
                    error_msg_dict['showAlertText'] = u"Variable {0} Error\n\nYou must include a valid substitution index in your source URL for this variable.".format(sub[0].replace('sub', ''))
                    return False, valuesDict, error_msg_dict

        return True, valuesDict, error_msg_dict

    def validatePrefsConfigUi(self, valuesDict):
        """
        title placeholder

        docstring placeholder

        -----

        """

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

    def checkVersionNow(self):
        """
        Check to ensure that the plugin is the most current version

        The checkVersionNow() method is called if user selects "Check For Plugin
        Updates..." Indigo menu item. It is only called by user request.

        -----

        """

        try:
            self.updater.checkVersionNow()
        except Exception as sub_error:
            self.logger.warning(u"Update checker error: {0}".format(sub_error))

    def commsKillAll(self):
        """
        Disable communication of all plugin devices

        commsKillAll() sets the enabled status of all plugin devices to false.

        -----

        """

        for dev in indigo.devices.itervalues("self"):

            try:
                indigo.device.enable(dev, value=False)
            except Exception as sub_error:
                self.logger.critical(u"Exception when trying to unkill all comms. Error: {0} (Line {1})".format(sub_error, sys.exc_traceback.tb_lineno))

        return True

    def commsUnkillAll(self):
        """
        Enable communication of all plugin devices

        commsUnkillAll() sets the enabled status of all plugin devices to true.

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
        Initiate data refresh based on menu call

        The refreshDataAction() method refreshes data for all devices based on a plugin
        menu call.

        -----

        :param valuesDict:
        """

        self.refreshData()
        return True

    def refreshData(self):
        """
        The refreshData() method controls the updating of all plugin devices

        Initiate a data refresh based on a normal plugin cycle.

        -----

        """

        # If there are no devices created or all devices are disabled.
        if len(self.managedDevices) == 0:
            self.logger.warning(u"No GhostXML devices have been created.")
            return True

        try:
            for devId in self.managedDevices:

                dev = self.managedDevices[devId].device
                self.managedDevices[devId].queue.put(dev)

            return True

            # =============================================================

        except Exception as sub_error:
            self.logger.critical(u"Error refreshing devices. Please check settings.")
            self.logger.critical(unicode(sub_error))
            return False

    def refreshDataForDevAction(self, valuesDict):
        """
        Initiate a device refresh baed on an Indigo Action call

        The refreshDataForDevAction() method refreshes data for a selected device
        based on a plugin action call.

        -----

        :param valuesDict:
        """

        dev = self.managedDevices[valuesDict.deviceId].device
        self.managedDevices[dev.id].queue.put(dev)

        return True

    def stopSleep(self, start_sleep):
        """
        Update device sleep value as warranted

        The stopSleep() method accounts for changes to the user upload interval
        preference. The plugin checks every 2 seconds to see if the sleep interval
        should be updated.

        -----

        :param start_sleep:
        """

        total_sleep = float(self.pluginPrefs.get('configMenuUploadInterval', 300))

        if t.time() - start_sleep > total_sleep:
            return True

        return False

    def timeToUpdate(self, dev):
        """
        Determine if a device is ready for a refresh

        Returns True if the device is ready to be updated, else returns False.

        -----

        :param dev:
        """

        # If device has a deviceTimestamp key and is enabled.
        if "deviceTimestamp" in dev.states.iterkeys() and dev.enabled:  # Added dev.enabled test - DaveL17 2017-09-18

            # If the refresh frequency is zero, the device is a manual only refresh.
            if int(dev.pluginProps.get("refreshFreq", 300)) == 0:
                return False

            # If the refresh frequency is not zero, test to see if the device is ready for a refresh.
            else:
                t_since_upd = int(t.time() - float(dev.states["deviceTimestamp"]))

                # If it's time for the device to be updated.
                if int(t_since_upd) > int(dev.pluginProps.get("refreshFreq", 300)):

                    self.logger.debug(u"Time since update ({0}) is greater than configured frequency ({1})".format(t_since_upd, dev.pluginProps["refreshFreq"]))
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

    -----

    """
    def __init__(self, plugin, device):

        self.pluginDeviceIsInitializing = True

        self.device      = device
        self.host_plugin = plugin

        self.deviceNeedsUpdated = ''
        self.finalDict          = {}
        self.jsonRawData        = ''
        self.rawData            = ''

        self.queue      = Queue(maxsize=0)
        self.dev_thread = threading.Thread(name=self.device.id, target=self.initiate_device_update, args=(self.queue,))
        self.dev_thread.start()

        self.pluginDeviceIsInitializing = False

    def __str__(self):

        return u"GhostXML Device: {0}, {1}, {2}".format(self.device.name, self.dev_thread, self.queue)

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
            # Initiate curl call to data source.
            url = dev.pluginProps['sourceXML']

            if dev.pluginProps.get('doSubs', False):
                self.host_plugin.logger.debug(u"Device & URL: {0} @ {1}  (before substitution)".format(dev.name, url))
                url = self.host_plugin.substitute(url.replace("[A]", "%%v:" + dev.pluginProps['subA'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[B]", "%%v:" + dev.pluginProps['subB'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[C]", "%%v:" + dev.pluginProps['subC'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[D]", "%%v:" + dev.pluginProps['subD'] + "%%"))
                url = self.host_plugin.substitute(url.replace("[E]", "%%v:" + dev.pluginProps['subE'] + "%%"))
                self.host_plugin.logger.debug(u"Device & URL: {0} @ {1}  (after substitution)".format(dev.name, url))

            username = dev.pluginProps.get('digestUser', '')
            password = dev.pluginProps.get('digestPass', '')

            use_auth = dev.pluginProps.get('useAuth', False)

            if dev.pluginProps.get('useDigest', False) in ['true', 'True', True]:
                use_digest = True
            else:
                use_digest = False

            # Digest auth
            if use_auth and use_digest:
                proc = subprocess.Popen(["curl", '-vs', '--digest', '-u', username + ':' + password, url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Basic auth
            elif use_auth and not use_digest:
                proc = subprocess.Popen(["curl", '-vs', '-u', username + ':' + password, url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # No auth
            else:
                proc = subprocess.Popen(["curl", '-vs', url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            (result, err) = proc.communicate()

            if int(proc.returncode) != 0:
                self.host_plugin.logger.warning(u"curl error {0}.".format(err))

            return result

        except IOError:

            self.host_plugin.logger.warning(u"{0} - IOError:  Skipping until next scheduled poll.".format(dev.name))
            self.host_plugin.logger.debug(u"Device is offline. No data to return. Returning dummy dict.")
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No comm")
            return '{"GhostXML": "IOError"}'

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
            pattern = re.compile("|".join(chars_to_replace.keys()))

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

            self.host_plugin.logger.debug(u"Cleaned data: {0}".format(self.jsonRawData))

        except ValueError as sub_error:
            self.host_plugin.logger.critical(u'Error cleaning dictionary keys: {0}'.format(sub_error))

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

            self.host_plugin.logger.debug(u"Initial data: {0}".format(parsed_simplejson))

            # if List flattens once - with addition of No_ to the beginning (Indigo appears
            # to not allow DeviceNames to start with Numbers) then flatDict runs - and
            # appears to run correctly (as no longer list - dict) if isinstance(list) then
            # will flatten list down to dict.

            if isinstance(parsed_simplejson, list):

                parsed_simplejson = dict((u"No_" + unicode(i), v) for (i, v) in enumerate(parsed_simplejson))

            self.jsonRawData = flatdict.FlatDict(parsed_simplejson, delimiter='_ghostxml_')

            # self.host_plugin.logger.debug(self.jsonRawData)

            return self.jsonRawData

        except ValueError as sub_error:
            self.host_plugin.logger.warning(dev.name + ": " + unicode(sub_error))

    def parse_state_values(self, dev):
        """
        Parse data values to device states

        The parse_state_values() method walks through the dict and assigns the
        corresponding value to each device state.

        -----

        :param dev:
        """

        state_list = []

        self.host_plugin.logger.debug(u"Writing device states:")

        sorted_list = sorted(self.finalDict.iterkeys())

        for key in sorted_list:
            try:

                self.host_plugin.logger.debug(u"   {0} = {1}".format(key, self.finalDict[key]))

                state_list.append({'key': unicode(key), 'value': unicode(self.finalDict[key])})

            except ValueError as sub_error:
                self.host_plugin.logger.critical(u"Error parsing key/value pair: {0} = {1}. Reason: {2}".format(key, self.finalDict[key], sub_error))
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
            self.host_plugin.logger.debug(u"Refreshing device: {0}".format(dev.name))
            self.rawData = self.get_the_data(dev)

            # Throw the data to the appropriate module to flatten it.
            dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Processing")

            update_time = t.strftime("%m/%d/%Y at %H:%M")
            dev.updateStateOnServer('deviceLastUpdated', value=update_time)
            dev.updateStateOnServer('deviceTimestamp', value=t.time())

            if dev.pluginProps['feedType'] == "XML":
                self.host_plugin.logger.debug(u"Source type: XML")
                self.rawData = self.strip_namespace(dev, self.rawData)
                self.finalDict = iterateXML.iterateMain(self.rawData)

            elif dev.pluginProps['feedType'] == "JSON":
                self.host_plugin.logger.debug(u"Source type: JSON")
                self.finalDict = self.parse_the_json(dev, self.rawData)
                self.clean_the_keys(self.finalDict)

            else:
                self.host_plugin.logger.warning(u"{0}: The plugin only supports XML and JSON data sources.".format(dev.name))

            if self.finalDict is not None:
                # Create the device states.
                self.deviceNeedsUpdated = True
                self.host_plugin.logger.debug(u"Device needs update: {0}".format(self.deviceNeedsUpdated))
                dev.stateListOrDisplayStateIdChanged()

                # Put the final values into the device states.
                self.parse_state_values(dev)

                if "GhostXML" in dev.states:
                    dev.updateStateOnServer('deviceIsOnline', value=False, uiValue=dev.states['GhostXML'])
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                else:
                    dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Updated")
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                dev.setErrorStateOnServer(None)
                self.host_plugin.logger.debug(u"Device refreshed: {0}".format(dev.name))

            else:
                # Set the Timestamp so that the seconds-since-update code doesn't keep checking
                # a dead link / invalid URL every 5 seconds - it will keep checking on it's
                # normal schedule. BUT don't set the "lastUpdated" value so humans can see when
                # it last successfully updated.
                dev.updateStateOnServer('deviceTimestamp', value=t.time())
                dev.setErrorStateOnServer("Error")

        else:
            self.host_plugin.logger.debug(u"Device not available for update: {0} [Enabled: {1}, Configured: {2}]".format(dev.name, dev.enabled, dev.configured))
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

            self.host_plugin.logger.debug(self.rawData)

            return self.rawData

        except ValueError as sub_error:
            self.host_plugin.logger.warning(u"{0} - Error parsing source data: {1}. Skipping until next scheduled poll.".format(dev.name, unicode(sub_error)))
            self.rawData = '<?xml version="1.0" encoding="UTF-8"?><Emptydict><Response>No data to return.</Response></Emptydict>'
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No data")
            return self.rawData
