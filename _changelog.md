### v2024.1.1
- Fixes bug in 2024.1.0 that caused some JSON payloads to cause the device to stick on "processing".

### v2024.1.0
- Adds menu item to Manage Plugin Devices (enable/disable select devices).
- Updates flatdict module to v4.0.0 and most recent license.
- Reduces Indigo plugin API requirement to 3.0 (latest version should be compatible with Indigo 2022.1 and later.)
- Fixes bug in device config substitutions example.
- Introduces new plugin unit tests.
- Code refinements.
 
### v2023.0.2
- Minor code refinements.
 
### v2023.0.1
- Code enhancements.

### v2022.3.3
- Fixes a bug where devices displaying an `IOError` state incorrectly report as being online.
 
### v2022.3.2
- Bumps version number.
 
### v2022.3.1
- Takes v2022.3.0 out of beta.

### v2022.3.0
- Updates most communication to use the `requests` library instead of `curl`.
- Fixes bug where debug level might not be honored on startup.
- Wiki updates. 

### v2022.2.1
- Adds foundation for API `3.2`.
- Adds some examples on how to handle filenames with spaces in them to device config dialog.
- Adds httpcodes lookup library for later use.
- Code cleanup.

### v2022.1.2
- Adds foundation for API `3.1`.

### v2022.1.2
- Adds `_to_do_list.md` and changes changelog to markdown.
- Moves plugin environment logging to plugin menu item (log only on request).
- Fixes bug where plugin device object wouldn't honor current debug logging level.

### v2022.1.1
- Ensure that a device's ID is removed from managed devices when the device is deleted (even if the device has not been
  fully configured).
- Improves error logging when WAN/LAN not present.

### v2022.0.1
- Updates plugin for Indigo 2022.1 and Python 3.
- Updates FlatDict to v4.0.0
- Standardizes Indigo method implementation.

### v0.5.15
- Code refinements

### v0.5.14
- Implements Constants.py
- Code refinements

### v0.5.13
- Better traps OS error where plugin attempts to kill a process that is no longer running.
- Debug logging refinements.

### v0.5.12
- Sync

### v0.5.11
- Removes code marked for deletion. Refer to v0.5.10 if any needs to be restored.
- Adds flat_dict_license.txt
- Updates ghostXML license.
- code refinements.

### v0.5.10
- Prepares old 'sqlLoggerIgnoreStates' that's saved to pluginProps for deletion. Should run in this state for a bit in
  case something needs to be put back.

### v0.5.09
- Fixes typo in device_start_comm.

### v0.5.08
- Fixes bug in setting to ignore SQL logging.

### v0.5.07
- Removes unneeded returns from plugin Action methods.

### v0.5.06
- Adds reminders to various curl options in comments.

### v0.5.05
- Adds curl return code definitions to provide more human-friendly reporting of curl errors.

### v0.5.04
- Refines saving of device preferences changes.

### v0.5.03
- Adds bearer authentication method.

### v0.5.02
- Adds support for raw curl substitutions.

### v0.5.01
- Adds UI for variable substitution for raw curl commands.

### v0.4.57
- Fixes bug where states for Real Type devices were returned as strings when device comm first started.

### v0.4.56
- Code refinements.

### v0.4.55
- Adds option to turn off curl globbing.

### v0.4.54
- Adds code to address tags that start with the 'illegal' @ character.

### v0.4.53
- Adds Disable SQL logging feature.

### v0.4.52
- Fixes device validation bug that precluded setting FTP source URL.

### v0.4.51
- Fixes device validation bug that precluded setting manual refresh rate.

### v0.4.50
- Fixes bug where offline JSON sources would result in a cascading key name (changing '.ui' to '_dot_ui_' with each
  plugin cycle).

### v0.4.49
- Fixes bug where a device with a parse error would not be taken offline after max retries exceeded.

### v0.4.48
- Adds wider exception trapping to plugin device object class.

### v0.4.47
- Fixes bug where devices could not be brought back from error state.

### v0.4.46
- Fixes bug where string type device still received some true type state values.

### v0.4.45
- Updates to device name in Indigo now properly reflected in self.managedDevices.

