"""
Indigo Device Filters

Provides a reference list of Indigo device filter strings used in device configuration UI dropdowns. These filter
strings control which device types are displayed in device-picker fields within plugin configuration dialogs.
"""
DEVICE_FILTERS = [
    "com.somePlugin.devTypeId" 
    "com.somePlugin",  # all device types defined by some other plugin
    "indigo.controller",  # include devices that can send commands
    "indigo.dimmer",  # dimmer devices
    "indigo.insteon",  # include INSTEON devices - this is an interface filter that can be used with other filters
    "indigo.iodevice",  # input/output devices
    "indigo.relay",  # relay devices
    "indigo.responder",  # include devices whose state can be changed
    "indigo.sensor",  # all sensor type devices: motion sensors, TriggerLinc, SynchroLinc (sensor devices that have a virtual state in Indigo)
    "indigo.sprinkler",  # sprinklers
    "indigo.thermostat",  # thermostats
    "indigo.x10",  # include X10 devices - this is an interface filter that can be used with other filters
    "indigo.zwave",  # include Z-Wave devices - this is an interface filter that can be used with other filters
    "self.devTypeId",  # all devices of type deviceTypeId, where deviceTypeId is one of the device types specified by the calling plugin
    "self",  # all device types defined by the calling plugin
]
