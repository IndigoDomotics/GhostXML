# ![GhostXML Logo](https://github.com/IndigoDomotics/GhostXML/wiki/img/img_ghostxmlLogo.png)  
# ![shield](https://img.shields.io/github/release/IndigoDomotics/GhostXML.svg) ![indigo-version](https://img.shields.io/badge/Indigo-7.0-blueviolet.svg) ![indigo-version](https://img.shields.io/badge/Python-2.7-darkgreen.svg)

The GhostXML plugin allows users to create custom devices for XML and 
JSON data sources.

The purpose of the GhostXML plugin is to interface with XML and JSON 
files (web-based or on the local machine) and parse the XML to 
device states. If the structure of the XML or JSON changes over 
time, the plugin will pick up the new structure and add the states 
automatically. Similarly, if the XML or JSON source drops keys from 
the data, those states will disappear from the device states list.

As noted above, the plugin supports XML and JSON feeds.  It also 
includes the ability to perform variable substitutions within a 
URL, and provides a facility for Basic and Digest Authentication for 
downloading data from sites that require a username and password. 

Notes: The plugin's need for Internet access will depend on
the data sources used. If you limit use to data sources on
your internal network, the only aspect of the plugin that requires 
Internet access is to check for plugin software updates.  These 
features are not required to use the plugin.

