"""Power status sensor."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PJLinkConfigEntry
from .entity import PJLinkEntity

# PJLink POWR values; the Hitachi client reports the same codes (no warm-up).
POWER_STATUS = {"0": "standby", "1": "on", "2": "cooling_down", "3": "warming_up"}


async def async_setup_entry(
    hass: HomeAssistant, entry: PJLinkConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the status sensor."""
    async_add_entities([PowerStatusSensor(entry.runtime_data)])


class PowerStatusSensor(PJLinkEntity, SensorEntity):
    """Standby, on, warming up or cooling down."""

    _attr_translation_key = "power_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(POWER_STATUS.values())

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "power_status")

    @property
    def native_value(self) -> str | None:
        return POWER_STATUS.get(self.coordinator.data.get("power"))
