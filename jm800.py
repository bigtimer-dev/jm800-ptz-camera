#!/usr/bin/env python3
"""Client for the JM800S5 (ONVIF_ICAMERA, fw V3.4.x) IP camera's private XML API.

The web UI talks to the camera by POSTing SOAP-ish envelopes to http://<cam>/<endpoint>.
Each request carries the username and password, DES-ECB encrypted with the fixed key
"WebLogin" (null padded, hex encoded). There is no session: every request is
authenticated by those two header fields, so the values can be computed once.

Stdlib only, so it can be dropped into a Home Assistant custom component as-is
(wrap calls in hass.async_add_executor_job) or used from the command line:

    python3 jm800.py CAMERA_IP admin PASSWORD info
    python3 jm800.py CAMERA_IP admin PASSWORD get getPtzConfig
    python3 jm800.py CAMERA_IP admin PASSWORD ptz left 5 --duration 0.5
    python3 jm800.py CAMERA_IP admin PASSWORD preset call 1
    python3 jm800.py CAMERA_IP admin PASSWORD snapshot out.jpg
"""
import argparse
import hashlib
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------- DES (ECB) --

_PC1 = [57, 49, 41, 33, 25, 17, 9, 1, 58, 50, 42, 34, 26, 18, 10, 2, 59, 51, 43, 35, 27, 19, 11, 3,
        60, 52, 44, 36, 63, 55, 47, 39, 31, 23, 15, 7, 62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37,
        29, 21, 13, 5, 28, 20, 12, 4]
_PC2 = [14, 17, 11, 24, 1, 5, 3, 28, 15, 6, 21, 10, 23, 19, 12, 4, 26, 8, 16, 7, 27, 20, 13, 2,
        41, 52, 31, 37, 47, 55, 30, 40, 51, 45, 33, 48, 44, 49, 39, 56, 34, 53, 46, 42, 50, 36, 29, 32]
_SHIFTS = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]
_IP = [58, 50, 42, 34, 26, 18, 10, 2, 60, 52, 44, 36, 28, 20, 12, 4, 62, 54, 46, 38, 30, 22, 14, 6,
       64, 56, 48, 40, 32, 24, 16, 8, 57, 49, 41, 33, 25, 17, 9, 1, 59, 51, 43, 35, 27, 19, 11, 3,
       61, 53, 45, 37, 29, 21, 13, 5, 63, 55, 47, 39, 31, 23, 15, 7]
_FP = [40, 8, 48, 16, 56, 24, 64, 32, 39, 7, 47, 15, 55, 23, 63, 31, 38, 6, 46, 14, 54, 22, 62, 30,
       37, 5, 45, 13, 53, 21, 61, 29, 36, 4, 44, 12, 52, 20, 60, 28, 35, 3, 43, 11, 51, 19, 59, 27,
       34, 2, 42, 10, 50, 18, 58, 26, 33, 1, 41, 9, 49, 17, 57, 25]
_E = [32, 1, 2, 3, 4, 5, 4, 5, 6, 7, 8, 9, 8, 9, 10, 11, 12, 13, 12, 13, 14, 15, 16, 17,
      16, 17, 18, 19, 20, 21, 20, 21, 22, 23, 24, 25, 24, 25, 26, 27, 28, 29, 28, 29, 30, 31, 32, 1]
_P = [16, 7, 20, 21, 29, 12, 28, 17, 1, 15, 23, 26, 5, 18, 31, 10,
      2, 8, 24, 14, 32, 27, 3, 9, 19, 13, 30, 6, 22, 11, 4, 25]
_S = [
    [14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7, 0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8,
     4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0, 15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13],
    [15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10, 3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5,
     0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15, 13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9],
    [10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8, 13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1,
     13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7, 1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12],
    [7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15, 13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9,
     10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4, 3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14],
    [2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9, 14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6,
     4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14, 11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3],
    [12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11, 10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8,
     9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6, 4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13],
    [4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1, 13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6,
     1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2, 6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12],
    [13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7, 1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2,
     7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8, 2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11],
]


def _permute(value, table, width):
    out = 0
    for pos in table:
        out = (out << 1) | ((value >> (width - pos)) & 1)
    return out


