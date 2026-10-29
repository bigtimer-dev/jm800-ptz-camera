# JM800 PTZ Camera for Home Assistant

A fully local Home Assistant integration for **JM800S5** PTZ cameras: generic Chinese PTZ/dome cameras whose web UI runs on a `gSOAP/2.8` server and that report the ONVIF manufacturer `ONVIF_ICAMERA`. It gives you instant motion **and person** detection, PTZ control, lights, sounds, and all the main camera settings as Home Assistant entities, with no cloud, app, or web UI needed.

> Not affiliated with any camera manufacturer. The private API was reverse-engineered from the camera's own web interface. See [API.md](API.md).

## Supported cameras

Tested with:

| Model | Firmware |
|---|---|
| `JM800S5_AF` | `JM800S5_AF_V100-A_YSSD-RTMP-GB-H5 V3.4.0.10` (web UI v2.400) |

Other cameras with the same web interface will probably work. A quick check is to open `http://CAMERA_IP/` and look for a server header of `gSOAP/2.8`. If you try another model, please open an issue saying whether it works.

## Features

| Type | What you get |
|---|---|
| **Camera** | Live RTSP stream + snapshots (main stream; a sub-stream entity is included but disabled by default) |
| **Binary sensors** | **Motion**: instant, from ONVIF events. **Person**: instant, from the camera's alarm push; clears itself after 30 s if the end event is missed. |
| **Switches** | Motion detection, person detection, person tracking, person auto-zoom, draw person box, alarm light flash and alarm sound (for person and motion), flip horizontal/vertical |
| **Numbers** | Light brightness, motion sensitivity (1–100), person sensitivity (0–4), speaker/mic volume, image brightness/contrast/saturation/sharpness, PTZ speed |
| **Selects** | Day/night (IR-cut) mode, light type (IR / white / smart dual), light brightness mode, alarm sound files, **Go to preset**, sound to play |
| **Buttons** | PTZ up/down/left/right, zoom in/out, stop, auto-tracking start/stop, cruise start/stop, light on/off, force day/night, play/stop sound, reboot |
| **Sensors** | SD card status and usage, camera clock (with NTP server), PTZ presets |
| **Actions** | `jm800.ptz`, `jm800.goto_preset`, `jm800.save_preset`, `jm800.delete_preset`, `jm800.play_sound`, `jm800.stop_sound`, `jm800.set_day_night`, `jm800.set_light`, `jm800.raw_command` |
| **Event** | `jm800_alarm` for every alarm the camera pushes |

## Requirements

