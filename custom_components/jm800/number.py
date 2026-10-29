"""Numeric camera settings plus a local PTZ speed used by the PTZ buttons."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode, RestoreNumber
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import JM800ConfigEntry, JM800Coordinator, JM800Data
from .entity import JM800Entity


@dataclass(frozen=True, kw_only=True)
class XmlNumberDescription(NumberEntityDescription):
    source: str
    path: str
    attr: str


def _image(key: str, name: str, attr: str, icon: str) -> XmlNumberDescription:
    return XmlNumberDescription(key=key, name=name, icon=icon, source="video", path="Capture", attr=attr,
                                native_min_value=0, native_max_value=255, native_step=1,
                                mode=NumberMode.SLIDER, entity_category=EntityCategory.CONFIG)


NUMBERS = [
    XmlNumberDescription(key="light_brightness", name="Light brightness", icon="mdi:brightness-6",
                         source="video", path="Capture", attr="led_brightness_value",
                         native_min_value=0, native_max_value=100, native_step=1,
                         native_unit_of_measurement=PERCENTAGE, mode=NumberMode.SLIDER),
    XmlNumberDescription(key="motion_sensitivity", name="Motion sensitivity", icon="mdi:tune",
                         source="motion", path=".", attr="Sensitivity",
                         native_min_value=1, native_max_value=100, native_step=1, mode=NumberMode.SLIDER),
    XmlNumberDescription(key="person_sensitivity", name="Person sensitivity", icon="mdi:tune",
                         source="person", path=".", attr="Sensitivity",
                         native_min_value=0, native_max_value=4, native_step=1, mode=NumberMode.SLIDER),
    XmlNumberDescription(key="speaker_volume", name="Speaker volume", icon="mdi:volume-high",
                         source="audio", path="Capture", attr="VolumePlay",
                         native_min_value=1, native_max_value=100, native_step=1,
                         native_unit_of_measurement=PERCENTAGE, mode=NumberMode.SLIDER),
    XmlNumberDescription(key="mic_volume", name="Microphone volume", icon="mdi:microphone",
                         source="audio", path="Capture", attr="Volume",
                         native_min_value=1, native_max_value=100, native_step=1,
                         native_unit_of_measurement=PERCENTAGE, mode=NumberMode.SLIDER,
                         entity_category=EntityCategory.CONFIG),
    _image("image_brightness", "Image brightness", "Brightness", "mdi:brightness-5"),
    _image("image_contrast", "Image contrast", "Contrast", "mdi:contrast-box"),
    _image("image_saturation", "Image saturation", "Saturation", "mdi:palette"),
    _image("image_sharpness", "Image sharpness", "Sharpness", "mdi:image-filter-center-focus"),
]


async def async_setup_entry(hass: HomeAssistant, entry: JM800ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    data = entry.runtime_data
    async_add_entities([*(JM800XmlNumber(data.coordinator, d) for d in NUMBERS), JM800PtzSpeed(data)])


class JM800XmlNumber(JM800Entity, NumberEntity):
    entity_description: XmlNumberDescription

    def __init__(self, coordinator: JM800Coordinator, description: XmlNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        d = self.entity_description
        value = self.xml_attr(d.source, d.path, d.attr)
        try:
            return float(value) if value is not None else None
        except ValueError:
            return None

    async def async_set_native_value(self, value: float) -> None:
        d = self.entity_description
        await self.coordinator.async_set(d.source, d.path, **{d.attr: int(value)})


class JM800PtzSpeed(JM800Entity, RestoreNumber):
    """Not stored on the camera; used by the PTZ buttons."""

    _attr_name = "PTZ speed"
    _attr_icon = "mdi:speedometer"
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, data: JM800Data) -> None:
        super().__init__(data.coordinator, "ptz_speed")
        self._data = data
        self._attr_native_value = 5

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self._attr_native_value = last.native_value
        self._data.extra["ptz_speed"] = int(self._attr_native_value)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self._data.extra["ptz_speed"] = int(value)
        self.async_write_ha_state()
