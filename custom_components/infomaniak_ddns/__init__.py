"""Infomaniak DDNS integration for Home Assistant."""
from __future__ import annotations

import asyncio
import itertools
import logging
from datetime import timedelta
from urllib.parse import urlencode

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_CUSTOM_SERVICES,
    CONF_FAST_DETECTION,
    CONF_FAST_INTERVAL,
    CONF_HOSTNAME,
    CONF_IP_ENTITY,
    CONF_IP_MODE,
    CONF_IP_SERVICES,
    CONF_IP_STATIC,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_UPDATE_URL,
    CONF_USERNAME,
    DEFAULT_FAST_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_UPDATE_URL,
    DOMAIN,
    IP_MODE_AUTO,
    IP_MODE_ENTITY,
    IP_MODE_STATIC,
    IP_SERVICES_DEFAULT,
    SERVICE_UPDATE,
)
from .helpers import IP_REGEX, is_valid_ipv4, is_valid_service_url

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Infomaniak DDNS from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = InfomaniakDDNSCoordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Détection rapide de changement d'IP WAN (optionnelle, configurée via Options)
    coordinator.async_setup_fast_detection()

    # Reconstruit le pool de services + le timer rapide si les options changent
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Service pour forcer une mise à jour manuelle (enregistré une seule fois)
    if not hass.services.has_service(DOMAIN, SERVICE_UPDATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UPDATE,
            _async_handle_update_service,
            schema=vol.Schema({vol.Optional(CONF_HOSTNAME): str}),
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Premier rafraîchissement en arrière-plan (non bloquant pour le setup)
    hass.async_create_task(coordinator.async_refresh())

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Appelé quand l'utilisateur modifie les options (services IP, détection rapide...)."""
    coordinator: InfomaniakDDNSCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.update_interval = timedelta(
        minutes=entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    )
    coordinator.async_rebuild_ip_service_pool()
    coordinator.async_setup_fast_detection()
    await coordinator.async_request_refresh()


async def _async_handle_update_service(call: ServiceCall) -> None:
    """Force une mise à jour DDNS pour un ou tous les hostnames configurés."""
    hostname = str(call.data.get(CONF_HOSTNAME, "")).strip()
    for coordinator in call.hass.data[DOMAIN].values():
        if hostname and coordinator.entry.data[CONF_HOSTNAME] != hostname:
            continue
        await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: InfomaniakDDNSCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.async_unload()
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_UPDATE)
    return unload_ok


