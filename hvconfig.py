import json
import os
from caenhv import SY4527, SY5527

# --- Default System Settings ---
IP_ADDRESS = "172.16.2.51"
SYSTEM_TYPE = SY4527
USERNAME = "admin"
PASSWORD = "admin"

# --- Communication Settings ---
CMD_PORT = 5555
PUB_PORT = 5556

# --- Service Settings ---
LOG_FILE = "hvserver.log"
PID_FILE = "hvserver.pid"

def load_config(config_path="config.json"):
    """
    Override default constants with values from a JSON file if it exists.
    """
    global IP_ADDRESS, SYSTEM_TYPE, USERNAME, PASSWORD
    global CMD_PORT, PUB_PORT, LOG_FILE, PID_FILE

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                cfg = json.load(f)
                
            if "IP_ADDRESS" in cfg: IP_ADDRESS = cfg["IP_ADDRESS"]
            if "SYSTEM_TYPE" in cfg: SYSTEM_TYPE = cfg["SYSTEM_TYPE"]
            if "USERNAME" in cfg: USERNAME = cfg["USERNAME"]
            if "PASSWORD" in cfg: PASSWORD = cfg["PASSWORD"]
            if "CMD_PORT" in cfg: CMD_PORT = cfg["CMD_PORT"]
            if "PUB_PORT" in cfg: PUB_PORT = cfg["PUB_PORT"]
            if "LOG_FILE" in cfg: LOG_FILE = cfg["LOG_FILE"]
            if "PID_FILE" in cfg: PID_FILE = cfg["PID_FILE"]
            
            print(f"[hvconfig] Configuration loaded from {config_path}")
            return True
        except Exception as e:
            print(f"[hvconfig] Failed to load {config_path}: {e}")
    return False

# Initialize configuration on import
load_config()
