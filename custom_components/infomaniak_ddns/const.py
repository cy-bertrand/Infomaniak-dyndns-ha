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

IP_MODE_AUTO = "auto"      # IP WAN détectée par Infomaniak (défaut)
IP_MODE_STATIC = "static"  # IP fixe saisie manuellement
IP_MODE_ENTITY = "entity"  # IP lue depuis un entity_id HA

IP_MODES = [IP_MODE_AUTO, IP_MODE_STATIC, IP_MODE_ENTITY]

# Réponses API
RESPONSE_GOOD = "good"
RESPONSE_NOCHG = "nochg"
RESPONSE_BADAUTH = "badauth"
RESPONSE_NOHOST = "nohost"
RESPONSE_NOTFQDN = "notfqdn"
RESPONSE_ABUSE = "abuse"
RESPONSE_911 = "911"

# --- NOUVEAU : détection rapide de changement d'IP WAN ---
CONF_FAST_DETECTION = "fast_detection"
CONF_FAST_INTERVAL = "fast_interval"
DEFAULT_FAST_INTERVAL = 60  # secondes
MIN_FAST_INTERVAL = 15
MAX_FAST_INTERVAL = 3600

# --- NOUVEAU : rotation de services publics de détection d'IP ---
CONF_IP_SERVICES = "ip_services"
CONF_CUSTOM_SERVICES = "custom_services"

IP_SERVICES_DEFAULT = {
    "ifconfig_me": {
        "name": "ifconfig.me",
        "url": "https://ifconfig.me/ip",
        "enabled_default": True,
    },
    "icanhazip": {
        "name": "icanhazip.com",
        "url": "https://icanhazip.com",
        "enabled_default": True,
    },
    "ipify": {
        "name": "ipify.org",
        "url": "https://api.ipify.org",
        "enabled_default": True,
    },
    "ident_me": {
        "name": "ident.me",
        "url": "https://v4.ident.me",
        "enabled_default": True,
    },
    "ipecho": {
        "name": "ipecho.net",
        "url": "https://ipecho.net/plain",
        "enabled_default": False,
    },
    "aws_checkip": {
        "name": "AWS checkip",
        "url": "https://checkip.amazonaws.com",
        "enabled_default": False,
    },
    "ipinfo": {
        "name": "ipinfo.io",
        "url": "https://ipinfo.io/ip",
        "enabled_default": False,
    },
    "seeip": {
        "name": "seeip.org",
        "url": "https://api.seeip.org",
        "enabled_default": False,
    },
}
