- Additional auth types: Oauth2, WSSE
- Germ of an idea: a GhostXML plugin api where users can send a url and get back a flatdict.
  - would need to handle auth
  - would need to handle errors
- Raw Curl auth always disables TLS certificate verification (`-vsk` in `plugin.py`'s
  `get_the_data`, ~line 1132) with no way to opt back in, unlike every other auth mode which
  uses `requests`' default `verify=True`. Default to verified TLS and make insecure mode an
  explicit opt-in device setting if it's still needed for self-signed-cert setups.
