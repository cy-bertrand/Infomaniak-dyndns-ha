"""Infomaniak DDNS integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
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
    DEFAULT_UPDATE_URL,
    DEFAULT_UPDATE_INTERVAL,
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

    # Schedule periodic updates
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


class InfomaniakDDNSCoordinator:
    """Coordinator for Infomaniak DDNS updates."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.hass = hass
        self.entry = entry
        self.last_result: str | None = None
        self.last_ip: str | None = None
        self.last_error: str | None = None
        self.update_count: int = 0
        self._listeners: list = []

    def async_add_listener(self, update_callback) -> callable:
        """Listen for data updates."""
        self._listeners.append(update_callback)

        def remove_listener():
            self._listeners.remove(update_callback)

        return remove_listener

    def _notify_listeners(self):
        for listener in self._listeners:
            listener()

    async def async_refresh(self, _now=None) -> None:
        """Update DDNS record."""
        update_url = self.entry.data.get(CONF_UPDATE_URL, DEFAULT_UPDATE_URL)
        hostname = self.entry.data[CONF_HOSTNAME]
        username = self.entry.data[CONF_USERNAME]
        password = self.entry.data[CONF_PASSWORD]

        url = f"{update_url}?hostname={hostname}"
        session = async_get_clientsession(self.hass)

        try:
            async with async_timeout.timeout(30):
                resp = await session.post(
                    url,
                    auth=aiohttp.BasicAuth(username, password),
                )
                text = await resp.text()
                text = text.strip()
                _LOGGER.debug("Infomaniak DDNS response: %s", text)

                if text.startswith("good") or text.startswith("nochg"):
                    # Extract IP from response (e.g., "good 1.2.3.4" or "nochg 1.2.3.4")
                    parts = text.split()
                    if len(parts) >= 2:
                        self.last_ip = parts[1]
                    self.last_result = text
                    self.last_error = None
                    self.update_count += 1
                    _LOGGER.info(
                        "Infomaniak DDNS update for %s: %s", hostname, text
                    )
                else:
                    self.last_result = text
                    self.last_error = text
                    _LOGGER.warning(
                        "Infomaniak DDNS update failed for %s: %s", hostname, text
                    )

        except asyncio.TimeoutError:
            self.last_error = "Timeout"
            _LOGGER.error("Timeout updating Infomaniak DDNS for %s", hostname)
        except aiohttp.ClientError as err:
            self.last_error = str(err)
            _LOGGER.error("Error updating Infomaniak DDNS for %s: %s", hostname, err)
        finally:
            self._notify_listeners()
