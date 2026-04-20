import json
import os
from caenhv import SY4527, SY5527

# ===========================================================================
# Hardware Connection Settings
# ===========================================================================
IP_ADDRESS = "172.16.2.51"
SYSTEM_TYPE = SY4527
USERNAME = "admin"
PASSWORD = "admin"
HV_TABLE = "hv.table"

# ===========================================================================
# ZeroMQ Communication Ports (hvserver ↔ clients)
# ===========================================================================
CMD_PORT = 5555   # REQ/REP command channel
PUB_PORT = 5556   # PUB/SUB telemetry channel

# ===========================================================================
# HV Server Service Settings
# ===========================================================================
SERVER_LOG_FILE     = "hvserver.log"
SERVER_PID_FILE     = "hvserver.pid"
RECONNECT_INTERVAL  = 30.0   # seconds between hardware reconnection attempts

# ===========================================================================
# HV Logger Service Settings
# ===========================================================================
LOGGER_LOG_FILE = "hvlogger.log"
LOGGER_PID_FILE = "hvlogger.pid"
LOGGER_INTERVAL = 60.0   # polling interval in seconds

# ===========================================================================
# InfluxDB Settings (for hvlogger)
# ===========================================================================
INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "your-influxdb-token"
INFLUX_ORG    = "cups"
INFLUX_BUCKET = "hv"


# ===========================================================================
# config.json override
# ===========================================================================


def load_config(config_path="config.json"):
    """
    Override default constants with values from a JSON file if it exists.
    All keys are optional; only the ones present in the file will be overridden.
    """
    global IP_ADDRESS, SYSTEM_TYPE, USERNAME, PASSWORD, HV_TABLE
    global CMD_PORT, PUB_PORT
    global SERVER_LOG_FILE, SERVER_PID_FILE, RECONNECT_INTERVAL
    global LOGGER_LOG_FILE, LOGGER_PID_FILE, LOGGER_INTERVAL
    global INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET

    if not os.path.exists(config_path):

        return False

    try:
        with open(config_path, 'r') as f:
            lines = f.readlines()
            
        # Safely strip # comments
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if " #" in line:
                line = line.split(" #")[0]
            cleaned.append(line)
            
        json_str = "\n".join(cleaned)
        cfg = json.loads(json_str)

        # Hardware
        if "IP_ADDRESS" in cfg:
            IP_ADDRESS = cfg["IP_ADDRESS"]
        if "SYSTEM_TYPE" in cfg:
            SYSTEM_TYPE = cfg["SYSTEM_TYPE"]
        if "USERNAME" in cfg:
            USERNAME = cfg["USERNAME"]
        if "PASSWORD" in cfg:
            PASSWORD = cfg["PASSWORD"]
        if "HV_TABLE" in cfg:
            HV_TABLE = cfg["HV_TABLE"]

        # Ports
        if "CMD_PORT" in cfg:
            CMD_PORT = cfg["CMD_PORT"]
        if "PUB_PORT" in cfg:
            PUB_PORT = cfg["PUB_PORT"]

        # Server service
        if "SERVER_LOG_FILE" in cfg:
            SERVER_LOG_FILE = cfg["SERVER_LOG_FILE"]
        if "SERVER_PID_FILE" in cfg:
            SERVER_PID_FILE = cfg["SERVER_PID_FILE"]
        if "RECONNECT_INTERVAL" in cfg:
            RECONNECT_INTERVAL = float(cfg["RECONNECT_INTERVAL"])

        # Logger service
        if "LOGGER_LOG_FILE" in cfg:
            LOGGER_LOG_FILE = cfg["LOGGER_LOG_FILE"]
        if "LOGGER_PID_FILE" in cfg:
            LOGGER_PID_FILE = cfg["LOGGER_PID_FILE"]
        if "LOGGER_INTERVAL" in cfg:
            LOGGER_INTERVAL = float(cfg["LOGGER_INTERVAL"])

        # InfluxDB
        if "INFLUX_URL" in cfg:
            INFLUX_URL = cfg["INFLUX_URL"]
        if "INFLUX_TOKEN" in cfg:
            INFLUX_TOKEN = cfg["INFLUX_TOKEN"]
        if "INFLUX_ORG" in cfg:
            INFLUX_ORG = cfg["INFLUX_ORG"]
        if "INFLUX_BUCKET" in cfg:
            INFLUX_BUCKET = cfg["INFLUX_BUCKET"]

        print(f"[hvconfig] Configuration loaded from {config_path}")

        return True
    except Exception as e:
        print(f"[hvconfig] Failed to load {config_path}: {e}")
    return False


# Initialize configuration on import
load_config()
