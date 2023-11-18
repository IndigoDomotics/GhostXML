### TODO
- When there's a parse error (like from a curl timeout), three messages are written to the
  event log. How to reduce to one?
- Additional auth types: Oauth2, WSSE
- If URL/Path for device is empty, raise exception
- Consider ramping back down on the minimum server API version to 3.0 (based on user feedback). Will require testing
