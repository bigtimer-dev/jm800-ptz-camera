"""One-shot camera actions: PTZ steps, tracking/cruise, lights, sounds, reboot."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import JM800Api, JM800Error
from .const import PRESET_CRUISE_OFF, PRESET_CRUISE_ON, PRESET_HUMAN_TRACE_OFF, PRESET_HUMAN_TRACE_ON
from .coordinator import JM800ConfigEntry, JM800Data
from .entity import JM800Entity


@dataclass(frozen=True, kw_only=True)
class JM800ButtonDescription(ButtonEntityDescription):
    press: Callable[[JM800Api, JM800Data], Awaitable[None]]


def _step(direction: str) -> Callable[[JM800Api, JM800Data], Awaitable[None]]:
    return lambda api, data: api.ptz_step(direction, data.extra.get("ptz_speed", 5), 0.5)


BUTTONS = [
    JM800ButtonDescription(key="ptz_up", name="PTZ up", icon="mdi:arrow-up-bold", press=_step("up")),
    JM800ButtonDescription(key="ptz_down", name="PTZ down", icon="mdi:arrow-down-bold", press=_step("down")),
    JM800ButtonDescription(key="ptz_left", name="PTZ left", icon="mdi:arrow-left-bold", press=_step("left")),
    JM800ButtonDescription(key="ptz_right", name="PTZ right", icon="mdi:arrow-right-bold", press=_step("right")),
    JM800ButtonDescription(key="zoom_in", name="Zoom in", icon="mdi:magnify-plus", press=_step("ZoomTele")),
    JM800ButtonDescription(key="zoom_out", name="Zoom out", icon="mdi:magnify-minus", press=_step("ZoomWide")),
    JM800ButtonDescription(key="ptz_stop", name="PTZ stop", icon="mdi:stop", press=lambda api, _: api.ptz_stop()),
    JM800ButtonDescription(key="tracking_start", name="Auto-tracking start", icon="mdi:target-account",
                           press=lambda api, _: api.preset(*PRESET_HUMAN_TRACE_ON)),
    JM800ButtonDescription(key="tracking_stop", name="Auto-tracking stop", icon="mdi:target",
                           press=lambda api, _: api.preset(*PRESET_HUMAN_TRACE_OFF)),
    JM800ButtonDescription(key="cruise_start", name="Cruise start", icon="mdi:rotate-360",
                           press=lambda api, _: api.preset(*PRESET_CRUISE_ON)),
    JM800ButtonDescription(key="cruise_stop", name="Cruise stop", icon="mdi:rotate-360",
                           press=lambda api, _: api.preset(*PRESET_CRUISE_OFF)),
    JM800ButtonDescription(key="light_on", name="Light on", icon="mdi:lightbulb-on",
                           press=lambda api, _: api.set_light(True)),
    JM800ButtonDescription(key="light_off", name="Light off", icon="mdi:lightbulb-off",
                           press=lambda api, _: api.set_light(False)),
    JM800ButtonDescription(key="day_mode", name="Force day mode", icon="mdi:weather-sunny",
                           press=lambda api, _: api.set_day_night(False)),
    JM800ButtonDescription(key="night_mode", name="Force night mode", icon="mdi:weather-night",
                           press=lambda api, _: api.set_day_night(True)),
    JM800ButtonDescription(key="play_sound", name="Play sound", icon="mdi:play",
                           press=lambda api, data: api.play_audio(data.extra.get("sound", "/opt/ch/alarm/Warning.mp3"))),
    JM800ButtonDescription(key="stop_sound", name="Stop sound", icon="mdi:stop-circle",
                           press=lambda api, _: api.stop_audio()),
    JM800ButtonDescription(key="reboot", name="Reboot", device_class=ButtonDeviceClass.RESTART,
                           entity_category=EntityCategory.CONFIG, press=lambda api, _: api.reboot()),
]


async def async_setup_entry(hass: HomeAssistant, entry: JM800ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    data = entry.runtime_data
    async_add_entities(JM800Button(data, d) for d in BUTTONS)


class JM800Button(JM800Entity, ButtonEntity):
    entity_description: JM800ButtonDescription

    def __init__(self, data: JM800Data, description: JM800ButtonDescription) -> None:
        super().__init__(data.coordinator, description.key)
        self.entity_description = description
        self._data = data

    async def async_press(self) -> None:
        try:
            await self.entity_description.press(self.coordinator.api, self._data)
        except JM800Error as err:
            raise HomeAssistantError(str(err)) from err
