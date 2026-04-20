# pycaenhv: Python Toolkit for CAEN High Voltage Systems

A modernized, lightweight Python toolkit for controlling and monitoring CAEN High Voltage (HV) devices (SY series mainframes, N1470, etc.).

This project uses a **ZeroMQ-based Server-Client architecture** to allow multiple simultaneous connections, remote monitoring, and robust background operation. A dedicated **slow-control logger** can forward long-term telemetry to a time-series database (e.g. InfluxDB) for Grafana dashboards.

## 1. Key Features
- **Server-Client Architecture**: A central server manages the hardware link, while multiple CLI/GUI clients can connect simultaneously.
- **Table-less Server**: The server automatically discovers all available hardware slots and channels. Configuration (naming, grouping) is managed by the clients via `hv.table`.
- **Automated Parameter Calculation**: Current limits ($I_0Set$) are automatically derived from target voltage and resistance ($I = V/R$) with a 10% safety margin.
- **Fault Tolerance (Degraded Mode)**: The server process continues handling ZMQ connections even if it loses physical connectivity to the CAEN mainframe, queuing reconnections safely while rejecting invalid writes.
- **Multi-Client Monitoring**: ZeroMQ PUB/SUB pattern allows 1 Hz real-time telemetry broadcasting to all connected clients simultaneously.
- **Slow-Control Logging**: `hvlogger.py` periodically records channel V/I and system health booleans (`server_connected`, `caen_connected`) to a time-series DB for long-term Grafana monitoring.
- **GUI & CLI Clients**: Professional terminal dashboard (CLI) and a PySide6 GUI with remote server address support.

## 2. File Structure
- `caenhv.py`: Core hardware interface wrapping `CAENHVWrapper` via `ctypes`. Supports dynamic crate map discovery.
- `hvchannel.py`: Shared data model for individual channel parameters.
- `hvconfig.py`: Centralized configuration for all services (hardware settings, ZMQ ports, service file paths).
- `hvserver.py`: Central background service. Manages the direct CAEN hardware connection and ZeroMQ sockets.
- `hvclient.py`: Shared ZMQ communication library used by CLI, GUI, and logger.
- `hvlogger.py`: Slow-control logger. Polls server telemetry and writes to a time-series DB (stubs provided).
- `hvcontrol.py`: CLI client for table-based monitoring and control.
- `hvcontrol_gui.py`: GUI client with remote server address selection and interactive table editing.
- `hvtweak.py`: Standalone CLI tool to directly control a single CAEN channel (bypasses server daemon).
- `caenprobe.py`: Standalone diagnostic tool to inspect active CAEN slots and channels.
- `hv.table`: (User-provided) Configuration file for channel-to-detector mapping.
- `config.json`: (User-provided) Primary configuration file for system settings (IP, User, InfluxDB, etc.).

## 3. Prerequisites

### 1) CAEN HV Wrapper Library
The official `CAENHVWrapper` C library must be installed and visible to the dynamic linker:
```bash
export LD_LIBRARY_PATH=/path/to/caen/lib:$LD_LIBRARY_PATH
```

### 2) Python Dependencies
```bash
pip install pyzmq PySide6 influxdb-client
```

### 3) System Dependencies (OpenSSL 1.1)
CAEN libraries often require OpenSSL 1.1 compatibility:
- **RHEL/Rocky/AlmaLinux**: `sudo dnf install compat-openssl11`
- **Qt xcb plugin**: `sudo dnf install xcb-util-cursor`

## 4. Configuration

### `hvconfig.py` and `config.json`
All defaults are defined in `hvconfig.py`, organized by service:

| Section | Constants |
|---------|-----------|
| Hardware | `IP_ADDRESS`, `SYSTEM_TYPE`, `USERNAME`, `PASSWORD` |
| ZMQ Ports | `CMD_PORT` (5555), `PUB_PORT` (5556) |
| Server service | `SERVER_LOG_FILE`, `SERVER_PID_FILE`, `RECONNECT_INTERVAL` |
| Logger service | `LOGGER_LOG_FILE`, `LOGGER_PID_FILE`, `LOGGER_INTERVAL` |
| InfluxDB | `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET` |

