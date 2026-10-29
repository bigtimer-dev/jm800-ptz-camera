"""On/off settings stored in the camera's XML configuration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import JM800ConfigEntry, JM800Coordinator
from .entity import JM800Entity


@dataclass(frozen=True, kw_only=True)
class XmlSwitchDescription(SwitchEntityDescription):
    source: str
    path: str
    attr: str


# Schedule-style flags use 0=off, 1=all day, 2=day, 3=night, 4=custom; anything but 0 counts as on.
SWITCHES = [
    XmlSwitchDescription(key="motion_detection", name="Motion detection", icon="mdi:motion-sensor",
                         source="motion", path=".", attr="Enable"),
    XmlSwitchDescription(key="person_detection", name="Person detection", icon="mdi:account-search",
                         source="person", path=".", attr="Enable"),
    XmlSwitchDescription(key="person_tracking", name="Person tracking", icon="mdi:target-account",
                         source="person", path="AlarmAction", attr="track_human"),
    XmlSwitchDescription(key="person_auto_zoom", name="Person auto zoom", icon="mdi:magnify-plus",
                         source="person", path="AlarmAction", attr="auto_zoom"),
    XmlSwitchDescription(key="person_box", name="Draw person box", icon="mdi:selection",
                         source="person", path="AlarmAction", attr="draw_human",
                         entity_category=EntityCategory.CONFIG),
    XmlSwitchDescription(key="person_light_flash", name="Person alarm light flash", icon="mdi:alarm-light",
                         source="person", path="AlarmAction", attr="light_twinkle"),
    XmlSwitchDescription(key="person_alarm_sound", name="Person alarm sound", icon="mdi:bullhorn",
                         source="person", path="AlarmAction/AudioPlayAction", attr="Enable"),
    XmlSwitchDescription(key="motion_light_flash", name="Motion alarm light flash", icon="mdi:alarm-light",
                         source="motion", path="AlarmAction", attr="light_twinkle"),
    XmlSwitchDescription(key="motion_alarm_sound", name="Motion alarm sound", icon="mdi:bullhorn",
                         source="motion", path="AlarmAction/AudioPlayAction", attr="Enable"),
    XmlSwitchDescription(key="flip_horizontal", name="Flip horizontal", icon="mdi:flip-horizontal",
                         source="video", path="Capture", attr="HFlip", entity_category=EntityCategory.CONFIG),
    XmlSwitchDescription(key="flip_vertical", name="Flip vertical", icon="mdi:flip-vertical",
                         source="video", path="Capture", attr="VFlip", entity_category=EntityCategory.CONFIG),
]


async def async_setup_entry(hass: HomeAssistant, entry: JM800ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(JM800XmlSwitch(coordinator, d) for d in SWITCHES)


class JM800XmlSwitch(JM800Entity, SwitchEntity):
    entity_description: XmlSwitchDescription

    def __init__(self, coordinator: JM800Coordinator, description: XmlSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        d = self.entity_description
        value = self.xml_attr(d.source, d.path, d.attr)
        return None if value is None else value.strip() not in ("0", "")

    async def _write(self, value: int) -> None:
        d = self.entity_description
        await self.coordinator.async_set(d.source, d.path, **{d.attr: value})

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._write(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._write(0)
