"""Motion (ONVIF events) and person (alarm push) sensors."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import PERSON_AUTO_OFF, SIGNAL_MOTION, SIGNAL_PUSH
from .coordinator import JM800ConfigEntry, JM800Data
from .entity import JM800Entity


async def async_setup_entry(hass: HomeAssistant, entry: JM800ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    data = entry.runtime_data
    async_add_entities([JM800MotionSensor(data), JM800PersonSensor(data)])


class JM800MotionSensor(JM800Entity, BinarySensorEntity):
    _attr_name = "Motion"
    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, data: JM800Data) -> None:
        super().__init__(data.coordinator, "motion")
        self._data = data

    @property
    def is_on(self) -> bool:
        return self._data.motion

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(
            self.hass, SIGNAL_MOTION.format(self.coordinator.serial), self.async_write_ha_state))


class JM800PersonSensor(JM800Entity, BinarySensorEntity):
    _attr_name = "Person"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_icon = "mdi:human"

    def __init__(self, data: JM800Data) -> None:
        super().__init__(data.coordinator, "person")
        self._attr_is_on = False
        self._cancel_off: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(
            self.hass, SIGNAL_PUSH.format(self.coordinator.serial), self._on_push))
        self.async_on_remove(self._cancel_timer)

    @callback
    def _cancel_timer(self) -> None:
        if self._cancel_off:
            self._cancel_off()
            self._cancel_off = None

    @callback
    def _on_push(self, payload: dict[str, Any]) -> None:
        if payload.get("AlarmSubType") != "HumanShapeDetect":
            return
        self._cancel_timer()
        self._attr_is_on = str(payload.get("OccurFlag")).lower() == "true"
        if self._attr_is_on:
            self._cancel_off = async_call_later(self.hass, PERSON_AUTO_OFF, self._auto_off)
        self.async_write_ha_state()

    @callback
    def _auto_off(self, _now) -> None:
        self._cancel_off = None
        self._attr_is_on = False
        self.async_write_ha_state()
