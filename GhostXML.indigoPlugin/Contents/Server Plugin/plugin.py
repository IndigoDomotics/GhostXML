#! /usr/bin/env python2.5
# -*- coding: utf-8 -*-

"""
GhostXML Plugin
Author: See (repo)

This plugin provides an engine which parses tag/value pairs into
transitive Indigo plugin device states.
"""

import datetime
import flatdict
import indigoPluginUpdateChecker
import iterateXML
import re
import simplejson
import subprocess
import time as t

# Establish default plugin prefs; create them if they don't already exist.
kDefaultPluginPrefs = {
    u'configMenuPollInterval': "300",  # Frequency of refreshes.
    u'configMenuServerTimeout': "15",  # Server timeout limit.
    u'showDebugInfo': False,           # Verbose debug logging?
    u'showDebugLevel': "1",            # Low, Medium or High debug output.
    u'updaterEmail': "",               # Email to notify of plugin updates.
    u'updaterEmailsEnabled': False     # Notification of plugin updates wanted.
}


class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.debugLog(u"Initializing GhostXML plugin.")

        self.debug                = self.pluginPrefs.get('showDebugInfo', False)
        self.debugLevel           = self.pluginPrefs.get('showDebugLevel', "1")
        self.deviceNeedsUpdated   = ''
        self.prefPollInterval     = int(self.pluginPrefs.get('configMenuPollInterval', "300"))
        self.prefServerTimeout    = int(self.pluginPrefs.get('configMenuServerTimeout', "15"))
        self.updater              = indigoPluginUpdateChecker.updateChecker(self, "http://indigodomotics.github.io/GhostXML/ghostXML_version.html")
        self.updaterEmailsEnabled = self.pluginPrefs.get('updaterEmailsEnabled', False)

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
                indigo.server.log(u"Debugging on (Level: %s)" % self.debugLevel)
            else:
                indigo.server.log(u"Debugging off.")

            if int(self.pluginPrefs['showDebugLevel']) >= 3:
                self.debugLog(u"valuesDict: %s " % unicode(valuesDict))

        return True

    # Start 'em up.
    def deviceStartComm(self, dev):
        if self.debugLevel >= 2:
            self.debugLog(u"deviceStartComm() method called.")
        indigo.server.log(u"Starting GhostXML device: " + dev.name)
        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Enabled")

    # Shut 'em down.
    def deviceStopComm(self, dev):
        if self.debugLevel >= 2:
            self.debugLog(u"deviceStopComm() method called.")
        indigo.server.log(u"Stopping GhostXML device: " + dev.name)
        dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="Disabled")

    def shutdown(self):
        if self.debugLevel >= 2:
            self.debugLog(u"shutdown() method called.")

    def startup(self):
        if self.debugLevel >= 2:
            self.debugLog(u"Starting GhostXML. startup() method called.")

        # See if there is a plugin update and whether the user wants to be notified.
        try:
            self.updater.checkVersionPoll()
        except Exception, e:
            self.errorLog(u"Update checker error: %s" % e)

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
            self.debugLog(u"Debug level: %s" % self.debugLevel)

        else:
            self.debug = False
            self.pluginPrefs['showDebugInfo'] = False
            indigo.server.log(u"Debugging off.")

    def validatePrefsConfigUi(self, valuesDict):
        if self.debugLevel >= 2:
            self.debugLog(u"validatePrefsConfigUi() method called.")

        errorMsgDict = indigo.Dict()
        updateEmail = valuesDict['updaterEmail']
        updateWanted = valuesDict['updaterEmailsEnabled']

        # Test plugin update notification settings.
        try:
            if updateWanted and not updateEmail:
                errorMsgDict['updaterEmail'] = u"If you want to be notified of updates, you must supply an email address."
                return (False, valuesDict, errorMsgDict)

            elif updateWanted and "@" not in updateEmail:
                errorMsgDict['updaterEmail'] = u"Valid email addresses have at leat one @ symbol in them (foo@bar.com)."

                return (False, valuesDict, errorMsgDict)

        except Exception, e:
            self.errorLog(u"Plugin configuration error: %s" % e)

        return (True, valuesDict)

    def checkVersionNow(self):
        """
        The checkVersionNow() method is called if user selects "Check
        For Plugin Updates..." Indigo menu item.
        """
        if self.debugLevel >= 2:
            self.debugLog(u"checkVersionNow() method called.")
        try:
            self.updater.checkVersionPoll()
        except Exception, e:
            self.errorLog(u"Update checker error: %s" % e)

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
            stateList = indigo.PluginBase.getDeviceStateList(self, dev)

            if stateList is not None:

                # Iterate the tags in finalDict into device state keys.
                self.debugLog(u"  Writing dynamic states to device.")
                for key in self.finalDict.iterkeys():

                    # Example: dynamicState =
                    # self.getDeviceStateDictForStringType(key, u'Trigger Test Label', u'State Label')
                    dynamicState = self.getDeviceStateDictForStringType(key, key, key)
                    stateList.append(dynamicState)

            self.deviceNeedsUpdated = False
            self.debugLog(u"Device needs updating set to: %s" % self.deviceNeedsUpdated)

            return stateList

        else:
            self.debugLog(u"Device has been updated. Blow state list up to Trigger and Control Page labels.")
            stateList = indigo.PluginBase.getDeviceStateList(self, dev)

            # Iterate the device states into trigger and control page
            # labels when the device is called.
            for state in dev.states:
                dynamicState = self.getDeviceStateDictForStringType(state, state, state)
                stateList.append(dynamicState)

            return stateList

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
            proc = subprocess.Popen(["curl", '-vs', url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (result, err) = proc.communicate()

            if err:
                if proc.returncode == 6:

                    f = open(self.logFile, 'a')
                    f.write(u"%s - Curl Return Code: %s\n%s \n" % (datetime.datetime.time(datetime.datetime.now()), proc.returncode, err))
                    f.close

                    self.errorLog(u"Error: Could not resolve host. Possible causes:")
                    self.errorLog(u"  The data service is offline.")
                    self.errorLog(u"  Your Indigo server can not reach the Internet.")
                    self.errorLog(u"  Your plugin is misconfigured.")
                    self.debugLog(err)

                elif err != "":
                    self.debugLog(u"\n" + err)

            return result

        except Exception, e:

            self.errorLog(u"%s - Error getting source data: %s. Skipping until next scheduled poll." % (dev.name, unicode(e)))
            self.debugLog(u"Device is offline. No data to return. Returning dummy dict.")
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No comm")
            result = ""
            return result

    def parseTheJSON(self, dev, root):
        """
        The parseTheJSON() method contains the steps to convert the
        JSON file into a flat dict.

        http://github.com/gmr/flatdict
        class flatdict.FlatDict(value=None, delimiter=None, former_type=<type 'dict'>)
        """
        if self.debugLevel >= 2:
            self.debugLog(u"parseTheJSON() method called.")
        try:
            parsed_simplejson = simplejson.loads(root)
            self.jsonRawData = flatdict.FlatDict(parsed_simplejson, delimiter='_')
            return self.jsonRawData
        except Exception, e:
            self.errorLog(unicode(e))

    def stripNamespace(self, dev, root):
        """
        The stripNamespace() method strips any XML namespace values, and
        loads into self.rawData.
        """
        if self.debugLevel >= 2:
            self.debugLog(u"stripNamespace() method called.")

        try:
            if root == "":
                root = '<?xml version="1.0" encoding="UTF-8"?><Emptydict><Response>No data to return.</Response></Emptydict>'

            # Remove namespace stuff if it's in there. There's probably
            # a more comprehensive re.sub() that could be run, but it
            # also could do *too* much.
            self.rawData = ''
            self.rawData = re.sub(' xmlns="[^"]+"', '', root)
            self.rawData = re.sub(' xmlns:xsi="[^"]+"', '', self.rawData)
            self.rawData = re.sub(' xmlns:xsd="[^"]+"', '', self.rawData)
            self.rawData = re.sub(' xsi:noNamespaceSchemaLocation="[^"]+"', '', self.rawData)

            if self.debugLevel >= 3:
                self.debugLog(unicode(self.rawData))
            return self.rawData

        except Exception, e:
            self.errorLog(u"%s - Error parsing source data: %s. Skipping until next scheduled poll." % (dev.name, unicode(e)))
            self.rawData = '<?xml version="1.0" encoding="UTF-8"?><Emptydict><Response>No data to return.</Response></Emptydict>'
            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="No data")
            return self.rawData

    def parseStateValues(self, dev):
        """
        The parseStateValues() method walks through the dict and
        assigns the corresponding value to each device state.
        """
        if self.debugLevel >= 2:
            self.debugLog(u"parseStateValues() method called.")

        self.debugLog(u"Writing device states:")
        sorted_list = sorted(self.finalDict.iterkeys())
        for key in sorted_list:
            try:
                if self.debugLevel >= 3:
                    self.debugLog(u"   %s = %s" % (unicode(key), unicode(self.finalDict[key])))
                dev.updateStateOnServer(unicode(key), value=unicode(self.finalDict[key]))
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                dev.updateStateOnServer('deviceIsOnline', value=True, uiValue=" ")

            except Exception, e:
                self.errorLog("Error parsing key/value pair: %s = %s. Reason: %s" % (unicode(key), unicode(self.finalDict[key]), e))
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Error")

    def refreshDataAction(self, valuesDict):
        """
        The refreshDataAction() method refreshes data for all devices
        based on a plugin menu call.
        """
        if self.debugLevel >= 2:
            self.debugLog(u"refreshDataAction() method called.")
        self.refreshData()
        return True

    def refreshData(self):
        """
        The refreshData() method is controls the updating of all
        plugin devices.
        """
        if self.debugLevel >= 2:
            self.debugLog(u"refreshData() method called.")

        try:
            # Check to see if there have been any devices created.
            if indigo.devices.itervalues(filter="self"):
                self.debugLog(u"Updating data...")

                for dev in indigo.devices.itervalues(filter="self"):

                    if dev.configured:
                        self.debugLog(u"Found configured device: %s" % dev.name)

                        if dev.enabled:
                            self.debugLog(u"   %s is enabled." % dev.name)

                            # Get the data.
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

                            else:
                                indigo.server.log(u"%s: The plugin only supports XML and JSON data sources." % dev.name)

                            # Create the device states.
                            self.deviceNeedsUpdated = True
                            self.debugLog(u"Device needs updating set to: %s" % self.deviceNeedsUpdated)
                            dev.stateListOrDisplayStateIdChanged()

                            # Put the final values into the device states.
                            self.parseStateValues(dev)

                            update_time = t.strftime("%m/%d/%Y at %H:%M")
                            dev.updateStateOnServer('deviceLastUpdated', value=update_time)
                            self.debugLog(u"%s updated." % dev.name)

                        else:
                            self.debugLog(unicode('    Disabled: %s' % dev.name))

            else:
                indigo.server.log(u"No GhostXML devices have been created.")

            return True

        except Exception, e:
            self.errorLog(u"Error refreshing devices. Please check settings.")
            self.errorLog(str(e))
            return False

    def stopSleep(self, startSleep):
        '''
        The stopSleep() method accounts for changes to the user
        upload interval preference. The plugin checks every 2 seconds
        to see if the sleep interval should be updated.
        '''
        try:
            # We subtract an additional 5 seconds to account for the 5
            # second sleep at the start of runConcurrentThread.
            totalSleep = float(self.pluginPrefs.get('configMenuUploadInterval', 300)) - 6
        except:
            totalSleep = iTimer
        if t.time() - startSleep > totalSleep:
            return True
        return False

    def runConcurrentThread(self):
        if self.debugLevel >= 2:
            self.debugLog(u"indigoPluginUpdater() method called.")


        try:
            while True:
                self.sleep(5)
                self.updater.checkVersionPoll()
                self.refreshData()

                startSleep = t.time()
                while True:
                    if self.stopSleep(startSleep):
                        break
                    self.sleep(2)

        except self.StopThread:
            self.debugLog(u'Fatal error. Stopping GhostXML thread.')
            pass
