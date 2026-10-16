"""Config flow for PJLink SE."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT

from .const import (
    CONF_PROTOCOL,
    DEFAULT_HITACHI_PORT,
    DEFAULT_PORT,
    DOMAIN,
    PROTOCOL_HITACHI,
    PROTOCOL_PJLINK,
    TIMEOUT,
)
from .hitachi import HitachiClient
from .pjlink import PJLinkAuthError, PJLinkClient, PJLinkError


_LOGGER = logging.getLogger(__name__)


class PJLinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the control protocol."""
        return self.async_show_menu(
            step_id="user", menu_options=[PROTOCOL_PJLINK, PROTOCOL_HITACHI]
        )

    async def async_step_pjlink(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_connect_step(
            PROTOCOL_PJLINK, PJLinkClient, DEFAULT_PORT, user_input
        )

    async def async_step_hitachi(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_connect_step(
            PROTOCOL_HITACHI, HitachiClient, DEFAULT_HITACHI_PORT, user_input
        )

    async def _async_connect_step(
        self,
        protocol: str,
        client_cls: type[PJLinkClient] | type[HitachiClient],
        default_port: int,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            self._async_abort_entries_match({CONF_HOST: host, CONF_PORT: port})
            password = user_input.get(CONF_PASSWORD) or None
            try:
                info = await client_cls(host, port, password, TIMEOUT).get_info()
            except PJLinkAuthError:
                errors["base"] = "invalid_auth"
            except PJLinkError as err:
                _LOGGER.warning("%s setup for %s:%s failed: %s", protocol, host, port, err)
                errors["base"] = "cannot_connect"
            else:
                data = {CONF_HOST: host, CONF_PORT: port, CONF_PROTOCOL: protocol}
                if password:
                    data[CONF_PASSWORD] = password
                return self.async_create_entry(
                    title=info.get("name") or host, data=data
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=default_port): int,
                vol.Optional(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id=protocol, data_schema=schema, errors=errors)
