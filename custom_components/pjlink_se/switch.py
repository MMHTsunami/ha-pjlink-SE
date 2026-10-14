"""Power, audio mute and video mute switches."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PJLinkConfigEntry
from .entity import PJLinkEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: PJLinkConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up switches."""
    c = entry.runtime_data
    async_add_entities([PowerSwitch(c), MuteSwitch(c, "audio"), MuteSwitch(c, "video")])


class PowerSwitch(PJLinkEntity, SwitchEntity):
    """Projector power (on while warming up)."""

    _attr_translation_key = "power"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def is_on(self) -> bool | None:
        p = self.coordinator.data.get("power")
        return None if p is None else p in ("1", "3")

    async def async_turn_on(self, **kwargs) -> None:
        await self._run(self.coordinator.client.set_power(True))

    async def async_turn_off(self, **kwargs) -> None:
        await self._run(self.coordinator.client.set_power(False))


class MuteSwitch(PJLinkEntity, SwitchEntity):
    """Audio or video mute."""

    def __init__(self, coordinator, kind: str) -> None:
        super().__init__(coordinator, f"{kind}_mute")
        self._kind = kind
        self._base = "2" if kind == "audio" else "1"
        self._attr_translation_key = f"{kind}_mute"

    @property
    def is_on(self) -> bool | None:
        m = self.coordinator.data.get("mute")
        if m is None:
            return None
        return m in (self._base + "1", "31")

    async def async_turn_on(self, **kwargs) -> None:
        await self._run(self.coordinator.client.set_mute(self._base + "1"))

    async def async_turn_off(self, **kwargs) -> None:
        await self._run(self.coordinator.client.set_mute(self._base + "0"))