### v0.4.44
- Fixes bug that caused all secondary boolean states to be set to False.

### v0.4.42
- Implements second device type that tries to coerce custom device states that reflect the data type (bool, integer,
  float, etc.)

### v0.4.41
- Removes timeout setting in plugin preferences since timeouts are now handled within each device independently.
- Improvements to device configuration validation.
- Improved image state handling when errored device is disabled (retain the state but clear the icon).
- Code refinements.

### v0.4.40
- Widens coverage to include additional API constructions.
- Code cleanup.

### v0.4.39
- Initial deprecation of the stop_sleep() method (unused).

### v0.4.38
- Moved max retries code to its own method.

### v0.4.37
- Removes all references to legacy version checking.

### v0.4.36
- Increases compliance with PEP 8.

### v0.4.35
- Adds trigger that fires when a device has been automatically disabled by the plugin due to failed attempts.

### v0.4.34
- Bug fixes.

### v0.4.34
- Improves setting of device online status in Indigo UI.
- Bug fix (syntax error)

### v0.4.33
- Fixes key 'deviceIsOnline.ui' does not exist bug.
- Makes device state 'parse-error' a permanent state (rather than dynamically generated).

### v0.4.32
- Revises device initialization code to allow existing device states to persist when plugin is restarted.

### v0.4.31
- Adds user-configurable setting for device auto-disable feature.

### v0.4.30
- Adds sendDevicePing() trap.

### v0.4.29
- Changes logging messages to report device names instead of device IDs.

### v0.4.28
- Moves None option to bottom of dropdown lists per Indigo convention.

### v0.4.27
- Standardizes SupportURL behavior across all plugin functions.

### v0.4.26
- Ensures plugin is compatible with the Indigo server version.

### v0.4.25
- Fixes plugin configuration validation bug.

### v0.4.24
- Fixes KeyError: key updaterEmail not found in dict error.

### v0.4.23
- Synchronize self.pluginPrefs in closed_prefs_config_ui().

### v0.4.22
- Audits kDefaultPluginPrefs.

### v0.4.21
- Removes plugin update checker.

### v0.4.20
- Changes "En/Disable All Devices" to "En/Disable all Plugin Devices".

### v0.4.19
- Changes Python lists to tuples where possible to improve performance.

### v0.4.17
- Finalizes raw curl feature.

### v0.4.16
- Consolidates pulls and other changes.

### v0.4.16
- Adds raw curl support.

### v0.4.14
- When device refresh frequency set to custom level (using GhostXML Action) number of seconds is added to the refresh
  frequency menu in the device configuration UI -- i.e., "Custom" becomes "Custom (123 seconds)"
- Fixes bug that resulted in duplicate control page and trigger entries for 'deviceIsOnline', 'deviceLastUpdated', and
  'deviceTimestamp'.
- Adds process ID to initial logging when plugin enabled.

### v0.4.13
- Moves proc kill timer to function.

### v0.4.12
- Fixes bug when new devices are created.
- Changes default debugging level to informational messages.

### v0.4.11
- Adds timeout setting to device config.

### v0.4.10
- Adds timeout to proc.communicate()

### v0.4.09
- Fixes new bug in setting of debug level for new plugin installs.

### v0.4.08
- Fixes bug in setting of debug level for new plugin installs.

### v0.4.07
- Completes refactoring of plugin methods. Indigo methods remain camelCase, plugin methods become
  'refresh_data_for_dev_action'.

### v0.4.06
- Adds new Action Item to adjust the refresh frequency of a specified GhostXML device.
- Improves device configuration validation and help bubble text.

### v0.4.05
- Adds feature to automatically disable a device if it has failed to refresh 10 times.

### v0.4.04
- Adds option for sites that require token authentication.
- Completely refactors threading.
- Migrates plugin devices to their own class.
- Updates docstrings to Sphinx standard.
- Refines logging.
- Fixes bug where changes to debug level not applied.
- Fixes bug where curl reported error when completed successfully.

flatdict.py
- Adds trap for dict values that are empty lists or empty dicts. The trap  replaces the list or dict with 'None'. This
  allows the plugin to retain and show the key as a device state.