* Home Assistant **2024.11 or newer**.
* The camera and Home Assistant on the same network.
* The camera must be able to reach Home Assistant over **plain HTTP** (default port 8123) to deliver person alarms. If your HA only listens on HTTPS, see [Troubleshooting](#troubleshooting).
* **ONVIF** enabled on the camera, with **ONVIF authentication off**. Both are the factory defaults (Settings → Network → ONVIF in the camera web UI). Motion events come through ONVIF.

## Installation

### HACS (recommended)

1. In Home Assistant, open **HACS** → menu (⋮) → **Custom repositories**.
2. Add `https://github.com/bigtimer-dev/jm800-ptz-camera` with type **Integration**.
3. Search for **JM800 PTZ Camera**, install it, and **restart Home Assistant**.

### Manual

1. Download this repository (green **Code** button → **Download ZIP**) and unzip it.
2. Copy the `custom_components/jm800` folder into your Home Assistant config folder, so you end up with `/config/custom_components/jm800/manifest.json`. You can use the **Samba share**, **SSH**, or **Studio Code Server** add-on.
3. **Restart Home Assistant.**

## Setup

1. Go to **Settings → Devices & services → Add integration** and search for **JM800 PTZ Camera**.
2. Enter:
   * **Host**: the camera's IP address. Give the camera a fixed IP or a DHCP reservation in your router so it doesn't change.
   * **HTTP port**: `80` unless you changed it.
   * **Username / Password**: the same login you use for the camera's web page.
3. Done. A **JM800 Camera** device appears with all its entities.

During setup the integration also points the camera's **alarm server** at your Home Assistant and turns on person-alarm push. Person detection needs this. To change it, open the integration → **Configure**:

* **Point the camera's alarm server at Home Assistant**: turn off if you manage the camera's alarm server yourself.
* **Home Assistant base URL**: leave empty to detect it automatically. Otherwise enter a URL the camera can reach, e.g. `http://192.168.1.10:8123`.

## Using it in automations

The entity IDs below assume the default device name **JM800 Camera**. With more than one camera, Home Assistant adds `_2`, `_3`, and so on.

**Person detected at night → white light on + warning sound**

```yaml
alias: Camera - person at night
triggers:
  - trigger: state
    entity_id: binary_sensor.jm800_camera_person
    to: "on"
conditions:
  - condition: sun
    after: sunset
    before: sunrise
actions:
  - action: button.press
    target:
      entity_id: button.jm800_camera_light_on
  - action: jm800.play_sound
    target:
      entity_id: camera.jm800_camera
    data:
      file: /opt/ch/alarm/Warning.mp3
```

**Send a phone notification with a snapshot when a person is seen**

```yaml
alias: Camera - notify person
triggers:
  - trigger: state
    entity_id: binary_sensor.jm800_camera_person
    to: "on"
actions:
  - action: camera.snapshot
    target:
      entity_id: camera.jm800_camera
    data:
      filename: /config/www/jm800_last_person.jpg
  - action: notify.mobile_app_your_phone
    data:
      message: Person detected
      data:
        image: /local/jm800_last_person.jpg
```

**Turn the camera to a preset when a door opens**

```yaml
alias: Camera - look at the gate
triggers:
  - trigger: state
    entity_id: binary_sensor.gate
    to: "on"
actions:
  - action: jm800.goto_preset
    target:
      entity_id: camera.jm800_camera
    data:
      preset: 1
```

**Person detection only while nobody is home**

```yaml
alias: Camera - detection follows presence
triggers:
  - trigger: state
    entity_id: zone.home
actions:
  - action: "switch.turn_{{ 'off' if states('zone.home') | int > 0 else 'on' }}"
    target:
      entity_id: switch.jm800_camera_person_detection
```

**Move the camera**

```yaml
action: jm800.ptz
target:
  entity_id: camera.jm800_camera
data:
  direction: left        # up, down, left, right, left_up, ..., ZoomTele, ZoomWide, FocusNear, FocusFar, stop
  speed: 5               # 1-10
  duration: 0.5          # seconds; 0 = keep moving until a "stop"
```

To save a preset, move the camera where you want it and call `jm800.save_preset` with a number. It then shows up in **Go to preset**.

Preset numbers **41, 64, 79, 82, 84, 92–99, 107, and 255** are reserved by the firmware for built-in functions (tracking, cruise, scan, and so on), so avoid them for your own positions.

**Any other alarm type** (vehicle, line crossing, and so on, once enabled on the camera with alarm-server push) arrives as an event:

```yaml
triggers:
  - trigger: event
    event_type: jm800_alarm
    event_data:
      subtype: HumanShapeDetect   # check Developer tools → Events → listen to jm800_alarm to see other subtypes
      active: true
```

**Advanced:** `jm800.raw_command` sends any command from [API.md](API.md) and returns the camera's response. Use it with "Response variable" in a script.

## Security recommendations

These cameras have weak security by design. Please:

* **Change the factory default password** in the camera's web UI.
* **Block the camera from the internet** in your router or firewall. The integration is 100% local and doesn't need internet. Several things are open by default: the snapshot URL needs **no login**, ONVIF has authentication off, and the Hikvision (8000) and Dahua (37777) SDK ports are open.
* Keep the camera on a separate VLAN or IoT network if you can.
* With internet blocked, give the camera a local time source. For example, run an NTP server add-on (such as chrony) on Home Assistant and set the camera's NTP server to Home Assistant's IP. The camera has no clock battery and loses the time on every reboot.
* The alarm push endpoint (`/HAPI/V1.0/...`) on Home Assistant can't use authentication, because the camera can't send credentials. The integration only accepts pushes from the IP address of a configured camera.

## Troubleshooting

| Problem | What to check |
|---|---|
| "Could not reach the camera" | IP/port correct? Can you open `http://CAMERA_IP/` in a browser? |
| "Wrong username or password" | After too many failed logins the camera locks the account; wait or reboot it. |
| **Motion** never turns on | ONVIF must be enabled with ONVIF auth **off**. Motion detection must be on (switch). |
| **Person** never turns on | Person detection switch on? The camera must reach `http://<HA IP>:8123`. If HA uses HTTPS only, or another port, or the auto-detected IP is wrong, set **Home Assistant base URL** in the integration options. Check that a firewall between camera and HA allows it. |
| Camera clock is wrong | See the NTP tip above. The clock shows in the **Camera clock** sensor. |

For debug logs, add this to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.jm800: debug
```

## Command-line tool

`jm800.py` is a stand-alone Python script (standard library only) for scripting or exploring the camera:

```bash
python3 jm800.py CAMERA_IP admin PASSWORD info
python3 jm800.py CAMERA_IP admin PASSWORD urls
python3 jm800.py CAMERA_IP admin PASSWORD get getPtzConfig
python3 jm800.py CAMERA_IP admin PASSWORD ptz left 5 --duration 0.5
python3 jm800.py CAMERA_IP admin PASSWORD preset call 1
python3 jm800.py CAMERA_IP admin PASSWORD snapshot out.jpg
```

## Development / testing

```bash
pip install pytest-homeassistant-custom-component PyTurboJPEG
JM800_HOST=CAMERA_IP JM800_PASSWORD=PASSWORD pytest -s
```

The live test loads the integration against a real camera and does the following: checks every entity, writes a setting back with its current value, fetches a snapshot, simulates a person push, and waits for a real ONVIF motion event.

## Known limitations

* The light on/off and force day/night buttons don't show a state, because the camera doesn't report one.
* Vehicle and other AI alarms don't have their own sensors yet. Use the `jm800_alarm` event.
* PTZ, preset, light, sound, tracking, cruise, and reboot commands send exactly what the camera's web UI sends. Feedback from other camera models is welcome.

## License

MIT. See [LICENSE](LICENSE).
