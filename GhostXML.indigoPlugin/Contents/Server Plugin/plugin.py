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
# TODO: How to make sure that the queue items are processed by the proper thread? Do we actually care if they aren't?
# TODO: Recover gracefully when a user improperly selects digest auth (had a user try to use digest instead of basic).  Return code 401 "unauthorized"

# Stock imports
import datetime
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
__version__   = u"0.3.14"

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
        """ docstring placeholder """

        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.pluginIsInitializing = True
        self.pluginIsShuttingDown = False

        indigo.server.log(u"")
        indigo.server.log(u"{0:=^130}".format(" Initializing New Plugin Session "))
        indigo.server.log(u"{0:<30} {1}".format("Plugin name:", pluginDisplayName))
        indigo.server.log(u"{0:<30} {1}".format("Plugin version:", pluginVersion))
        indigo.server.log(u"{0:<30} {1}".format("Plugin ID:", pluginId))
        indigo.server.log(u"{0:<30} {1}".format("Indigo version:", indigo.server.version))
        indigo.server.log(u"{0:<30} {1}".format("Python version:", sys.version.replace('\n', '')))
        indigo.server.log(u"{0:=^130}".format(""))

        self.debug                = self.pluginPrefs.get('showDebugInfo', False)
        self.debugLevel           = int(self.pluginPrefs.get('showDebugLevel', 1))
        self.logFile              = u"{0}/Logs/com.fogbert.indigoplugin.GhostXML/plugin.log".format(indigo.server.getInstallFolderPath())
        self.prefServerTimeout    = int(self.pluginPrefs.get('configMenuServerTimeout', "15"))
        self.updater              = indigoPluginUpdateChecker.updateChecker(self, "http://indigodomotics.github.io/GhostXML/ghostXML_version.html")
        self.updaterEmailsEnabled = self.pluginPrefs.get('updaterEmailsEnabled', False)

        self.deviceNeedsUpdated  = ''
        self.finalDict           = {}
        self.jsonRawData         = {}
        self.rawData             = ''

        # A dict of plugin devices that will be used to hold a copy of each
        # active plugin device and a queue for processing device updates. The
        # dict will be (re)populated in self.deviceStartComm() method.
        self.managedDevices = {}

        # A dict of plugin threads where device updates will be processed.
        self.managedThreads = {}

        # A queue to accept heartbeats to signal that some device needs to be updated.
        self.heartbeat_queue = Queue()

        # Convert old debugLevel scale to new scale if needed.
        # =============================================================
        if not isinstance(self.pluginPrefs['showDebugLevel'], int):
            if self.pluginPrefs['showDebugLevel'] == "High":
                self.pluginPrefs['showDebugLevel'] = 3
            elif self.pluginPrefs['showDebugLevel'] == "Medium":
                self.pluginPrefs['showDebugLevel'] = 2
            else:
                self.pluginPrefs['showDebugLevel'] = 1

        # Adding support for remote debugging in PyCharm. Other remote
        # debugging facilities can be added, but only one can be run at a time.
        # try:
        #     pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True, suspend=False)
        # except:
        #     pass

        self.pluginIsInitializing = False

    def __del__(self):
        """ docstring placeholder """

        if self.debugLevel >= 2:
            self.debugLog(u"__del__ method called.")

        indigo.PluginBase.__del__(self)

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        """ docstring placeholder """

        if self.debugLevel >= 2:
            self.debugLog(u"closedPrefsConfigUi() method called.")

        if userCancelled:
            self.debugLog(u"User prefs dialog cancelled.")

        if not userCancelled:
            self.debug = valuesDict.get('showDebugInfo', False)
            self.debugLevel = int(self.pluginPrefs.get('showDebugLevel', "1"))
            self.debugLog(u"User prefs saved.")

            if self.debug:
                indigo.server.log(u"Debugging on (Level: {0})".format(self.debugLevel))
            else:
                pass

            if int(self.pluginPrefs['showDebugLevel']) >= 3:
                self.debugLog(u"valuesDict: {0} ".format(valuesDict))

        return True

    def deviceStartComm(self, dev):
        """ docstring placeholder """

        if self.debugLevel >= 2:
            self.debugLog(u"deviceStartComm() method called.")
        self.debugLog(u"Starting GhostXML device: {0}".format(dev.name))

        # =============================================================
        # Added by DaveL17 17/09/28
        #
        # Add the device to the dict of managed devices where the key is the
        # device ID and the value is a copy of the device. References now
        # become self.managedDevices[dev.id].name instead of dev.name

        self.managedDevices[dev.id] = PluginDevice(dev)

        # Start a thread for the device instance (each device will have its own
        # thread).
        # dev_thread = threading.Thread(name=self.managedDevices[dev.id].device.id, target=self.deviceQueueProcessor, args=('args',))

        thread_name = u"{0} - {1}".format(dev.id, dev.name)
        dev_thread = threading.Thread(name=thread_name, target=self.deviceQueueProcessor)
        self.managedThreads[dev.id] = dev_thread
        dev_thread.start()

        # =============================================================

        dev.stateListOrDisplayStateIdChanged()
        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Waiting")

    def deviceStopComm(self, dev):
        """ docstring placeholder """

        if self.debugLevel >= 2:
            self.debugLog(u"deviceStopComm() method called.")
        self.debugLog(u"Stopping GhostXML device: {0}".format(dev.name))

        # =============================================================
        # Added by DaveL17 17/09/28
        #
        # Remove the device from the dict of managed devices and stop the
        # related thread when communication  with the device has been stopped.
        del self.managedDevices[dev.id]

        # Added by DaveL17 17/12/14
        # Timeout (0.5) to force join the thread if needed.
        self.managedThreads[dev.id].join(0.5)

        # =============================================================

        dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="Disabled")
        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    def runConcurrentThread(self):
        """ docstring placeholder """

        if self.debugLevel >= 2:
            self.debugLog(u"indigoPluginUpdater() method called.")

        self.sleep(5)

        try:
            while True:
                self.updater.checkVersionPoll()

                # =============================================================
                # Added by DaveL17 17/09/29

                for devId in self.managedDevices:
                    dev = self.managedDevices[devId].device

                    # DaveL17 17/09/30 moved update test to its own method.
                    if self.timeToUpdate(dev):
                        self.managedDevices[devId].queue.put(dev)
                        self.heartbeat_queue.put(u'')  # a placeholder to make the queue non-empty

                # =============================================================

                self.sleep(2)

        except self.StopThread:
            self.debugLog(u'Fatal error. Stopping GhostXML thread.')
            pass

    def shutdown(self):
        """ docstring placeholder """

        if self.debugLevel >= 2:
            self.debugLog(u"Shutting down GhostXML. shutdown() method called")

        self.pluginIsShuttingDown = True

    def startup(self):
        """ docstring placeholder """

        if self.debugLevel >= 2:
            self.debugLog(u"Starting GhostXML. startup() method called.")

        # Initialize all plugin devices to ensure that they're in the proper
        # state.
        # =============================================================
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
            self.errorLog(u"Update checker error: {0}".format(sub_error))

    def validateDeviceConfigUi(self, valuesDict, typeID, devId):
        """ Validate select device config menu settings. """

        # =============================================================
        # Device configuration validation Added DaveL17 17/12/19

        self.debugLog(u"validateDeviceConfigUi() method called.")

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

        # =============================================================

        return True, valuesDict, error_msg_dict

    def validatePrefsConfigUi(self, valuesDict):
        """ docstring placeholder """

        if self.debugLevel >= 2:
            self.debugLog(u"validatePrefsConfigUi() method called.")

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
                error_msg_dict['updaterEmail'] = u"Valid email addresses have at least one @ symbol in them (foo@bar.com)."
                error_msg_dict['showAlertText'] = u"Updater Email Error:\n\nThe plugin requires a valid email address in order to notify of plugin updates (email address must " \
                                                  u"contain an '@' sign."

                return False, valuesDict, error_msg_dict

        except Exception as sub_error:
            self.errorLog(u"Plugin configuration error: {0}".format(sub_error))

        return True, valuesDict

    def checkVersionNow(self):
        """
        The checkVersionNow() method is called if user selects "Check For
        Plugin Updates..." Indigo menu item.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"checkVersionNow() method called.")

        try:
            self.updater.checkVersionNow()
        except Exception as sub_error:
            self.errorLog(u"Update checker error: {0}".format(sub_error))

    def killAllComms(self):
        """
        killAllComms() sets the enabled status of all plugin devices to false.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"killAllComms() method called.")

        # =============================================================
        # Added by DaveL17 17/09/29
        #
        # Remove the call to the server to iterate over plugin devices, instead
        # using the dict of devices managed globally within the plugin.

        for devId in self.managedDevices:
            dev = self.managedDevices[devId]

        # =============================================================

            try:
                indigo.device.enable(dev, value=False)
            except Exception as sub_error:
                self.debugLog(u"Exception when trying to kill all comms. Error: {0} (Line {1})".format(sub_error, sys.exc_traceback.tb_lineno))

    def unkillAllComms(self):
        """
        unkillAllComms() sets the enabled status of all plugin devices to true.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"unkillAllComms() method called.")

        # Note that we can't use self.managed devices here because the list of
        # managed devices only includes those that are already enabled. Devices
        # are added to the managed list via deviceStartComm().  Therefore, we
        # need to use the Indigo iterator.
        for dev in indigo.devices.itervalues("self"):

            try:
                indigo.device.enable(dev, value=True)
            except Exception as sub_error:
                self.debugLog(u"Exception when trying to unkill all comms. Error: {0} (Line {1})".format(sub_error, sys.exc_traceback.tb_lineno))

    def deviceQueueProcessor(self):
        """
        Inspect each device's queue and send any queued devices to be
        processed.
        """

        while not self.pluginIsShuttingDown:

            if not self.heartbeat_queue.empty():

                for device in self.managedDevices:
                    device_queue = self.managedDevices[device].queue

                    if not device_queue.empty():
                        task = device_queue.get()
                        if self.debugLevel >= 3:
                            self.debugLog(u"Queue task {0} sent to thread {1}".format(task.id, threading.current_thread().name))
                        self.refreshDataForDev(task)

            # =============================================================
            # Added by DaveL17 17/12/13
            # The following sleep is necessary to cause the method to rest.
            # Otherwise, the method will chew up resources while waiting.
            self.sleep(1)
            # =============================================================

    def fixErrorState(self, dev):
        """
        If the 'deviceLastUpdated' state is an empty string, populate the state
        with a valid timestamp.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"fixErrorState() method called.")

        self.deviceNeedsUpdated = False
        dev.stateListOrDisplayStateIdChanged()
        update_time = t.strftime("%m/%d/%Y at %H:%M")
        dev.updateStateOnServer('deviceLastUpdated', value=update_time)
        dev.updateStateOnServer('deviceTimestamp', value=t.time())

    def getDeviceStateList(self, dev):
        """
        The getDeviceStateList() method pulls out all the keys in
        self.finalDict and assigns them to device states. It returns the
        modified stateList which is then written back to the device in the main
        thread. This method is automatically called by

            stateListOrDisplayStateIdChanged()

        and by Indigo when Triggers and Control Pages are built. Note that it's
        not possible to override Indigo's sorting of devices states which will
        present them as A, B, a, b.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"getDeviceStateList() method called.")

        if self.deviceNeedsUpdated and dev.enabled:  # Added dev.enabled test - DaveL17 17/09/18
            # This statement goes out and gets the existing state list for dev.
            self.debugLog(u"Pulling down existing state list.")
            state_list = indigo.PluginBase.getDeviceStateList(self, dev)

            if state_list is not None:

                # Iterate the tags in final_dict into device state keys.
                self.debugLog(u"  Writing dynamic states to device.")

                for key in self.finalDict.iterkeys():
                    # Example: dynamic_state = self.getDeviceStateDictForStringType(key, u'Trigger Test Label', u'State Label')
                    dynamic_state = self.getDeviceStateDictForStringType(key, key, key)
                    state_list.append(dynamic_state)

            ###########################
            # ADDED BY DaveL17 16/12/26
            # Inspect existing state list to new one to see if the state list
            # needs to be updated. If it doesn't, we can save some effort here.
            interim_state_list = [thing['Key'] for thing in state_list]
            for thing in [u'deviceIsOnline', u'deviceLastUpdated', ]:
                interim_state_list.remove(thing)

            if self.debugLevel >= 3:

                # Compare existing states to new ones
                if not set(interim_state_list) == set(self.finalDict.keys()):
                    self.debugLog(u"New states found.")
                    self.debugLog(u"Initial states: {0}".format(interim_state_list))  # existing states
                    self.debugLog(u"New states: {0}".format(self.finalDict.keys()))  # new states
                else:
                    self.debugLog(u"No new states found.")

            # END DaveL17 changes
            ###########################

            ###########################
            # ADDED BY howartp 18/06/16
            # Resolves issue with deviceIsOnline and deviceLastUpdated states
            # disappearing if there's a fault in the JSON data we receive, as
            # state_list MUST contain all desired states when it returns

            try:
                state_list.append(self.getDeviceStateDictForStringType('deviceIsOnline', 'deviceIsOnline', 'deviceIsOnline'))
                state_list.append(self.getDeviceStateDictForStringType('deviceLastUpdated', 'deviceLastUpdated', 'deviceLastUpdated'))
                state_list.append(self.getDeviceStateDictForStringType('deviceTimestamp', 'deviceTimestamp', 'deviceTimestamp'))

            except KeyError:
                # Ignore this error as we expect it to happen when all is healthy
                pass

            # END howartp changes
            ###########################

            self.deviceNeedsUpdated = False
            self.debugLog(u"Device needs updating set to: {0}".format(self.deviceNeedsUpdated))

            return state_list

        else:
            self.debugLog(u"Device has been updated. Blow state list up to Trigger and Control Page labels.")
            state_list = indigo.PluginBase.getDeviceStateList(self, dev)

            # Iterate the device states into trigger and control page labels
            # when the device is called.
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

    def getTheData(self, dev):
        """ The getTheData() method is used to retrieve target data files. """

        if self.debugLevel >= 2:
            self.debugLog(u"getTheData() method called.")

        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Download")

        try:
            # Initiate curl call to data source.
            url = dev.pluginProps['sourceXML']

            ###########################
            # ADDED BY howartp 18/06/16
            # Allows substitution of variable or device states into URL using a
            # user-friendly  version of the builtin Indigo substitution
            # mechanism

            if dev.pluginProps.get('doSubs', False):
                self.debugLog(u"Device & URL: {0} @ {1}  (before substitution)".format(dev.name, url))
                url = self.substitute(url.replace("[A]", "%%v:" + dev.pluginProps['subA'] + "%%"))
                url = self.substitute(url.replace("[B]", "%%v:" + dev.pluginProps['subB'] + "%%"))
                url = self.substitute(url.replace("[C]", "%%v:" + dev.pluginProps['subC'] + "%%"))
                url = self.substitute(url.replace("[D]", "%%v:" + dev.pluginProps['subD'] + "%%"))
                url = self.substitute(url.replace("[E]", "%%v:" + dev.pluginProps['subE'] + "%%"))
                self.debugLog(u"Device & URL: {0} @ {1}  (after substitution)".format(dev.name, url))

            ###########################
            # ADDED BY GlennNZ 28.11.16
            # to use Digest Auth or not add one normal call, one digest curl
            # call
            ###########################
            # ADDED BY DaveL17 11/28/16
            # Revised GlennNZ's additions to account for props that may not yet
            # be added to some devices. Should now not require devices to be
            # edited and saved.

            if dev.pluginProps.get('useDigest', False):
                username = dev.pluginProps.get('digestUser', '')
                password = dev.pluginProps.get('digestPass', '')
                proc = subprocess.Popen(["curl", '-vs', '--digest', '-u', username + ':' + password, url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            else:
                proc = subprocess.Popen(["curl", '-vs', url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            (result, err) = proc.communicate()

            if err:
                if proc.returncode in (6, 37):
                    f = open(self.logFile, 'a')
                    f.write("{0} - Curl Return Code: {1}\n{2} \n".format(datetime.datetime.time(datetime.datetime.now()), proc.returncode, err))
                    f.close()
                    raise IOError

                elif err is not 0:
                    self.debugLog(err)

                else:
                    pass

            return result

        # IOError Added by DaveL17 17/12/20
        except IOError:

            self.errorLog(u"{0} - IOError:  Skipping until next scheduled poll.".format(dev.name))
            self.debugLog(u"Device is offline. No data to return. Returning dummy dict.")
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No comm")
            return '{"GhostXML": "IOError"}'

    def cleanTheKeys(self, input_data):
        """
        Some dictionaries may have keys that contain problematic characters
        which Indigo doesn't like as state names. Let's get those characters
        out of there.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"cleanTheKeys() method called.")

        try:
            ###########################
            # Added by DaveL17 on 16/11/25.
            # Some characters need to be replaced with a valid replacement
            # value because simply deleting them could cause problems. Add
            # additional k/v pairs to chars_to_replace as needed.

            ###########################
            # ADDED BY GlennNZ 28.11.16
            # add true for True and false for False exchanges
            
            chars_to_replace = {'_ghostxml_': '_', '+': '_plus_', '-': '_minus_', 'true': 'True', 'false': 'False'}
            chars_to_replace = dict((re.escape(k), v) for k, v in chars_to_replace.iteritems())
            pattern = re.compile("|".join(chars_to_replace.keys()))

            for key in input_data.iterkeys():
                new_key = pattern.sub(lambda m: chars_to_replace[re.escape(m.group(0))], key)
                input_data[new_key] = input_data.pop(key)

            # Some characters can simply be eliminated. If something here
            # causes problems, remove the element from the set and add it to
            # the replacement dict above.
            chars_to_remove = {'/', '(', ')'}

            for key in input_data.iterkeys():
                new_key = ''.join([c for c in key if c not in chars_to_remove])
                input_data[new_key] = input_data.pop(key)

            ###########################
            # Added by DaveL17 on 16/11/28.
            # Indigo will not accept device state names that begin with a
            # number, so inspect them and prepend any with the string "No_" to
            # force them to something that Indigo will accept.
            temp_dict = {}

            for key in input_data.keys():
                if key[0].isdigit():
                    temp_dict[u'No_{0}'.format(key)] = input_data[key]
                else:
                    temp_dict[key] = input_data[key]

            input_data = temp_dict

            self.jsonRawData = input_data

            ###########################
            # ADDED BY GlennNZ 28.11.16
            # More debug
            if self.debugLevel >= 2:
                self.debugLog("cleanTheKeys result:")
                self.debugLog(self.jsonRawData)
            
        except Exception as sub_error:
            self.errorLog(u'Error cleaning dictionary keys: {0}'.format(sub_error))

    def parseTheJSON(self, dev, root):
        """
        The parseTheJSON() method contains the steps to convert the JSON file
        into a flat dict.

        http://github.com/gmr/flatdict
        class flatdict.FlatDict(value=None, delimiter=None, former_type=<type 'dict'>)
        """

        if self.debugLevel >= 2:
            self.debugLog(u"parseTheJSON() method called.")
        try:
            parsed_simplejson = simplejson.loads(root)

            if self.debugLevel >= 2:
                self.debugLog(u"Prior to FlatDict Running JSON")
                self.debugLog(parsed_simplejson)

            ###########################
            # ADDED BY GlennNZ 28.11.16
            # Check if list and then flatten to allow FlatDict to work in
            # theory!
            #
            # if List flattens once - with addition of No_ to the beginning
            # (Indigo appears to not allow DeviceNames to start with Numbers)
            # then flatDict runs - and appears to run correctly (as no longer
            # list - dict) if isinstance(list) then will flatten list down to
            # dict.

            if isinstance(parsed_simplejson, list):

                if self.debugLevel >= 2:
                    self.debugLog(u"List Detected - Flattening to Dict")

                # =============================================================
                # Added by DaveL17 17/12/13
                # Updates to Unicode.
                parsed_simplejson = dict((u"No_" + unicode(i), v) for (i, v) in enumerate(parsed_simplejson))
                # =============================================================

            if self.debugLevel >= 2:
                self.debugLog(u"After List Check, Before FlatDict Running JSON")

            self.jsonRawData = flatdict.FlatDict(parsed_simplejson, delimiter='_ghostxml_')

            if self.debugLevel >= 2:
                self.debugLog(self.jsonRawData)

            return self.jsonRawData

        except Exception as sub_error:
            self.errorLog(dev.name + ": " + unicode(sub_error))

    def parseStateValues(self, dev):
        """
        The parseStateValues() method walks through the dict and assigns the
        corresponding value to each device state.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"parseStateValues() method called.")

        self.debugLog(u"Writing device states:")
        
        sorted_list = sorted(self.finalDict.iterkeys())
        for key in sorted_list:
            try:
                if self.debugLevel >= 3:
                    self.debugLog(u"   {0} = {1}".format(key, self.finalDict[key]))
                dev.updateStateOnServer(unicode(key), value=unicode(self.finalDict[key]))

            except Exception as sub_error:
                self.errorLog(u"Error parsing key/value pair: {0} = {1}. Reason: {2}".format(key, self.finalDict[key], sub_error))
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Error")

    def refreshDataAction(self, valuesDict):
        """
        The refreshDataAction() method refreshes data for all devices based on
        a plugin menu call.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"refreshDataAction() method called.")
        self.refreshData()
        return True

    def refreshData(self):
        """
        The refreshData() method controls the updating of all plugin devices.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"refreshData() method called.")

        # If there are no devices created or all devices are disabled.
        if len(self.managedDevices) == 0:
            indigo.server.log(u"No GhostXML devices have been created.")
            return True

        try:
            # =============================================================
            # Added by DaveL17 17/09/29
            #
            # Remove the call to the server to iterate over plugin devices,
            # instead using the dict of devices managed globally within the
            # plugin.

            for devId in self.managedDevices:
                dev = self.managedDevices[devId].device

                self.refreshDataForDev(dev)

            return True

            # =============================================================

        except Exception as sub_error:
            self.errorLog(u"Error refreshing devices. Please check settings.")
            self.errorLog(unicode(sub_error))
            return False

    def refreshDataForDev(self, dev):
        """ Refreshes device data. """

        if self.debugLevel >= 2:
            self.debugLog(u"refreshDataForDev() method called.")

        lock = threading.Lock()

        ###########################
        # ADDED BY howartp 18/06/16
        # This was previously all inside refreshData() function Separating
        # it out allows devices to be refreshed individually
        if dev.configured:
            self.debugLog(u"Found configured device: {0}".format(dev.name))

            if dev.enabled:

                # Get the data.
                self.debugLog(u"Refreshing device: {0}".format(dev.name))
                self.rawData = self.getTheData(dev)

                with lock:
                    # Throw the data to the appropriate module to flatten it.
                    dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Processing")

                    # =============================================================
                    # Moved here by DaveL17 17/12/15
                    #
                    # By setting the device last updated time at the outset of
                    # the refresh cycle, we can avoid the collisions that take
                    # place when a device refresh takes longer than the 2
                    # second poll (when a device takes more than 2 seconds to
                    # refresh, it can be called to refresh again before it's
                    # finished the first -- resulting in a race).

                    update_time = t.strftime("%m/%d/%Y at %H:%M")
                    dev.updateStateOnServer('deviceLastUpdated', value=update_time)
                    dev.updateStateOnServer('deviceTimestamp', value=t.time())

                    # =============================================================

                    if dev.pluginProps['feedType'] == "XML":
                        self.debugLog(u"Source file type: XML")
                        self.rawData = self.stripNamespace(dev, self.rawData)
                        self.finalDict = iterateXML.iterateMain(self.rawData)

                    elif dev.pluginProps['feedType'] == "JSON":
                        self.debugLog(u"Source file type: JSON")
                        self.finalDict = self.parseTheJSON(dev, self.rawData)
                        self.cleanTheKeys(self.finalDict)

                    else:
                        indigo.server.log(u"{0}: The plugin only supports XML and JSON data sources.".format(dev.name))

                    if self.finalDict is not None:
                        # Create the device states.
                        self.deviceNeedsUpdated = True
                        self.debugLog(u"Device needs updating set to: {0}".format(self.deviceNeedsUpdated))
                        dev.stateListOrDisplayStateIdChanged()

                        # Put the final values into the device states.
                        self.parseStateValues(dev)

                        if "GhostXML" in dev.states:
                            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue=dev.states['GhostXML'])
                            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorTripped)
                        else:
                            dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Updated")
                            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                        dev.setErrorStateOnServer(None)
                        self.debugLog(u"{0} updated.".format(dev.name))

                    else:
                        # Set the Timestamp so that the seconds-since-update code
                        # doesn't keep checking a dead link / invalid URL every 5
                        # seconds - it will keep checking on it's normal schedule.
                        # BUT don't set the "lastUpdated" value so humans can see
                        # when it last successfully updated.
                        dev.updateStateOnServer('deviceTimestamp', value=t.time())
                        dev.setErrorStateOnServer("Error")

            else:
                self.debugLog(u"    Disabled: {0}".format(dev.name))
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    def refreshDataForDevAction(self, valuesDict):
        """
        The refreshDataForDevAction() method refreshes data for a selected
        device based on a plugin action call.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"refreshDataForDevAction() method called.")

        dev = self.managedDevices[valuesDict.deviceId]

        self.refreshDataForDev(dev)

        return True

    def stopSleep(self, start_sleep):
        """
        The stopSleep() method accounts for changes to the user upload
        interval preference. The plugin checks every 2 seconds to see if the
        sleep interval should be updated.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"stopSleep() method called.")

        total_sleep = float(self.pluginPrefs.get('configMenuUploadInterval', 300))

        if t.time() - start_sleep > total_sleep:
            return True

        return False

    def stripNamespace(self, dev, root):
        """
        The stripNamespace() method strips any XML namespace values, and loads
        into self.rawData.
        """

        if self.debugLevel >= 2:
            self.debugLog(u"stripNamespace() method called.")

        try:
            if root == "":
                root = '<?xml version="1.0" encoding="UTF-8"?><Emptydict><Response>No data to return.</Response></Emptydict>'

            # Remove namespace stuff if it's in there. There's probably a more
            # comprehensive re.sub() that could be run, but it also could do
            # *too* much.
            self.rawData = ''
            self.rawData = re.sub(' xmlns="[^"]+"', '', root)
            self.rawData = re.sub(' xmlns:xsi="[^"]+"', '', self.rawData)
            self.rawData = re.sub(' xmlns:xsd="[^"]+"', '', self.rawData)
            self.rawData = re.sub(' xsi:noNamespaceSchemaLocation="[^"]+"', '', self.rawData)

            if self.debugLevel >= 3:
                self.debugLog(self.rawData)
            return self.rawData

        except Exception as sub_error:
            self.errorLog(u"{0} - Error parsing source data: {1}. Skipping until next scheduled poll.".format(dev.name, unicode(sub_error)))
            self.rawData = '<?xml version="1.0" encoding="UTF-8"?><Emptydict><Response>No data to return.</Response></Emptydict>'
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No data")
            return self.rawData

    def timeToUpdate(self, dev):
        """
        Returns True if the device is ready to be updated, else returns False.
        """

        # We don't make a log entry when this method is called because it's called every 2 seconds.

        # If device has a deviceTimestamp key and is enabled.
        if "deviceTimestamp" in dev.states.iterkeys() and dev.enabled:  # Added dev.enabled test - DaveL17 17/09/18

            # If the device timestamp is an empty string, set it to a valid value.
            if dev.states["deviceTimestamp"] == "":
                self.fixErrorState(dev)

            # If the refresh frequency is zero, the device is a manual only refresh.
            if int(dev.pluginProps.get("refreshFreq", 300)) == 0:
                self.debugLog(u"    Refresh frequency: {0} (Manual refresh only)".format(dev.pluginProps["refreshFreq"]))
                return False

            # If the refresh frequency is not zero, test to see if the device is ready for a refresh.
            else:
                t_since_upd = int(t.time() - float(dev.states["deviceTimestamp"]))

                # If it's time for the device to be updated.
                if int(t_since_upd) > int(dev.pluginProps.get("refreshFreq", 300)):

                    self.debugLog(u"Time since update ({0}) is greater than configured frequency ({1})".format(t_since_upd, dev.pluginProps["refreshFreq"]))
                    return True

                # If it's not time for the device to be updated.
                return False

        # If the device does not have a timestamp key and/or is disabled.
        else:
            return False

    def toggleDebugEnabled(self):
        """ Toggle debug on/off. """

        if self.debugLevel >= 2:
            self.debugLog(u"toggleDebugEnabled() method called.")

        if not self.debug:
            self.debug = True
            self.pluginPrefs['showDebugInfo'] = True
            indigo.server.log(u"Debugging on.")
            self.debugLog(u"Debug level: {0}".format(self.debugLevel))

        else:
            self.debug = False
            self.pluginPrefs['showDebugInfo'] = False
            indigo.server.log(u"Debugging off.")


class PluginDevice(object):
    """
    The PluginDevice class is used to create an object to store data related to
    each enabled plugin device. The object contains an instance of the Indigo
    device and a command queue.
    """
    def __init__(self, device=None):
        self.device = device
        self.queue = Queue()
