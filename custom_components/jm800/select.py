"""Mode selects stored on the camera, plus preset and sound pickers."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import JM800Error
from .const import IR_CUT_MODES, LIGHT_BRIGHTNESS_MODES, LIGHT_TYPES
from .coordinator import JM800ConfigEntry, JM800Coordinator, JM800Data
from .entity import JM800Entity


@dataclass(frozen=True, kw_only=True)
class XmlSelectDescription(SelectEntityDescription):
    source: str
    path: str
    attr: str
    values: dict[str, str] | None = None  # camera value -> label; None = audio file list


SELECTS = [
    XmlSelectDescription(key="ir_mode", name="Day/night mode", icon="mdi:theme-light-dark",
                         source="video", path="Capture", attr="IrcutMode", values=IR_CUT_MODES),
    XmlSelectDescription(key="light_type", name="Light type", icon="mdi:lightbulb-on",
                         source="video", path="Capture", attr="led_mode", values=LIGHT_TYPES),
    XmlSelectDescription(key="light_brightness_mode", name="Light brightness mode", icon="mdi:brightness-auto",
                         source="video", path="Capture", attr="led_brightness_mode",
                         values=LIGHT_BRIGHTNESS_MODES),
    XmlSelectDescription(key="person_alarm_sound_file", name="Person alarm sound file", icon="mdi:music-note",
                         source="person", path="AlarmAction/AudioPlayAction", attr="FileName",
                         entity_category=EntityCategory.CONFIG),
    XmlSelectDescription(key="motion_alarm_sound_file", name="Motion alarm sound file", icon="mdi:music-note",
                         source="motion", path="AlarmAction/AudioPlayAction", attr="FileName",
                         entity_category=EntityCategory.CONFIG),
]


def _label(path: str) -> str:
    return path.rsplit("/alarm/", 1)[-1]


async def async_setup_entry(hass: HomeAssistant, entry: JM800ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    data = entry.runtime_data
    async_add_entities([
        *(JM800XmlSelect(data.coordinator, d) for d in SELECTS),
        JM800PresetSelect(data.coordinator),
        JM800SoundSelect(data),
    ])


class JM800XmlSelect(JM800Entity, SelectEntity):
    entity_description: XmlSelectDescription

    def __init__(self, coordinator: JM800Coordinator, description: XmlSelectDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    def _values(self) -> dict[str, str]:
        if self.entity_description.values is not None:
            return self.entity_description.values
        return {path: _label(path) for path in self.coordinator.audio_files}

    @property
    def options(self) -> list[str]:
        return list(self._values().values())

    @property
    def current_option(self) -> str | None:
        d = self.entity_description
        value = self.xml_attr(d.source, d.path, d.attr)
        return self._values().get(value) if value is not None else None

    async def async_select_option(self, option: str) -> None:
        d = self.entity_description
        value = next(k for k, v in self._values().items() if v == option)
        await self.coordinator.async_set(d.source, d.path, **{d.attr: value})


class JM800PresetSelect(JM800Entity, SelectEntity):
    """Choosing a preset moves the camera there."""

    _attr_name = "Go to preset"
    _attr_icon = "mdi:map-marker-radius"
    _attr_current_option = None

    def __init__(self, coordinator: JM800Coordinator) -> None:
        super().__init__(coordinator, "preset")

    @property
    def options(self) -> list[str]:
        root = (self.coordinator.data or {}).get("presets")
        if root is None:
            return []
        return [p.text for p in root.iter("p") if p.text]

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.api.preset("callpreset", int(option))
        except JM800Error as err:
            raise HomeAssistantError(str(err)) from err


class JM800SoundSelect(JM800Entity, SelectEntity):
    """Which built-in sound the "Play sound" button plays (kept in Home Assistant only)."""

    _attr_name = "Sound to play"
    _attr_icon = "mdi:playlist-music"

    def __init__(self, data: JM800Data) -> None:
        super().__init__(data.coordinator, "sound")
        self._data = data
        self._data.extra.setdefault("sound", "/opt/ch/alarm/Warning.mp3")

    @property
    def options(self) -> list[str]:
        return [_label(p) for p in self.coordinator.audio_files]

    @property
    def current_option(self) -> str | None:
        return _label(self._data.extra["sound"])

    async def async_select_option(self, option: str) -> None:
        self._data.extra["sound"] = next(p for p in self.coordinator.audio_files if _label(p) == option)
        self.async_write_ha_state()
