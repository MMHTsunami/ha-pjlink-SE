"""Data update coordinator."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .pjlink import PJLinkAuthError, PJLinkClient, PJLinkError

_LOGGER = logging.getLogger(__name__)


class PJLinkCoordinator(DataUpdateCoordinator[dict]):
    """Polls a projector."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: PJLinkClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self._info: dict = {}

    async def _async_update_data(self) -> dict:
        try:
            data = await self.client.get_state(with_info=not self._info)
        except PJLinkAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PJLinkError as err:
            raise UpdateFailed(str(err)) from err
        if not self._info:
            self._info = {
                k: data[k] for k in ("name", "manufacturer", "model", "sources")
            }
        data.update(self._info)
        return data
