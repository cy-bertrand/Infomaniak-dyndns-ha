"""Config flow for Infomaniak DDNS integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlencode

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector, config_validation as cv
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
    CONF_FAST_DETECTION,
    CONF_FAST_INTERVAL,
    DEFAULT_FAST_INTERVAL,
    MIN_FAST_INTERVAL,
    MAX_FAST_INTERVAL,
    CONF_IP_SERVICES,
    CONF_CUSTOM_SERVICES,
    IP_SERVICES_DEFAULT,
)
from .helpers import is_valid_ipv4, is_valid_service_url

_LOGGER = logging.getLogger(__name__)


async def _test_connection(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Test connection to Infomaniak DDNS API."""
    update_url = data.get(CONF_UPDATE_URL, DEFAULT_UPDATE_URL)
    hostname = data[CONF_HOSTNAME]
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]

    params = {"hostname": hostname}

    ip_mode = data.get(CONF_IP_MODE, IP_MODE_AUTO)
    if ip_mode == IP_MODE_STATIC:
        ip = data.get(CONF_IP_STATIC, "").strip()
        if ip:
            params["myip"] = ip

    separator = "&" if "?" in update_url else "?"
    url = f"{update_url}{separator}{urlencode(params)}"

    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(15):
            resp = await session.post(url, auth=aiohttp.BasicAuth(username, password))
            text = (await resp.text()).strip()
        _LOGGER.debug("Config flow validation response: %s", text)
        if resp.status != 200:
            raise CannotConnect
        if text.startswith("badauth"):
            raise InvalidAuth
        if text.startswith("nohost") or text.startswith("notfqdn"):
            raise InvalidHostname
        if text.startswith("911") or text.startswith("abuse"):
            raise CannotConnect
        return {"title": f"Infomaniak DDNS - {hostname}"}
    except TimeoutError as err:
        raise CannotConnect from err
    except aiohttp.ClientError as err:
        raise CannotConnect from err


def _base_schema(defaults: dict, *, require_password: bool = True) -> vol.Schema:
    """Schema step 1 : connexion + mode IP."""
    password_field = (
        vol.Required(CONF_PASSWORD)
        if require_password
        else vol.Optional(CONF_PASSWORD, default="")
    )
    return vol.Schema({
        vol.Optional(CONF_UPDATE_URL, default=defaults.get(CONF_UPDATE_URL, DEFAULT_UPDATE_URL)): str,
        vol.Required(CONF_HOSTNAME, default=defaults.get(CONF_HOSTNAME, "")): str,
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
        password_field: selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(
            CONF_UPDATE_INTERVAL,
            default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
        vol.Optional(CONF_IP_MODE, default=defaults.get(CONF_IP_MODE, IP_MODE_AUTO)):
            selector.selector({"select": {"options": [
                {"value": IP_MODE_AUTO, "label": "Auto - IP WAN détectée par Infomaniak (recommandé)"},
                {"value": IP_MODE_STATIC, "label": "IP fixe - saisie manuelle"},
                {"value": IP_MODE_ENTITY, "label": "Entité HA - lire l'IP depuis un capteur"},
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


def _fast_detection_schema(options: dict) -> vol.Schema:
    """schema pour la détection rapide + rotation de services WAN IP."""
    service_choices = {
        key: value["name"] for key, value in IP_SERVICES_DEFAULT.items()
    }
    default_selected_services = options.get(
        CONF_IP_SERVICES,
        [key for key, value in IP_SERVICES_DEFAULT.items() if value["enabled_default"]],
    )
    custom_services_text = "\n".join(options.get(CONF_CUSTOM_SERVICES, []))

    return vol.Schema({
        vol.Optional(
            CONF_FAST_DETECTION,
            default=options.get(CONF_FAST_DETECTION, False),
        ): bool,
        vol.Optional(
            CONF_FAST_INTERVAL,
            default=options.get(CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL),
        ): vol.All(vol.Coerce(int), vol.Range(min=MIN_FAST_INTERVAL, max=MAX_FAST_INTERVAL)),
        vol.Optional(
            CONF_IP_SERVICES,
            default=default_selected_services,
        ): cv.multi_select(service_choices),
        vol.Optional(
            "custom_services_raw",
            default=custom_services_text,
        ): str,
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
            if not is_valid_ipv4(ip):
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
# ---------------------------------------------------------------------------

class OptionsFlowHandler(config_entries.OptionsFlow):

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_PASSWORD):
                user_input[CONF_PASSWORD] = self.config_entry.data.get(CONF_PASSWORD, "")

            ip_mode = user_input.get(CONF_IP_MODE, IP_MODE_AUTO)

            if ip_mode == IP_MODE_STATIC:
                self._pending = user_input
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
                # Les modifications de données sont appliquées seulement à la
                # dernière étape, pour ne rien écrire si l'utilisateur annule.
                self._pending = merged
                # continue vers l'étape détection rapide / services IP
                return await self.async_step_fast_detection()

        return self.async_show_form(
            step_id="init",
            data_schema=_base_schema(self.config_entry.data, require_password=False),
            errors=errors,
        )

    async def async_step_static_ip(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        pending = getattr(self, "_pending", {})

        if user_input is not None:
            ip = user_input.get(CONF_IP_STATIC, "").strip()
            if not is_valid_ipv4(ip):
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
                    self._pending = merged
                    return await self.async_step_fast_detection()

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
                    self._pending = merged
                    return await self.async_step_fast_detection()

        defaults = {**self.config_entry.data, **pending}
        return self.async_show_form(
            step_id="entity_ip",
            data_schema=_entity_schema(defaults),
            errors=errors,
        )

    async def async_step_fast_detection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """détection rapide de changement d'IP WAN
        et sélection/rotation des services publics de détection d'IP"""
        if user_input is not None:
            custom_raw = user_input.pop("custom_services_raw", "")
            custom_urls = [u.strip() for u in custom_raw.splitlines() if u.strip()]
            valid_custom_urls = [u for u in custom_urls if is_valid_service_url(u)]
            if len(valid_custom_urls) != len(custom_urls):
                _LOGGER.warning(
                    "Certaines URLs personnalisées ont été ignorées (format invalide)"
                )
            user_input[CONF_CUSTOM_SERVICES] = valid_custom_urls

            # Applique maintenant les modifications de données, le flow étant complet.
            if pending := getattr(self, "_pending", None):
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=pending
                )

            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="fast_detection",
            data_schema=_fast_detection_schema(self.config_entry.options),
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
