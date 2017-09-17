#! /usr/bin/env python2.6
# -*- coding: utf-8 -*-

"""
GhostXML Plugin
Authors: See (repo)

This plugin provides an engine which parses tag/value pairs into
transitive Indigo plugin device states.
"""
# TODO: Keep an eye on unicode snafus.
# TODO: Get self.debugLog into iterateXML module.
# TODO: Right now, there is only low(1) and high(3) debugging.
# TODO: Place restrictions on methods?
# TODO: Potential bugs for keys with empty list values {'key': []} will not produce a custom state?

import datetime
import re
import subprocess
import time as t
import sys

import flatdict
import simplejson

import indigoPluginUpdateChecker
import iterateXML

try:
    import pydevd  # To support remote debugging
except ImportError as error:
    pass

try:
    import indigo
except:
    pass

__author__    = "DaveL17, GlennNZ, howartp"
__build__     = ""
__copyright__ = 'There is no copyright for the GhostXML code base.'
__license__   = "MIT"
__title__     = 'Bike Share Plugin for Indigo Home Control'
__version__   = '0.3.09'

# Establish default plugin prefs; create them if they don't already exist.
kDefaultPluginPrefs = {
    u'configMenuPollInterval': "300",  # Frequency of refreshes.
    u'configMenuServerTimeout': "15",  # Server timeout limit.
    u'refreshFreq': 300,  # Device-specific update frequency
    u'showDebugInfo': False,  # Verbose debug logging?
    u'showDebugLevel': "1",  # Low, Medium or High debug output.
    u'updaterEmail': "",  # Email to notify of plugin updates.
    u'updaterEmailsEnabled': False  # Notification of plugin updates wanted.
}


