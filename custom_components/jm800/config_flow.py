"""Config flow for the JM800 camera."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import JM800Api, JM800AuthError, JM800Error
from .const import CONF_CONFIGURE_PUSH, CONF_PUSH_URL, DEFAULT_PORT, DOMAIN


async def _validate(hass, data: Mapping[str, Any]) -> dict[str, str]:
    api = JM800Api(async_get_clientsession(hass), data[CONF_HOST], data[CONF_PORT],
                   data[CONF_USERNAME], data[CONF_PASSWORD])
    await api.login()
    return await api.device_info()


class JM800ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _validate(self.hass, user_input)
            except JM800AuthError:
                errors["base"] = "invalid_auth"
            except JM800Error:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["serial"])
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                return self.async_create_entry(title=f"{info['model']} ({user_input[CONF_HOST]})", data=user_input)

        defaults = user_input or {}
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "admin")): str,
            vol.Required(CONF_PASSWORD): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                await _validate(self.hass, data)
            except JM800AuthError:
                errors["base"] = "invalid_auth"
            except JM800Error:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        schema = vol.Schema({
            vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): str,
            vol.Required(CONF_PASSWORD): str,
        })
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return JM800OptionsFlow()


class JM800OptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema({
            vol.Required(CONF_CONFIGURE_PUSH, default=options.get(CONF_CONFIGURE_PUSH, True)): bool,
            vol.Optional(CONF_PUSH_URL, description={"suggested_value": options.get(CONF_PUSH_URL, "")}): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
