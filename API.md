# JM800S5 camera – private HTTP API

Reverse-engineered from the camera's web UI (web v2.400) on 2026-10-29.

| | |
|---|---|
| Model | `JM800S5_AF` (ONVIF manufacturer `ONVIF_ICAMERA`), PTZ + autofocus |
| Firmware | `JM800S5_AF_V100-A_YSSD-RTMP-GB-H5 V3.4.0.10 build 2025-05-07` |
| Kernel | Linux 5.10.61 armv7l |
| Web server | `gSOAP/2.8` on port 80 |
| Other ports | 554 RTSP, 8000 Hik-compatible SDK, 37777 Dahua-compatible SDK, 12351 H5 player, 8091 PTZ |

✅ = verified against the live camera. Everything else is the exact request the web UI sends (taken from its JS), but was **not** executed, so the camera's state is unchanged.

---

## 1. Request format and authentication

Every call is `POST http://<cam>/<endpoint>`, with this body:

```xml
<?xml version="1.0"?><soap:Envelope xmlns:soap="http://www.w3.org/2001/12/soap-envelope"><soap:Header>	<userid>USERID</userid>	<passwd>PASSWD</passwd></soap:Header><soap:Body>BODY</soap:Body></soap:Envelope>
```

* The header must be exactly `Content-Type: application/x-www-form-urlencoded`. With `; charset=…` added, any other type, or no type at all, the server returns a SOAP fault.
* `USERID` and `PASSWD` are `hex(DES_ECB(key="WebLogin", plaintext))`. The plaintext is null-padded to a multiple of 8 bytes. Before encryption, `"` and `\` are backslash-escaped.
  * `admin`  → `52851dbd7918bbae`
  * `password` → `83d0cfed87e96b79`
* **The API is stateless.** Each request is authenticated by those two fields alone. No cookie or session is needed, so you can compute the values once and reuse them forever.
* A wrong password returns the plain-text body `passwordError`. Too many failures return `passwordLock`.
* For `get*` endpoints, leave `BODY` empty.
* For `set*` settings endpoints, the UI does a **read-modify-write**: it calls the matching `get*`, edits attributes in the XML, and POSTs the whole document back as `BODY`.
* Responses are bare XML (no SOAP wrapper), or plain text for simple commands.

`jm800.py` in this folder implements all of this using only the Python standard library.

---

## 2. Video, snapshots and events (standard protocols, best for Home Assistant)

| What | URL / method |
|---|---|
| ✅ Main stream (2560×1440 H.264, 16 kHz G.711A audio) | `rtsp://USER:PASSWORD@CAMERA_IP:554/stream0` |
| ✅ Sub stream (720×480 H.264) | `rtsp://USER:PASSWORD@CAMERA_IP:554/stream1` |
| ✅ Snapshot, main | `http://CAMERA_IP/cgi-bin/snapshot.cgi?stream=0` |
| ✅ Snapshot, sub | `http://CAMERA_IP/cgi-bin/snapshot.cgi?stream=1` |
| ✅ ONVIF device service | `http://CAMERA_IP/onvif/device_service`. ONVIF auth is **off** by default (`OnvifAuth="0"`). |
| ✅ ONVIF services | `/onvif/media`, `/onvif/ptz`, `/onvif/events`, `/onvif/imaging`, `/onvif/deviceIO`, `/onvif/analytics` |

ONVIF also returns the form `rtsp://…/stream0?username=admin&password=<MD5(password) upper hex>`.

✅ ONVIF event topics, which the HA ONVIF integration turns into binary sensors:

| Topic | Data |
|---|---|
| `tns1:RuleEngine/CellMotionDetector/Motion` | `IsMotion` (bool) |
| `tns1:VideoSource/MotionAlarm` | `State` (bool) |
| `tns1:Device/Trigger/AlarmIn` | `State` |
| `tns1:Device/Trigger/DigitalInput` | `LogicalState` |
| `tns1:Device/Trigger/Relay` | `LogicalState` |
| `tns1:UserAlarm/Call/Alarm` | `Action` |

