"""Input source select."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PJLinkConfigEntry
from .entity import PJLinkEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PJLinkConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the source select."""
    async_add_entities([SourceSelect(entry.runtime_data)])


class SourceSelect(PJLinkEntity, SelectEntity):
    """Select the projector input."""

    _attr_translation_key = "source"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "source")

    @property
    def _sources(self) -> dict[str, str]:
        return self.coordinator.data.get("sources", {})

    @property
    def options(self) -> list[str]:
        return list(self._sources.values())

    @property
    def current_option(self) -> str | None:
        return self._sources.get(self.coordinator.data.get("input"))

    async def async_select_option(self, option: str) -> None:
        for code, name in self._sources.items():
            if name == option:
                await self._run(self.coordinator.client.set_input(code))
                return
