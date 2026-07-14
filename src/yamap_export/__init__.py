"""yamap-export — bulk export of YAMAP activities for archival and migration.

The package only ever reads *your own* public activity data through YAMAP's
JSON endpoints, plus (optionally) your own GPS tracks using the login token
stored in your browser. It never uploads anything and never transmits your
token anywhere except to api.yamap.com.
"""

__version__ = "0.1.0"
