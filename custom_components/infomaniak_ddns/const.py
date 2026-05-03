"""Constants for Infomaniak DDNS integration."""

DOMAIN = "infomaniak_ddns"

CONF_UPDATE_URL = "update_url"
CONF_HOSTNAME = "hostname"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_UPDATE_URL = "https://infomaniak.com/nic/update"
DEFAULT_UPDATE_INTERVAL = 5  # minutes

# Possible responses from Infomaniak DDNS API
RESPONSE_GOOD = "good"
RESPONSE_NOCHG = "nochg"
RESPONSE_BADAUTH = "badauth"
RESPONSE_NOHOST = "nohost"
RESPONSE_NOTFQDN = "notfqdn"
RESPONSE_ABUSE = "abuse"
RESPONSE_911 = "911"