class InfomaniakDDNSCoordinator(DataUpdateCoordinator[dict | None]):
    """Coordinator for Infomaniak DDNS updates."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            ),
            always_update=True,
        )
        self.entry = entry
        self.last_result: str | None = None
        self.last_ip: str | None = None
        self.last_error: str | None = None
        self.last_ip_source: str | None = None
        self.update_count: int = 0
        self.check_count: int = 0
        self.last_ip_service: str | None = None

        # Détection rapide + rotation de services IP
        self._last_known_wan_ip: str | None = None
        self._fast_unsub = None
        self._fast_lock = asyncio.Lock()
        self._service_cycle = None
        self._pool_size = 0
        self.async_rebuild_ip_service_pool()

    # Propriétés publiques exposées aux capteurs
    @property
    def pool_size(self) -> int:
        return self._pool_size

    @property
    def last_known_wan_ip(self) -> str | None:
        return self._last_known_wan_ip

    def async_notify_listeners(self) -> None:
        """Notifie les listeners (capteurs) sans déclencher une mise à jour DDNS."""
        self.async_update_listeners()

    def _resolve_ip(self) -> tuple[str | None, str]:
        """
        Resolve the IP to use for the DDNS update.
        Returns (ip_or_None, source_description).
        None means 'let Infomaniak auto-detect'.
        """
        ip_mode = self.entry.data.get(CONF_IP_MODE, IP_MODE_AUTO)

        if ip_mode == IP_MODE_STATIC:
            ip = self.entry.data.get(CONF_IP_STATIC, "").strip()
            if ip and is_valid_ipv4(ip):
                return ip, f"static ({ip})"
            _LOGGER.warning("Static IP '%s' is invalid, falling back to auto-detect", ip)
            return None, "auto (fallback — static IP invalide)"

        elif ip_mode == IP_MODE_ENTITY:
            entity_id = self.entry.data.get(CONF_IP_ENTITY, "").strip()
            if entity_id:
                state = self.hass.states.get(entity_id)
                if state and state.state not in ("unknown", "unavailable", ""):
                    ip = state.state.strip()
                    if is_valid_ipv4(ip):
                        return ip, f"entity {entity_id} ({ip})"
                    _LOGGER.warning(
                        "Entity '%s' value '%s' is not a valid IPv4, falling back to auto-detect",
                        entity_id, ip,
                    )
                else:
                    _LOGGER.warning(
                        "Entity '%s' is unavailable or unknown, falling back to auto-detect",
                        entity_id,
                    )
            return None, f"auto (fallback — entity {entity_id} indisponible)"

        # IP_MODE_AUTO : pas de paramètre myip → Infomaniak détecte l'IP WAN de HA
        return None, "auto (IP WAN détectée par Infomaniak)"

    async def _async_update_data(self) -> dict | None:
        """Effectue réellement la mise à jour DDNS."""
        update_url = self.entry.data.get(CONF_UPDATE_URL, DEFAULT_UPDATE_URL)
        hostname = self.entry.data[CONF_HOSTNAME]
        username = self.entry.data[CONF_USERNAME]
        password = self.entry.data[CONF_PASSWORD]

        ip, ip_source = self._resolve_ip()
        self.last_ip_source = ip_source

        params = {"hostname": hostname}
        if ip:
            params["myip"] = ip
        separator = "&" if "?" in update_url else "?"
        url = f"{update_url}{separator}{urlencode(params)}"

        session = async_get_clientsession(self.hass)
        self.check_count += 1

        try:
            async with asyncio.timeout(30):
                resp = await session.post(
                    url,
                    auth=aiohttp.BasicAuth(username, password),
                )
                text = (await resp.text()).strip()
            _LOGGER.debug("Infomaniak DDNS response [%s, ip_source=%s]: %s", hostname, ip_source, text)

            if resp.status != 200:
                self.last_result = f"HTTP {resp.status}"
                self.last_error = f"HTTP {resp.status} ({text[:100]})"
                _LOGGER.warning("DDNS %s update failed: %s", hostname, self.last_error)
                return {"result": self.last_result, "error": self.last_error}

            if text.startswith("good") or text.startswith("nochg"):
                parts = text.split()
                if len(parts) >= 2:
                    self.last_ip = parts[1]
                elif ip:
                    self.last_ip = ip
                self.last_result = text
                self.last_error = None
                if text.startswith("good"):
                    self.update_count += 1
                _LOGGER.info("DDNS %s updated — %s (source: %s)", hostname, text, ip_source)
            else:
                self.last_result = text
                self.last_error = text
                _LOGGER.warning("DDNS %s update failed: %s", hostname, text)

        except TimeoutError:
            self.last_error = "Timeout"
            _LOGGER.error("Timeout updating Infomaniak DDNS for %s", hostname)
        except aiohttp.ClientError as err:
            self.last_error = str(err)
            _LOGGER.error("Error updating Infomaniak DDNS for %s: %s", hostname, err)

        return {"result": self.last_result, "error": self.last_error}

    # ------------------------------------------------------------------
    # Rotation de services de détection d'IP publique
    # ------------------------------------------------------------------
    def async_rebuild_ip_service_pool(self) -> None:
        """(Re)construit la liste circulaire des services d'IP à interroger,
        à partir des options choisies par l'utilisateur (cases cochées +
        services personnalisés)."""
        options = self.entry.options

        selected_keys = options.get(
            CONF_IP_SERVICES,
            [key for key, value in IP_SERVICES_DEFAULT.items() if value["enabled_default"]],
        )
        urls = [
            IP_SERVICES_DEFAULT[key]["url"]
            for key in selected_keys
            if key in IP_SERVICES_DEFAULT
        ]

        for url in options.get(CONF_CUSTOM_SERVICES, []):
            if is_valid_service_url(url):
                urls.append(url)
            else:
                _LOGGER.warning("URL de service IP personnalisée invalide ignorée: %s", url)

        if not urls:
            _LOGGER.warning(
                "Aucun service d'IP sélectionné, utilisation du service de secours icanhazip.com"
            )
            urls = [IP_SERVICES_DEFAULT["icanhazip"]["url"]]

        self._pool_size = len(urls)
        self._service_cycle = itertools.cycle(urls)
        _LOGGER.debug("Pool de services IP reconstruit (%s services)", self._pool_size)

    async def _async_get_current_wan_ip_from_services(self) -> str | None:
        """Interroge le prochain service du pool (round-robin), avec repli
        automatique sur les autres services en cas d'échec/timeout."""
        session = async_get_clientsession(self.hass)

        for _ in range(max(self._pool_size, 1)):
            url = next(self._service_cycle)
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    text = (await resp.text()).strip()
                    match = IP_REGEX.search(text)
                    if match and is_valid_ipv4(match.group(0)):
                        self.last_ip_service = url
                        return match.group(0)
                    _LOGGER.debug("Réponse inattendue de %s: %s", url, text)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Service IP %s indisponible (%s), essai suivant", url, err)

        self.last_ip_service = None
        _LOGGER.debug("Aucun service d'IP n'a répondu lors de ce cycle de détection rapide")
        return None

    # ------------------------------------------------------------------
    # Détection rapide de changement d'IP WAN
    # ------------------------------------------------------------------
    def async_setup_fast_detection(self) -> None:
        """Active ou désactive le timer de détection rapide selon les options."""
        if self._fast_unsub is not None:
            self._fast_unsub()
            self._fast_unsub = None

        if self.entry.options.get(CONF_FAST_DETECTION, False):
            interval = self.entry.options.get(CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL)
            self._fast_unsub = async_track_time_interval(
                self.hass,
                self._async_check_wan_ip_change,
                timedelta(seconds=interval),
            )
            _LOGGER.info("Détection rapide de changement d'IP WAN activée (intervalle: %ss)", interval)
        else:
            _LOGGER.debug("Détection rapide de changement d'IP WAN désactivée")

    async def _async_check_wan_ip_change(self, _now=None) -> None:
        """Callback périodique : vérifie l'IP WAN via le pool de services et
        force une mise à jour DDNS immédiate en cas de changement, sans
        attendre le cycle lent normal. Sérialisé pour éviter les chevauchements."""
        if self._fast_lock.locked():
            _LOGGER.debug("Vérification rapide d'IP déjà en cours, exécution ignorée")
            return

        async with self._fast_lock:
            current_ip = await self._async_get_current_wan_ip_from_services()
            if current_ip is None:
                self.async_notify_listeners()
                return

            if self._last_known_wan_ip is not None and current_ip != self._last_known_wan_ip:
                _LOGGER.info(
                    "Changement d'IP WAN détecté (%s -> %s), mise à jour DDNS forcée",
                    self._last_known_wan_ip,
                    current_ip,
                )
                self._last_known_wan_ip = current_ip
                await self.async_request_refresh()
            else:
                self._last_known_wan_ip = current_ip
                self.async_notify_listeners()

    def async_unload(self) -> None:
        """À appeler lors du déchargement de l'entrée pour stopper le timer rapide."""
        if self._fast_unsub is not None:
            self._fast_unsub()
            self._fast_unsub = None
