"""Constants for the JM800 camera integration."""

DOMAIN = "jm800"

CONF_PUSH_URL = "push_url"
CONF_CONFIGURE_PUSH = "configure_push"

DEFAULT_PORT = 80
SCAN_INTERVAL_SECONDS = 30

# The camera POSTs alarms to <alarm server url host:port>/HAPI/V1.0/<url path>/Event/Notification.
PUSH_URL_PATH = "/jm800"
PUSH_VIEW_URL = "/HAPI/V1.0/{tail:.*}"

EVENT_ALARM = f"{DOMAIN}_alarm"
SIGNAL_MOTION = f"{DOMAIN}_motion_{{}}"
SIGNAL_PUSH = f"{DOMAIN}_push_{{}}"

# Seconds after which an "active" person alarm is cleared if the camera never sends the end event.
PERSON_AUTO_OFF = 30

# Readable config documents: key -> (get endpoint, set endpoint or None)
SOURCES = {
    "video": ("getMediaVideoConfig", "setMediaVideoCaptureConfig"),
    "motion": ("getMotionDetectAlarm", "setMotionDetectAlarm"),
    "person": ("getPdAlarm", "setPdAlarm"),
    "audio": ("getMediaAudioConfig", "setMediaAudioConfig"),
    "storage": ("getStorageDevInfo", None),
    "time": ("getTimeConfig", "setTimeConfig"),
    "presets": ("getPresetList", None),
}

PTZ_DIRECTIONS = [
    "up", "down", "left", "right", "left_up", "right_up", "left_down", "right_down",
    "ZoomTele", "ZoomWide", "FocusNear", "FocusFar", "IrisLarge", "IrisSmall",
]

# Presets the firmware maps to built-in functions (from getPtzConfig AdvanceConfig).
PRESET_HUMAN_TRACE_ON = ("callpreset", 92)
PRESET_HUMAN_TRACE_OFF = ("callpreset", 94)
PRESET_CRUISE_ON = ("callpreset", 41)
PRESET_CRUISE_OFF = ("setpreset", 255)

IR_CUT_MODES = {
    "0": "Auto",
    "1": "Day/night schedule",
    "2": "Passive",
    "3": "Manual",
    "6": "Manual always on",
    "7": "Manual always off",
}
LIGHT_TYPES = {"0": "Infrared", "1": "White light", "2": "Smart dual light"}
LIGHT_BRIGHTNESS_MODES = {"1": "Manual", "2": "Auto", "3": "Low power"}