class Plugin(indigo.PluginBase):
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        indigo.server.log(u"")
        indigo.server.log(u"{0:=^130}".format(" Initializing New Plugin Session "))
        indigo.server.log(u"{0:<31} {1}".format("Plugin name:", pluginDisplayName))
        indigo.server.log(u"{0:<31} {1}".format("Plugin version:", pluginVersion))
        indigo.server.log(u"{0:<31} {1}".format("Plugin ID:", pluginId))
        indigo.server.log(u"{0:<31} {1}".format("Indigo version:", indigo.server.version))
        indigo.server.log(u"{0:<31} {1}".format("Python version:", sys.version.replace('\n', '')))
        indigo.server.log(u"{0:=^130}".format(""))

        self.debug = self.pluginPrefs.get('showDebugInfo', False)
        self.debugLevel = self.pluginPrefs.get('showDebugLevel', 1)
        self.deviceNeedsUpdated = ''
        self.logFile = u"{0}/Logs/com.fogbert.indigoplugin.GhostXML/plugin.log".format(indigo.server.getInstallFolderPath())
        self.prefServerTimeout = int(self.pluginPrefs.get('configMenuServerTimeout', "15"))
        updater_url = "http://indigodomotics.github.io/GhostXML/ghostXML_version.html"
        self.updater = indigoPluginUpdateChecker.updateChecker(self, updater_url)
        self.updaterEmailsEnabled = self.pluginPrefs.get('updaterEmailsEnabled', False)

        # Adding support for remote debugging in PyCharm. Other remote debugging facilities can be added, but only one can be run at a time.
        # pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True, suspend=False)  # To enable remote PyCharm Debugging, uncomment this line.

        # Convert old debugLevel scale to new scale if needed.
        # =============================================================
        if not isinstance(self.pluginPrefs['showDebugLevel'], int):
            if self.pluginPrefs['showDebugLevel'] == "High":
                self.pluginPrefs['showDebugLevel'] = 3
            elif self.pluginPrefs['showDebugLevel'] == "Medium":
                self.pluginPrefs['showDebugLevel'] = 2
            else:
                self.pluginPrefs['showDebugLevel'] = 1

    def __del__(self):
        if self.debugLevel >= 2:
            self.debugLog(u"__del__ method called.")
        indigo.PluginBase.__del__(self)

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if self.debugLevel >= 2:
            self.debugLog(u"closedPrefsConfigUi() method called.")

        if userCancelled:
            self.debugLog(u"User prefs dialog cancelled.")

        if not userCancelled:
            self.debug = valuesDict.get('showDebugInfo', False)
            self.debugLevel = self.pluginPrefs.get('showDebugLevel', "1")
            self.debugLog(u"User prefs saved.")

            if self.debug:
                indigo.server.log(u"Debugging on (Level: {0})".format(self.debugLevel))
            else:
                indigo.server.log(u"Debugging off.")

            if int(self.pluginPrefs['showDebugLevel']) >= 3:
                self.debugLog(u"valuesDict: {0} ".format(valuesDict))

        return True

    # Start 'em up.
    def deviceStartComm(self, dev):
        if self.debugLevel >= 2:
            self.debugLog(u"deviceStartComm() method called.")
        indigo.server.log(u"Starting GhostXML device: " + dev.name)
        dev.stateListOrDisplayStateIdChanged()
        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Enabled")

    # Shut 'em down.
    def deviceStopComm(self, dev):
        if self.debugLevel >= 2:
            self.debugLog(u"deviceStopComm() method called.")
        indigo.server.log(u"Stopping GhostXML device: " + dev.name)
        dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="Disabled")
        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    def runConcurrentThread(self):
        # TODO: note that I disabled several self.debugLog entries in runConcurrentThread() because they will flood the log with entries every five seconds.
        if self.debugLevel >= 2:
            self.debugLog(u"indigoPluginUpdater() method called.")

        self.sleep(5)

        try:
            while True:
                self.updater.checkVersionPoll()

                # self.debugLog(u" ")

                for dev in indigo.devices.itervalues(filter="self"):

                    # self.debugLog(u"{0}:".format(dev.name))  # DaveL17: I commented out this line so that it didn't print to the log every 5 seconds.

                    if "deviceTimestamp" in dev.states.iterkeys():
                        if dev.states["deviceTimestamp"] == "":
                            self.fixErrorState(dev)

                        if int(dev.pluginProps.get("refreshFreq", 300)) == 0:
                            self.debugLog(u"    Refresh frequency: {0} (Manual refresh only)".format(dev.pluginProps["refreshFreq"]))

                        else:
                            t_since_upd = int(t.time() - float(dev.states["deviceTimestamp"]))

                            # self.debugLog(u"    Time since update: {0}".format(t_since_upd))  # DaveL17: I commented out this line so that it didn't print to the log every 5 seconds.

                            if int(t_since_upd) > int(dev.pluginProps.get("refreshFreq", 300)):

                                self.debugLog(u"Time since update ({0}) is greater than configured frequency ({1})".format(t_since_upd, dev.pluginProps["refreshFreq"]))

                                self.refreshDataForDev(dev)

                    else:
                        self.fixErrorState(dev)

                self.sleep(5)

        except self.StopThread:
            self.debugLog(u'Fatal error. Stopping GhostXML thread.')
            pass

    def shutdown(self):
        if self.debugLevel >= 2:
            self.debugLog(u"shutdown() method called.")

    def startup(self):
        if self.debugLevel >= 2:
            self.debugLog(u"Starting GhostXML. startup() method called.")

        # See if there is a plugin update and whether the user wants to be notified.
        try:
            self.updater.checkVersionPoll()
        except Exception as error:
            self.errorLog(u"Update checker error: {0}".format(error))

    def validatePrefsConfigUi(self, valuesDict):
        if self.debugLevel >= 2:
            self.debugLog(u"validatePrefsConfigUi() method called.")

        error_msg_dict = indigo.Dict()
        update_email = valuesDict['updaterEmail']
        update_wanted = valuesDict['updaterEmailsEnabled']

        # Test plugin update notification settings.
        try:
            if update_wanted and not update_email:
                error_msg_dict['updaterEmail'] = u"If you want to be notified of updates, you must supply an email address."
                error_msg_dict['showAlertText'] = u"Updater Email Error:\n\nThe plugin requires a valid email address in order to notify of plugin updates."
                return False, valuesDict, error_msg_dict

            elif update_wanted and "@" not in update_email:
                error_msg_dict['updaterEmail'] = u"Valid email addresses have at least one @ symbol in them (foo@bar.com)."
                error_msg_dict['showAlertText'] = u"Updater Email Error:\n\nThe plugin requires a valid email address in order to notify of plugin updates (email address must contain an '@' sign."

                return False, valuesDict, error_msg_dict

        except Exception as error:
            self.errorLog(u"Plugin configuration error: {0}".format(error))

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
        except Exception as error:
            self.errorLog(u"Update checker error: {0}".format(error))

    def killAllComms(self):
        """ killAllComms() sets the enabled status of all plugin devices to
        false. """

        for dev in indigo.devices.itervalues("self"):
            try:
                indigo.device.enable(dev, value=False)
            except Exception as error:
                self.debugLog(u"Exception when trying to kill all comms. Error: {0} (Line {1})".format(error))

    def unkillAllComms(self):
        """ unkillAllComms() sets the enabled status of all plugin devices to
        true. """

        for dev in indigo.devices.itervalues("self"):
            try:
                indigo.device.enable(dev, value=True)
            except Exception as error:
                self.debugLog(u"Exception when trying to unkill all comms. Error: {0} (Line {1})".format(error))

    def fixErrorState(self, dev):
        self.deviceNeedsUpdated = False
        dev.stateListOrDisplayStateIdChanged()
        update_time = t.strftime("%m/%d/%Y at %H:%M")
        dev.updateStateOnServer('deviceLastUpdated', value=update_time)
        dev.updateStateOnServer('deviceTimestamp', value=t.time())
        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Enabled")

    def getDeviceStateList(self, dev):
        """
        The getDeviceStateList() method pulls out all the keys in
        self.finalDict and assigns them to device states. It returns the
        modified stateList which is then written back to the device in
        the main thread. This method is automatically called by

            stateListOrDisplayStateIdChanged()

        and by Indigo when Triggers and Control Pages are built.
        """
        if self.debugLevel >= 2:
            self.debugLog(u"getDeviceStateList() method called.")

        if self.deviceNeedsUpdated:
            # This statement goes out and gets the existing state list for dev.
            self.debugLog(u"Pulling down existing state list.")
            state_list = indigo.PluginBase.getDeviceStateList(self, dev)

            if state_list is not None:

                # Iterate the tags in final_dict into device state keys.
                self.debugLog(u"  Writing dynamic states to device.")
                for key in self.finalDict.iterkeys():
                    # Example: dynamic_state =
                    # self.getDeviceStateDictForStringType(key, u'Trigger Test Label', u'State Label')
                    dynamic_state = self.getDeviceStateDictForStringType(key, key, key)
                    state_list.append(dynamic_state)

            ###########################
            # ADDED BY DaveL17 12/26/16
            # Inspect existing state list to new one to see if the state list needs to be updated.
            # If it doesn't, we can save some effort here.
            interim_state_list = [thing['Key'] for thing in state_list]
            for thing in [u'deviceIsOnline', u'deviceLastUpdated', ]:
                interim_state_list.remove(thing)
            self.debugLog(unicode(interim_state_list))  # existing states
            self.debugLog(unicode(self.finalDict.keys()))  # new states
            self.debugLog(unicode(set(interim_state_list) == set(self.finalDict.keys())))  # compare existing states to new ones
            #
            # END DaveL17 changes
            ###########################

            ###########################
            # ADDED BY howartp 18/06/16
            # Resolves issue with deviceIsOnline and deviceLastUpdated states disappearing if there's a fault
            # in the JSON data we receive, as state_list MUST contain all desired states when it returns

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

            # Iterate the device states into trigger and control page labels when the device is called.
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
        """
        if self.debugLevel >= 2:
            self.debugLog(u"getTheData() method called.")

        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Download")
        try:
            # Initiate curl call to data source.
            url = dev.pluginProps['sourceXML']

            ###########################
            # ADDED BY howartp 18/06/16
            # Allows substitution of variable or device states into URL using a
            #  user-friendly  version of the builtin Indigo substitution
            #  mechanism

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
                ###########################
                # ADDED BY GlennNZ 28.11.16, moved by DaveL17 11/28/2016.
                # use Digest Username and Password if enabled will need devices
                #  open and resaved ?could add check

                username = dev.pluginProps.get('digestUser', '')
                password = dev.pluginProps.get('digestPass', '')

                proc = subprocess.Popen(["curl", '-vs', '--digest', '-u', username + ':' + password, url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                proc = subprocess.Popen(["curl", '-vs', url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (result, err) = proc.communicate()

            if err:
                if proc.returncode == 6:

                    f = open(self.logFile, 'a')
                    f.write("{0} - Curl Return Code: {1}\n{2} \n".format(datetime.datetime.time(datetime.datetime.now()), proc.returncode, err))
                    f.close()

                    self.errorLog(u"Error: Could not resolve host. Possible causes:")
                    self.errorLog(u"  The data service is offline.")
                    self.errorLog(u"  Your Indigo server can not reach the Internet.")
                    self.errorLog(u"  Your plugin is mis-configured.")
                    self.debugLog(err)

                elif err is not 0:
                    self.debugLog(err)

                else:
                    pass

            return result

        except Exception as error:

            self.errorLog(u"{0} - Error getting source data: {1}. Skipping until next scheduled poll.".format(dev.name, unicode(error)))
            self.debugLog(u"Device is offline. No data to return. Returning dummy dict.")
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No comm")
            result = ""
            return result

    def cleanTheKeys(self, input_data):
        # Some dictionaries may have keys that contain problematic characters which Indigo doesn't like as state names.
        # Let's get those characters out of there.
        try:
            ###########################
            # Added by DaveL17 on 11/25/2016.
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

            # Some characters can simply be eliminated. If something here causes problems, remove the element from the
            # set and add it to the replacement dict above.
            chars_to_remove = set(['/', '(', ')'])
            for key in input_data.iterkeys():
                new_key = ''.join([c for c in key if c not in chars_to_remove])
                input_data[new_key] = input_data.pop(key)

            ###########################
            # Added by DaveL17 on 11/28/2016.
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
            
        except Exception as error:
            self.errorLog(u'Error cleaning dictionary keys: {0}'.format(error))

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
            # self.errorLog(unicode(parsed_simplejson))
            if self.debugLevel >= 2:
                self.debugLog("Prior to FlatDict Running Json")
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
                    self.debugLog("List Detected - Flattening to Dict")
                parsed_simplejson = dict(("No_" + str(i), v) for (i, v) in enumerate(parsed_simplejson))
            if self.debugLevel >= 2:    
                self.debugLog("After List Check, Before FlatDict Running Json")

            self.jsonRawData = flatdict.FlatDict(parsed_simplejson, delimiter='_ghostxml_')

            if self.debugLevel >= 2:
                self.debugLog(self.jsonRawData)
            return self.jsonRawData
        except Exception as error:
            self.errorLog(dev.name + ": " + unicode(error))

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
                    self.debugLog(u"   {0} = {1}".format(unicode(key), unicode(self.finalDict[key])))
                dev.updateStateOnServer(unicode(key), value=unicode(self.finalDict[key]))
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                dev.updateStateOnServer('deviceIsOnline', value=True, uiValue=" ")

            except Exception as error:
                self.errorLog(u"Error parsing key/value pair: {0} = {1}. Reason: {2}".format(unicode(key), unicode(self.finalDict[key]), error))
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
        The refreshData() method controls the updating of all plugin
        devices.
        """
        if self.debugLevel >= 2:
            self.debugLog(u"refreshData() method called.")

        try:
            # Check to see if there have been any devices created.
            if indigo.devices.itervalues(filter="self"):
                self.debugLog(u"Updating data...")

                for dev in indigo.devices.itervalues(filter="self"):
                    self.refreshDataForDev(dev)

            else:
                indigo.server.log(u"No GhostXML devices have been created.")

            return True

        except Exception as error:
            self.errorLog(u"Error refreshing devices. Please check settings.")
            self.errorLog(unicode(error))
            return False

    def refreshDataForDev(self, devId):

        dev = indigo.devices[devId]

        ###########################
        # ADDED BY howartp 18/06/16
        # This was previously all inside refreshData() function Separating it out allows devices
        # to be refreshed individually
        if dev.configured:
            self.debugLog(u"Found configured device: {0}".format(dev.name))

            if dev.enabled:
                self.debugLog(u"   {0} is enabled.".format(dev.name))

                # Get the data.
                self.debugLog(u"Refreshing device: {0}".format(dev.name))
                self.rawData = self.getTheData(dev)

                # Throw the data to the appropriate module to flatten it.
                dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Processing")
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

                    update_time = t.strftime("%m/%d/%Y at %H:%M")
                    dev.updateStateOnServer('deviceLastUpdated', value=update_time)
                    dev.updateStateOnServer('deviceTimestamp', value=t.time())
                    dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Enabled")
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
        The refreshDataForDevAction() method refreshes data for a selected device based on
        a plugin action call.
        """
        if self.debugLevel >= 2:
            self.debugLog(u"refreshDataForDevAction() method called.")

        dev = indigo.devices[valuesDict.deviceId]

        self.refreshDataForDev(dev)
        return True

    def stopSleep(self, start_sleep):
        """
        The stopSleep() method accounts for changes to the user upload interval
        preference. The plugin checks every 2 seconds to see if the sleep
        interval should be updated.
        """
        try:
            total_sleep = float(self.pluginPrefs.get('configMenuUploadInterval', 300))
        except:
            total_sleep = iTimer  # TODO: Note variable iTimer is an unresolved reference.
                                  # howartp: I think the try/except block could simply be removed since the self.pluginPrefs.get()
                                  # statement will set the value to 300 if there's value available.  Suggest that fix.  DaveL17
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

        except Exception as error:
            self.errorLog(u"{0} - Error parsing source data: {1}. Skipping until next scheduled poll.".format(dev.name, unicode(error)))
            self.rawData = '<?xml version="1.0" encoding="UTF-8"?><Emptydict><Response>No data to return.</Response></Emptydict>'
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No data")
            return self.rawData

    def toggleDebugEnabled(self):
        """
        Toggle debug on/off.
        """
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
