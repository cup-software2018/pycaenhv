# pycaenhv v1.0: Python Toolkit for CAEN High Voltage Systems

A lightweight Python toolkit for direct control and monitoring of CAEN High Voltage (HV) devices (SY series mainframes, NDT1470, etc.).

This version provides **direct hardware access** via the official `CAENHVWrapper` C library using Python's `ctypes`.

## 1. Key Features
- **Direct Hardware Access**: CLI and GUI communicate directly with the CAEN mainframe.
- **Centralized Configuration**: Hardware settings (IP, credentials, system type) are managed in `hvconfig.py` with optional `config.json` override.
- **Automated Parameter Calculation**: Automatically calculates current limits ($I_0Set$) from target voltage ($V$) and resistance ($R$ in MΩ) via Ohm's Law, including a 10% safety margin.
- **Group-based Management**: Apply settings and power commands to named channel groups.
- **Real-time Monitoring**: Terminal dashboard (CLI) and PySide6 GUI for live VMon/IMon display.
- **Hardware Diagnostic Tool**: `caenprobe.py` for quickly inspecting active slots and channels.

## 2. File Structure
- `caenhv.py`: Core hardware interface wrapping `CAENHVWrapper` via `ctypes`. Supports dynamic crate map discovery.
- `hvconfig.py`: Centralized configuration (IP, credentials, ports, system type). Supports `config.json` overrides.
- `hvcontrol.py`: CLI for table-based monitoring and control.
- `hvcontrol_gui.py`: GUI for interactive monitoring and control.
- `hvchannel.py`: Shared data model for individual channel parameters.
- `caenprobe.py`: Standalone diagnostic tool to inspect active slots and channels.
- `hv.table`: (User-provided) Configuration file for channel-to-detector mapping.

## 3. Prerequisites

### 1) CAEN HV Wrapper Library
Official `CAENHVWrapper` library must be installed and in your library path:
```bash
export LD_LIBRARY_PATH=/path/to/caen/lib:$LD_LIBRARY_PATH
```

### 2) Python Dependencies
Requires `PySide6` for the GUI:
```bash
pip install PySide6
```

### 3) System Dependencies (OpenSSL 1.1)
CAEN libraries often require OpenSSL 1.1 compatibility:
- **RHEL/Rocky/AlmaLinux**: `sudo dnf install compat-openssl11`

## 4. Configuration

### `hvconfig.py` and `config.json`
All hardware connection settings are managed in `hvconfig.py`. To customize without modifying source code, create a `config.json` in the project root:

```json
{
  "IP_ADDRESS": "192.168.0.152",
  "SYSTEM_TYPE": 3,
  "USERNAME": "admin",
  "PASSWORD": "admin"
}
```
*(System Type: 2 for SY4527, 3 for SY5527, 6 for N1470)*

### `hv.table` Format
Create a space-delimited text file to map your detector channels:
```text
# name    slot   channel    HV(V)   R(MOhm)  pmtid   group
pmt_01    0      0          1914.0  2.2      1       10
pmt_02    0      1          1850.0  2.2      2       10
```

## 5. Usage

### Probe Hardware (Check Slots & Channels)
```bash
python caenprobe.py
```

### CLI (`hvcontrol.py`)
On startup, the CLI automatically connects, applies all table settings (`V0Set`, `I0Set`, `Name`), and then performs the requested action.

```bash
# Monitor all channels
python hvcontrol.py mon -t hv.table

# Monitor a specific group
python hvcontrol.py mon -g 10 -t hv.table

# Power ON a group, then switch to monitoring
python hvcontrol.py on -g 10 -t hv.table

# Power OFF all channels, then switch to monitoring
python hvcontrol.py off -t hv.table
```
*Press `q` to exit the monitoring dashboard.*

### GUI (`hvcontrol_gui.py`)
```bash
python hvcontrol_gui.py
```
1. **Load Table**: Click **Browse...** to select your `hv.table` file.
2. **Connect**: Enter the mainframe IP and click **Connect**. Settings are automatically synchronized.
3. **Interactive Control**:
   - **Edit V/Name**: Double-click **Name** or **Set (V)** cells to modify values. Changes are applied to hardware immediately.
   - **Toggle Power**: Double-click the **Status** cell of a channel to toggle it ON/OFF.
   - **Group Control**: Use the **Group Filter** dropdown and the **Power ON / OFF** buttons.