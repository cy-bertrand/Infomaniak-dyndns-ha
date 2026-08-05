"""Sensor platform for Infomaniak DDNS."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_FAST_DETECTION,
    CONF_FAST_INTERVAL,
    CONF_HOSTNAME,
    CONF_IP_MODE,
    CONF_UPDATE_INTERVAL,
    CONF_UPDATE_URL,
    DEFAULT_FAST_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_UPDATE_URL,
    DOMAIN,
    IP_MODE_AUTO,
)
from . import InfomaniakDDNSCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: InfomaniakDDNSCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        InfomaniakDDNSStatusSensor(coordinator, entry),
        InfomaniakDDNSIPSensor(coordinator, entry),
    ])


class InfomaniakDDNSBaseSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: InfomaniakDDNSCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._hostname = entry.data[CONF_HOSTNAME]

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"Infomaniak DDNS – {self._hostname}",
            manufacturer="Infomaniak",
            model="DDNS",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class InfomaniakDDNSStatusSensor(InfomaniakDDNSBaseSensor):
    translation_key = "infomaniak_ddns_status"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_status"

    @property
    def icon(self) -> str:
        if self._coordinator.last_error:
            return "mdi:cloud-alert"
        if self._coordinator.last_result and self._coordinator.last_result.startswith("nochg"):
            return "mdi:cloud-check-outline"
        return "mdi:cloud-check"

    @property
    def native_value(self) -> str | None:
        if self._coordinator.last_error:
            return "error"
        if self._coordinator.last_result:
            if self._coordinator.last_result.startswith("good"):
                return "updated"
            if self._coordinator.last_result.startswith("nochg"):
                return "unchanged"
        return "unknown"

    @property
    def extra_state_attributes(self) -> dict:
        ip_mode = self._entry.data.get(CONF_IP_MODE, IP_MODE_AUTO)
        return {
            "hostname": self._hostname,
            "last_response": self._coordinator.last_result,
            "last_error": self._coordinator.last_error,
            "ip_source": self._coordinator.last_ip_source,
            "ip_mode": ip_mode,
            "update_count": self._coordinator.update_count,
            "check_count": self._coordinator.check_count,
            "update_url": self._entry.data.get(CONF_UPDATE_URL, DEFAULT_UPDATE_URL),
            "update_interval_minutes": self._entry.data.get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
            ),
            "fast_detection_enabled": self._entry.options.get(CONF_FAST_DETECTION, False),
            "fast_detection_interval_seconds": self._entry.options.get(
                CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL
            ),
            "ip_services_pool_size": self._coordinator.pool_size,
            "last_ip_service": self._coordinator.last_ip_service,
        }


class InfomaniakDDNSIPSensor(InfomaniakDDNSBaseSensor):
    translation_key = "infomaniak_ddns_ip"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_ip"

    @property
    def icon(self) -> str:
        return "mdi:ip-network"

    @property
    def native_value(self) -> str | None:
        return self._coordinator.last_ip

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "ip_source": self._coordinator.last_ip_source,
            "ip_mode": self._entry.data.get(CONF_IP_MODE, IP_MODE_AUTO),
            "last_known_wan_ip_fast_check": self._coordinator.last_known_wan_ip,
            "last_ip_service": self._coordinator.last_ip_service,
        }
