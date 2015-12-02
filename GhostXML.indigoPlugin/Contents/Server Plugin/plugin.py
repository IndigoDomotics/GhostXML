#! /usr/bin/env python2.5
# -*- coding: utf-8 -*-

"""
GhostXML Plugin
Author: See (repo)

This plugin provides an XML engine which parses tag/value pairs into
Indigo plugin device states.
"""

import time
import indigoPluginUpdateChecker
import iterateXML
import re
import socket
import urllib2

# Establish default plugin prefs; create them if they don't already
# exist.
kDefaultPluginPrefs = {
    u'configMenuPollInterval': "300",  # Frequency of refreshes.
    u'configMenuServerTimeout': "15",  # Server timeout limit.
    u'showDebugInfo': False,  # Verbose debug logging?
    u'showDebugLevel': "Low",  # Low, Medium or High debug output.
    u'updaterEmail': "",  # Email to notify of plugin updates.
    u'updaterEmailsEnabled': False  # Notification of plugin updates wanted.
    }


class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.debugLog(u"Initializing OWServer plugin.")

        self.debug = (self.pluginPrefs.get('showDebugInfo', False))
        self.debugLevel = (self.pluginPrefs.get('showDebugLevel', "Low"))
        self.deviceNeedsUpdated = ('')
        self.prefPollInterval = (int(self.pluginPrefs.get('configMenuPollInterval', 300)))
        self.prefServerTimeout = (int(self.pluginPrefs.get('configMenuServerTimeout', 15)))
        self.updater = (indigoPluginUpdateChecker.updateChecker(self, "http://indigodomotics.github.io/GhostXML/ghostXML_version.html"))
        self.updaterEmailsEnabled = (self.pluginPrefs.get('updaterEmailsEnabled', False))

    def __del__(self):
        self.debugLog(u"__del__ method called.")
        indigo.PluginBase.__del__(self)

    def startup(self):
        self.debugLog(u"Starting GhostXML.  startup() method called.")

        # See if there is a plugin update and whether the user wants to
        # be notified.
        try:
            self.updater.checkVersionPoll()

        except Exception, e:
            self.errorLog(u"Update checker error: %s" % e)

    # Start 'em up.
    def deviceStartComm(self, dev):
        self.debugLog(u"deviceStartComm() method called.")
        indigo.server.log(u"Starting GhostXML device: " + dev.name)
        dev.updateStateOnServer('deviceIsOnline', value=True, uiValue="Enabled")

    # Shut 'em down.
    def deviceStopComm(self, dev):
        self.debugLog(u"deviceStopComm() method called.")
        indigo.server.log(u"Stopping GhostXML device: " + dev.name)
        dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="Disabled")

    def shutdown(self):
        self.debugLog(u"shutdown() method called.")
        self.debugLog(u"Shutting down GhostXML plugin.")

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.debugLog(u"closedPrefsConfigUi() method called.")

        if userCancelled:
            self.debugLog(u"User prefs dialog cancelled.")

        if not userCancelled:
            self.debug = valuesDict.get('showDebugInfo', False)
            self.debugLog(u"User prefs saved.")

            if self.debug:
                indigo.server.log(u"Debugging on (Level: %s)" % self.debugLevel)
            else:
                indigo.server.log(u"Debugging off.")

            if self.pluginPrefs['showDebugLevel'] == "High":
                self.debugLog(u"valuesDict: %s " % unicode(valuesDict))

        return True

    def toggleDebugEnabled(self):
        # Toggle debug on/off.
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

    def validatePrefsConfigUi(self, valuesDict, dev):
        self.debugLog(u"validatePrefsConfigUi() method called.")

        errorMsgDict = indigo.Dict()
        updateEmail = valuesDict['updaterEmail']
        updateWanted = valuesDict['updaterEmailsEnabled']

        # Test plugin update notification settings.
        try:
            if updateWanted and not updateEmail:
                errorMsgDict['updaterEmail'] = (
                    u"If you want to be notified of updates, you must supply "
                    "an email address.")
                return (False, valuesDict, errorMsgDict)

            elif updateWanted and "@" not in updateEmail:
                errorMsgDict['updaterEmail'] = (
                    u"Valid email addresses have at leat one @ symbol in "
                    "them (foo@bar.com).")

                return (False, valuesDict, errorMsgDict)

        except Exception, e:
            self.errorLog(u"Plugin configuration error: %s" % e)

        return (True, valuesDict)

    def checkVersionNow(self):
        # Called if user selects "Check For Plugin Updates..."
        # Indigo menu item.
        self.debugLog(u"checkVersionNow() method called.")
        self.updater.checkVersionNow()

    def getDeviceStateList(self, dev):
        """
        This method pulls out all the keys in self.xmlDict and assigns
        them to device states. It returns the modified stateList which
        is then written back to the device in the main thread. This
        method is automatically called by

                stateListOrDisplayStateIdChanged()

        and by Indigo when Triggers and Control Pages are built.
        """
        self.debugLog(u"getDeviceStateList() method called.")

        if self.deviceNeedsUpdated:

            # This statement goes out and gets the existing state list
            # for dev.
            self.debugLog(u"Pulling down existing state list.")
            stateList = indigo.PluginBase.getDeviceStateList(self, dev)

            if stateList is not None:

                # Iterate the XML tags in xmlDict into device state
                # keys.
                self.debugLog(u"  Writing dynamic states to device.")
                for key in self.xmlDict.iterkeys():

                    # Example: dynamicState =
                    # self.getDeviceStateDictForStringType(key, u'Trigger Test Label', u'State Label')
                    dynamicState = (self.getDeviceStateDictForStringType(key, key, key))
                    stateList.append(dynamicState)

            self.deviceNeedsUpdated = False
            self.debugLog(u"Device needs updating set to: %s" % self.deviceNeedsUpdated)

            return stateList

        else:
            self.debugLog(
                u"Device has been updated. Blow state list up to Trigger and "
                "Control Page labels.")
            stateList = indigo.PluginBase.getDeviceStateList(self, dev)

            # Iterate the device states into trigger and control page
            # labels when the device is called.
            for state in dev.states:

                dynamicState = (self.getDeviceStateDictForStringType(state, state, state))
                stateList.append(dynamicState)

            return stateList

    def getXML(self, dev, xmlAddress):
        """
        This method reaches out to the specified location, pulls down
        the XML data, strips any XML namespace values, and loads it
        into self.xmlRawData
        """
        self.debugLog(u"getXML() method called.")

        if not xmlAddress:
            self.errorLog(u"GhostXML requires a valid XML source file to do its job.")
            self.errorLog(u"Please create a device and enter an XML source to continue.")

        else:
            self.debugLog(u"Grabbing XML data...")
            self.debugLog(u"=========================================")
            self.debugLog(u"XML source: %s" % xmlAddress)

            try:
                socket.setdefaulttimeout(self.prefServerTimeout)
                f = urllib2.urlopen(xmlAddress)
                root = str(f.read())
                f.close()

                # Remove namespace stuff if it's in there. There's
                # probably a more comprehensive re.sub() that could be
                # run, but it also could do *too* much. Think about
                # moving this to the iterateXML module.
                self.xmlRawData = ''
                self.xmlRawData = re.sub(' xmlns="[^"]+"', '', root)
                self.xmlRawData = re.sub(' xmlns:xsi="[^"]+"', '', self.xmlRawData)
                self.xmlRawData = re.sub(' xmlns:xsd="[^"]+"', '', self.xmlRawData)
                self.xmlRawData = re.sub(' xsi:noNamespaceSchemaLocation="[^"]+"', '', self.xmlRawData)

                self.debugLog(u"%s - file retrieved." % dev.name)
                dev.updateStateOnServer('deviceIsOnline', value=True, uiValue=" ")
                self.debugLog(u"Returning self.xmlRawData:")
                self.debugLog(unicode(self.xmlRawData))
                return self.xmlRawData

            except urllib2.HTTPError, e:
                dev.updateStateOnServer('deviceIsOnline', value=False, uiValue=" ")

                self.errorLog(
                    u"%s - HTTP error getting source data. %s. Skipping until "
                    "next scheduled poll." % (dev.name, unicode(e)))
                self.debugLog(
                    u"Device is offline. No XML to return. Returning dummy "
                    "dict:")
                self.xmlRawData = (
                    '<?xml version="1.0" encoding="UTF-8"?>''<Emptydict>'
                    '<Response>No XML to return.</Response></Emptydict>')
                return self.xmlRawData

            except Exception, e:
                dev.updateStateOnServer('deviceIsOnline', value=False, uiValue=" ")

                self.errorLog(
                    u"%s - Error getting source data: %s. Skipping until next "
                    "scheduled poll." % (dev.name, unicode(e)))
                self.debugLog(
                    u"Device is offline. No XML to return. Returning dummy "
                    "dict.")
                if 'Connection refused' in unicode(e):
                    self.xmlRawData = (
                        '<?xml version="1.0" encoding="UTF-8"?><Emptydict>'
                        '<Response>Connection refused.</Response></Emptydict>')
                elif 'Network is unreachable' in unicode(e):
                    self.xmlRawData = (
                        '<?xml version="1.0" encoding="UTF-8"?><Emptydict>'
                        '<Response>Network is unreachable.</Response>'
                        '</Emptydict>')
                else:
                    self.xmlRawData = (
                        '<?xml version="1.0" encoding="UTF-8"?><Emptydict>'
                        '<Response>No XML to return.</Response></Emptydict>')

                return self.xmlRawData

    def parseXMLStateValues(self, dev):
        """
        This method walks through the XML dict and assigns the
        corresponding value to each device state.
        """
        self.debugLog(u"parseXMLStateValues() method called.")

        self.debugLog(u"Writing device states:")
        sorted_list = sorted(self.xmlDict.iterkeys())
        for key in sorted_list:
            try:
                self.debugLog(u"   %s = %s" % (unicode(key), unicode(self.xmlDict[key])))
                dev.updateStateOnServer(unicode(key), value=unicode(self.xmlDict[key]))

            except Exception, e:
                self.errorLog("Error parsing key/value pair: %s = %s. Reason: %s" %
                              (unicode(key), unicode(self.xmlDict[key]), e))

    def refreshDataAction(self, valuesDict):
        """
        The  refreshDataAction() method refreshes data for all devices
        based on a plugin menu call. Note that the code in this method
        is generally the same as runConcurrentThread(). Changes
        reflected there may need to be added here as well.
        """
        self.debugLog(u"refreshDataAction() method called.")

        self.refreshDataMenu()

        return True

    def refreshDataMenu(self):
        self.debugLog(u"refreshDataMenu() method called.")

        try:

            # Check to see if there have been any devices created.
            if indigo.devices.itervalues(filter="self"):
                self.debugLog(u"Updating GhostXML data...")

                for dev in indigo.devices.itervalues(filter="self"):

                    if dev.configured:
                        self.debugLog(u"Found configured device: %s" % dev.name)

                        if dev.enabled:
                            self.debugLog(u"   %s is enabled." % dev.name)

                            # Get the xml from the location from the
                            # device props.
                            self.getXML(dev, dev.pluginProps['sourceXML'])

                            # Throw the xml to the iterateXML module to do
                            # some stuff.
                            self.debugLog(u"iterateXML() module called.")
                            self.xmlDict = (iterateXML.iterateMain(self.xmlRawData))

                            self.deviceNeedsUpdated = True
                            self.debugLog(u"Device needs updating set to: %s" % self.deviceNeedsUpdated)
                            dev.stateListOrDisplayStateIdChanged()

                            # Put the final key/value pairs into device
                            # states.
                            self.parseXMLStateValues(dev)

                            update_time = time.strftime("%m/%d/%Y at %H:%M")
                            dev.updateStateOnServer('deviceLastUpdated', value=update_time)
                            indigo.server.log(u"%s updated." % dev.name)

                        else:
                            self.debugLog(unicode("    Disabled: %s" % dev.name))
                            dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="Disabled")

            else:
                indigo.server.log(u"No GhostXML devices have been created.")

        except self.StopThread:
            self.debugLog(u"Fatal error. Stopping GhostXML thread.")
            pass

    def runConcurrentThread(self):
        self.debugLog(u"indigoPluginUpdater() method called.")

        self.updater.checkVersionPoll()

        try:
            while True:
                self.prefPollInterval = (int(self.pluginPrefs.get('configMenuPollInterval', 300)))
                self.sleep(5)

                # Check to see if there have been any devices created.
                if indigo.devices.itervalues(filter="self"):
                    self.debugLog(u"Updating GhostXML data...")

                    for dev in indigo.devices.itervalues(filter="self"):

                        if dev.configured:
                            self.debugLog(u"Found configured device: %s" % dev.name)

                            if dev.enabled:
                                self.debugLog(u"   %s is enabled." % dev.name)

                                # Get the xml from the location from
                                # the device props.
                                self.getXML(dev, dev.pluginProps['sourceXML'])

                                # Throw the xml to the iterateXML
                                # module to do some stuff.
                                self.debugLog(u"iterateXML() module called.")

                                self.xmlDict = (iterateXML.iterateMain(self.xmlRawData))

                                self.deviceNeedsUpdated = True
                                self.debugLog(u"Device needs updating set to: %s" % self.deviceNeedsUpdated)
                                dev.stateListOrDisplayStateIdChanged()

                                # Put the final key/value pairs into
                                # device states.
                                self.parseXMLStateValues(dev)

                                update_time = time.strftime("%m/%d/%Y at %H:%M")
                                dev.updateStateOnServer('deviceLastUpdated', value=update_time)
                                self.debugLog(u"%s updated." % dev.name)

                            else:
                                self.debugLog(unicode('    Disabled: %s' % dev.name))
                                dev.updateStateOnServer('deviceIsOnline', value=False, uiValue="Disabled")

                else:

                    indigo.server.log(u"No GhostXML devices have been created.")

                self.sleep(self.prefPollInterval-5)

        except self.StopThread:
            self.debugLog(u'Fatal error. Stopping GhostXML thread.')
            pass