### v0.4.02
- Migrates writing of device states to API 2.0 `[ dev.updateStatesOnServer() ]`.

### v0.4.01
- Requires Indigo 7.0
- Updates to Indigo API 2.0
- Removes Toggle Debug from plugin menu.

### v0.3.18
- Adds ability to parse JSON keys that contains spaces.

### v0.3.17
- Fixes bug that could occur when establishing new devices with Basic Auth.
- Code clean up.

### v0.3.16
- Updates plugin update checker to use curl to overcome outdated security of Apple's Python install.

### v0.3.15
- Adds basic authentication.
- Cosmetic changes to device config dialog.
- Fixed bug in comms_kill_all
- Fixed bug in call to manually refresh a device.

### v0.3.14
- Improves Indigo UI messages during device processing.
- Implements device configuration settings validation.
- Adds proc.returncode 37 and explicit trap for data download.
- Adds more descriptive response for failed data downloads.
- Adds 'self.pluginIsShuttingDown' to make plugin shutdown more politely.
- Adds timeout to device_stop_comm to force threads to join after 0.5 seconds.
- Improves PEP 8 compliance for iterateXML.py.

### v0.3.13
- Converts last string operations to Unicode.

### v0.3.12
- Fixes bug where plugin was using too many system resources while waiting for device update request.

### v0.3.11
- Implements self.managedDevices where a dict of plugin devices will be maintained by the plugin (instead of making a
  server call to indigo.devices.itervalues('self')
- Code cleanup.
- Configures for IPS distribution.

### v0.3.10
- Installs threading in place of multiprocessing.

### v0.3.09
- Unwinds multiprocessing pool changes.

### v0.3.08
- Moved GhostXML Action Refresh Data For Device to the Device Actions Group.
- Moved GhostXML Action Refresh Data For All Devices to the Device Actions Group. (Select New Action Group --> Device 
  Actions --> GhostXML Controls)
- Migrated processing of device updates to multiprocessing pool. This change lays the groundwork for devices to update 
  individually and without having to wait for other devices to finish updating.
- Added dict.get() to certain dev.pluginProps for robustness.
- Fixes bug in establishment of logFile write under certain exceptions.
- Standardizes plugin menu item styles. Menu items with an ellipsis (...) denote that a dialog box will open. Menu
  items without an ellipsis denote that the plugin will take immediate action.

### v0.3.07
- Stylistic changes to Indigo Plugin Update Checker module.
- Adds environment information to the log when plugin is initialized.

### v0.3.06
- Adds menu item to enable/disable all plugin devices.
- Fixes bug in plugin update checker when invoked from the Indigo plugins menu.
- Properly sets icon state to off when GhostXML device is disabled.
- Code refinements.

### v0.3.05
- Adds capacity to work with more data sources:
  - Adds digest authentication option.
  - Converts JSON arrays to JSON objects when needed (when arrays are delivered).
  - Converts JSON key names that start with a number so that Indigo will accept them.

### v0.3.02
- Fixes bug where 'refreshFreq' is not a valid device property.
- Eliminates some deprecated code.
- Cleans up plugin configuration menu.

### v0.3.01
- Increases the plugin's ability to contend with certain characters that may be present in JSON keys.

### v0.3.00
- Introduces a new feature to allow Indigo substitutions into URLs (added by Howartp.)
- Adds device refresh Action item (added by Howartp.)
- Code stability enhancements.

### v0.2.06
- Moves device refresh timing to the device config menu so that each device refreshes at its own rate
- Adds action to allow refresh of individual feeds
- Adds option for manually refreshing feeds (ie no timed auto-refresh)
- Adds refresh when a new device is added - runs at next run_concurrent_thread() loop (ie 5 seconds)

### v0.2.05
- Adds a method, _clean_the_keys() which removes certain characters from dictionary key names that Indigo cannot use
  for device state names.

### v0.2.04
- Fixes bug where some Unicode sources could cause data download error ('ascii' codec can't decode).
- Deprecates _toDo.txt file over embedded TODOs in the code.

### v0.2.03
- Small update to correct fatal error in data typing.

### v0.2.02
- Fixes plugin config menu error.
