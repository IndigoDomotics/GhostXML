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
# TODO: (the ignoring update request) was trying to apply the values from one device to the states of another device).

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

        # ============================ Configure Logging ==============================
        # Added by DaveL17 2018-05-22
        # Convert from legacy ['low', 'medium', 'high'] or [1, 2, 3].
        try:
            if int(self.pluginPrefs.get('showDebugLevel', '30')) < 10:
                self.pluginPrefs['showDebugLevel'] *= 10
        except ValueError:
            self.pluginPrefs['showDebugLevel'] = 30

        self.debugLevel = self.pluginPrefs['showDebugLevel']
        self.plugin_file_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d\t%(levelname)-10s\t%(name)s.%(funcName)-28s %(msg)s', datefmt='%Y-%m-%d %H:%M:%S'))
        self.indigo_log_handler.setLevel(self.debugLevel)

        # End DaveL17 changes.
        # =====================================================================

        # TODO: is the self.logFile code still needed with the migration to logging()?
        self.logFile              = u"{0}/Logs/com.fogbert.indigoplugin.GhostXML/plugin.log".format(indigo.server.getInstallFolderPath())
        self.prefServerTimeout    = int(self.pluginPrefs.get('configMenuServerTimeout', "15"))

        self.updater              = indigoPluginUpdateChecker.updateChecker(self, "https://raw.githubusercontent.com/indigodomotics/GhostXML/master/ghostXML_version.html")
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

        # Adding support for remote debugging in PyCharm. Other remote
        # debugging facilities can be added, but only one can be run at a time.
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

        self.logger.debug(u"Starting GhostXML device: {0}".format(dev.name))

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

        self.logger.debug(u"Stopping GhostXML device: {0}".format(dev.name))

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
            self.logger.warning(u'Stopping GhostXML thread.')
            pass

    def shutdown(self):

        self.pluginIsShuttingDown = True

    def startup(self):

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
            self.logger.warning(u"Update checker error: {0}".format(sub_error))

    def validateDeviceConfigUi(self, valuesDict, typeID, devId):

        # =============================================================
        # Device configuration validation Added DaveL17 17/12/19

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

    # =============================== Plugin Methods ===============================

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
                error_msg_dict['updaterEmail'] = u"Valid email addresses have at least one @ symbol in them (foo@bar.com)."
                error_msg_dict['showAlertText'] = u"Updater Email Error:\n\nThe plugin requires a valid email address in order to notify of plugin updates (email address must " \
                                                  u"contain an '@' sign."

                return False, valuesDict, error_msg_dict

        except Exception as sub_error:
            self.logger.warning(u"Plugin configuration error: {0}".format(sub_error))

        return True, valuesDict

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

    def killAllComms(self):
        """
        Disable communication of all plugin devices

        killAllComms() sets the enabled status of all plugin devices to false.

        -----

        """

        for dev in indigo.devices.itervalues("self"):

            try:
                indigo.device.enable(dev, value=False)
            except Exception as sub_error:
                self.logger.critical(u"Exception when trying to unkill all comms. Error: {0} (Line {1})".format(sub_error, sys.exc_traceback.tb_lineno))

        return True

    def unkillAllComms(self):
        """
        Enable communication of all plugin devices

        unkillAllComms() sets the enabled status of all plugin devices to true.

        -----

        """

        for dev in indigo.devices.itervalues("self"):

            try:
                indigo.device.enable(dev, value=True)
            except Exception as sub_error:
                self.logger.critical(u"Exception when trying to unkill all comms. Error: {0} (Line {1})".format(sub_error, sys.exc_traceback.tb_lineno))

        return True

    def deviceQueueProcessor(self):
        """
        Inspect each device's queue and send any queued devices to be processed

        The deviceQueueProcessor() method inspects each device's queue and, if there
        are queue items present, sends those tasks to be processed.

        _____

        """

        while not self.pluginIsShuttingDown:

            if not self.heartbeat_queue.empty():

                for device in self.managedDevices:
                    device_queue = self.managedDevices[device].queue

                    if not device_queue.empty():
                        task = device_queue.get()
                        indigo.server.log(u"Queue task {0} sent to thread {1}".format(task.id, threading.current_thread().name))
                        # self.logger.debug(u"Queue task {0} sent to thread {1}".format(task.id, threading.current_thread().name))
                        self.refreshDataForDev(task)

            # =============================================================
            # Added by DaveL17 2017-12-13
            # The following sleep is necessary to cause the method to rest.
            # Otherwise, the method will chew up resources while waiting.
            self.sleep(1)
            # =============================================================

    def fixErrorState(self, dev):
        """
        Ensure each device has a valid 'deviceLastUpdated' state

        If the 'deviceLastUpdated' state is an empty string, populate the state with a
        valid timestamp.

        -----

        :param dev:
        """

        self.deviceNeedsUpdated = False
        dev.stateListOrDisplayStateIdChanged()
        update_time = t.strftime("%m/%d/%Y at %H:%M")
        dev.updateStateOnServer('deviceLastUpdated', value=update_time)
        dev.updateStateOnServer('deviceTimestamp', value=t.time())

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

        if self.deviceNeedsUpdated and dev.enabled:  # Added dev.enabled test - DaveL17 17/09/18
            # This statement goes out and gets the existing state list for dev.
            self.logger.debug(u"Pulling down existing state list.")
            state_list = indigo.PluginBase.getDeviceStateList(self, dev)

            if state_list is not None:

                # Iterate the tags in final_dict into device state keys.
                self.logger.debug(u"  Writing dynamic states to device.")

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

            # Compare existing states to new ones
            if not set(interim_state_list) == set(self.finalDict.keys()):
                self.logger.debug(u"New states found.")
                self.logger.debug(u"Initial states: {0}".format(interim_state_list))  # existing states
                self.logger.debug(u"New states: {0}".format(self.finalDict.keys()))  # new states
            else:
                self.logger.debug(u"No new states found.")

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
            self.logger.debug(u"Device needs updating set to: {0}".format(self.deviceNeedsUpdated))

            return state_list

        else:
            self.logger.debug(u"Device has been updated. Blow state list up to Trigger and Control Page labels.")
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
        """
        The getTheData() method is used to retrieve target data files.

        The getTheData() method is used to construct the relevant API URL, sends
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

            ###########################
            # ADDED BY howartp 18/06/16
            # Allows substitution of variable or device states into URL using a
            # user-friendly  version of the builtin Indigo substitution
            # mechanism

            if dev.pluginProps.get('doSubs', False):
                self.logger.debug(u"Device & URL: {0} @ {1}  (before substitution)".format(dev.name, url))
                url = self.substitute(url.replace("[A]", "%%v:" + dev.pluginProps['subA'] + "%%"))
                url = self.substitute(url.replace("[B]", "%%v:" + dev.pluginProps['subB'] + "%%"))
                url = self.substitute(url.replace("[C]", "%%v:" + dev.pluginProps['subC'] + "%%"))
                url = self.substitute(url.replace("[D]", "%%v:" + dev.pluginProps['subD'] + "%%"))
                url = self.substitute(url.replace("[E]", "%%v:" + dev.pluginProps['subE'] + "%%"))
                self.logger.debug(u"Device & URL: {0} @ {1}  (after substitution)".format(dev.name, url))

            ###########################
            # ADDED BY GlennNZ 28.11.16
            # to use Digest Auth or not add one normal call, one digest curl
            # call
            ###########################
            # ADDED BY DaveL17 16/11/28
            # Revised GlennNZ's additions to account for props that may not yet
            # be added to some devices. Should now not require devices to be
            # edited and saved.
            ###########################
            # ADDED BY DaveL17 17/12/25
            # Added basic authentication.
            username = dev.pluginProps.get('digestUser', '')
            password = dev.pluginProps.get('digestPass', '')

            ###########################
            # ADDED BY DaveL17 18/03/26
            # Coerces 'useDigest' to boolean.
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

            if err:
                if proc.returncode in (6, 37):
                    f = open(self.logFile, 'a')
                    f.write("{0} - Curl Return Code: {1}\n{2} \n".format(datetime.datetime.time(datetime.datetime.now()), proc.returncode, err))
                    f.close()
                    raise IOError

                elif err is not 0:
                    self.logger.debug(err)

                else:
                    pass

            return result

        # IOError Added by DaveL17 17/12/20
        except IOError:

            self.logger.warning(u"{0} - IOError:  Skipping until next scheduled poll.".format(dev.name))
            self.logger.debug(u"Device is offline. No data to return. Returning dummy dict.")
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No comm")
            return '{"GhostXML": "IOError"}'

    def cleanTheKeys(self, input_data):
        """
        Ensure that state names are valid for Indigo

        Some dictionaries may have keys that contain problematic characters which
        Indigo doesn't like as state names. Let's get those characters out of there.

        -----

        :param input_data:
        """

        try:
            ###########################
            # Added by DaveL17 on 16/11/25.
            # Some characters need to be replaced with a valid replacement
            # value because simply deleting them could cause problems. Add
            # additional k/v pairs to chars_to_replace as needed.

            ###########################
            # ADDED BY GlennNZ 28.11.16
            # add true for True and false for False exchanges
            
            chars_to_replace = {'_ghostxml_': '_', '+': '_plus_', '-': '_minus_', 'true': 'True', 'false': 'False', ' ': '_'}
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
            self.logger.debug("cleanTheKeys result:")
            self.logger.debug(self.jsonRawData)

        except Exception as sub_error:
            self.logger.critical(u'Error cleaning dictionary keys: {0}'.format(sub_error))

    def parseTheJSON(self, dev, root):
        """
        Parse JSON data

        The parseTheJSON() method contains the steps to convert the JSON file into a
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

            self.logger.debug(u"Prior to FlatDict Running JSON")
            self.logger.debug(parsed_simplejson)

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

                self.logger.debug(u"List Detected - Flattening to Dict")

                # =============================================================
                # Added by DaveL17 17/12/13
                # Updates to Unicode.
                parsed_simplejson = dict((u"No_" + unicode(i), v) for (i, v) in enumerate(parsed_simplejson))
                # =============================================================

            self.logger.debug(u"After List Check, Before FlatDict Running JSON")

            # if self.debugLevel >= 2:
            #     self.logger.debug(u"After List Check, Before FlatDict Running JSON")

            self.jsonRawData = flatdict.FlatDict(parsed_simplejson, delimiter='_ghostxml_')

            self.logger.debug(self.jsonRawData)

            return self.jsonRawData

        except Exception as sub_error:
            self.logger.warning(dev.name + ": " + unicode(sub_error))

    def parseStateValues(self, dev):
        """
        Parse data values to device states

        The parseStateValues() method walks through the dict and assigns the
        corresponding value to each device state.

        -----

        :param dev:
        """

        state_list = []

        self.logger.debug(u"Writing device states:")
        
        sorted_list = sorted(self.finalDict.iterkeys())
        for key in sorted_list:
            try:

                self.logger.debug(u"   {0} = {1}".format(key, self.finalDict[key]))

                state_list.append({'key': unicode(key), 'value': unicode(self.finalDict[key])})

            except Exception as sub_error:
                self.logger.critical(u"Error parsing key/value pair: {0} = {1}. Reason: {2}".format(key, self.finalDict[key], sub_error))
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                state_list.append({'key': 'deviceIsOnline', 'value': True, 'uiValue': "Error"})

        dev.updateStatesOnServer(state_list)

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
            # =============================================================
            # Added by DaveL17 17/09/29
            #
            # Remove the call to the server to iterate over plugin devices,
            # instead of using the dict of devices managed globally within the
            # plugin.

            for devId in self.managedDevices:
                dev = self.managedDevices[devId].device

                self.refreshDataForDev(dev)

            return True

            # =============================================================

        except Exception as sub_error:
            self.logger.critical(u"Error refreshing devices. Please check settings.")
            self.logger.critical(unicode(sub_error))
            return False

    def refreshDataForDev(self, dev):
        """
        Initiate refresh of device as required

        If a device is both configured and enabled, initiate a refresh.

        -----

        :param dev:
        """

        lock = threading.Lock()

        ###########################
        # ADDED BY howartp 18/06/16
        # This was previously all inside refreshData() function Separating
        # it out allows devices to be refreshed individually
        if dev.configured:
            self.logger.debug(u"Found configured device: {0}".format(dev.name))

            if dev.enabled:

                # Get the data.
                self.logger.debug(u"Refreshing device: {0}".format(dev.name))
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
                        self.logger.debug(u"Source file type: XML")
                        self.rawData = self.stripNamespace(dev, self.rawData)
                        self.finalDict = iterateXML.iterateMain(self.rawData)

                    elif dev.pluginProps['feedType'] == "JSON":
                        self.logger.debug(u"Source file type: JSON")
                        self.finalDict = self.parseTheJSON(dev, self.rawData)
                        self.cleanTheKeys(self.finalDict)

                    else:
                        self.logger.warning(u"{0}: The plugin only supports XML and JSON data sources.".format(dev.name))

                    if self.finalDict is not None:
                        # Create the device states.
                        self.deviceNeedsUpdated = True
                        self.logger.debug(u"Device needs updating set to: {0}".format(self.deviceNeedsUpdated))
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
                        self.logger.debug(u"{0} updated.".format(dev.name))

                    else:
                        # Set the Timestamp so that the seconds-since-update code
                        # doesn't keep checking a dead link / invalid URL every 5
                        # seconds - it will keep checking on it's normal schedule.
                        # BUT don't set the "lastUpdated" value so humans can see
                        # when it last successfully updated.
                        dev.updateStateOnServer('deviceTimestamp', value=t.time())
                        dev.setErrorStateOnServer("Error")

            else:
                self.logger.debug(u"    Disabled: {0}".format(dev.name))
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    def refreshDataForDevAction(self, valuesDict):
        """
        Initiate a device refresh baed on an Indigo Action call

        The refreshDataForDevAction() method refreshes data for a selected device
        based on a plugin action call.

        -----

        :param valuesDict:
        """

        dev = self.managedDevices[valuesDict.deviceId].device
        self.refreshDataForDev(dev)

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

    def stripNamespace(self, dev, root):
        """
        Strip XML namespace from payload

        The stripNamespace() method strips any XML namespace values, and loads into
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
            # comprehensive re.sub() that could be run, but it also could do
            # *too* much.
            self.rawData = ''
            self.rawData = re.sub(' xmlns="[^"]+"', '', root)
            self.rawData = re.sub(' xmlns:xsi="[^"]+"', '', self.rawData)
            self.rawData = re.sub(' xmlns:xsd="[^"]+"', '', self.rawData)
            self.rawData = re.sub(' xsi:noNamespaceSchemaLocation="[^"]+"', '', self.rawData)

            self.logger.debug(self.rawData)

            return self.rawData

        except Exception as sub_error:
            self.logger.warning(u"{0} - Error parsing source data: {1}. Skipping until next scheduled poll.".format(dev.name, unicode(sub_error)))
            self.rawData = '<?xml version="1.0" encoding="UTF-8"?><Emptydict><Response>No data to return.</Response></Emptydict>'
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No data")
            return self.rawData

    def timeToUpdate(self, dev):
        """
        Determine if a device is ready for a refresh

        Returns True if the device is ready to be updated, else returns False.

        -----

        :param dev:
        """

        # We don't make a log entry when this method is called because it's called every 2 seconds.

        # If device has a deviceTimestamp key and is enabled.
        if "deviceTimestamp" in dev.states.iterkeys() and dev.enabled:  # Added dev.enabled test - DaveL17 17/09/18

            # If the device timestamp is an empty string, set it to a valid value.
            if dev.states["deviceTimestamp"] == "":
                self.fixErrorState(dev)

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
    def __init__(self, device=None):

        self.device = device
        self.queue = Queue()
