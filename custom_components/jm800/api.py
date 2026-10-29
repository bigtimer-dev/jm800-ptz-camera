"""Async client for the JM800 camera's private XML API and ONVIF events."""
from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from urllib.parse import quote

import aiohttp

from .const import SOURCES
from .des import encrypt_credential

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=10)
# The server answers with a SOAP fault unless the Content-Type is exactly this (no charset).
_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}


class JM800Error(Exception):
    """Communication error."""


class JM800AuthError(JM800Error):
    """Wrong credentials or account locked."""


class JM800Api:
    """One camera. Every request carries the DES-obfuscated credentials; there is no session."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, username: str, password: str) -> None:
        self.session = session
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.base = f"http://{host}:{port}"
        self._uid = encrypt_credential(_escape(username))
        self._pwd = encrypt_credential(_escape(password))
        # The camera's web server is small; serialize requests to it.
        self._lock = asyncio.Lock()

    def _envelope(self, body: str) -> str:
        return ('<?xml version="1.0"?><soap:Envelope xmlns:soap="http://www.w3.org/2001/12/soap-envelope">'
                f"<soap:Header>\t<userid>{self._uid}</userid>\t<passwd>{self._pwd}</passwd></soap:Header>"
                f"<soap:Body>{body}</soap:Body></soap:Envelope>")

    async def call(self, endpoint: str, body: str = "") -> str:
        """POST an envelope to /<endpoint>; return the response text."""
        data = self._envelope(body).encode()
        async with self._lock:
            for attempt in range(2):
                try:
                    async with self.session.post(f"{self.base}/{endpoint}", data=data, timeout=TIMEOUT,
                                                 headers=_HEADERS) as resp:
                        text = await resp.text(errors="replace")
                    break
                except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                    # The camera occasionally resets a connection right after a settings change.
                    if attempt:
                        raise JM800Error(f"{endpoint}: {err}") from err
                    await asyncio.sleep(1)
        stripped = text.strip()
        if stripped in ("passwordError", "passwordLock"):
            raise JM800AuthError(stripped)
        return text

    async def get_xml(self, endpoint: str) -> ET.Element:
        text = (await self.call(endpoint)).strip()
        try:
            return ET.fromstring(text)
        except ET.ParseError as err:
            raise JM800Error(f"{endpoint}: unparsable response {text[:120]!r}") from err

    async def update(self, key: str, mutate: Callable[[ET.Element], None]) -> ET.Element:
        """Read-modify-write a settings document, the way the web UI saves; returns the new document."""
        get_ep, set_ep = SOURCES[key]
        root = await self.get_xml(get_ep)
        mutate(root)
        await self.call(set_ep, ET.tostring(root, encoding="unicode"))
        return root

    async def set_attrs(self, key: str, path: str, attrs: dict[str, str]) -> ET.Element:
        def mutate(root: ET.Element) -> None:
            el = root if path == "." else root.find(path)
            if el is None:
                raise JM800Error(f"{key}: element {path} not found")
            for name, value in attrs.items():
                el.set(name, str(value))
        return await self.update(key, mutate)

    # -- info
    async def login(self) -> None:
        text = await self.call("ipcLogin")
        if "<SystemFunction" not in text:
            raise JM800Error(f"unexpected login response {text[:120]!r}")

    async def device_info(self) -> dict[str, str]:
        root = await self.get_xml("getSystemVersionInfo")
        version, serial = root.find("VersionInfo"), root.find("SerialNumber")
        firmware = (version.get("fsVersion") or "").strip()
        return {
            "serial": serial.get("serialNumber"),
            "firmware": firmware,
            "model": firmware.split("_V")[0] if "_V" in firmware else "JM800",
        }

    async def fetch_state(self) -> dict[str, ET.Element]:
        return {key: await self.get_xml(get_ep) for key, (get_ep, _) in SOURCES.items()}

    async def audio_files(self) -> list[str]:
        return [f.get("path") for f in (await self.get_xml("getAudioActionFiles")).iter("File")]

    # -- media
    def rtsp_url(self, stream: int = 0) -> str:
        return (f"rtsp://{quote(self.username, safe='')}:{quote(self.password, safe='')}"
                f"@{self.host}:554/stream{stream}")

    async def snapshot(self, stream: int = 0) -> bytes:
        async with self.session.get(f"{self.base}/cgi-bin/snapshot.cgi?stream={stream}", timeout=TIMEOUT) as resp:
            resp.raise_for_status()
            return await resp.read()

    # -- PTZ
    async def ptz_move(self, direction: str, speed: int = 5) -> None:
        await self.call("setPTZCmd", f"<xml><cmd>{direction}</cmd><panspeed>{speed}</panspeed>"
                                     f"<tiltspeed>{speed}</tiltspeed></xml>")

    async def ptz_stop(self) -> None:
        await self.call("setPTZCmd", "<xml><cmd>stop</cmd></xml>")

    async def ptz_step(self, direction: str, speed: int = 5, duration: float = 0.5) -> None:
        await self.ptz_move(direction, speed)
        try:
            await asyncio.sleep(duration)
        finally:
            await self.ptz_stop()

    async def preset(self, action: str, number: int) -> None:
        """action: callpreset | setpreset | clearpreset."""
        flag = "<flag>1</flag>" if action == "setpreset" else ""
        await self.call("PresetList", f"<xml><cmd>{action}</cmd><preset>{number}</preset>{flag}</xml>")

    # -- lights / day-night
    async def set_day_night(self, night: bool) -> None:
        await self.call("setIRCutManual_DayNight", "NightMode" if night else "DayMode")

    async def set_light(self, on: bool) -> None:
        await self.call("setLed_KeepOn_Off", "KeepOn" if on else "KeepOff")

    # -- audio
    async def play_audio(self, path: str) -> None:
        await self.call("playAudioActionFile", path)

    async def stop_audio(self) -> None:
        await self.call("stopAudioActionFile")

    # -- alarm push
    async def alarm_server_url(self) -> str:
        return (await self.get_xml("getAlarmServerConfig")).get("url") or ""

    async def set_alarm_server(self, url: str) -> None:
        await self.call("setNetworkAlarmServerConfig",
                        f'<AlarmServerConfig url="{url}" Username="" Password="" withattachment="0" />')

    # -- system
    async def reboot(self) -> None:
        await self.call("SystemMaintain",
                        "<SystemMaintain><Order>SystemReboot</Order><Value></Value></SystemMaintain>")


def _escape(text: str) -> str:
    # checkLoginStr() in the web UI
    return text.replace("\\", "\\\\").replace('"', '\\"')


# ------------------------------------------------------------------- ONVIF --

_SOAP = ('<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
         'xmlns:a="http://www.w3.org/2005/08/addressing"><s:Header>{header}</s:Header><s:Body>{body}</s:Body>'
         '</s:Envelope>')
_EVENTS_NS = "http://www.onvif.org/ver10/events/wsdl"
_NOTIFICATION_RE = re.compile(r"<wsnt:NotificationMessage>.*?</wsnt:NotificationMessage>", re.S)
_TOPIC_RE = re.compile(r"<wsnt:Topic[^>]*>([^<]+)")
_ITEM_RE = re.compile(r'SimpleItem Name="([^"]+)" Value="([^"]*)"')


class OnvifEvents:
    """Minimal ONVIF PullPoint consumer (the camera has ONVIF auth disabled)."""

    SUBSCRIPTION_SECONDS = 600

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int,
                 on_event: Callable[[str, dict[str, str]], None]) -> None:
        self.session = session
        self.events_url = f"http://{host}:{port}/onvif/events"
        self.on_event = on_event
        self._address: str | None = None

    async def _soap(self, url: str, body: str, action: str = "", timeout: float = 10) -> str:
        header = f"<a:Action>{action}</a:Action><a:To>{url}</a:To>" if action else ""
        async with self.session.post(
            url, data=_SOAP.format(header=header, body=body).encode(),
            headers={"Content-Type": "application/soap+xml"},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            return await resp.text(errors="replace")

    async def _subscribe(self) -> None:
        text = await self._soap(
            self.events_url,
            f'<CreatePullPointSubscription xmlns="{_EVENTS_NS}"><InitialTerminationTime>'
            f"PT{self.SUBSCRIPTION_SECONDS}S</InitialTerminationTime></CreatePullPointSubscription>",
        )
        match = re.search(r"Address>([^<]+)</", text)
        if not match:
            raise JM800Error(f"ONVIF subscribe failed: {text[:200]!r}")
        self._address = match.group(1)

    async def unsubscribe(self) -> None:
        if self._address:
            try:
                await self._soap(self._address, '<Unsubscribe xmlns="http://docs.oasis-open.org/wsn/b-2"/>',
                                 "http://docs.oasis-open.org/wsn/bw-2/SubscriptionManager/UnsubscribeRequest")
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass
            self._address = None

    async def run(self) -> None:
        """Pull forever; resubscribe before expiry and back off on errors."""
        loop = asyncio.get_running_loop()
        backoff = 5
        while True:
            try:
                await self._subscribe()
                expires = loop.time() + self.SUBSCRIPTION_SECONDS - 60
                backoff = 5
                while loop.time() < expires:
                    text = await self._soap(
                        self._address,
                        f'<PullMessages xmlns="{_EVENTS_NS}"><Timeout>PT20S</Timeout>'
                        "<MessageLimit>50</MessageLimit></PullMessages>",
                        f"{_EVENTS_NS}/PullPointSubscription/PullMessagesRequest",
                        timeout=35,
                    )
                    if "PullMessagesResponse" not in text:
                        raise JM800Error(f"ONVIF pull failed: {text[:200]!r}")
                    for message in _NOTIFICATION_RE.findall(text):
                        topic = _TOPIC_RE.search(message)
                        if topic:
                            self.on_event(topic.group(1).split(":", 1)[-1], dict(_ITEM_RE.findall(message)))
                await self.unsubscribe()
            except asyncio.CancelledError:
                await self.unsubscribe()
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, JM800Error) as err:
                _LOGGER.debug("ONVIF events error, retrying in %ss: %s", backoff, err)
                self._address = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300)
