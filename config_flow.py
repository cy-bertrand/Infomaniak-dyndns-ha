"""Config flow for Infomaniak DDNS integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
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


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input by performing a test DDNS update call."""
    update_url = data.get(CONF_UPDATE_URL, DEFAULT_UPDATE_URL)
    hostname = data[CONF_HOSTNAME]
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]

    url = f"{update_url}?hostname={hostname}"
    session = async_get_clientsession(hass)

    try:
        async with async_timeout.timeout(15):
            resp = await session.post(
                url,
                auth=aiohttp.BasicAuth(username, password),
            )
            text = (await resp.text()).strip()
            _LOGGER.debug("Validation response: %s", text)

            if text.startswith("badauth"):
                raise InvalidAuth
            if text.startswith("nohost") or text.startswith("notfqdn"):
                raise InvalidHostname
            if text.startswith("911"):
                raise CannotConnect
            # good or nochg are success
            return {"title": f"Infomaniak DDNS – {hostname}"}

    except asyncio.TimeoutError as err:
        raise CannotConnect from err
    except aiohttp.ClientError as err:
        raise CannotConnect from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Infomaniak DDNS."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
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
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_URL, default=DEFAULT_UPDATE_URL
                    ): str,
                    vol.Required(CONF_HOSTNAME): str,
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Merge with existing data for validation
            merged = {**self.config_entry.data, **user_input}
            try:
                await validate_input(self.hass, merged)
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
                    self.config_entry, data={**self.config_entry.data, **user_input}
                )
                return self.async_create_entry(title="", data={})

        current = self.config_entry.data
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_URL,
                        default=current.get(CONF_UPDATE_URL, DEFAULT_UPDATE_URL),
                    ): str,
                    vol.Required(
                        CONF_HOSTNAME,
                        default=current.get(CONF_HOSTNAME, ""),
                    ): str,
                    vol.Required(
                        CONF_USERNAME,
                        default=current.get(CONF_USERNAME, ""),
                    ): str,
                    vol.Required(
                        CONF_PASSWORD,
                        default=current.get(CONF_PASSWORD, ""),
                    ): str,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                }
            ),
            errors=errors,
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


class InvalidHostname(Exception):
    """Error to indicate the hostname is invalid."""
