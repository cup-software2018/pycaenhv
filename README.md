# pycaenhv: Python Toolkit for CAEN High Voltage Systems

A lightweight Python toolkit designed for efficient control and monitoring of CAEN High Voltage (HV) devices, specifically optimized for the **NDT1470** and SY series mainframes. This project wraps the official `CAENHVWrapper` C library using Python's `ctypes`, providing a high-level Pythonic interface and a robust Command Line Interface (CLI).

## 1. Key Features
- **Pythonic API**: Simple methods for voltage/current monitoring, power control, and parameter configuration.
- **Automated Parameter Calculation**: Automatically calculates the current limit ($I_0Set$) based on target voltage ($V$) and resistance ($R$ in MΩ) using Ohm's Law ($I = V/R$), including a default 10% safety margin.
- **Real-time Monitoring Dashboard**: High-performance terminal dashboard using the `curses` library to display real-time VMon, IMon, and channel status.
- **Group-based Management**: Efficiently manage channels by grouping them to apply settings or power commands collectively.

## 2. File Structure
- `caenhv.py`: Core module for C library binding and hardware communication.
- `hvchannel.py`: Data model for individual channel state and properties.
- `hvcontrol.py`: CLI controller and entry point.
- `hvcontrol_gui.py`: GUI controller and entry point.
- `hv.table`: Configuration file containing channel mappings and HV parameters.

## 3. Prerequisites

### 1) CAEN HV Wrapper Library
The official `CAENHVWrapper` library must be installed. Ensure the library path is added to your environment variables:
```bash
export LD_LIBRARY_PATH=/path/to/caen/lib:$LD_LIBRARY_PATH
```

### 2) Python Dependencies
To use the GUI, install PySide6:
```bash
pip install PySide6
```

### 3) System Dependencies (OpenSSL 1.1)
On modern Linux distributions (e.g., AlmaLinux 9, Ubuntu 22.04+), you may need OpenSSL 1.1 compatibility packages to resolve `libcrypto.so.1.1` errors.
- **RHEL/Rocky/AlmaLinux**:
```bash
sudo dnf install compat-openssl11
```

## 4. Usage

### 0) Configuring the HV Table (`hv.table`)
Create a text file to define your detector channels. (Space or tab-delimited)
```text
# name    slot   channel    HV      R(Mohm)  pmtid   group
pmt_01    0      0          1914.0  2.2      1       10
pmt_02    0      1          1850.0  2.2      2       10
...
```

### 1) CLI Commands
All actions support the `-g [group_name]` flag to target specific groups (default is `all`).

1. **Apply Settings (Voltage & Current)**
   Sets `V0Set` and `I0Set` for channels based on the table.
```bash
python hvcontrol.py set -g 10
```

2. **Power On & Monitor**
   Turns on the power for the specified group and immediately enters the monitoring dashboard.
```bash
python hvcontrol.py on -g 10
```

3. **Monitor Only**
   Launches the real-time status dashboard. Press `q` to exit.
```bash
python hvcontrol.py mon
```

4. **Power Off**
```bash
python hvcontrol.py off -g all
```

### 2) Launch the GUI
```bash
python hvcontrol_gui.py
```

#### GUI Workflow
1. **Load Data**: Click **Browse...** to select your `hv.table` file. *(Note: You must load a table before connecting).*
2. **Connect**: Enter the target IP address and click **Connect**. Monitoring will start automatically.
3. **Filter & Control Group**: Select a specific group from the **Group Filter** dropdown. The selected channels will turn blue. Use the **Power ON / OFF** buttons to control only the filtered group.
4. **Individual Control**: Double-click the **Status** cell (e.g., the word "OFF" or "ON") of a specific channel to safely toggle its power.