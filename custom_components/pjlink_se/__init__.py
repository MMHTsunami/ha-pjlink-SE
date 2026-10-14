"""The PJLink SE integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import TIMEOUT
from .coordinator import PJLinkCoordinator
from .pjlink import PJLinkClient

PLATFORMS = [Platform.SWITCH, Platform.SELECT, Platform.BUTTON]

type PJLinkConfigEntry = ConfigEntry[PJLinkCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PJLinkConfigEntry) -> bool:
    """Set up a projector from a config entry."""
    client = PJLinkClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_PASSWORD),
        TIMEOUT,
    )
    coordinator = PJLinkCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PJLinkConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
