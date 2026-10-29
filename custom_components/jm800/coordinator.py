"""Polling coordinator holding the camera's settings documents."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import JM800Api, JM800AuthError, JM800Error, OnvifEvents
from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class JM800Coordinator(DataUpdateCoordinator[dict[str, ET.Element]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: JM800Api, info: dict[str, str]) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {api.host}",
                         update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS))
        self.api = api
        self.info = info
        self.serial = info["serial"]
        self.audio_files: list[str] = []

    async def _async_update_data(self) -> dict[str, ET.Element]:
        try:
            if not self.audio_files:
                self.audio_files = await self.api.audio_files()
            return await self.api.fetch_state()
        except JM800AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except JM800Error as err:
            raise UpdateFailed(str(err)) from err

    async def async_set(self, key: str, path: str, **attrs: str | int) -> None:
        """Write attributes on a settings document and publish the result without waiting for a poll."""
        try:
            root = await self.api.set_attrs(key, path, {k: str(v) for k, v in attrs.items()})
        except JM800Error as err:
            raise HomeAssistantError(f"Could not change {key}: {err}") from err
        self.async_set_updated_data({**self.data, key: root})


@dataclass
class JM800Data:
    coordinator: JM800Coordinator
    events: OnvifEvents | None = None
    motion: bool = False
    extra: dict = field(default_factory=dict)


type JM800ConfigEntry = ConfigEntry[JM800Data]
