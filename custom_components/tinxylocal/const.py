"""Constants for the Tinxy Local integration."""

DOMAIN = "tinxylocal"

CONF_MQTT_PASS = "mqtt_pass"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE = "device"
CONF_REQUEST_TIMEOUT = "request_timeout"
CONF_POLLING_INTERVAL = "polling_interval"
CONF_SETUP_MODE = "setup_mode"
CONF_RELAY_COUNT = "relay_count"

SETUP_MODE_CLOUD = "cloud"
SETUP_MODE_MANUAL = "manual"

TINXY_BACKEND = "https://backend.tinxy.in/"

DEFAULT_REQUEST_TIMEOUT = 5
DEFAULT_POLLING_INTERVAL = 15
DEFAULT_RATE_LIMIT_DELAY = 0.25  # Seconds between sequential commands to the same device