✅ **Alarm push:** the camera can POST alarms to an HTTP server set with `setNetworkAlarmServerConfig` (§3.7). Each alarm type sends one only if its `<AlarmAction notify_alarmserver>` is non-zero (0 off, 1 all day, 2 daytime, 3 night, 4 custom schedule). This is the only way to get **person** detection; ONVIF reports generic motion only.

* Configured URL `http://HOST:PORT/some/path` → the camera POSTs to `http://HOST:PORT/HAPI/V1.0//some/path/Event/Notification` (note the double slash). `User-Agent: HAPI NOTIFY`. No authentication.
* The body is JSON (sent as `application/x-www-form-urlencoded`). One POST at the start of a detection and one at the end:

```json
{"AlarmType":"ObjectDetect","AlarmSubType":"HumanShapeDetect","TimeStamp":1767268800,
 "LocalTime":"2026-01-01 12:00:00","ChannelNo":0,"NotificationType":0,"OccurFlag":"true",
 "DeviceID":"<serial number>","AlarmInfo":{"image":null,"ObjectDetectInfo":null}}
```

---

## 3. Private XML API

### 3.1 Login and info
| Endpoint | Body | Returns |
|---|---|---|
| ✅ `ipcLogin` | empty | `<SystemFunction>` capability list plus a `sessionid` (not needed) |
| ✅ `getSystemVersionInfo` | – | kernel, firmware, serial |
| ✅ `getSystemControlString` | – | `+cap1+cap2…` feature flags |
| ✅ `getSystemConfig` | – | system/maintenance config |
| ✅ `getNetworkStatus` | – | IP, MAC, cloud status |
| ✅ `getTimeConfig` / `setTimeConfig` | – / RMW | time, NTP, timezone, DST (see below) |
| ✅ `getStorageDevInfo` | – | `sd1`/`sd2`/`usb`/`network`: `mounted total used free percent` |
| ✅ `getVideoSize` | – | main/sub resolution |
| ✅ `getMiscConfig` / `setMiscConfig` | – / RMW | UI language |
| ✅ `getCurrentAllConfig` | – | full config dump |
| ✅ `getDefaultConfigMsg` | – | factory defaults |
| ✅ `getAppType`, `get_mstar_chip_uuid`, `getSysBootStatus` | – | misc |

✅ `<TimeConfig TimeMode="NTP|MANUAL" CurTime="YYYY-MM-DD HH:MM:SS" TimeZone="…">`, with a child `<NTPConfig ServerIP="" ServerPort="123" RefreshInterval="60"/>`.
* `TimeZone` is **UTC offset in minutes + 720**: `480` = GMT-04:00, `1200` = GMT+08:00, `720` = UTC.
* `CurTime` is local time and only applies in `MANUAL` mode.
* The camera has no battery-backed clock. In `MANUAL` mode it resets to 2018-01-01 on every reboot, so use NTP.
* Tip: if the camera is blocked from the internet, run an NTP server on your LAN (e.g. a chrony add-on on Home Assistant) and set `ServerIP` to it.

### 3.2 PTZ
| Endpoint | Body |
|---|---|
| `setPTZCmd` (move) | `<xml><cmd>DIR</cmd><panspeed>S</panspeed><tiltspeed>S</tiltspeed></xml>` |
| `setPTZCmd` (stop) | `<xml><cmd>stop</cmd></xml>` |
| `setPTZCmd` (lens) | `<xml><cmd>LENSCMD</cmd></xml>` |
| ✅ `getPresetList` | – → `<PresetList><p>92</p>…` |
| `PresetList` (go to) | `<xml><cmd>callpreset</cmd><preset>N</preset></xml>` |
| `PresetList` (save) | `<xml><cmd>setpreset</cmd><preset>N</preset><flag>1</flag></xml>` |
| `PresetList` (delete) | `<xml><cmd>clearpreset</cmd><preset>N</preset></xml>` |
| `set3DYuntaiCoordinate` | `<Yuntai3D><Coordinate StartX="" StartY="" EndX="" EndY="" /></Yuntai3D>` (drag-box zoom) |
| ✅ `getPtzConfig` / `setPtzCommomConfig`, `setPtzAfConfig`, `setPtzAdvanceConfig` | PTZ protocol, AF, digital zoom, advanced functions |

