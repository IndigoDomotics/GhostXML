# GhostXML Plugin for Indigo Home Automation

## Synopsis
GhostXML is a plugin that supports calls to API endpoints using an array of authentication protocols. It is capable of 
processing both XML and JSON payloads and making payload data available in Indigo device states.

## Workflow
- User creates a unique device object for each API endpoint.
- User enters payload type, URL/Path, authentication settings (as needed) and other settings that apply to the 
  connection instance.
- After a successful connection, the plugin parses the returned payload into custom device states.
- The states are ephemeral. In other words, an individual state will continue to be available as long as subsequent 
  API calls return the associated key/value pair.
- If the API stops returning a specific key, the state will be removed from the associated device.

## Project Structure
- The project is divided into two distinct and separate repositories:
  - GhostXML.indigoPlugin: the main plugin repository, and
  - GhostXML.wiki: the plugin wiki repository.
  - Changes to the plugin files should not be pushed to the wiki repo, and changes to the wiki should not be pushed to 
    the plugin repository.
