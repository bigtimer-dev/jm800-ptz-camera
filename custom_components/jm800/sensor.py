"""Storage, clock and preset sensors."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import JM800ConfigEntry, JM800Coordinator
from .entity import JM800Entity


@dataclass(frozen=True, kw_only=True)
class JM800SensorDescription(SensorEntityDescription):
    value: Callable[[JM800Entity], Any]
    attributes: Callable[[JM800Entity], dict[str, Any]] | None = None


def _presets(entity: JM800Entity) -> list[int]:
    root = (entity.coordinator.data or {}).get("presets")
    return [] if root is None else [int(p.text) for p in root.iter("p") if p.text and p.text.isdigit()]


def _storage(entity: JM800Entity) -> dict[str, Any]:
    root = (entity.coordinator.data or {}).get("storage")
    return {} if root is None else {child.tag: dict(child.attrib) for child in root}


SENSORS = [
    JM800SensorDescription(
        key="sd_usage", name="SD card usage", icon="mdi:sd", native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda e: e.xml_attr("storage", "sd1", "percent"),
        attributes=lambda e: _storage(e),
    ),
    JM800SensorDescription(
        key="sd_status", name="SD card", icon="mdi:sd", entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda e: "mounted" if e.xml_attr("storage", "sd1", "mounted") == "1" else "not mounted",
    ),
    JM800SensorDescription(
        key="camera_time", name="Camera clock", icon="mdi:clock-outline", entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda e: e.xml_attr("time", ".", "CurTime"),
        attributes=lambda e: {
            "time_mode": e.xml_attr("time", ".", "TimeMode"),
            "ntp_server": e.xml_attr("time", "NTPConfig", "ServerIP"),
            "timezone_code": e.xml_attr("time", ".", "TimeZone"),
        },
    ),
    JM800SensorDescription(
        key="presets", name="PTZ presets", icon="mdi:map-marker-multiple",
        value=lambda e: len(_presets(e)),
        attributes=lambda e: {"presets": _presets(e)},
    ),
]


async def async_setup_entry(hass: HomeAssistant, entry: JM800ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(JM800Sensor(coordinator, d) for d in SENSORS)


class JM800Sensor(JM800Entity, SensorEntity):
    entity_description: JM800SensorDescription

    def __init__(self, coordinator: JM800Coordinator, description: JM800SensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attributes
        return fn(self) if fn else None
