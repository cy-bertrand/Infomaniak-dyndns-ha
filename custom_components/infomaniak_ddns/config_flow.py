"""Config flow for Infomaniak DDNS integration."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

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

_IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def _is_valid_ipv4(ip: str) -> bool:
    if not _IPV4_RE.match(ip):
        return False
    return all(0 <= int(o) <= 255 for o in ip.split("."))


async def _test_connection(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Test connection to Infomaniak DDNS API."""
    update_url = data.get(CONF_UPDATE_URL, DEFAULT_UPDATE_URL)
    hostname = data[CONF_HOSTNAME]
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]

    url = f"{update_url}?hostname={hostname}"

    ip_mode = data.get(CONF_IP_MODE, IP_MODE_AUTO)
    if ip_mode == IP_MODE_STATIC:
        ip = data.get(CONF_IP_STATIC, "").strip()
        if ip:
            url += f"&myip={ip}"

    session = async_get_clientsession(hass)
    try:
        async with async_timeout.timeout(15):
            resp = await session.post(url, auth=aiohttp.BasicAuth(username, password))
            text = (await resp.text()).strip()
            _LOGGER.debug("Config flow validation response: %s", text)
            if text.startswith("badauth"):
                raise InvalidAuth
            if text.startswith("nohost") or text.startswith("notfqdn"):
                raise InvalidHostname
            if text.startswith("911"):
                raise CannotConnect
            return {"title": f"Infomaniak DDNS \u2013 {hostname}"}
    except asyncio.TimeoutError as err:
        raise CannotConnect from err
    except aiohttp.ClientError as err:
        raise CannotConnect from err


def _base_schema(defaults: dict) -> vol.Schema:
    """Schema step 1 : connexion + mode IP."""
    return vol.Schema({
        vol.Optional(CONF_UPDATE_URL, default=defaults.get(CONF_UPDATE_URL, DEFAULT_UPDATE_URL)): str,
        vol.Required(CONF_HOSTNAME, default=defaults.get(CONF_HOSTNAME, "")): str,
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
        vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
        vol.Optional(
            CONF_UPDATE_INTERVAL,
            default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
        vol.Optional(CONF_IP_MODE, default=defaults.get(CONF_IP_MODE, IP_MODE_AUTO)):
            selector.selector({"select": {"options": [
                {"value": IP_MODE_AUTO,   "label": "Auto \u2014 IP WAN d\u00e9tect\u00e9e par Infomaniak (recommand\u00e9)"},
                {"value": IP_MODE_STATIC, "label": "IP fixe \u2014 saisie manuelle"},
                {"value": IP_MODE_ENTITY, "label": "Entit\u00e9 HA \u2014 lire l'IP depuis un capteur"},
            ]}}),
    })


def _static_ip_schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_IP_STATIC, default=defaults.get(CONF_IP_STATIC, "")): str,
    })


def _entity_schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_IP_ENTITY, default=defaults.get(CONF_IP_ENTITY, "")): str,
    })


