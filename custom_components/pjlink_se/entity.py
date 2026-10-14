"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PJLinkCoordinator


class PJLinkEntity(CoordinatorEntity[PJLinkCoordinator]):
    """Entity bound to a projector device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PJLinkCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        data = coordinator.data or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
        )

    async def _run(self, coro) -> None:
        from homeassistant.exceptions import HomeAssistantError

        from .pjlink import PJLinkError

        try:
            await coro
        except PJLinkError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
