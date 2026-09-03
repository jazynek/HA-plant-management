"""Config flow for Plant Management."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_CHECK_TIME,
    CONF_NOTIFY_SERVICE,
    DEFAULT_CHECK_TIME,
    DOMAIN,
)


class PlantManagementConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow: this integration manages all plants as one hub."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="Zarządzanie roślinami", data={}, options=user_input)

        schema = vol.Schema(
            {
                vol.Optional(CONF_NOTIFY_SERVICE, default=""): str,
                vol.Optional(CONF_CHECK_TIME, default=DEFAULT_CHECK_TIME): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PlantManagementOptionsFlow(config_entry)


class PlantManagementOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_NOTIFY_SERVICE, default=options.get(CONF_NOTIFY_SERVICE, "")
                ): str,
                vol.Optional(
                    CONF_CHECK_TIME, default=options.get(CONF_CHECK_TIME, DEFAULT_CHECK_TIME)
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