* `DIR`: `up down left right left_up right_up left_down right_down ZoomTele ZoomWide FocusNear FocusFar IrisLarge IrisSmall`
* `LENSCMD`: `zoomtele zoomwide FocusNearAutoOff FocusFarAutoOff IrisOpenAutoOff IrisCloseAutoOff`
* Speed `S` is 1–10; the UI default is 5. Movement continues until `stop` is sent. The UI sends `stop` 5 times, 20 ms apart, to be sure it lands.

Special presets, which trigger built-in functions:

| Function | Preset | Command |
|---|---|---|
| ScanBegin / ScanEnd | 92 / 93 | set |
| Scan on | 99 | call |
| Orbit | 98 | call |
| PTZ restore | 82 | call |
| Focus restore | 84 | call |
| Guard position | 79 | call |
| PTZ reboot | 94 | call |

✅ The advanced functions in `getPtzConfig` say this firmware uses: **Human tracking on** = call 92, **Human tracking off** = call 94, **Cruise on** = call 41, **Cruise off** = set 255, **PTZ restore** = set 107 then call 64.

### 3.3 Image, day/night and lights
| Endpoint | Body |
|---|---|
| `setIRCutManual_DayNight` | `DayMode` or `NightMode` (plain text) |
| `setLed_KeepOn_Off` | `KeepOn` or `KeepOff` (plain text) |
| ✅ `getMediaVideoConfig` → `setMediaVideoCaptureConfig` | RMW on `<Video><Capture …/>` |
| `setMediaVideoEncodeConfig` | RMW, `<EncodeConfig Stream=1/2/3 …>` |
| `setMediaVideoOverlayConfig`, `setMediaVideoUserOverlayConfig`, `setMediaVideoMaskConfig`, `setMediaVideoROIConfig` | RMW on OSD, privacy masks, ROI |
| ✅ `getMediaVideoJpegEncodeConfig` / `setMediaVideoPictureConfig` | JPEG settings |
| `setForceIdr` | force a keyframe |
| ✅ `getIrcutOpenLedDelayOption` | list of LED delay values |

Useful attributes in `<Capture>`:

| Attribute | Values |
|---|---|
| `IrcutMode` | 0 Auto (active), 1 Day+Night schedule, 2 Passive, 3 Manual, 6 Manual always on, 7 Manual always off |
| `IrcutNightStartTime` / `IrcutNightEndTime` | `HH:MM:SS` |
| `IrcutKeepColor` | 0/1 |
| `led_mode` | 0 Pure IR, 1 Pure white light, 2 Smart dual light |
| `led_brightness_mode` | 1 Manual, 2 Auto, 3 Low power |
| `led_brightness_value` | 0–100 |
| Other image attributes | `Brightness Contrast Saturation Sharpness` 0–255; `HFlip VFlip rotate` 0/1; `WDRMode` 0/1; `BackLight HLC` |

### 3.4 Detection and alarms
All of these are RMW. Toggle the root element's `Enable="0|1"`. Most also have `arming_flag`, a schedule (`TimeSpanCfg`), and an `<AlarmAction>` with flags `alarm_push`, `notify_alarmserver`, `light_twinkle`, `alarm_led`, IO output and audio.

| get / set | Feature |
|---|---|
| ✅ `getMotionDetectAlarm` / `setMotionDetectAlarm` | motion detection (`Sensitivity`, `AlarmThreshold`, `BlockConfig` grid) |
| ✅ `getPdAlarm` / `setPdAlarm` | **person/vehicle detection** (`Type`, `Sensitivity`, polygon, `track_human`, `auto_zoom`, `draw_human`) |
| ✅ `getVideoGateAlarm` / `setVideoGateAlarm` | line crossing / area intrusion |
| ✅ `getVideoRegionAi` / `setVideoRegionAi` | region AI |
| ✅ `getFdAlarm` / `setFdAlarm` | face detection |
| ✅ `getLprAlarm` / `setLprAlarm` | license plate |
| ✅ `getFlameAndFlumesAlarm` / `setFlameAndFlumesAlarm` | fire/smoke |
| ✅ `getVideoCoverAlarm` / `setVideoCoverAlarm` | tamper |
| ✅ `getInputAlarm` / `setInputAlarm` | alarm input |
| ✅ `getOutput` / `setOutput` | alarm output ports 1–4 (`Duration`, `TriggerType`) |
| `setManualInputAlarm` | manual alarm trigger |
| ✅ `getTempHumidityInfo` / `setTempHumidityInfo` | temp/humidity alarm limits |
| ✅ `getIsPdMadpLicenseValid` | AI license check |

