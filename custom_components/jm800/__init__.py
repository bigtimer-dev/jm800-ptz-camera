"""JM800 PTZ camera integration (private XML API + ONVIF events + alarm push)."""
from __future__ import annotations

import logging

from homeassistant.components.network import async_get_source_ip
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import JM800Api, JM800AuthError, JM800Error, OnvifEvents
from .const import CONF_CONFIGURE_PUSH, CONF_PUSH_URL, DOMAIN, PUSH_URL_PATH, SIGNAL_MOTION
from .coordinator import JM800ConfigEntry, JM800Coordinator, JM800Data
from .push import JM800PushView

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

MOTION_TOPIC = "RuleEngine/CellMotionDetector/Motion"


async def async_setup_entry(hass: HomeAssistant, entry: JM800ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = JM800Api(session, entry.data[CONF_HOST], entry.data[CONF_PORT],
                   entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    try:
        await api.login()
        info = await api.device_info()
    except JM800AuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except JM800Error as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = JM800Coordinator(hass, entry, api, info)
    await coordinator.async_config_entry_first_refresh()
    data = JM800Data(coordinator)
    entry.runtime_data = data

    domain_data = hass.data.setdefault(DOMAIN, {"hosts": {}})
    if not domain_data.get("view"):
        hass.http.register_view(JM800PushView(hass))
        domain_data["view"] = True
    domain_data["hosts"][info["serial"]] = api.host

    if entry.options.get(CONF_CONFIGURE_PUSH, True):
        await _configure_push(hass, entry, api, coordinator)

    @callback
    def on_onvif_event(topic: str, items: dict[str, str]) -> None:
        if topic == MOTION_TOPIC and "IsMotion" in items:
            data.motion = items["IsMotion"] == "true"
            async_dispatcher_send(hass, SIGNAL_MOTION.format(info["serial"]))

    data.events = OnvifEvents(session, api.host, api.port, on_onvif_event)
    entry.async_create_background_task(hass, data.events.run(), f"{DOMAIN} onvif events {api.host}")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _configure_push(hass: HomeAssistant, entry: JM800ConfigEntry, api: JM800Api,
                          coordinator: JM800Coordinator) -> None:
    """Point the camera's alarm server at this Home Assistant and enable it for person detection."""
    base = entry.options.get(CONF_PUSH_URL)
    if not base:
        ip = await async_get_source_ip(hass, target_ip=api.host)
        base = f"http://{ip}:{hass.http.server_port}"
    url = base.rstrip("/") + PUSH_URL_PATH
    try:
        if await api.alarm_server_url() != url:
            _LOGGER.info("Setting %s alarm server to %s", api.host, url)
            await api.set_alarm_server(url)
        action = coordinator.data["person"].find("AlarmAction")
        if action is not None and action.get("notify_alarmserver", "0") == "0":
            await coordinator.async_set("person", "AlarmAction", notify_alarmserver=1)
    except JM800Error as err:
        _LOGGER.warning("Could not configure alarm push on %s: %s", api.host, err)


async def _async_reload(hass: HomeAssistant, entry: JM800ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: JM800ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        if entry.runtime_data.events:
            await entry.runtime_data.events.unsubscribe()
        hass.data[DOMAIN]["hosts"].pop(entry.runtime_data.coordinator.serial, None)
    return unloaded
