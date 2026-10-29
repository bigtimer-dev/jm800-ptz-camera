"""Live test against a real camera: JM800_HOST=<camera ip> JM800_PASSWORD=<password> pytest -s"""
import asyncio
import json
import os

import pytest
import pytest_socket
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jm800.const import DOMAIN

HOST = os.environ.get("JM800_HOST")
pytestmark = pytest.mark.skipif(not HOST, reason="set JM800_HOST to run against a real camera")


@pytest.fixture
def allow_camera():
    pytest_socket.enable_socket()
    pytest_socket.socket_allow_hosts(["127.0.0.1", HOST])


async def test_live(hass, hass_client_no_auth, allow_camera):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": HOST, "port": 80, "username": os.environ.get("JM800_USER", "admin"),
              "password": os.environ.get("JM800_PASSWORD", "")},
        options={"configure_push": False},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state.value == "loaded"
    serial = entry.runtime_data.coordinator.serial
    registry = er.async_get(hass)

    def eid(domain: str, key: str) -> str:
        return registry.async_get_entity_id(domain, DOMAIN, f"{serial}_{key}")

    states = sorted(hass.states.async_all(), key=lambda s: s.entity_id)
    for s in states:
        if s.domain in ("camera", "binary_sensor", "switch", "number", "select", "sensor", "button"):
            print(f"{s.entity_id:55} {s.state!s:22} {dict((k, v) for k, v in s.attributes.items() if k in ('options', 'presets', 'time_mode', 'ntp_server'))}")
    assert not [s.entity_id for s in states if s.state == "unavailable" and not s.entity_id.endswith("sub_stream")]

    # Read-modify-write round trip with the current value (no change on the camera).
    sens = hass.states.get(eid("number", "person_sensitivity"))
    await hass.services.async_call("number", "set_value",
                                   {"entity_id": sens.entity_id, "value": float(sens.state)}, blocking=True)
    assert hass.states.get(sens.entity_id).state == sens.state

    # Snapshot through the camera entity.
    client = await hass_client_no_auth()
    cam = hass.states.get(eid("camera", "camera_0"))
    resp = await client.get(f"/api/camera_proxy/{cam.entity_id}?token={cam.attributes['access_token']}")
    body = await resp.read()
    print("snapshot", resp.status, len(body))
    assert resp.status == 200 and body[:2] == b"\xff\xd8"

    # Raw command action with response.
    result = await hass.services.async_call(DOMAIN, "raw_command", {"entity_id": cam.entity_id, "endpoint": "getVideoSize"},
                                            blocking=True, return_response=True)
    print("raw_command", result)

    # Push from an unknown address is rejected; from the camera address it drives the person sensor.
    payload = {"AlarmType": "ObjectDetect", "AlarmSubType": "HumanShapeDetect", "OccurFlag": "true",
               "DeviceID": serial, "TimeStamp": 1}
    resp = await client.post("/HAPI/V1.0//jm800/Event/Notification", data=json.dumps(payload))
    assert resp.status == 403
    hass.data[DOMAIN]["hosts"][payload["DeviceID"]] = "127.0.0.1"
    events = []
    hass.bus.async_listen("jm800_alarm", events.append)
    resp = await client.post("/HAPI/V1.0//jm800/Event/Notification", data=json.dumps(payload))
    await hass.async_block_till_done()
    assert resp.status == 200
    assert hass.states.get(eid("binary_sensor", "person")).state == "on"
    assert events and events[0].data["subtype"] == "HumanShapeDetect"
    payload["OccurFlag"] = "false"
    await client.post("/HAPI/V1.0//jm800/Event/Notification", data=json.dumps(payload))
    await hass.async_block_till_done()
    assert hass.states.get(eid("binary_sensor", "person")).state == "off"

    # Real ONVIF motion: watch for up to 40 s.
    seen = set()
    for _ in range(40):
        seen.add(hass.states.get(eid("binary_sensor", "motion")).state)
        if "on" in seen:
            break
        await asyncio.sleep(1)
    print("motion states seen:", seen)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