### 3.5 Audio
| Endpoint | Body |
|---|---|
| ✅ `getAudioActionFiles` | – → list of MP3 files on the camera |
| `playAudioActionFile` | file path as plain text, e.g. `/opt/ch/alarm/Dog_bark.mp3` |
| `stopAudioActionFile` | empty |
| ✅ `getMediaAudioConfig` / `setMediaAudioConfig` | RMW: `Volume`, `VolumePlay`, codec, AEC |

Built-in files: `attention_en.mp3`, `alarm-plc.mp3`, `Welcome.mp3`, `Warning.mp3`, `Dog_bark.mp3`, `Audio.mp3`, `en/attention.mp3`. All are under `/opt/ch/alarm/`.

### 3.6 Recording and storage
`getRecordConfig`/`setRecordConfig`, `getRecordQueryInfo`, `replayQueryCacheClear`, `setStorageDevFormat`, `setStorageDevMount`, `setStorageDevUnmount`, `setDeleteFile`.

### 3.7 Network and services
| get / set | |
|---|---|
| ✅ `getNetworkConfig` / `setNetworkLANConfig` | LAN, Wi-Fi, AP |
| ✅ `getMediaStreamConfig` / `setMediaStreamConfig` | enable/disable RTSP, ONVIF (and `OnvifAuth`), Hik/Dahua SDK ports, RTMP, HTTPS |
| ✅ `getWifiConfig` / `setWifiConfig`, `getWifiAPConfig` / `setWifiAPConfig`, `getWifiAPInfo`, `getWifiConnected`, `getWiFiNetworkStatus` | Wi-Fi |
| ✅ `getAlarmServerConfig` / `setNetworkAlarmServerConfig` | `<AlarmServerConfig url="" Username="" Password="" withattachment="0|1" />` |
| ✅ `getFTPConfig` / `setFTPConfig` / `setTestFTP` | FTP |
| ✅ `getSMTPConfig` / `setSMTPConfig` / `setTestSMTP` | e-mail |
| ✅ `getRtmpConfig` / `setRtmpConfig` | RTMP push |
| ✅ `getGB28181Config`, `getGAT1400Config`, `getPlatformConfig` (+ `set…`) | Chinese platform protocols |
| `setNetworkP2PConfig`, `P2p_unbindDevice` | P2P cloud |

### 3.8 Users and system
| Endpoint | Body |
|---|---|
| ✅ `getUserConfig` | users. ⚠️ **returns passwords in plain text** |
| `setAddUserConfig` / `setEditUserConfig` / `setDelUserConfig` | user management |
| `SystemMaintain` (reboot) | `<SystemMaintain><Order>SystemReboot</Order><Value></Value></SystemMaintain>` |
| `SystemMaintain` (factory reset) | `<SystemMaintain><Order>ConfigRestore</Order><Value></Value></SystemMaintain>` |
| `setTimerMaintainConfig` | scheduled auto-reboot |
| `setFirmwareUpgrade`, `getFirmwareUploadProgress`, `WebUploadconfiguration` | firmware/config upload |

### Dead code
The JS also contains a Dahua-style JSON-RPC client (`/login`, `/IPC`, `configManager.*`, `magicBox.*`, …). This firmware returns nothing on those endpoints, so ignore them.

---

## 4. Security notes
* `/cgi-bin/snapshot.cgi` serves images **without any authentication**.
* ONVIF has authentication turned off (`OnvifAuth="0"`). The Hik (8000) and Dahua (37777) SDK ports are open, also with auth off.
* The "encryption" is DES with a fixed public key and no nonce. Anyone who sniffs one request can replay it forever, so treat it as plain text.
* `getUserConfig` and `getNetworkConfig` return the admin password and Wi-Fi keys in clear text.
* Recommended: keep the camera on an isolated VLAN with no internet access, change the factory default password, and enable `OnvifAuth`.