def _subkeys(key):
    k = _permute(int.from_bytes(key, "big"), _PC1, 64)
    c, d = k >> 28, k & 0xFFFFFFF
    keys = []
    for s in _SHIFTS:
        c = ((c << s) | (c >> (28 - s))) & 0xFFFFFFF
        d = ((d << s) | (d >> (28 - s))) & 0xFFFFFFF
        keys.append(_permute((c << 28) | d, _PC2, 56))
    return keys


def _des_block(block, keys):
    v = _permute(int.from_bytes(block, "big"), _IP, 64)
    left, right = v >> 32, v & 0xFFFFFFFF
    for k in keys:
        x = _permute(right, _E, 32) ^ k
        f = 0
        for i in range(8):
            six = (x >> (42 - 6 * i)) & 0x3F
            f = (f << 4) | _S[i][(((six & 0x20) >> 4) | (six & 1)) * 16 + ((six >> 1) & 0xF)]
        left, right = right, left ^ _permute(f, _P, 32)
    return _permute((right << 32) | left, _FP, 64).to_bytes(8, "big")


def encrypt_credential(text, key=b"WebLogin"):
    """Same as the web UI's stringToHex(des("WebLogin", text, 1, 0))."""
    data = text.encode("latin-1")
    data += b"\0" * (-len(data) % 8)
    keys = _subkeys(key)
    return b"".join(_des_block(data[i:i + 8], keys) for i in range(0, len(data), 8)).hex()


# ------------------------------------------------------------------ client --

PTZ_MOVES = ["up", "down", "left", "right", "left_up", "right_up", "left_down", "right_down",
             "ZoomTele", "ZoomWide", "FocusNear", "FocusFar", "IrisLarge", "IrisSmall"]

# Special presets the firmware maps to built-in functions (from the web UI / getPtzConfig).
SPECIAL_PRESETS = {
    "ScanBegin": (92, "setpreset"), "ScanEnd": (93, "setpreset"), "ScanOn": (99, "callpreset"),
    "Orbit": (98, "callpreset"), "PtzRestore": (82, "callpreset"), "FocusRestore": (84, "callpreset"),
    "GuardPos": (79, "callpreset"), "PtzReboot": (94, "callpreset"),
}


class JM800Error(Exception):
    pass


