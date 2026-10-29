"""Camera entity (RTSP stream + snapshot) and the PTZ / preset / audio actions."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import voluptuous as vol

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import JM800Error
from .const import PTZ_DIRECTIONS
from .coordinator import JM800ConfigEntry, JM800Coordinator
from .entity import JM800Entity


async def async_setup_entry(hass: HomeAssistant, entry: JM800ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([
        JM800CameraEntity(coordinator, 0),
        JM800CameraEntity(coordinator, 1),
    ])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service("ptz", {
        vol.Required("direction"): vol.In(PTZ_DIRECTIONS + ["stop"]),
        vol.Optional("speed", default=5): vol.All(vol.Coerce(int), vol.Range(1, 10)),
        vol.Optional("duration", default=0.5): vol.All(vol.Coerce(float), vol.Range(0, 30)),
    }, "async_ptz")
    preset = {vol.Required("preset"): vol.All(vol.Coerce(int), vol.Range(1, 255))}
    platform.async_register_entity_service("goto_preset", preset, "async_goto_preset")
    platform.async_register_entity_service("save_preset", preset, "async_save_preset")
    platform.async_register_entity_service("delete_preset", preset, "async_delete_preset")
    platform.async_register_entity_service("play_sound", {
        vol.Optional("file", default="/opt/ch/alarm/Warning.mp3"): cv.string,
    }, "async_play_sound")
    platform.async_register_entity_service("stop_sound", {}, "async_stop_sound")
    platform.async_register_entity_service("set_day_night", {
        vol.Required("mode"): vol.In(["day", "night"]),
    }, "async_set_day_night")
    platform.async_register_entity_service("set_light", {
        vol.Required("on"): cv.boolean,
    }, "async_set_light")
    platform.async_register_entity_service("raw_command", {
        vol.Required("endpoint"): cv.matches_regex(r"^[A-Za-z0-9_]+$"),
        vol.Optional("body", default=""): cv.string,
    }, "async_raw_command", supports_response=SupportsResponse.OPTIONAL)


class JM800CameraEntity(JM800Entity, Camera):
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator: JM800Coordinator, stream: int) -> None:
        JM800Entity.__init__(self, coordinator, f"camera_{stream}")
        Camera.__init__(self)
        self._stream = stream
        self._attr_name = None if stream == 0 else "Sub stream"
        self._attr_entity_registry_enabled_default = stream == 0

    @property
    def api(self):
        return self.coordinator.api

    async def stream_source(self) -> str | None:
        return self.api.rtsp_url(self._stream)

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        try:
            return await self.api.snapshot(self._stream)
        except Exception:  # noqa: BLE001 - a missed frame should not raise into the UI
            return None

    async def _run(self, coro) -> None:
        try:
            await coro
        except JM800Error as err:
            raise HomeAssistantError(str(err)) from err

    async def async_ptz(self, direction: str, speed: int = 5, duration: float = 0.5) -> None:
        if direction == "stop":
            await self._run(self.api.ptz_stop())
        elif duration == 0:
            await self._run(self.api.ptz_move(direction, speed))  # keeps moving until "stop"
        else:
            await self._run(self.api.ptz_step(direction, speed, duration))

    async def async_goto_preset(self, preset: int) -> None:
        await self._run(self.api.preset("callpreset", preset))

    async def async_save_preset(self, preset: int) -> None:
        await self._run(self.api.preset("setpreset", preset))
        await self.coordinator.async_request_refresh()

    async def async_delete_preset(self, preset: int) -> None:
        await self._run(self.api.preset("clearpreset", preset))
        await self.coordinator.async_request_refresh()

    async def async_play_sound(self, file: str) -> None:
        await self._run(self.api.play_audio(file))

    async def async_stop_sound(self) -> None:
        await self._run(self.api.stop_audio())

    async def async_set_day_night(self, mode: str) -> None:
        await self._run(self.api.set_day_night(mode == "night"))

    async def async_set_light(self, on: bool) -> None:
        await self._run(self.api.set_light(on))

    async def async_raw_command(self, endpoint: str, body: str = "") -> ServiceResponse:
        try:
            text = await self.api.call(endpoint, body)
        except JM800Error as err:
            raise HomeAssistantError(str(err)) from err
        try:
            root = ET.fromstring(text.strip())
            return {"response": text, "root": root.tag, "attributes": dict(root.attrib)}
        except ET.ParseError:
            return {"response": text}
