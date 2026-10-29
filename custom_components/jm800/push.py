"""Receiver for the camera's "alarm server" HTTP push (person detection and other AI alarms).

Captured payload (POST /HAPI/V1.0/<path>/Event/Notification, User-Agent "HAPI NOTIFY"):
{"AlarmType":"ObjectDetect","AlarmSubType":"HumanShapeDetect","TimeStamp":1767268800,
 "LocalTime":"2026-01-01 12:00:00","ChannelNo":0,"NotificationType":0,"OccurFlag":"true",
 "DeviceID":"EF000000XXXXXXXX","AlarmInfo":{"image":null,"ObjectDetectInfo":null}}
"""
from __future__ import annotations

import json
import logging

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, EVENT_ALARM, PUSH_VIEW_URL, SIGNAL_PUSH

_LOGGER = logging.getLogger(__name__)


class JM800PushView(HomeAssistantView):
    """Unauthenticated (the camera cannot authenticate); only accepts known cameras from their own IP."""

    url = PUSH_VIEW_URL
    name = f"api:{DOMAIN}:push"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def post(self, request: web.Request, tail: str = "") -> web.Response:
        text = await request.text()
        try:
            payload = json.loads(text)
        except ValueError:
            _LOGGER.debug("Ignoring non-JSON push: %r", text[:200])
            return web.Response(text="OK")
        serial = str(payload.get("DeviceID", ""))
        allowed = self.hass.data.get(DOMAIN, {}).get("hosts", {})
        if allowed.get(serial) != request.remote:
            _LOGGER.warning("Ignoring alarm push for %s from %s", serial, request.remote)
            return web.Response(status=403)
        _LOGGER.debug("Alarm push from %s: %s", serial, payload)
        self.hass.bus.async_fire(EVENT_ALARM, {
            "serial": serial,
            "type": payload.get("AlarmType"),
            "subtype": payload.get("AlarmSubType"),
            "active": str(payload.get("OccurFlag")).lower() == "true",
            "timestamp": payload.get("TimeStamp"),
            "raw": payload,
        })
        async_dispatcher_send(self.hass, SIGNAL_PUSH.format(serial), payload)
        return web.Response(text="OK")