# ---------------------------------------------------------------------------
# Config Flow — première installation
# ---------------------------------------------------------------------------

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow for Infomaniak DDNS."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            ip_mode = user_input.get(CONF_IP_MODE, IP_MODE_AUTO)

            if ip_mode == IP_MODE_STATIC:
                return await self.async_step_static_ip()
            if ip_mode == IP_MODE_ENTITY:
                return await self.async_step_entity_ip()

            try:
                info = await _test_connection(self.hass, self._data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors[CONF_PASSWORD] = "invalid_auth"
            except InvalidHostname:
                errors[CONF_HOSTNAME] = "invalid_hostname"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=self._data)

        return self.async_show_form(
            step_id="user",
            data_schema=_base_schema(self._data),
            errors=errors,
        )

    async def async_step_static_ip(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            ip = user_input.get(CONF_IP_STATIC, "").strip()
            if not _is_valid_ipv4(ip):
                errors[CONF_IP_STATIC] = "invalid_ip"
            else:
                self._data.update(user_input)
                try:
                    info = await _test_connection(self.hass, self._data)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors[CONF_PASSWORD] = "invalid_auth"
                except InvalidHostname:
                    errors[CONF_HOSTNAME] = "invalid_hostname"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(title=info["title"], data=self._data)

        return self.async_show_form(
            step_id="static_ip",
            data_schema=_static_ip_schema(self._data),
            errors=errors,
            description_placeholders={"hostname": self._data.get(CONF_HOSTNAME, "")},
        )

    async def async_step_entity_ip(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = user_input.get(CONF_IP_ENTITY, "").strip()
            if not entity_id:
                errors[CONF_IP_ENTITY] = "invalid_entity"
            else:
                self._data.update(user_input)
                test_data = {**self._data, CONF_IP_MODE: IP_MODE_AUTO}
                try:
                    info = await _test_connection(self.hass, test_data)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors[CONF_PASSWORD] = "invalid_auth"
                except InvalidHostname:
                    errors[CONF_HOSTNAME] = "invalid_hostname"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(title=info["title"], data=self._data)

        return self.async_show_form(
            step_id="entity_ip",
            data_schema=_entity_schema(self._data),
            errors=errors,
            description_placeholders={"hostname": self._data.get(CONF_HOSTNAME, "")},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "OptionsFlowHandler":
        """Create the options flow — ne pas passer config_entry (HA 2025.12+)."""
        return OptionsFlowHandler()


# ---------------------------------------------------------------------------
# Options Flow — reconfiguration
#
# Compatible HA 2025.12+ :
#   - Pas de __init__, pas de self.config_entry = config_entry
#   - self.config_entry est fourni automatiquement par la classe parente
#   - self._data remplacé par self.config_entry.data
#   - self._pending transfère les données entre étapes
# ---------------------------------------------------------------------------

class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow handler compatible HA 2025.12+."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            ip_mode = user_input.get(CONF_IP_MODE, IP_MODE_AUTO)

            if ip_mode == IP_MODE_STATIC:
                self._pending: dict[str, Any] = user_input
                return await self.async_step_static_ip()

            if ip_mode == IP_MODE_ENTITY:
                self._pending = user_input
                return await self.async_step_entity_ip()

            merged = {**self.config_entry.data, **user_input}
            try:
                await _test_connection(self.hass, merged)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors[CONF_PASSWORD] = "invalid_auth"
            except InvalidHostname:
                errors[CONF_HOSTNAME] = "invalid_hostname"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=merged
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=_base_schema(self.config_entry.data),
            errors=errors,
        )

    async def async_step_static_ip(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        pending = getattr(self, "_pending", {})

        if user_input is not None:
            ip = user_input.get(CONF_IP_STATIC, "").strip()
            if not _is_valid_ipv4(ip):
                errors[CONF_IP_STATIC] = "invalid_ip"
            else:
                merged = {**self.config_entry.data, **pending, **user_input}
                try:
                    await _test_connection(self.hass, merged)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors[CONF_PASSWORD] = "invalid_auth"
                except InvalidHostname:
                    errors[CONF_HOSTNAME] = "invalid_hostname"
                except Exception:
                    errors["base"] = "unknown"
                else:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=merged
                    )
                    return self.async_create_entry(title="", data={})

        defaults = {**self.config_entry.data, **pending}
        return self.async_show_form(
            step_id="static_ip",
            data_schema=_static_ip_schema(defaults),
            errors=errors,
        )

    async def async_step_entity_ip(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        pending = getattr(self, "_pending", {})

        if user_input is not None:
            entity_id = user_input.get(CONF_IP_ENTITY, "").strip()
            if not entity_id:
                errors[CONF_IP_ENTITY] = "invalid_entity"
            else:
                merged = {**self.config_entry.data, **pending, **user_input}
                test_data = {**merged, CONF_IP_MODE: IP_MODE_AUTO}
                try:
                    await _test_connection(self.hass, test_data)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors[CONF_PASSWORD] = "invalid_auth"
                except InvalidHostname:
                    errors[CONF_HOSTNAME] = "invalid_hostname"
                except Exception:
                    errors["base"] = "unknown"
                else:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=merged
                    )
                    return self.async_create_entry(title="", data={})

        defaults = {**self.config_entry.data, **pending}
        return self.async_show_form(
            step_id="entity_ip",
            data_schema=_entity_schema(defaults),
            errors=errors,
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CannotConnect(Exception):
    """Cannot connect to the DDNS server."""


class InvalidAuth(Exception):
    """Invalid authentication credentials."""


class InvalidHostname(Exception):
    """Invalid or unknown hostname."""