Create a `config.json` in the project root to override any setting without modifying source code. Note that inline `//` comments are fully supported by the config loader!
```json
{
  // ================= CAEN Hardware Connection =================
  "IP_ADDRESS": "172.16.2.51",              // CAEN Crate IP Address
  "SYSTEM_TYPE": 2,                         // 2 = SY4527, 3 = SY5527, 6 = N1470
  "USERNAME": "admin",                      // CAEN Crate Login Username
  "PASSWORD": "admin",                      // CAEN Crate Login Password

  // ================= ZeroMQ Communication Ports ===============
  "CMD_PORT": 5555,                         // Request/Reply port for commands
  "PUB_PORT": 5556,                         // Publisher port for telemetry data

  // ================= Server / Logger daemon settings ==========
  "SERVER_LOG_FILE": "hvserver.log",
  "SERVER_PID_FILE": "hvserver.pid",
  "RECONNECT_INTERVAL": 30.0,
  "LOGGER_LOG_FILE": "hvlogger.log",
  "LOGGER_PID_FILE": "hvlogger.pid",
  "LOGGER_INTERVAL": 60.0,

  // ================= InfluxDB Configuration ===================
  "INFLUX_URL": "https://influxdb.amore2.yemilab.kr", // InfluxDB API Endpoint
  "INFLUX_TOKEN": "your-influxdb-token",              // DB Auth Token
  "INFLUX_ORG": "AMoRE2",                             // InfluxDB Organization
  "INFLUX_BUCKET": "HV"                               // InfluxDB Bucket name
}
```

### `hv.table` Format
Space-delimited text file mapping detector channels:
```text
# name   slot  channel  HV(V)   R(MOhm)  pmtid  group
pmt_01   0     0        1914.0  2.2      1      10
pmt_02   0     1        1850.0  2.2      2      10
```

## 5. Usage

### Step 1: Start the Server (`hvserver.py`)
The server must be running before any client can connect.

```bash
# Foreground (with log to stdout)
python hvserver.py

# Daemon mode (background)
python hvserver.py --daemon

# With custom IP / system type
python hvserver.py --ip 172.16.2.51 --sys 2
```
*The server auto-discovers all slots and channels. Check `hvserver.log` for details.*

**Server management:**
```bash
kill -0 $(cat hvserver.pid) && echo "Running"  # check alive
kill $(cat hvserver.pid)                        # graceful stop
```

### Step 2: Connect a Client

#### CLI (`hvcontrol.py`)
*Note: The CLI distinctly reports both ZMQ Server connectivity and CAEN Hardware connectivity.*
```bash
python hvcontrol.py mon -t hv.table          # monitor all channels
python hvcontrol.py on  -g 10 -t hv.table   # power ON group 10, then monitor
python hvcontrol.py off -t hv.table          # power OFF all, then monitor
```
*Press `q` to exit the monitoring dashboard.*

#### GUI (`hvcontrol_gui.py`)
*Note: The GUI distinctly reports both ZMQ Server connectivity and CAEN Hardware connectivity in the bottom status bar.*
```bash
python hvcontrol_gui.py
```
1. **Load Table**: Click **Browse...** to select your `hv.table`.
2. **Set Server**: Enter the **Server Address** (`localhost` or remote IP).
3. **Connect**: Click **Connect**. Table settings (Names, V, I-limits) are synchronized to hardware.
4. **Interactive Control**:
   - **Edit VSet / Name**: Double-click a cell in the **Set (V)** or **Name** column.
   - **Toggle Power**: Double-click a channel's **Status** cell.
   - **Group Control**: Use the **Group Filter** dropdown and **Power ON / OFF** buttons.

### Step 3: Start the Logger (`hvlogger.py`)
The logger runs independently and periodically records telemetry natively to InfluxDB. 
It uses `hv.table` to selectively filter and record only active channels. It also supports **hot-reloading**: if `hv.table` is modified, the logger automatically detects the change and updates its tracking without needing a restart.

```bash
# Foreground test (10 s interval, debug output)
python hvlogger.py --interval 10 --debug

# Daemon mode (60 s interval, default)
python hvlogger.py --daemon

# Remote server
python hvlogger.py --host 192.168.0.10 --daemon
```

**Logger management:**
```bash
kill -0 $(cat hvlogger.pid) && echo "Running"   # check alive
tail -f hvlogger.log                             # watch log
kill $(cat hvlogger.pid)                         # graceful stop
```

**DB Writes and Health monitoring:**
The logger uses the official `influxdb-client` package. It records standardized data and health structures:
- **Server Health**: Logs boolean values for `server_connected` (ZMQ ping success) and `caen_connected` (Hardware interface operational). If `server_connected` is False, `caen_connected` is implicitly `None` (Unknown).
- **Logger Health**: Logs internal metrics (Uptime, Memory RSS, Error counts) indicating the logger daemon itself is alive.

## 6. Standalone Channel Tweaking (`hvtweak.py`)
For hardware calibrations and quick checks, `hvtweak.py` communicates directly with the CAEN crate (bypassing `hvserver.py`) to control a single channel. It is entirely standalone.
```bash
# Read current channel status (e.g., slot 0, ch 5)
python hvtweak.py 0 5

# Set Voltage to 1500 V and Current Limit to 500 uA
python hvtweak.py 0 5 -V 1500 -I 500

# Turn ON and set Voltage simultaneously
python hvtweak.py 0 5 -V 2000 --on

# Advanced options (run fully independent from config.json)
python hvtweak.py 0 5 -V 100 --on -a 192.168.1.100 -t 2 -u admin -p admin
```

