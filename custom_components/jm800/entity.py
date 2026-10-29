"""Base entity for the JM800 camera."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JM800Coordinator


class JM800Entity(CoordinatorEntity[JM800Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: JM800Coordinator, key: str) -> None:
        super().__init__(coordinator)
        info = coordinator.info
        self._attr_unique_id = f"{coordinator.serial}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial)},
            manufacturer="ONVIF_ICAMERA",
            model=info["model"],
            name="JM800 Camera",
            serial_number=coordinator.serial,
            sw_version=info["firmware"],
            configuration_url=coordinator.api.base,
        )

    def xml_attr(self, source: str, path: str, attr: str) -> str | None:
        """Attribute from one of the coordinator's settings documents."""
        root: ET.Element | None = (self.coordinator.data or {}).get(source)
        if root is None:
            return None
        el = root if path == "." else root.find(path)
        return None if el is None else el.get(attr)
