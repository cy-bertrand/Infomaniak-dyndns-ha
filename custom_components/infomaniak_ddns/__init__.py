"""Infomaniak DDNS integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta

import aiohttp
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_UPDATE_URL,
    CONF_HOSTNAME,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_IP_MODE,
    CONF_IP_STATIC,
    CONF_IP_ENTITY,
    DEFAULT_UPDATE_URL,
    DEFAULT_UPDATE_INTERVAL,
    IP_MODE_AUTO,
    IP_MODE_STATIC,
    IP_MODE_ENTITY,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Infomaniak DDNS from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = InfomaniakDDNSCoordinator(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await coordinator.async_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    interval = timedelta(minutes=entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
    entry.async_on_unload(
        async_track_time_interval(hass, coordinator.async_refresh, interval)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _is_valid_ipv4(ip: str) -> bool:
    pattern = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
    if not pattern.match(ip):
        return False
    return all(0 <= int(o) <= 255 for o in ip.split("."))


class InfomaniakDDNSCoordinator:
    """Coordinator for Infomaniak DDNS updates."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.last_result: str | None = None
        self.last_ip: str | None = None
        self.last_error: str | None = None
        self.last_ip_source: str | None = None
        self.update_count: int = 0
        self._listeners: list = []

    def async_add_listener(self, update_callback) -> callable:
        self._listeners.append(update_callback)
        def remove_listener():
            self._listeners.remove(update_callback)
        return remove_listener

    def _notify_listeners(self):
        for listener in self._listeners:
            listener()

    def _resolve_ip(self) -> tuple[str | None, str]:
        """
        Resolve the IP to use for the DDNS update.
        Returns (ip_or_None, source_description).
        None means 'let Infomaniak auto-detect'.
        """
        ip_mode = self.entry.data.get(CONF_IP_MODE, IP_MODE_AUTO)

        if ip_mode == IP_MODE_STATIC:
            ip = self.entry.data.get(CONF_IP_STATIC, "").strip()
            if ip and _is_valid_ipv4(ip):
                return ip, f"static ({ip})"
            _LOGGER.warning("Static IP '%s' is invalid, falling back to auto-detect", ip)
            return None, "auto (fallback — static IP invalide)"

        elif ip_mode == IP_MODE_ENTITY:
            entity_id = self.entry.data.get(CONF_IP_ENTITY, "").strip()
            if entity_id:
                state = self.hass.states.get(entity_id)
                if state and state.state not in ("unknown", "unavailable", ""):
                    ip = state.state.strip()
                    if _is_valid_ipv4(ip):
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

    async def async_refresh(self, _now=None) -> None:
        """Perform the DDNS update."""
        update_url = self.entry.data.get(CONF_UPDATE_URL, DEFAULT_UPDATE_URL)
        hostname = self.entry.data[CONF_HOSTNAME]
        username = self.entry.data[CONF_USERNAME]
        password = self.entry.data[CONF_PASSWORD]

        ip, ip_source = self._resolve_ip()
        self.last_ip_source = ip_source

        url = f"{update_url}?hostname={hostname}"
        if ip:
            url += f"&myip={ip}"

        session = async_get_clientsession(self.hass)

        try:
            async with async_timeout.timeout(30):
                resp = await session.post(
                    url,
                    auth=aiohttp.BasicAuth(username, password),
                )
                text = (await resp.text()).strip()
                _LOGGER.debug("Infomaniak DDNS response [%s, ip_source=%s]: %s", hostname, ip_source, text)

                if text.startswith("good") or text.startswith("nochg"):
                    parts = text.split()
                    if len(parts) >= 2:
                        self.last_ip = parts[1]
                    elif ip:
                        self.last_ip = ip
                    self.last_result = text
                    self.last_error = None
                    self.update_count += 1
                    _LOGGER.info("DDNS %s updated — %s (source: %s)", hostname, text, ip_source)
                else:
                    self.last_result = text
                    self.last_error = text
                    _LOGGER.warning("DDNS %s update failed: %s", hostname, text)

        except asyncio.TimeoutError:
            self.last_error = "Timeout"
            _LOGGER.error("Timeout updating Infomaniak DDNS for %s", hostname)
        except aiohttp.ClientError as err:
            self.last_error = str(err)
            _LOGGER.error("Error updating Infomaniak DDNS for %s: %s", hostname, err)
        finally:
            self._notify_listeners()
