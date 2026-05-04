"""Constants for Infomaniak DDNS integration."""

DOMAIN = "infomaniak_ddns"

CONF_UPDATE_URL = "update_url"
CONF_HOSTNAME = "hostname"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_IP_MODE = "ip_mode"
CONF_IP_STATIC = "ip_static"
CONF_IP_ENTITY = "ip_entity"

DEFAULT_UPDATE_URL = "https://infomaniak.com/nic/update"
DEFAULT_UPDATE_INTERVAL = 15  # minutes

IP_MODE_AUTO = "auto"        # IP WAN détectée par Infomaniak (défaut)
IP_MODE_STATIC = "static"    # IP fixe saisie manuellement
IP_MODE_ENTITY = "entity"    # IP lue depuis un entity_id HA

IP_MODES = [IP_MODE_AUTO, IP_MODE_STATIC, IP_MODE_ENTITY]

# Réponses API
RESPONSE_GOOD = "good"
RESPONSE_NOCHG = "nochg"
RESPONSE_BADAUTH = "badauth"
RESPONSE_NOHOST = "nohost"
RESPONSE_NOTFQDN = "notfqdn"
RESPONSE_ABUSE = "abuse"
RESPONSE_911 = "911"