class JM800Camera:
    def __init__(self, host, username="admin", password="", port=80, timeout=8):
        self.base = f"http://{host}:{port}"
        self.host = host
        self.username = username
        self.password = password
        self.timeout = timeout
        self._uid = encrypt_credential(self._escape(username))
        self._pwd = encrypt_credential(self._escape(password))

    @staticmethod
    def _escape(s):
        # checkLoginStr(): backslash-escape quotes and backslashes before encrypting
        return s.replace("\\", "\\\\").replace('"', '\\"')

    def envelope(self, body=""):
        return ('<?xml version="1.0"?><soap:Envelope xmlns:soap="http://www.w3.org/2001/12/soap-envelope">'
                f"<soap:Header>\t<userid>{self._uid}</userid>\t<passwd>{self._pwd}</passwd></soap:Header>"
                f"<soap:Body>{body}</soap:Body></soap:Envelope>")

    def call(self, endpoint, body=""):
        """POST an envelope to /<endpoint> and return the raw response text."""
        req = urllib.request.Request(f"{self.base}/{endpoint.lstrip('/')}",
                                     data=self.envelope(body).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.read().decode("utf-8", "replace")

    def get_xml(self, endpoint):
        text = self.call(endpoint).strip()
        try:
            return ET.fromstring(text)
        except ET.ParseError as e:
            raise JM800Error(f"{endpoint}: unparsable response {text[:200]!r}") from e

    def update(self, get_endpoint, set_endpoint, mutate):
        """Read-modify-write, the way the web UI saves every settings page.

        `mutate(root)` edits the ElementTree from `get_endpoint` in place; the whole document
        is then posted to `set_endpoint`.
        """
        root = self.get_xml(get_endpoint)
        mutate(root)
        return self.call(set_endpoint, ET.tostring(root, encoding="unicode"))

    # -- session / info
    def login(self):
        """/ipcLogin: returns the capability list. 'passwordLock' means too many bad attempts."""
        text = self.call("ipcLogin")
        if text.strip() == "passwordLock":
            raise JM800Error("account locked after failed logins")
        if "<SystemFunction" not in text:
            raise JM800Error(f"login failed: {text[:200]!r}")
        return [f.get("Fun") for f in ET.fromstring(text).iter("Fun") if f.get("Fun")]

    def device_info(self):
        root = self.get_xml("getSystemVersionInfo")
        v, sn = root.find("VersionInfo"), root.find("SerialNumber")
        return {"kernel": v.get("kernelVersion"), "firmware": v.get("fsVersion").strip(),
                "serial": sn.get("serialNumber")}

    # -- media
    def rtsp_url(self, stream=0):
        """stream 0 = main (2560x1440), 1 = sub (720x480). Plain user:pass also works."""
        md5 = hashlib.md5(self.password.encode()).hexdigest().upper()
        return f"rtsp://{self.host}:554/stream{stream}?username={self.username}&password={md5}"

    def snapshot(self, stream=0):
        url = f"{self.base}/cgi-bin/snapshot.cgi?stream={stream}"
        with urllib.request.urlopen(url, timeout=self.timeout) as r:
            return r.read()

    # -- PTZ
    def ptz_move(self, direction, speed=5):
        """Start moving (speed 1-10). Keeps going until ptz_stop()."""
        return self.call("setPTZCmd", f"<xml><cmd>{direction}</cmd><panspeed>{speed}</panspeed>"
                                      f"<tiltspeed>{speed}</tiltspeed></xml>")

    def ptz_stop(self):
        return self.call("setPTZCmd", "<xml><cmd>stop</cmd></xml>")

    def ptz_step(self, direction, speed=5, duration=0.5):
        self.ptz_move(direction, speed)
        time.sleep(duration)
        return self.ptz_stop()

    def ptz_3d_zoom(self, start_x, start_y, end_x, end_y):
        """Drag-box 3D positioning. Coordinates as the web UI sends them (video pixel space)."""
        return self.call("set3DYuntaiCoordinate",
                         f'<Yuntai3D><Coordinate StartX="{start_x}" StartY="{start_y}" '
                         f'EndX="{end_x}" EndY="{end_y}" /></Yuntai3D>')

    def presets(self):
        return [int(p.text) for p in self.get_xml("getPresetList").iter("p")]

    def preset(self, action, number):
        """action: 'callpreset' | 'setpreset' | 'clearpreset'."""
        flag = "<flag>1</flag>" if action == "setpreset" else ""
        return self.call("PresetList", f"<xml><cmd>{action}</cmd><preset>{number}</preset>{flag}</xml>")

    def special(self, name):
        num, action = SPECIAL_PRESETS[name]
        return self.preset(action, num)

    # -- day/night & lights
    def set_day_night(self, night):
        return self.call("setIRCutManual_DayNight", "NightMode" if night else "DayMode")

    def set_light(self, on):
        return self.call("setLed_KeepOn_Off", "KeepOn" if on else "KeepOff")

    def capture_settings(self):
        return dict(self.get_xml("getMediaVideoConfig").find("Capture").attrib)

    def set_capture(self, **attrs):
        """e.g. set_capture(IrcutMode=3, led_mode=1, led_brightness_value=50, HFlip=0)."""
        def mutate(root):
            cap = root.find("Capture")
            for k, v in attrs.items():
                cap.set(k, str(v))
        return self.update("getMediaVideoConfig", "setMediaVideoCaptureConfig", mutate)

    # -- detection toggles
    def set_motion_detection(self, enable):
        return self.update("getMotionDetectAlarm", "setMotionDetectAlarm",
                           lambda r: r.set("Enable", "1" if enable else "0"))

    def set_person_detection(self, enable):
        return self.update("getPdAlarm", "setPdAlarm",
                           lambda r: r.set("Enable", "1" if enable else "0"))

    # -- audio
    def audio_files(self):
        return [f.get("path") for f in self.get_xml("getAudioActionFiles").iter("File")]

    def play_audio(self, path="/opt/ch/alarm/Warning.mp3"):
        return self.call("playAudioActionFile", path)

    def stop_audio(self):
        return self.call("stopAudioActionFile")

    # -- alarm push (camera -> HTTP server, e.g. a Home Assistant webhook)
    def set_alarm_server(self, url, username="", password="", with_snapshot=False):
        return self.call("setNetworkAlarmServerConfig",
                         f'<AlarmServerConfig url="{url}" Username="{username}" Password="{password}" '
                         f'withattachment="{1 if with_snapshot else 0}" />')

    # -- system
    def storage(self):
        return {c.tag: dict(c.attrib) for c in self.get_xml("getStorageDevInfo")}

    def reboot(self):
        return self.call("SystemMaintain",
                         "<SystemMaintain><Order>SystemReboot</Order><Value></Value></SystemMaintain>")


# --------------------------------------------------------------------- CLI --

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("user")
    ap.add_argument("password")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    sub.add_parser("urls")
    p = sub.add_parser("get", help="POST an empty envelope to a get* endpoint and print the XML")
    p.add_argument("endpoint")
    p = sub.add_parser("raw", help="POST an arbitrary body to an endpoint")
    p.add_argument("endpoint")
    p.add_argument("body", nargs="?", default="")
    p = sub.add_parser("ptz")
    p.add_argument("direction", choices=PTZ_MOVES + ["stop"])
    p.add_argument("speed", nargs="?", type=int, default=5)
    p.add_argument("--duration", type=float, default=0.5)
    p = sub.add_parser("preset")
    p.add_argument("action", choices=["call", "set", "clear", "list"])
    p.add_argument("number", nargs="?", type=int)
    p = sub.add_parser("special")
    p.add_argument("name", choices=list(SPECIAL_PRESETS))
    p = sub.add_parser("daynight")
    p.add_argument("mode", choices=["day", "night"])
    p = sub.add_parser("light")
    p.add_argument("state", choices=["on", "off"])
    p = sub.add_parser("motion")
    p.add_argument("state", choices=["on", "off"])
    p = sub.add_parser("person")
    p.add_argument("state", choices=["on", "off"])
    p = sub.add_parser("audio")
    p.add_argument("action", choices=["list", "play", "stop"])
    p.add_argument("path", nargs="?", default="/opt/ch/alarm/Warning.mp3")
    p = sub.add_parser("snapshot")
    p.add_argument("out")
    p.add_argument("--stream", type=int, default=0)
    sub.add_parser("reboot")
    a = ap.parse_args()

    cam = JM800Camera(a.host, a.user, a.password)
    out = None
    if a.cmd == "info":
        cam.login()
        out = cam.device_info()
    elif a.cmd == "urls":
        out = "\n".join([cam.rtsp_url(0), cam.rtsp_url(1),
                         f"{cam.base}/cgi-bin/snapshot.cgi?stream=0", f"{cam.base}/cgi-bin/snapshot.cgi?stream=1"])
    elif a.cmd == "get":
        out = cam.call(a.endpoint)
    elif a.cmd == "raw":
        out = cam.call(a.endpoint, a.body)
    elif a.cmd == "ptz":
        out = cam.ptz_stop() if a.direction == "stop" else cam.ptz_step(a.direction, a.speed, a.duration)
    elif a.cmd == "preset":
        out = cam.presets() if a.action == "list" else cam.preset(a.action + "preset", a.number)
    elif a.cmd == "special":
        out = cam.special(a.name)
    elif a.cmd == "daynight":
        out = cam.set_day_night(a.mode == "night")
    elif a.cmd == "light":
        out = cam.set_light(a.state == "on")
    elif a.cmd == "motion":
        out = cam.set_motion_detection(a.state == "on")
    elif a.cmd == "person":
        out = cam.set_person_detection(a.state == "on")
    elif a.cmd == "audio":
        out = {"list": cam.audio_files, "stop": cam.stop_audio}.get(a.action, lambda: cam.play_audio(a.path))()
    elif a.cmd == "snapshot":
        data = cam.snapshot(a.stream)
        with open(a.out, "wb") as f:
            f.write(data)
        out = f"wrote {len(data)} bytes to {a.out}"
    elif a.cmd == "reboot":
        out = cam.reboot()
    print(out if isinstance(out, str) else repr(out))


if __name__ == "__main__":
    sys.exit(main())
