"""Config flow for PJLink SE."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT

from .const import DEFAULT_PORT, DOMAIN, TIMEOUT
from .pjlink import PJLinkAuthError, PJLinkClient, PJLinkError


class PJLinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            self._async_abort_entries_match({CONF_HOST: host, CONF_PORT: port})
            password = user_input.get(CONF_PASSWORD) or None
            try:
                info = await PJLinkClient(host, port, password, TIMEOUT).get_info()
            except PJLinkAuthError:
                errors["base"] = "invalid_auth"
            except PJLinkError:
                errors["base"] = "cannot_connect"
            else:
                data = {CONF_HOST: host, CONF_PORT: port}
                if password:
                    data[CONF_PASSWORD] = password
                return self.async_create_entry(
                    title=info.get("name") or host, data=data
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
