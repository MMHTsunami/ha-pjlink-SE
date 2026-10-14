"""Volume up/down buttons (PJLink class 2 only)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PJLinkConfigEntry
from .entity import PJLinkEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PJLinkConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up volume buttons for class 2 projectors."""
    c = entry.runtime_data
    if c.data.get("class", 1) >= 2:
        async_add_entities([VolumeButton(c, True), VolumeButton(c, False)])


class VolumeButton(PJLinkEntity, ButtonEntity):
    """Step the volume."""

    def __init__(self, coordinator, up: bool) -> None:
        key = "volume_up" if up else "volume_down"
        super().__init__(coordinator, key)
        self._up = up
        self._attr_translation_key = key

    async def async_press(self) -> None:
        await self._run(self.coordinator.client.volume(self._up))
